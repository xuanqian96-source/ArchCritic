"""盘点长程 Goal 所需的基准样本、知识卡和公共建筑案例。"""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import re
from typing import Any

from app.benchmarking.asset_content_validation import (
    approved_source_records,
    case_draft_has_deep_evidence,
    case_draft_record_is_complete,
    count_eligible_cases,
    count_eligible_knowledge,
    eligible_questions,
    knowledge_card_record_is_complete,
    note_is_approved,
    permitted_media_records,
    question_record_is_complete,
)


SCORE_IN_NAME = re.compile(r"[\(（]\s*\d+(?:\.\d+)?\s*分\s*[\)）]")
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".svg", ".tif", ".tiff"}
FORBIDDEN_INPUT_KEYS = {
    "teacher_score",
    "teacher_scores",
    "score_range",
    "score_ranges",
    "acceptable_score_interval",
    "facts",
    "must_issues",
    "optional_issues",
    "forbidden_issues",
    "ground_truth",
    "answer",
    "answers",
    "grade_band",
    "sample_id",
}
FORBIDDEN_INPUT_TEXT = (
    "教师评分",
    "教师成绩",
    "原始成绩",
    "高分样本",
    "中档样本",
    "低分样本",
    "人工标准答案",
    "人工标注答案",
)
REQUIRED_TRUTH_FIELDS = {
    "case_id",
    "teacher_score",
    "teacher_score_reason",
    "teacher_scored_at",
    "reviewer_type",
    "acceptable_score_interval",
    "grade_band",
    "facts",
    "must_issues",
    "optional_issues",
    "forbidden_issues",
    "authorization_status",
    "anonymization_record",
    "annotation_version",
    "review_record",
}


def audit_goal_assets(dataset_root: Path, knowledge_root: Path) -> dict[str, Any]:
    """生成不包含教师具体分数和标注答案的资产盘点。"""
    dataset = audit_dataset(dataset_root)
    knowledge = audit_knowledge_base(knowledge_root)
    gates = build_gate_summary(dataset, knowledge)
    return {
        "audit_version": "goal-asset-audit-v1",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "contains_teacher_scores": False,
        "contains_annotation_answers": False,
        "dataset": dataset,
        "knowledge_base": knowledge,
        "gates": gates,
    }


def audit_dataset(dataset_root: Path) -> dict[str, Any]:
    """检查样本数量、匿名输入、答案隔离和验收元数据。"""
    prepared_root = dataset_root / ".prepared"
    index = read_json(prepared_root / "index.json", {"cases": []})
    truth = read_json(prepared_root / "ground_truth.json", {"cases": []})
    index_cases = index.get("cases", []) if isinstance(index, dict) else []
    truth_cases = truth.get("cases", []) if isinstance(truth, dict) else []
    truth_by_id = {
        item.get("case_id"): item
        for item in truth_cases
        if isinstance(item, dict) and item.get("case_id")
    }

    model_input_violations: list[dict[str, Any]] = []
    prepared_case_ids: list[str] = []
    sample_ids = {
        str(item.get("sample_id", "")).strip()
        for item in truth_cases
        if isinstance(item, dict) and item.get("sample_id")
    }
    for item in index_cases:
        if not isinstance(item, dict):
            continue
        case_id = str(item.get("case_id", "")).strip()
        if case_id:
            prepared_case_ids.append(case_id)
        input_path = prepared_root / str(item.get("input_file", ""))
        payload = read_json(input_path, {})
        violations = find_input_violations(payload, sample_ids)
        if violations:
            model_input_violations.append(
                {"case_id": case_id or "unknown", "violations": violations}
            )

    raw_sample_dirs = find_raw_sample_dirs(dataset_root)
    score_bearing_names = sum(bool(SCORE_IN_NAME.search(path.name)) for path in raw_sample_dirs)
    band_counts = {"high": 0, "mid": 0, "low": 0, "unknown": 0}
    metadata_complete = 0
    for item in truth_cases:
        if not isinstance(item, dict):
            band_counts["unknown"] += 1
            continue
        band_counts[score_band(item.get("teacher_score"))] += 1
        if REQUIRED_TRUTH_FIELDS.issubset(item):
            metadata_complete += 1

    ground_truth_path = prepared_root / "ground_truth.json"
    inputs_root = prepared_root / "inputs"
    answer_isolation = (
        "insufficient_same_prepared_root"
        if ground_truth_path.parent == inputs_root.parent
        else "separate_root"
    )
    taskbook_count = len(
        [
            path
            for path in dataset_root.glob("*")
            if path.is_file()
            and path.suffix.lower() in {".pdf", ".docx", ".txt"}
            and ("任务书" in path.name or "教学大纲" in path.name)
        ]
    )

    return {
        "raw_sample_count": len(raw_sample_dirs),
        "prepared_input_count": len(prepared_case_ids),
        "prepared_case_ids": sorted(prepared_case_ids),
        "band_rule": {"low": "<75", "mid": "75-89.99", "high": ">=90"},
        "band_counts": band_counts,
        "taskbook_count": taskbook_count,
        "raw_names_with_score_count": score_bearing_names,
        "model_input_violation_count": len(model_input_violations),
        "model_input_violations": model_input_violations,
        "answer_isolation": answer_isolation,
        "metadata_complete_case_count": metadata_complete,
        "double_reviewed_case_count": count_reviewed_cases(truth_cases),
        "authorization_verified_case_count": count_verified_authorizations(truth_cases),
        "current_cases_allowed_as_final_test": False,
        "acceptance_ready_case_count": 0,
        "notes": [
            "现有样本已参与开发，只能作为开发回归集。",
            "盘点输出不包含教师具体分数或人工答案。",
        ],
    }


