"""准备并运行九样本、四条件的会议论文正式实验。"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import hashlib
import json
from pathlib import Path
from statistics import mean
import time
import traceback
from typing import Any

from app.benchmarking.anonymize import redact_case_identity
from app.benchmarking.baseline_snapshot import collect_relevant_files, fingerprint_files
from app.benchmarking.blind_protocol import (
    calculate_knowledge_fingerprint,
    freeze_blind_results,
    validate_blind_input_root,
)
from app.benchmarking.dataset import BenchmarkCase, load_benchmark_cases
from app.benchmarking.paper_experiment_prompts import (
    CONDITION_NAMES,
    DIRECT_SYSTEM_PROMPT,
    STRUCTURED_SYSTEM_PROMPT,
    run_single_model_condition,
)
from app.benchmarking.preprocess import (
    is_low_resolution_source,
    prepare_drawing_files,
    prepare_taskbook,
    write_json,
)
from app.benchmarking.runner import (
    build_context,
    calculate_prompt_fingerprint,
    prepare_model_urls,
)
from app.llm.client import get_llm_client


PAPER_CONDITIONS = tuple(CONDITION_NAMES)
AGENT_LABELS = {
    "drawing_agent": "图面表达",
    "function_agent": "功能与流线",
    "site_agent": "场地与回应",
    "form_agent": "几何形式",
    "structure_agent": "结构与可行性",
    "review_agent": "综合评审",
}


def prepare_paper_experiment(
    dataset_root: Path,
    input_root: Path,
    private_answers_root: Path,
) -> dict[str, Any]:
    """生成九份不含标注摘要的匿名输入和物理分离答案包。"""
    ensure_empty_target(input_root, "匿名输入")
    ensure_empty_target(private_answers_root, "私有答案")
    cases = load_benchmark_cases(dataset_root)
    if len(cases) != 9:
        raise ValueError(f"论文实验要求恰好九份标注样本，当前发现 {len(cases)} 份。")
    taskbook = prepare_taskbook(dataset_root)
    index_items = []
    redaction_audits = []
    inputs_root = input_root / "inputs"
    for case in cases:
        case_root = inputs_root / case.case_id
        drawing_paths = prepare_drawing_files(case, case_root / "drawings", False)
        redaction_audits.append(redact_case_identity(case, drawing_paths))
        payload = build_anonymous_case_input(case, drawing_paths, build_loo_guidance(cases, case))
        write_json(case_root / "input.json", payload)
        index_items.append(
            {
                "case_id": case.case_id,
                "input_file": f"inputs/{case.case_id}/input.json",
                "drawing_count": len(drawing_paths),
            }
        )

    index = {
        "version": 4,
        "experiment": "paper-four-condition-nine-case-v1",
        "taskbook_file": "taskbook.json" if taskbook else "",
        "cases": index_items,
    }
    write_json(input_root / "index.json", index)
    if taskbook:
        write_json(input_root / "taskbook.json", taskbook)
    private_answers = {
        "version": 2,
        "experiment": "paper-four-condition-nine-case-v1",
        "cases": [case.build_ground_truth() for case in cases],
    }
    write_json(private_answers_root / "ground_truth.json", private_answers)
    validation = validate_blind_input_root(input_root)
    bundle_fingerprint = calculate_input_bundle_fingerprint(input_root, index)
    input_manifest = {
        "version": 1,
        "created_at": now_text(),
        "case_count": len(cases),
        "case_ids": [case.case_id for case in cases],
        "input_index_sha256": sha256_file(input_root / "index.json"),
        "input_bundle_sha256": bundle_fingerprint,
        "contains_teacher_scores": False,
        "contains_annotation_answers": False,
        "uses_researcher_description": False,
        "uses_researcher_page_summary": False,
        "loo_score_guidance": True,
        "validation": validation,
    }
    write_json(input_root / "BLIND_INPUT_BUNDLE.json", input_manifest)
    write_json(
        private_answers_root / "PRIVATE_ANSWERS.json",
        {
            "created_at": now_text(),
            "case_count": len(cases),
            "ground_truth_sha256": sha256_file(private_answers_root / "ground_truth.json"),
            "must_not_mount_in_blind_run": True,
        },
    )
    write_json(private_answers_root / "IDENTITY_REDACTION_AUDIT.json", {
        "created_at": now_text(),
        "case_count": len(redaction_audits),
        "total_redactions": sum(item["redaction_count"] for item in redaction_audits),
        "cases": redaction_audits,
    })
    return input_manifest


def build_anonymous_case_input(
    case: BenchmarkCase,
    drawing_paths: list[Path],
    score_band_guidance: str,
) -> dict[str, Any]:
    """只保留原始图纸、课程公共信息和不含本样本答案的分档锚点。"""
    drawings = []
    for index, path in enumerate(drawing_paths, start=1):
        drawings.append(
            {
                "drawing_type": "board",
                "original_name": f"D{index:02d}",
                "relative_path": f"drawings/{path.name}",
                "mime_type": "image/png" if path.suffix.lower() == ".png" else "image/jpeg",
                "description": "",
                "low_resolution": is_low_resolution_source(path),
            }
        )
    return {
        "case_id": case.case_id,
        "project_name": "匿名公共文化建筑课程设计",
        "building_type": "博物馆及记忆档案馆类公共文化建筑",
        "grade": "大二",
        "design_stage": "图纸阶段",
        "description": "",
        "score_band_guidance": score_band_guidance,
        "drawings": drawings,
    }


def build_loo_guidance(cases: list[BenchmarkCase], heldout: BenchmarkCase) -> str:
    """只用其余八份样本构造课程分档尺度，不包含当前样本自身答案。"""
    bands = (
        ("60—74分档", lambda score: score < 75),
        ("75—89分档", lambda score: 75 <= score < 90),
        ("90—100分档", lambda score: score >= 90),
    )
    lines = [
        "以下为同课程其他作品形成的匿名聚合尺度，已排除当前待评作品。",
        "只用于统一宽严尺度，不包含任何具体作品名称、问题或当前作品答案。",
    ]
    others = [case for case in cases if case.case_id != heldout.case_id]
    for band_name, predicate in bands:
        items = [case for case in others if predicate(case.teacher_score)]
        if not items:
            continue
        score_text = f"课程总分均值约 {mean(item.teacher_score for item in items):.1f}"
        dimension_parts = []
        for agent_type, label in AGENT_LABELS.items():
            centers = [
                (item.score_ranges[agent_type]["min"] + item.score_ranges[agent_type]["max"]) / 2
                for item in items
                if agent_type in item.score_ranges
            ]
            if centers:
                dimension_parts.append(f"{label}约 {mean(centers):.1f}")
        lines.append(
            f"- {band_name}：{score_text}；"
            + ("，".join(dimension_parts) if dimension_parts else "按课程要求综合判断")
            + f"；参考作品数 {len(items)}。"
        )
    return "\n".join(lines)


def run_paper_condition(
    input_root: Path,
    results_root: Path,
    condition: str,
    provider: str,
    model: str,
    workers: int = 1,
) -> dict[str, Any]:
    """在无答案环境中运行并冻结一个实验条件。"""
    if condition not in PAPER_CONDITIONS:
        raise ValueError(f"未知论文实验条件：{condition}")
    if results_root.exists() and any(results_root.iterdir()):
        raise ValueError(f"结果目录不为空，不得覆盖：{results_root}")
    validation = validate_blind_input_root(input_root)
    index = read_json(input_root / "index.json")
    taskbook_name = str(index.get("taskbook_file", "")).strip()
    taskbook = read_json(input_root / taskbook_name) if taskbook_name else {}
    selected = list(index.get("cases", []))
    results_root.mkdir(parents=True, exist_ok=True)
    manifest = {
        "protocol": "paper-four-condition-nine-case-v1",
        "test_id": condition,
        "condition": condition,
        "condition_name": CONDITION_NAMES[condition],
        "provider": provider,
        "model": model,
        "started_at": now_text(),
        "case_ids": [str(item["case_id"]) for item in selected],
        "input_index_sha256": validation["index_sha256"],
        "input_bundle_sha256": calculate_input_bundle_fingerprint(input_root, index),
        "taskbook_sha256": sha256_file(input_root / taskbook_name) if taskbook_name else "",
        "prompt_fingerprint": condition_prompt_fingerprint(condition),
        "review_code_fingerprint": calculate_review_code_fingerprint(),
        "knowledge_fingerprint": (
            calculate_knowledge_fingerprint()
            if condition == "c3_multi_agent_knowledge"
            else ""
        ),
        "contains_teacher_scores": False,
        "contains_annotation_answers": False,
        "results_may_be_selected": False,
    }
    write_json(results_root / "run_manifest.json", manifest)
    upload_cache = prepare_model_urls(input_root, selected, provider, model)
    outputs: list[Path] = []
    failures: list[str] = []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        futures = {}
        for item in selected:
            input_file = input_root / str(item["input_file"])
            future = executor.submit(
                run_paper_case,
                input_file,
                taskbook,
                upload_cache,
                provider,
                model,
                condition,
            )
            futures[future] = str(item["case_id"])
        for future in as_completed(futures):
            case_id = futures[future]
            try:
                result = future.result()
            except Exception as exc:  # noqa: BLE001 - 正式实验必须保留技术失败
                failures.append(case_id)
                write_json(
                    results_root / "errors" / f"{case_id}.json",
                    {
                        "case_id": case_id,
                        "failed_at": now_text(),
                        "error_type": type(exc).__name__,
                        "message": str(exc)[:1000],
                        "traceback": traceback.format_exc()[-5000:],
                    },
                )
                continue
            output = results_root / f"{case_id}.json"
            write_json(output, result)
            outputs.append(output)
            print(
                f"{condition} {case_id} 完成：{result['report']['overall_score']}",
                flush=True,
            )
    manifest["completed_at"] = now_text()
    manifest["successful_count"] = len(outputs)
    manifest["technical_failure_count"] = len(failures)
    manifest["technical_failure_case_ids"] = sorted(failures)
    manifest["run_status"] = "complete" if not failures else "technical_failures"
    write_json(results_root / "run_manifest.json", manifest)
    if not failures:
        freeze_blind_results(results_root, manifest)
    return manifest


def run_paper_case(
    input_file: Path,
    taskbook: dict[str, Any],
    upload_cache: dict[str, str],
    provider: str,
    model: str,
    condition: str,
) -> dict[str, Any]:
    """运行一份匿名样本，并保存条件审计信息。"""
    case_input = read_json(input_file)
    llm_client = get_llm_client(provider, model)
    include_knowledge = condition == "c3_multi_agent_knowledge"
    context = build_context(
        case_input,
        input_file.parent,
        upload_cache,
        provider,
        taskbook,
        "legacy_v1",
        None,
        include_knowledge,
    )
    started = time.monotonic()
    if condition == "c0_direct":
        report, prompt_audit = run_single_model_condition(llm_client, context, False)
    elif condition == "c1_structured_single":
        report, prompt_audit = run_single_model_condition(llm_client, context, True)
    else:
        report = llm_client.generate_evaluation(context)
        prompt_audit = {
            "prompt_sha256": calculate_prompt_fingerprint("legacy_v1"),
            "score_band_guidance": context.get("score_band_guidance", ""),
            "knowledge_reference_ids": [
                str(item.get("reference_id") or "") for item in context.get("references", [])
            ],
        }
    duration = round(time.monotonic() - started, 3)
    return {
        "case_id": case_input["case_id"],
        "provider": provider,
        "model": model,
        "condition": condition,
        "condition_name": CONDITION_NAMES[condition],
        "completed_at": now_text(),
        "duration_seconds": duration,
        "contains_judge": False,
        "contains_teacher_score": False,
        "input_audit": {
            "description_is_empty": not bool(case_input.get("description")),
            "page_descriptions_are_empty": all(
                not bool(item.get("description")) for item in case_input.get("drawings", [])
            ),
            "score_guidance_excludes_current_case": True,
            "knowledge_enabled": include_knowledge,
        },
        "prompt_audit": prompt_audit,
        "report": report,
    }


def condition_prompt_fingerprint(condition: str) -> str:
    """返回四个实验条件各自的提示词指纹。"""
    if condition == "c0_direct":
        content = DIRECT_SYSTEM_PROMPT
    elif condition == "c1_structured_single":
        content = STRUCTURED_SYSTEM_PROMPT
    else:
        content = calculate_prompt_fingerprint("legacy_v1")
    return hashlib.sha256(f"{condition}\n{content}".encode("utf-8")).hexdigest()[:16]


def ensure_empty_target(path: Path, label: str) -> None:
    """禁止覆盖已有实验数据。"""
    if path.exists() and any(path.iterdir()):
        raise ValueError(f"{label}目录不为空，不得覆盖：{path}")
    path.mkdir(parents=True, exist_ok=True)


def read_json(path: Path) -> dict[str, Any]:
    """读取 UTF-8 JSON。"""
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    """计算文件哈希。"""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def calculate_input_bundle_fingerprint(
    input_root: Path,
    index: dict[str, Any],
) -> str:
    """对任务书、匿名配置和全部图纸计算稳定联合指纹。"""
    paths = [input_root / "index.json"]
    taskbook_name = str(index.get("taskbook_file", "")).strip()
    if taskbook_name:
        paths.append(input_root / taskbook_name)
    for item in index.get("cases", []):
        input_file = input_root / str(item["input_file"])
        paths.append(input_file)
        payload = read_json(input_file)
        for drawing in payload.get("drawings", []):
            paths.append(input_file.parent / str(drawing["relative_path"]))
    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda item: str(item.relative_to(input_root))):
        relative = str(path.relative_to(input_root)).replace("\\", "/")
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(sha256_file(path).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def calculate_review_code_fingerprint() -> str:
    """冻结影响评图的当前代码状态。"""
    project_root = Path(__file__).resolve().parents[3]
    return fingerprint_files(project_root, collect_relevant_files(project_root))


def now_text() -> str:
    """返回带时区时间。"""
    return datetime.now().astimezone().isoformat(timespec="seconds")
