"""通过真实 ArchCritic 多 Agent 链路运行匿名基准样本。"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import traceback
from typing import Any

from app.config import get_settings
from app.llm.client import get_llm_client
from app.llm.dashscope_files import DashScopeFileClient
from app.knowledge_selection import prepare_reference_bundle
from app.services.taskbooks import (
    STAGE_BASE_WEIGHTS,
    build_weight_reasons,
    calculate_dimension_weights,
)
from app.services.taskbook_rules import build_structured_requirements
from app.scoring.calibration import load_calibrator
from app.scoring.visual_anchors import build_visual_anchor_context
from app.wiki import load_wiki_references


CORE_FACT_WORDS = (
    "总平",
    "平面",
    "剖面",
    "立面",
    "主入口",
    "楼梯",
    "电梯",
    "卫生间",
    "流线",
    "结构体系",
)


def run_benchmark_round(
    prepared_root: Path,
    results_root: Path,
    provider: str,
    model: str,
    workers: int = 2,
    case_ids: set[str] | None = None,
    architecture: str = "legacy_v1",
    calibration_file: Path | None = None,
) -> list[Path]:
    """上传匿名图纸并并行运行一轮真实评图。"""
    index = read_json(prepared_root / "index.json")
    taskbook_file = prepared_root / index.get("taskbook_file", "taskbook.json")
    taskbook = read_json(taskbook_file) if taskbook_file.is_file() else {}
    truth_by_id = {
        item["case_id"]: item for item in read_json(prepared_root / "ground_truth.json")["cases"]
    }
    selected = [
        item for item in index["cases"] if not case_ids or item["case_id"] in case_ids
    ]
    calibrator = load_calibrator(calibration_file)
    upload_cache = prepare_model_urls(prepared_root, selected, provider, model)
    results_root.mkdir(parents=True, exist_ok=True)
    output_paths = []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        futures = {}
        for item in selected:
            input_file = prepared_root / item["input_file"]
            future = executor.submit(
                run_case,
                input_file,
                truth_by_id[item["case_id"]],
                taskbook,
                upload_cache,
                provider,
                model,
                architecture,
                calibrator,
            )
            futures[future] = item["case_id"]
        for future in as_completed(futures):
            case_id = futures[future]
            try:
                result = future.result()
            except Exception as exc:  # noqa: BLE001 - 单样本失败不能中断整轮基准
                error_path = results_root / "errors" / f"{case_id}.json"
                write_json(
                    error_path,
                    {
                        "case_id": case_id,
                        "error_type": type(exc).__name__,
                        "message": str(exc)[:1000],
                        "traceback": traceback.format_exc()[-4000:],
                        "failed_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                    },
                )
                print(f"{case_id} 失败：{type(exc).__name__}：{str(exc)[:160]}", flush=True)
                continue
            output_path = results_root / f"{case_id}.json"
            write_json(output_path, result)
            output_paths.append(output_path)
            print(f"{case_id} 完成：{result['report']['overall_score']}", flush=True)
    return sorted(output_paths)


def prepare_model_urls(
    prepared_root: Path,
    selected: list[dict],
    provider: str,
    model: str,
    extra_files: list[dict[str, Any]] | None = None,
) -> dict[str, str]:
    """为百炼准备临时 OSS 地址，避免以 base64 发送正式图纸。"""
    if provider != "dashscope":
        return {}
    settings = get_settings()
    cache_file = prepared_root / "model_url_cache.json"
    cache = read_json(cache_file) if cache_file.exists() else {"items": {}}
    client = DashScopeFileClient(
        settings.dashscope_api_key,
        model,
        settings.llm_timeout_seconds,
        settings.llm_trust_env,
    )
    resolved = {}

    def resolve_file(path: Path, mime_type: str, label: str) -> None:
        """复用同一缓存上传一张当前图纸或视觉锚点。"""
        key = str(path.resolve())
        signature = f"{path.stat().st_size}:{path.stat().st_mtime_ns}"
        cached = cache["items"].get(key, {})
        if cached.get("signature") == signature and not cache_expired(
            cached.get("expires_at")
        ):
            resolved[key] = cached["url"]
            return
        uploaded = client.upload_file(path, mime_type)
        cache["items"][key] = {
            "signature": signature,
            "url": uploaded.url,
            "expires_at": uploaded.expires_at.isoformat(),
        }
        resolved[key] = uploaded.url
        write_json(cache_file, cache)
        print(f"已准备模型图纸：{label}/{path.name}", flush=True)

    for item in selected:
        input_file = prepared_root / item["input_file"]
        case_input = read_json(input_file)
        for drawing in case_input["drawings"]:
            path = input_file.parent / drawing["relative_path"]
            resolve_file(path, drawing["mime_type"], str(item["case_id"]))
    for item in extra_files or []:
        resolve_file(
            Path(item["path"]).resolve(),
            str(item.get("mime_type") or "image/jpeg"),
            str(item.get("label") or "视觉锚点"),
        )
    return resolved


def run_case(
    input_file: Path,
    truth: dict,
    taskbook: dict,
    upload_cache: dict[str, str],
    provider: str,
    model: str,
    architecture: str,
    calibrator: dict | None,
) -> dict:
    """运行一个匿名样本，并用独立文本裁判核对语义结果。"""
    case_input = read_json(input_file)
    llm_client = get_llm_client(provider, model)
    context = build_context(
        case_input,
        input_file.parent,
        upload_cache,
        provider,
        taskbook,
        architecture,
        calibrator,
    )
    report = llm_client.generate_evaluation(context)
    judge = judge_report(llm_client, report, truth)
    return {
        "case_id": case_input["case_id"],
        "provider": provider,
        "model": model,
        "architecture": architecture,
        "calibrator_version": (calibrator or {}).get("version", "not_configured"),
        "prompt_fingerprint": calculate_prompt_fingerprint(architecture),
        "completed_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "report": report,
        "judge": judge,
    }


def build_context(
    case_input: dict,
    case_root: Path,
    upload_cache: dict[str, str],
    provider: str,
    taskbook: dict,
    architecture: str = "legacy_v1",
    calibrator: dict | None = None,
    include_knowledge: bool = True,
    visual_anchor_root: Path | None = None,
) -> dict:
    """构造与产品真实评图相同字段的模型上下文。"""
    stage = case_input["design_stage"]
    active_agents = list(STAGE_BASE_WEIGHTS[stage])
    taskbook_text = taskbook.get("full_text", "")
    weights = calculate_dimension_weights(stage, "大二", taskbook_text, active_agents)
    drawing_types = [item["drawing_type"] for item in case_input["drawings"]]
    references = []
    if include_knowledge:
        references = load_wiki_references(
            get_settings().wiki_dir,
            stage,
            limit=40,
            query_context={
                "project_name": case_input["project_name"],
                "building_type": case_input["building_type"],
                "design_stage": stage,
                "description": case_input["description"],
                "drawing_types": drawing_types,
            },
        )
    references = prepare_reference_bundle(
        references,
        stage,
        active_agents,
        human_approved_only=architecture == "evidence_v2",
    )
    drawings = []
    for item in case_input["drawings"]:
        path = (case_root / item["relative_path"]).resolve()
        model_file_url = upload_cache.get(str(path), "")
        drawings.append(
            {
                **item,
                "file_url": "",
                "model_file_url": model_file_url,
                "usable_for_model": bool(model_file_url),
                "analysis_purpose": item["description"],
            }
        )
    has_taskbook = bool(taskbook_text)
    task_summary = taskbook.get("summary", "") or (
        "未提供原始课程任务书，只能按建筑学大二公共文化建筑课程成果评价。"
    )
    requirements = taskbook.get("requirements", [])
    structured_requirements = taskbook.get("structured_requirements") or (
        build_structured_requirements(requirements)
    )
    visual_score_anchors = (
        build_visual_anchor_context(
            visual_anchor_root,
            upload_cache,
            provider,
        )
        if visual_anchor_root
        else []
    )
    return {
        "project_name": case_input["project_name"],
        "building_type": case_input["building_type"],
        "owner_name": "匿名学生",
        "grade": "大二",
        "design_stage": stage,
        "enabled_agents": [],
        "description": case_input["description"],
        "task_book_summary": task_summary,
        "task_book_text": taskbook_text,
        "task_book_requirements": requirements,
        "task_book_profile": {
            "has_task_book": has_taskbook,
            "source_files": taskbook.get("source_files", []),
            "summary": task_summary,
            "requirements": requirements,
            "structured_requirements": structured_requirements,
            "dimension_weights": weights,
            "weight_reasons": build_weight_reasons(
                "大二", taskbook_text, active_agents, weights
            ),
        },
        "dimension_weights": weights,
        "structured_requirements": structured_requirements,
        "scoring_architecture": architecture,
        "score_calibration": calibrator,
        "score_band_guidance": case_input.get("score_band_guidance", ""),
        "visual_score_anchors": visual_score_anchors,
        "drawing_scope": "已提供本次成果的全部展板，模型必须综合读取全部页面。",
        "drawings": drawings,
        "references": references,
        "knowledge_policy": (
            "human_approved_only" if architecture == "evidence_v2" else "compatible"
        ),
        "missing_information": [
            *([] if has_taskbook else [
                "未提供原始课程任务书，任务书符合性不能作为确定结论。"
            ]),
            *([] if architecture != "evidence_v2" or references else [
                "当前没有通过人工复核的知识卡；本次只能依据任务书和图纸评分，知识引用为空。"
            ]),
        ],
    }


def judge_report(llm_client: Any, report: dict, truth: dict) -> dict:
    """用独立文本裁判比较模型报告和人工事实，不把答案提供给被测 Agent。"""
    facts = [
        item for item in truth.get("facts", [])
        if any(word in item["item"] for word in CORE_FACT_WORDS)
    ]
    prompt = {
        "人工事实": facts,
        "必须识别问题": truth.get("must_issues", []),
        "禁止误报": truth.get("forbidden_issues", []),
        "待核对模型报告": report,
    }
    request = {
        "model": llm_client.model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是建筑评图基准裁判，只比较给定人工标注和模型报告。"
                    "语义相同即可算命中；模型未提及不能算命中；把不确定写成确定缺失应算错误。"
                    "禁止误报只有在模型明确说出了被禁止结论时才算 violated。"
                    "必须逐项原样返回人工事实的 item、必须问题和禁止误报的 id，不得漏项。"
                    "只输出 JSON，结构必须是："
                    '{"fact_results":[{"item":"原始事实项","correct":true,"evidence":"报告依据"}],'
                    '"must_issue_results":[{"id":"M-01","matched":true,"evidence":"报告依据"}],'
                    '"forbidden_results":[{"id":"N-01","violated":false,"evidence":"判断依据"}]}。'
                ),
            },
            {
                "role": "user",
                "content": json.dumps(prompt, ensure_ascii=False),
            },
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0,
        "max_tokens": 4500,
        "timeout": min(120, get_settings().llm_timeout_seconds),
    }
    if getattr(llm_client, "extra_body", None):
        request["extra_body"] = llm_client.extra_body
    response = llm_client.client.chat.completions.create(
        **request,
    )
    raw = json.loads(response.choices[0].message.content or "{}")
    return normalize_judge(raw, facts, truth)


def normalize_judge(raw: dict, facts: list[dict], truth: dict) -> dict:
    """约束裁判输出字段，缺失项按未命中处理。"""
    return {
        "fact_results": normalize_boolean_items(raw.get("fact_results"), facts, "item", "correct"),
        "must_issue_results": normalize_boolean_items(
            raw.get("must_issue_results"), truth.get("must_issues", []), "id", "matched"
        ),
        "forbidden_results": normalize_boolean_items(
            raw.get("forbidden_results"), truth.get("forbidden_issues", []), "id", "violated"
        ),
    }


def normalize_boolean_items(raw_items: Any, expected: list[dict], key: str, flag: str) -> list[dict]:
    """按人工标注顺序补齐裁判布尔结果。"""
    by_id = {
        str(item.get(key)): item for item in raw_items or [] if isinstance(item, dict)
    }
    return [
        {
            key: item[key],
            flag: bool(by_id.get(str(item[key]), {}).get(flag, False)),
            "evidence": str(by_id.get(str(item[key]), {}).get("evidence", ""))[:240],
        }
        for item in expected
    ]


def cache_expired(value: str | None) -> bool:
    """判断百炼临时地址是否已经或即将失效。"""
    if not value:
        return True
    expires_at = datetime.fromisoformat(value)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return (expires_at - datetime.now(timezone.utc)).total_seconds() < 3600


def calculate_prompt_fingerprint(architecture: str = "legacy_v1") -> str:
    """记录本轮实际提示词文件摘要，便于确认两轮是否真正发生变化。"""
    agents_root = Path(__file__).resolve().parents[1] / "agents"
    prompts_root = agents_root / "prompts"
    digest = hashlib.sha256()
    active_prompt_files = [
        prompts_root / "function_agent_v1.py",
        prompts_root / "scheme_agents_v1.py",
    ]
    if architecture == "evidence_v2":
        active_prompt_files.extend(
            [
                prompts_root / "evidence_agents_v2.py",
                agents_root / "evidence_inventory.py",
                agents_root / "taskbook_compliance.py",
            ]
        )
    if architecture == "visual_anchor_v1":
        active_prompt_files.append(
            prompts_root / "visual_score_calibration_v1.py"
        )
    for path in active_prompt_files:
        digest.update(str(path.relative_to(agents_root)).encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()[:16]


def read_json(path: Path) -> dict:
    """读取 UTF-8 JSON。"""
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict) -> None:
    """写入 UTF-8 JSON。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