def audit_knowledge_base(knowledge_root: Path) -> dict[str, Any]:
    """检查知识卡、案例、来源和媒体授权的可验收性。"""
    knowledge_notes = markdown_files(
        knowledge_root / "04常见问题"
    ) + markdown_files(knowledge_root / "05评价维度")
    case_notes = markdown_files(knowledge_root / "03优秀案例笔记")
    standard_notes = markdown_files(knowledge_root / "02设计规范笔记")

    source_record_files = list(knowledge_root.rglob("source-record*.json"))
    all_source_records = [
        item
        for path in source_record_files
        for item in normalize_records(read_json(path, []))
    ]
    media_files = [
        path
        for path in (knowledge_root / "00原始资料" / "优秀案例").rglob("*")
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    ] if knowledge_root.is_dir() else []
    media_records = read_media_records(knowledge_root)
    approved_sources = approved_source_records(all_source_records)
    approved_source_ids = {str(item.get("source_id")) for item in approved_sources}
    permitted_media = permitted_media_records(media_records, approved_source_ids)
    permitted_media_ids = {str(item.get("media_id")) for item in permitted_media}
    eligible_knowledge, knowledge_levels = count_eligible_knowledge(
        knowledge_notes, approved_source_ids
    )
    knowledge_draft_records = [
        item
        for path in knowledge_root.rglob("knowledge-card-drafts*.json")
        for item in normalize_records(read_json(path, []))
    ]
    valid_knowledge_drafts = sum(
        knowledge_card_record_is_complete(item, approved_source_ids)
        for item in knowledge_draft_records
    )
    approved_knowledge_drafts = [
        item
        for item in knowledge_draft_records
        if knowledge_card_record_is_complete(item, approved_source_ids)
        and item.get("review_status") == "approved"
        and item.get("human_review_confirmed") is True
    ]
    if knowledge_draft_records:
        eligible_knowledge = len(approved_knowledge_drafts)
        knowledge_levels = {
            level: sum(item.get("level") == level for item in approved_knowledge_drafts)
            for level in ("beginner", "advanced", "master")
        }
    eligible_cases, deep_cases = count_eligible_cases(
        case_notes, approved_source_ids, permitted_media_ids
    )
    case_draft_records = [
        item
        for path in knowledge_root.rglob("public-building-case-drafts*.json")
        for item in normalize_records(read_json(path, []))
    ]
    valid_case_drafts = sum(
        case_draft_record_is_complete(item, approved_source_ids)
        for item in case_draft_records
    )
    deep_ready_case_drafts = sum(
        case_draft_record_is_complete(item, approved_source_ids)
        and case_draft_has_deep_evidence(item)
        for item in case_draft_records
    )
    approved_case_drafts = [
        item
        for item in case_draft_records
        if case_draft_record_is_complete(item, approved_source_ids)
        and item.get("review_status") == "approved"
        and item.get("human_review_confirmed") is True
        and item.get("media_permission_status") == "cleared"
        and bool(item.get("media_record_ids"))
        and set(map(str, item.get("media_record_ids", []))) <= permitted_media_ids
    ]
    if case_draft_records:
        eligible_cases = len(approved_case_drafts)
        deep_cases = sum(case_draft_has_deep_evidence(item) for item in approved_case_drafts)
    core_source_records = [
        item
        for item in approved_sources
        if item.get("counts_as_core_source") is True
    ]
    case_worklists = [
        item
        for path in knowledge_root.rglob("case-source-worklist.json")
        for item in normalize_records(read_json(path, []))
    ]
    case_source_coverage = sum(
        bool(item.get("reliable_source_record_ids"))
        and all(
            str(source_id) in approved_source_ids
            for source_id in item.get("reliable_source_record_ids", [])
        )
        for item in case_worklists
        if isinstance(item, dict)
    )
    question_files = list(knowledge_root.rglob("*question*.json"))
    question_candidates = [
        item
        for path in question_files
        for item in normalize_records(read_json(path, []))
        if isinstance(item, dict)
    ]
    questions = [
        item
        for item in eligible_questions(question_candidates, approved_source_ids)
        if item.get("human_review_confirmed") is True
    ]
    question_draft_records = [
        item
        for path in knowledge_root.rglob("question-drafts*.json")
        for item in normalize_records(read_json(path, []))
    ]
    valid_question_drafts = sum(
        question_record_is_complete(item, approved_source_ids)
        for item in question_draft_records
    )

    return {
        "standard_note_count": len(standard_notes),
        "approved_standard_note_count": sum(note_is_approved(path) for path in standard_notes),
        "approved_source_record_count": len(approved_sources),
        "core_source_record_count": len(core_source_records),
        "knowledge_card_candidate_count": len(knowledge_notes),
        "knowledge_card_structured_draft_count": len(knowledge_draft_records),
        "knowledge_card_valid_draft_count": valid_knowledge_drafts,
        "eligible_knowledge_card_count": eligible_knowledge,
        "knowledge_cards_by_level": knowledge_levels,
        "case_candidate_count": len(case_notes),
        "case_candidate_with_approved_source_count": case_source_coverage,
        "case_structured_draft_count": len(case_draft_records),
        "case_valid_draft_count": valid_case_drafts,
        "case_deep_ready_draft_count": deep_ready_case_drafts,
        "eligible_case_count": eligible_cases,
        "deep_case_count": deep_cases,
        "media_file_count": len(media_files),
        "media_with_permission_record_count": min(len(permitted_media), len(media_files)),
        "fixed_question_count": len(questions),
        "structured_question_draft_count": len(question_draft_records),
        "valid_question_draft_count": valid_question_drafts,
        "adversarial_or_unanswerable_question_count": sum(
            item.get("question_type") in {"adversarial", "unanswerable"} for item in questions
        ),
        "source_registry_present": bool(source_record_files),
        "notes": [
            "候选笔记只有字段、来源、权限和审核都齐全才计入验收。",
            "只有图片或待分析占位内容的案例不计入深度案例。",
        ],
    }


