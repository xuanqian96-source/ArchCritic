"""对四条件论文实验进行严格语义核对、统计和暂停门槛判断。"""

from __future__ import annotations

from datetime import datetime
import json
import math
from pathlib import Path
from statistics import mean
from typing import Any

from app.agents.function_agent import extract_json_text
from app.benchmarking.blind_protocol import verify_frozen_results
from app.benchmarking.metrics import pearson_correlation, spearman_correlation
from app.benchmarking.paper_experiment_prompts import CONDITION_NAMES
from app.config import get_settings
from app.llm.client import get_llm_client


STRICT_JUDGE_SYSTEM_PROMPT = """
你是建筑设计课评图实验的严格裁判。你只能比较人工标注清单和模型报告，不负责重新评图。

匹配规则：
1. 只有问题对象、核心缺陷和主要影响相同，才是 exact。
2. 主题相近但缺少核心对象或核心缺陷，只能是 partial。
3. 消防疏散、无障碍、后勤运输、一般参观流线、结构和图面表达属于不同问题，不得互相替代。
4. “功能不完整”“流线需优化”等宽泛语句不能匹配更具体的人工问题。
5. 同一条模型意见最多完整匹配一个人工必须问题。
6. 模型未提及必须返回 none，不得用推断补足。
7. 人工事实的状态也要一致；把“不确定”写成确定存在或确定缺失不算 exact。
8. 只输出 JSON，不要输出 Markdown。
""".strip()


def judge_paper_condition(
    results_root: Path,
    private_answers_file: Path,
    judgments_root: Path,
    provider: str,
    model: str,
) -> dict[str, Any]:
    """在结果冻结后，用严格规则逐份核对标注清单。"""
    frozen = verify_frozen_results(results_root)
    if judgments_root.exists() and any(judgments_root.iterdir()):
        raise ValueError(f"裁判目录不为空，不得覆盖：{judgments_root}")
    judgments_root.mkdir(parents=True, exist_ok=True)
    answers = read_json(private_answers_file)
    truth_by_id = {item["case_id"]: item for item in answers.get("cases", [])}
    client = get_llm_client(provider, model)
    hashes = {}
    for result_file in sorted(results_root.glob("CASE-*.json")):
        result = read_json(result_file)
        case_id = str(result["case_id"])
        truth = truth_by_id[case_id]
        judgment = strict_judge_report(client, result["report"], truth)
        output = {
            "case_id": case_id,
            "condition": result.get("condition", ""),
            "source_result": result_file.name,
            "judged_at": now_text(),
            "judge_provider": provider,
            "judge_model": model,
            "judge_protocol": "strict-paper-judge-v1",
            "judge": judgment,
        }
        output_file = judgments_root / f"{case_id}.judge.json"
        write_json(output_file, output)
        hashes[output_file.name] = sha256_text(output_file.read_text(encoding="utf-8"))
    manifest = {
        "protocol": frozen["protocol"],
        "test_id": frozen["test_id"],
        "judged_at": now_text(),
        "private_answers_file": private_answers_file.name,
        "judgment_hashes": hashes,
        "strict_matching": True,
    }
    write_json(judgments_root / "judgment_manifest.json", manifest)
    return manifest


def judge_paper_condition_local(
    results_root: Path,
    private_answers_file: Path,
    decisions_file: Path,
    judgments_root: Path,
) -> dict[str, Any]:
    """只在本地读取私有答案，按预先保存的逐条决定生成核对结果。"""
    frozen = verify_frozen_results(results_root)
    if judgments_root.exists() and any(judgments_root.iterdir()):
        raise ValueError(f"裁判目录不为空，不得覆盖：{judgments_root}")
    answers = read_json(private_answers_file)
    truth_by_id = {item["case_id"]: item for item in answers.get("cases", [])}
    decisions = read_json(decisions_file)
    decisions_by_id = decisions.get("cases", {})
    result_files = sorted(results_root.glob("CASE-*.json"))
    expected_ids = {path.stem for path in result_files}
    if set(decisions_by_id) != expected_ids:
        raise ValueError("本地核对决定必须完整覆盖冻结结果，且不得多出样本。")
    judgments_root.mkdir(parents=True, exist_ok=True)
    hashes = {}
    for result_file in result_files:
        result = read_json(result_file)
        case_id = str(result["case_id"])
        judgment = build_local_judgment(
            result["report"],
            truth_by_id[case_id],
            decisions_by_id[case_id],
        )
        output = {
            "case_id": case_id,
            "condition": result.get("condition", ""),
            "source_result": result_file.name,
            "judged_at": now_text(),
            "judge_protocol": "local-strict-author-audit-v1",
            "private_answers_sent_to_external_service": False,
            "decisions_file": decisions_file.name,
            "judge": judgment,
        }
        output_file = judgments_root / f"{case_id}.judge.json"
        write_json(output_file, output)
        hashes[output_file.name] = sha256_text(output_file.read_text(encoding="utf-8"))
    manifest = {
        "protocol": frozen["protocol"],
        "test_id": frozen["test_id"],
        "judged_at": now_text(),
        "judgment_hashes": hashes,
        "judge_protocol": "local-strict-author-audit-v1",
        "decisions_sha256": sha256_text(decisions_file.read_text(encoding="utf-8")),
        "private_answers_sent_to_external_service": False,
        "fact_status_scored": False,
    }
    write_json(judgments_root / "judgment_manifest.json", manifest)
    return manifest