def build_gate_summary(dataset: dict[str, Any], knowledge: dict[str, Any]) -> dict[str, Any]:
    """把任务书的资产门槛转换为明确的通过与缺口。"""
    checks = {
        "dataset_total": dataset["prepared_input_count"] >= 20,
        "dataset_high": dataset["band_counts"]["high"] >= 6,
        "dataset_mid": dataset["band_counts"]["mid"] >= 6,
        "dataset_low": dataset["band_counts"]["low"] >= 6,
        "dataset_double_reviewed": dataset["double_reviewed_case_count"] >= 10,
        "dataset_authorized": dataset["authorization_verified_case_count"] >= 20,
        "model_inputs_clean": dataset["model_input_violation_count"] == 0,
        "answers_physically_separated": dataset["answer_isolation"] == "separate_root",
        "core_sources": knowledge["core_source_record_count"] >= 3,
        "knowledge_cards": knowledge["eligible_knowledge_card_count"] >= 60,
        "knowledge_levels": all(
            knowledge["knowledge_cards_by_level"].get(level, 0) >= 20
            for level in ("beginner", "advanced", "master")
        ),
        "public_building_cases": knowledge["eligible_case_count"] >= 20,
        "deep_cases": knowledge["deep_case_count"] >= 10,
        "media_permissions": (
            knowledge["media_file_count"] > 0
            and knowledge["media_with_permission_record_count"] == knowledge["media_file_count"]
        ),
        "fixed_questions": knowledge["fixed_question_count"] >= 30,
        "adversarial_questions": knowledge["adversarial_or_unanswerable_question_count"] >= 10,
    }
    return {
        "passed": sum(checks.values()),
        "failed": sum(not value for value in checks.values()),
        "all_asset_gates_passed": all(checks.values()),
        "checks": checks,
    }


def find_input_violations(payload: Any, sample_ids: set[str]) -> list[str]:
    """递归检查模型输入中的答案字段和成绩暗示。"""
    violations: set[str] = set()

    def visit(value: Any, path: str) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                normalized = str(key).strip().lower()
                child_path = f"{path}.{key}" if path else str(key)
                if normalized in FORBIDDEN_INPUT_KEYS:
                    violations.add(f"forbidden_key:{child_path}")
                visit(child, child_path)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                visit(child, f"{path}[{index}]")
        elif isinstance(value, str):
            if SCORE_IN_NAME.search(value):
                violations.add(f"score_in_text:{path}")
            if any(token in value for token in FORBIDDEN_INPUT_TEXT):
                violations.add(f"answer_hint_in_text:{path}")
            if any(sample_id and sample_id in value for sample_id in sample_ids):
                violations.add(f"raw_sample_id_in_text:{path}")

    visit(payload, "")
    return sorted(violations)


def find_raw_sample_dirs(dataset_root: Path) -> list[Path]:
    """识别同时含标注 Markdown 和图纸目录的原始样本。"""
    if not dataset_root.is_dir():
        return []
    return sorted(
        path
        for path in dataset_root.iterdir()
        if path.is_dir()
        and not path.name.startswith(".")
        and (path / "图纸").is_dir()
        and any(path.glob("*.md"))
    )


def score_band(value: Any) -> str:
    """按冻结分档规则统计数量，不对外输出具体分数。"""
    try:
        score = float(value)
    except (TypeError, ValueError):
        return "unknown"
    if score >= 90:
        return "high"
    if score >= 75:
        return "mid"
    return "low"


def count_reviewed_cases(cases: list[Any]) -> int:
    """统计存在第二评审者可核对记录的样本。"""
    return sum(
        bool(item.get("review_record"))
        and isinstance(item.get("review_record"), (dict, list))
        for item in cases
        if isinstance(item, dict)
    )


def count_verified_authorizations(cases: list[Any]) -> int:
    """统计已明确授权可用的样本。"""
    accepted = {"approved", "authorized", "internal_only", "demo_allowed", "public_allowed"}
    return sum(
        str(item.get("authorization_status", "")).strip().lower() in accepted
        for item in cases
        if isinstance(item, dict)
    )


def markdown_files(root: Path) -> list[Path]:
    """返回目录下的 Markdown 文件。"""
    return sorted(root.rglob("*.md")) if root.is_dir() else []


def read_media_records(knowledge_root: Path) -> list[dict[str, Any]]:
    """读取知识库内所有媒体授权登记表。"""
    records: list[dict[str, Any]] = []
    for path in knowledge_root.rglob("media-manifest*.json") if knowledge_root.is_dir() else []:
        records.extend(normalize_records(read_json(path, [])))
    return records


def normalize_records(value: Any) -> list[dict[str, Any]]:
    """把数组或带 records 字段的 JSON 统一为记录列表。"""
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict) and isinstance(value.get("records"), list):
        return [item for item in value["records"] if isinstance(item, dict)]
    return []


def read_json(path: Path, fallback: Any) -> Any:
    """安全读取 UTF-8 JSON，缺失时返回默认值。"""
    if not path.is_file():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return fallback