def build_local_judgment(
    report: dict[str, Any],
    truth: dict[str, Any],
    decision: dict[str, Any],
) -> dict[str, Any]:
    """校验本地逐条决定，并转换成与统计模块一致的结构。"""
    predictions = build_prediction_items(report)
    prediction_ids = {item["prediction_id"] for item in predictions}
    must_ids = {item["id"] for item in truth.get("must_issues", [])}
    optional_ids = {item["id"] for item in truth.get("optional_issues", [])}
    mappings = {
        "must_exact": decision.get("must_exact", {}),
        "must_partial": decision.get("must_partial", {}),
        "optional_exact": decision.get("optional_exact", {}),
        "optional_partial": decision.get("optional_partial", {}),
    }
    for label, mapping in mappings.items():
        if not isinstance(mapping, dict):
            raise ValueError(f"本地核对字段必须是对象：{label}")
        allowed_refs = must_ids if label.startswith("must_") else optional_ids
        invalid_predictions = set(mapping) - prediction_ids
        invalid_references = set(mapping.values()) - allowed_refs
        if invalid_predictions or invalid_references:
            raise ValueError(
                f"本地核对编号无效：{label}，"
                f"模型项 {sorted(invalid_predictions)}，人工项 {sorted(invalid_references)}"
            )
    exact_predictions = list(mappings["must_exact"])
    if len(exact_predictions) != len(set(exact_predictions)):
        raise ValueError("同一模型意见不得重复严格命中人工必须问题。")
    reverse_exact = list(mappings["must_exact"].values())
    if len(reverse_exact) != len(set(reverse_exact)):
        raise ValueError("同一人工必须问题不得被重复计为严格命中。")
    all_mapped_predictions = [
        prediction_id
        for mapping in mappings.values()
        for prediction_id in mapping
    ]
    if len(all_mapped_predictions) != len(set(all_mapped_predictions)):
        raise ValueError("同一模型意见只能选择一个主要匹配类别。")

    must_reverse_exact = {value: key for key, value in mappings["must_exact"].items()}
    must_reverse_partial = {
        value: key for key, value in mappings["must_partial"].items()
        if value not in must_reverse_exact
    }
    prediction_results = []
    for prediction in predictions:
        prediction_id = prediction["prediction_id"]
        classification = "unsupported"
        reference_id = ""
        for label in (
            "must_exact",
            "optional_exact",
            "must_partial",
            "optional_partial",
        ):
            if prediction_id in mappings[label]:
                classification = label
                reference_id = mappings[label][prediction_id]
                break
        prediction_results.append(
            {
                **prediction,
                "classification": classification,
                "reference_id": reference_id,
                "evidence": prediction["text"],
                "reason": str(
                    decision.get("reasons", {}).get(prediction_id, "")
                )[:400],
            }
        )
    violated = set(decision.get("forbidden_violations", []))
    allowed_forbidden = {item["id"] for item in truth.get("forbidden_issues", [])}
    if violated - allowed_forbidden:
        raise ValueError(f"禁止误报编号无效：{sorted(violated - allowed_forbidden)}")
    return {
        "fact_results": [],
        "must_reference_results": [
            {
                "id": item["id"],
                "match": (
                    "exact"
                    if item["id"] in must_reverse_exact
                    else "partial"
                    if item["id"] in must_reverse_partial
                    else "none"
                ),
                "prediction_id": (
                    must_reverse_exact.get(item["id"])
                    or must_reverse_partial.get(item["id"])
                    or ""
                ),
                "evidence": "",
                "reason": "",
            }
            for item in truth.get("must_issues", [])
        ],
        "prediction_results": prediction_results,
        "forbidden_results": [
            {
                "id": item["id"],
                "violated": item["id"] in violated,
                "evidence": "",
            }
            for item in truth.get("forbidden_issues", [])
        ],
        "local_audit_notes": list(decision.get("notes", [])),
    }


def strict_judge_report(
    llm_client: Any,
    report: dict[str, Any],
    truth: dict[str, Any],
) -> dict[str, Any]:
    """调用严格文本裁判，并补齐缺失的人工条目和模型意见。"""
    predictions = build_prediction_items(report)
    facts = list(truth.get("facts", []))
    must_issues = list(truth.get("must_issues", []))
    optional_issues = list(truth.get("optional_issues", []))
    forbidden_issues = list(truth.get("forbidden_issues", []))
    prompt = {
        "人工事实": facts,
        "人工必须问题": must_issues,
        "人工可选问题": optional_issues,
        "禁止误报": forbidden_issues,
        "模型修改意见": predictions,
        "模型完整报告": report,
        "返回结构": {
            "fact_results": [
                {
                    "item": "人工事实原item",
                    "match": "exact/partial/wrong/not_mentioned",
                    "evidence": "模型原文",
                    "reason": "理由",
                }
            ],
            "must_reference_results": [
                {
                    "id": "人工M编号",
                    "match": "exact/partial/none",
                    "prediction_id": "P编号或空",
                    "reason": "理由",
                }
            ],
            "prediction_results": [
                {
                    "prediction_id": "P编号",
                    "classification": (
                        "must_exact/must_partial/optional_exact/"
                        "optional_partial/unsupported/unverifiable"
                    ),
                    "reference_id": "M或O编号或空",
                    "reason": "理由",
                }
            ],
            "forbidden_results": [
                {"id": "N编号", "violated": False, "evidence": "模型原文或理由"}
            ],
        },
    }
    request = {
        "model": llm_client.model,
        "messages": [
            {"role": "system", "content": STRICT_JUDGE_SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0,
        "max_tokens": 6500,
        "timeout": min(180, get_settings().llm_timeout_seconds),
    }
    if getattr(llm_client, "extra_body", None):
        request["extra_body"] = llm_client.extra_body
    response = llm_client.client.chat.completions.create(**request)
    raw = json.loads(extract_json_text(response.choices[0].message.content or "{}"))
    return normalize_strict_judgment(
        raw,
        facts,
        must_issues,
        predictions,
        forbidden_issues,
    )


def build_prediction_items(report: dict[str, Any]) -> list[dict[str, str]]:
    """把最终报告中的主要修改意见编号，避免裁判自由改写。"""
    predictions = []
    for prefix, field in (("PM", "must_fix"), ("PS", "should_improve")):
        for index, text in enumerate(report.get(field, []) or [], start=1):
            predictions.append(
                {
                    "prediction_id": f"{prefix}-{index:02d}",
                    "source_field": field,
                    "text": str(text),
                }
            )
    return predictions


def normalize_strict_judgment(
    raw: dict[str, Any],
    facts: list[dict[str, Any]],
    must_issues: list[dict[str, Any]],
    predictions: list[dict[str, str]],
    forbidden_issues: list[dict[str, Any]],
) -> dict[str, Any]:
    """按输入编号补齐裁判结果，缺项从严按未命中处理。"""
    fact_map = {
        str(item.get("item")): item
        for item in raw.get("fact_results", [])
        if isinstance(item, dict)
    }
    must_map = {
        str(item.get("id")): item
        for item in raw.get("must_reference_results", [])
        if isinstance(item, dict)
    }
    prediction_map = {
        str(item.get("prediction_id")): item
        for item in raw.get("prediction_results", [])
        if isinstance(item, dict)
    }
    forbidden_map = {
        str(item.get("id")): item
        for item in raw.get("forbidden_results", [])
        if isinstance(item, dict)
    }
    normalized = {
        "fact_results": [
            normalize_choice(
                {"item": item["item"]},
                fact_map.get(str(item["item"]), {}),
                "match",
                {"exact", "partial", "wrong", "not_mentioned"},
                "not_mentioned",
            )
            for item in facts
        ],
        "must_reference_results": [
            normalize_choice(
                {"id": item["id"]},
                must_map.get(str(item["id"]), {}),
                "match",
                {"exact", "partial", "none"},
                "none",
                extra_key="prediction_id",
            )
            for item in must_issues
        ],
        "prediction_results": [
            normalize_choice(
                {"prediction_id": item["prediction_id"], "text": item["text"]},
                prediction_map.get(item["prediction_id"], {}),
                "classification",
                {
                    "must_exact",
                    "must_partial",
                    "optional_exact",
                    "optional_partial",
                    "unsupported",
                    "unverifiable",
                },
                "unverifiable",
                extra_key="reference_id",
            )
            for item in predictions
        ],
        "forbidden_results": [
            {
                "id": item["id"],
                "violated": bool(
                    forbidden_map.get(str(item["id"]), {}).get("violated", False)
                ),
                "evidence": str(
                    forbidden_map.get(str(item["id"]), {}).get("evidence", "")
                )[:400],
            }
            for item in forbidden_issues
        ],
    }
    enforce_one_to_one_exact_matches(normalized)
    return normalized


def enforce_one_to_one_exact_matches(judgment: dict[str, Any]) -> None:
    """同一条模型意见最多严格命中一个人工必须问题。"""
    used_predictions: set[str] = set()
    for item in judgment.get("must_reference_results", []):
        prediction_id = str(item.get("prediction_id", "")).strip()
        if item.get("match") != "exact" or not prediction_id:
            continue
        if prediction_id in used_predictions:
            item["match"] = "partial"
            item["reason"] = (
                str(item.get("reason", ""))[:300]
                + "；同一模型意见已用于另一条严格命中，本条从严降为部分匹配。"
            )[:400]
            continue
        used_predictions.add(prediction_id)


def normalize_choice(
    base: dict[str, Any],
    raw: dict[str, Any],
    field: str,
    allowed: set[str],
    fallback: str,
    extra_key: str | None = None,
) -> dict[str, Any]:
    """规范裁判枚举并保留简短理由。"""
    value = str(raw.get(field, fallback))
    result = {
        **base,
        field: value if value in allowed else fallback,
        "evidence": str(raw.get("evidence", ""))[:400],
        "reason": str(raw.get("reason", ""))[:400],
    }
    if extra_key:
        result[extra_key] = str(raw.get(extra_key, ""))[:40]
    return result


def calculate_paper_metrics(
    results_root: Path,
    judgments_root: Path,
    private_answers_file: Path,
) -> dict[str, Any]:
    """计算单个实验条件的分数误差与严格问题指标。"""
    verify_frozen_results(results_root)
    answers = read_json(private_answers_file)
    truth_by_id = {item["case_id"]: item for item in answers.get("cases", [])}
    rows = []
    for result_file in sorted(results_root.glob("CASE-*.json")):
        result = read_json(result_file)
        case_id = str(result["case_id"])
        judgment = read_json(judgments_root / f"{case_id}.judge.json")["judge"]
        truth = truth_by_id[case_id]
        teacher_score = float(truth["teacher_score"])
        model_score = float(result["report"]["overall_score"])
        must_results = judgment.get("must_reference_results", [])
        prediction_results = judgment.get("prediction_results", [])
        strict_tp = len(
            {
                item.get("id")
                for item in must_results
                if item.get("match") == "exact" and item.get("id")
            }
        )
        prediction_total = len(prediction_results)
        must_total = len(must_results)
        strict_precision = strict_tp / prediction_total if prediction_total else 0.0
        must_recall = strict_tp / must_total if must_total else 0.0
        strict_f1 = harmonic_mean(strict_precision, must_recall)
        relevant_predictions = sum(
            item.get("classification") in {"must_exact", "optional_exact"}
            for item in prediction_results
        )
        facts = judgment.get("fact_results", [])
        rows.append(
            {
                "case_id": case_id,
                "teacher_score": teacher_score,
                "model_score": model_score,
                "signed_error": model_score - teacher_score,
                "absolute_error": abs(model_score - teacher_score),
                "must_total": must_total,
                "must_exact_hits": strict_tp,
                "prediction_total": prediction_total,
                "strict_issue_precision": strict_precision,
                "must_issue_recall": must_recall,
                "strict_issue_f1": strict_f1,
                "relevant_prediction_count": relevant_predictions,
                "fact_total": len(facts),
                "fact_exact_hits": sum(item.get("match") == "exact" for item in facts),
                "forbidden_violations": sum(
                    bool(item.get("violated"))
                    for item in judgment.get("forbidden_results", [])
                ),
            }
        )
    return aggregate_paper_rows(rows, results_root)


def aggregate_paper_rows(
    rows: list[dict[str, Any]],
    results_root: Path,
) -> dict[str, Any]:
    """按条件汇总九份配对结果。"""
    teacher_scores = [row["teacher_score"] for row in rows]
    model_scores = [row["model_score"] for row in rows]
    must_total = sum(row["must_total"] for row in rows)
    strict_tp = sum(row["must_exact_hits"] for row in rows)
    prediction_total = sum(row["prediction_total"] for row in rows)
    relevant_total = sum(row["relevant_prediction_count"] for row in rows)
    fact_total = sum(row["fact_total"] for row in rows)
    fact_hits = sum(row["fact_exact_hits"] for row in rows)
    precision = strict_tp / prediction_total if prediction_total else 0.0
    recall = strict_tp / must_total if must_total else 0.0
    manifest = read_json(results_root / "run_manifest.json")
    return {
        "condition": manifest["condition"],
        "condition_name": manifest["condition_name"],
        "case_count": len(rows),
        "score_mae": rounded(mean(row["absolute_error"] for row in rows)),
        "score_rmse": rounded(
            math.sqrt(mean(row["signed_error"] ** 2 for row in rows))
        ),
        "score_mean_bias": rounded(mean(row["signed_error"] for row in rows)),
        "score_pearson_r": rounded(pearson_correlation(teacher_scores, model_scores), 4),
        "score_spearman_rho": rounded(
            spearman_correlation(teacher_scores, model_scores), 4
        ),
        "must_exact_hits": strict_tp,
        "must_total": must_total,
        "prediction_total": prediction_total,
        "strict_issue_precision": rounded(precision, 4),
        "must_issue_recall": rounded(recall, 4),
        "strict_issue_f1": rounded(harmonic_mean(precision, recall), 4),
        "broader_relevance_precision": rounded(
            relevant_total / prediction_total if prediction_total else 0.0, 4
        ),
        "fact_exact_hits": fact_hits,
        "fact_total": fact_total,
        "fact_status_accuracy": rounded(
            fact_hits / fact_total if fact_total else 0.0, 4
        ),
        "forbidden_violation_count": sum(row["forbidden_violations"] for row in rows),
        "mean_duration_seconds": rounded(
            mean(
                float(read_json(path).get("duration_seconds", 0))
                for path in sorted(results_root.glob("CASE-*.json"))
            )
        ),
        "cases": rows,
    }


def evaluate_pause_gate(metrics: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """按运行前规则判断是否需要暂停并等待用户。"""
    reasons = []
    c0 = metrics.get("c0_direct")
    if c0:
        if c0["strict_issue_f1"] >= 0.85:
            reasons.append("直接评审严格问题F1达到或超过0.85，异常偏高。")
        if c0["strict_issue_f1"] >= 0.75 and c0["score_mae"] <= 5:
            reasons.append("直接评审同时达到较高问题F1和不超过5分的MAE。")
    c1 = metrics.get("c1_structured_single")
    c2 = metrics.get("c2_multi_agent")
    if c0 and c1:
        if (
            c1["strict_issue_f1"] < c0["strict_issue_f1"] - 0.10
            and c1["score_mae"] > c0["score_mae"] + 5
        ):
            reasons.append("结构化提示词条件相对直接评审出现明显双重退化。")
    if c1 and c2:
        if (
            c2["strict_issue_f1"] < c1["strict_issue_f1"] - 0.10
            and c2["score_mae"] > c1["score_mae"] + 5
        ):
            reasons.append("多Agent条件相对单模型出现明显双重退化。")
    return {
        "pause_required": bool(reasons),
        "reasons": reasons,
        "c3_excluded_from_gate": True,
        "rule_version": "paper-pause-gate-v1",
    }


def harmonic_mean(left: float, right: float) -> float:
    """计算F1。"""
    return 2 * left * right / (left + right) if left + right else 0.0


def rounded(value: float, digits: int = 2) -> float:
    """稳定舍入。"""
    return round(float(value), digits)


def read_json(path: Path) -> dict[str, Any]:
    """读取JSON。"""
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: dict[str, Any]) -> None:
    """写入JSON。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def sha256_text(value: str) -> str:
    """计算文本哈希。"""
    import hashlib

    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def now_text() -> str:
    """返回带时区时间。"""
    return datetime.now().astimezone().isoformat(timespec="seconds")
