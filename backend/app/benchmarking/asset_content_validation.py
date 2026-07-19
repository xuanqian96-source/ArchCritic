"""严格验证知识卡、公共建筑案例、来源、媒体和固定问答是否可计入验收。"""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any


KNOWLEDGE_REQUIRED_FIELDS = {
    "card_id",
    "title",
    "level",
    "learning_objective",
    "prerequisites",
    "building_types",
    "stages",
    "dimensions",
    "student_explanation",
    "key_terms",
    "related_cards",
    "related_cases",
    "self_test",
    "source_type",
    "source_record_ids",
    "source_locators",
    "copyright_status",
    "allowed_use",
    "organizer",
    "review_status",
    "reviewer",
    "version",
}
CASE_REQUIRED_FIELDS = {
    "case_id",
    "title",
    "architect",
    "location",
    "year",
    "scale",
    "building_type",
    "reliable_source_record_ids",
    "media_record_ids",
    "site_strategy",
    "functional_organization",
    "circulation",
    "spatial_sequence",
    "form_strategy",
    "structure_strategy",
    "environmental_response",
    "key_drawings",
    "transferable_lessons",
    "application_limits",
    "related_knowledge_cards",
    "similar_cases",
    "depth_evidence_categories",
    "review_status",
    "reviewer",
    "version",
}
SOURCE_REQUIRED_FIELDS = {
    "source_id",
    "source_title",
    "source_author_or_organization",
    "source_url_or_file",
    "publication_or_project_date",
    "accessed_at",
    "source_type",
    "license_or_permission",
    "allowed_use",
    "original_file_hash_or_snapshot_hash",
    "review_status",
    "reviewer",
}
ALLOWED_USE = {"internal_only", "demo_allowed", "public_allowed"}
INCOMPLETE_VALUES = {
    "",
    "[]",
    "{}",
    "null",
    "none",
    "unknown",
    "unverified",
    "not_cleared",
    "pending",
    "todo",
    "tbd",
    "待补充",
    "待核验",
    "未核验",
    "未知",
}


def approved_source_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """只保留字段有值、用途明确且已审核的来源记录。"""
    return [item for item in records if source_record_is_eligible(item)]


def source_record_is_eligible(record: dict[str, Any]) -> bool:
    """判断单条来源记录能否支撑正式内容。"""
    return (
        SOURCE_REQUIRED_FIELDS.issubset(record)
        and all(value_is_complete(record.get(field)) for field in SOURCE_REQUIRED_FIELDS)
        and record.get("review_status") == "approved"
        and record.get("allowed_use") in ALLOWED_USE
        and meaningful_permission(record.get("license_or_permission"))
    )


def permitted_media_records(
    records: list[dict[str, Any]], approved_source_ids: set[str]
) -> list[dict[str, Any]]:
    """只保留有文件哈希、有效来源、许可范围和审核人的媒体记录。"""
    required = {
        "media_id",
        "relative_path",
        "sha256",
        "source_record_id",
        "license_or_permission",
        "allowed_use",
        "review_status",
        "reviewer",
    }
    return [
        item
        for item in records
        if required.issubset(item)
        and all(value_is_complete(item.get(field)) for field in required)
        and str(item.get("source_record_id")) in approved_source_ids
        and item.get("review_status") == "approved"
        and item.get("allowed_use") in ALLOWED_USE
        and meaningful_media_permission(item.get("license_or_permission"))
    ]


def count_eligible_knowledge(
    paths: list[Path], approved_source_ids: set[str]
) -> tuple[int, dict[str, int]]:
    """统计字段、来源和审核全部通过的分层知识卡。"""
    levels = {"beginner": 0, "advanced": 0, "master": 0}
    eligible = 0
    for path in paths:
        fields = parse_frontmatter(path)
        source_ids = field_list(fields.get("source_record_ids", ""))
        level = field_scalar(fields.get("level", ""))
        if not note_fields_complete(fields, KNOWLEDGE_REQUIRED_FIELDS):
            continue
        if field_scalar(fields.get("review_status", "")) != "approved":
            continue
        if level not in levels or not source_ids or not set(source_ids) <= approved_source_ids:
            continue
        eligible += 1
        levels[level] += 1
    return eligible, levels


def knowledge_card_record_is_complete(
    record: dict[str, Any], approved_source_ids: set[str]
) -> bool:
    """验证结构化知识卡草稿具有可复核内容，但不把待审核草稿计为正式卡。"""
    if not KNOWLEDGE_REQUIRED_FIELDS.issubset(record):
        return False
    content_fields = KNOWLEDGE_REQUIRED_FIELDS - {"review_status"}
    if not all(value_is_complete(record.get(field)) for field in content_fields):
        return False
    if not re.fullmatch(r"KC-[A-Z0-9-]+", str(record.get("card_id", ""))):
        return False
    if record.get("level") not in {"beginner", "advanced", "master"}:
        return False
    if record.get("allowed_use") not in ALLOWED_USE:
        return False
    if record.get("review_status") not in {"draft", "pending", "approved", "rejected"}:
        return False
    source_ids = {str(value) for value in record.get("source_record_ids", [])}
    if not source_ids or not source_ids <= approved_source_ids:
        return False
    list_fields = (
        "prerequisites",
        "building_types",
        "stages",
        "dimensions",
        "key_terms",
        "related_cards",
        "related_cases",
        "self_test",
        "source_locators",
    )
    if any(not isinstance(record.get(field), list) or not record[field] for field in list_fields):
        return False
    if any(
        not isinstance(item, dict)
        or not value_is_complete(item.get("question"))
        or not item.get("expected_points")
        for item in record["self_test"]
    ):
        return False
    return all(
        isinstance(item, dict)
        and str(item.get("source_id")) in source_ids
        and value_is_complete(item.get("locator"))
        for item in record["source_locators"]
    )


def case_draft_record_is_complete(
    record: dict[str, Any], approved_source_ids: set[str]
) -> bool:
    """验证案例草稿的学科字段与逐项证据完整，但不替代正式审核和媒体授权。"""
    required = CASE_REQUIRED_FIELDS | {
        "evidence_register",
        "media_permission_status",
        "draft_scope",
    }
    if not required.issubset(record):
        return False
    content_fields = required - {"review_status", "media_permission_status"}
    if not all(value_is_complete(record.get(field)) for field in content_fields):
        return False
    if not re.fullmatch(r"PBC-[A-Z0-9-]+", str(record.get("case_id", ""))):
        return False
    if record.get("review_status") not in {"draft", "pending", "approved", "rejected"}:
        return False
    if record.get("media_permission_status") not in {
        "not_cleared",
        "partially_cleared",
        "cleared",
    }:
        return False
    source_ids = {str(value) for value in record.get("reliable_source_record_ids", [])}
    if not source_ids or not source_ids <= approved_source_ids:
        return False
    list_fields = (
        "media_record_ids",
        "key_drawings",
        "transferable_lessons",
        "related_knowledge_cards",
        "similar_cases",
        "depth_evidence_categories",
        "evidence_register",
    )
    if any(not isinstance(record.get(field), list) for field in list_fields):
        return False
    if not record["media_record_ids"] or not all(
        re.fullmatch(r"MEDIA-[A-Z0-9-]+", str(value))
        for value in record["media_record_ids"]
    ):
        return False
    if not record["key_drawings"] or not record["related_knowledge_cards"]:
        return False
    if not all(
        re.fullmatch(r"KC-[A-Z0-9-]+", str(value))
        for value in record["related_knowledge_cards"]
    ):
        return False
    if not 3 <= len(record["transferable_lessons"]) <= 5:
        return False
    allowed_depth = {"site", "function_and_circulation", "space_and_form", "section_or_structure"}
    if not set(record["depth_evidence_categories"]) <= allowed_depth:
        return False
    if len(set(record["depth_evidence_categories"])) < 2:
        return False
    evidence = record["evidence_register"]
    if len(evidence) < 4:
        return False
    supported_categories = set()
    for item in evidence:
        if not isinstance(item, dict):
            return False
        if not all(
            value_is_complete(item.get(field))
            for field in ("category", "source_id", "locator", "supports", "evidence_type")
        ):
            return False
        if str(item["source_id"]) not in source_ids:
            return False
        if item["evidence_type"] not in {"official_fact", "disciplinary_inference"}:
            return False
        supported_categories.add(str(item["category"]))
    return len(supported_categories & allowed_depth) >= 2


def case_draft_has_deep_evidence(record: dict[str, Any]) -> bool:
    """判断结构化案例草稿是否已具备至少三个分析维度的可定位证据。"""
    allowed_depth = {"site", "function_and_circulation", "space_and_form", "section_or_structure"}
    declared = set(record.get("depth_evidence_categories", [])) & allowed_depth
    evidenced = {
        str(item.get("category"))
        for item in record.get("evidence_register", [])
        if isinstance(item, dict)
    } & allowed_depth
    return len(declared & evidenced) >= 3


def note_is_approved(path: Path) -> bool:
    """判断 Markdown 内容是否有明确审核状态和审核人。"""
    fields = parse_frontmatter(path)
    return (
        field_scalar(fields.get("review_status", "")) == "approved"
        and value_is_complete(fields.get("reviewer"))
    )


def count_eligible_cases(
    paths: list[Path],
    approved_source_ids: set[str],
    permitted_media_ids: set[str],
) -> tuple[int, int]:
    """统计来源、媒体、完整分析和审核全部通过的案例与深度案例。"""
    eligible = 0
    deep = 0
    for path in paths:
        fields = parse_frontmatter(path)
        source_ids = field_list(fields.get("reliable_source_record_ids", ""))
        media_ids = field_list(fields.get("media_record_ids", ""))
        if not note_fields_complete(fields, CASE_REQUIRED_FIELDS):
            continue
        if field_scalar(fields.get("review_status", "")) != "approved":
            continue
        if not source_ids or not set(source_ids) <= approved_source_ids:
            continue
        if not media_ids or not set(media_ids) <= permitted_media_ids:
            continue
        eligible += 1
        depth = set(field_list(fields.get("depth_evidence_categories", "")))
        if len(depth & {"site", "function_and_circulation", "space_and_form", "section_or_structure"}) >= 3:
            deep += 1
    return eligible, deep


def eligible_questions(
    records: list[dict[str, Any]], approved_source_ids: set[str]
) -> list[dict[str, Any]]:
    """只统计题目、类型、审核人和预期来源均可核查的固定问答。"""
    return [
        item
        for item in records
        if item.get("review_status") == "approved"
        and question_record_is_complete(item, approved_source_ids)
    ]


def question_record_is_complete(
    record: dict[str, Any], approved_source_ids: set[str]
) -> bool:
    """验证固定问答草稿的答案点、来源和防编造要求。"""
    required = {
        "question_id",
        "level",
        "question_type",
        "question",
        "expected_answer_points",
        "expected_source_record_ids",
        "expected_source_locators",
        "forbidden_behaviors",
        "review_status",
        "reviewer",
        "version",
    }
    if not required.issubset(record):
        return False
    scalar_fields = ("question_id", "level", "question_type", "question", "reviewer", "version")
    if not all(value_is_complete(record.get(field)) for field in scalar_fields):
        return False
    if not re.fullmatch(r"Q-[A-Z0-9-]+", str(record.get("question_id", ""))):
        return False
    if record.get("level") not in {"beginner", "advanced", "master"}:
        return False
    question_type = record.get("question_type")
    if question_type not in {"evidence_based", "adversarial", "unanswerable"}:
        return False
    if record.get("review_status") not in {"draft", "pending", "approved", "rejected"}:
        return False
    if not record.get("expected_answer_points") or not record.get("forbidden_behaviors"):
        return False
    source_ids = {str(value) for value in record.get("expected_source_record_ids", [])}
    locators = record.get("expected_source_locators", [])
    if question_type == "evidence_based":
        return bool(source_ids) and source_ids <= approved_source_ids and bool(locators)
    return not source_ids and not locators


def parse_frontmatter(path: Path) -> dict[str, str]:
    """读取 Markdown YAML 前置区的顶层字段及其原始值。"""
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---", 4)
    if end < 0:
        return {}
    fields: dict[str, list[str]] = {}
    current = ""
    for line in text[4:end].splitlines():
        match = re.match(r"^([A-Za-z][A-Za-z0-9_]*)\s*:\s*(.*)$", line)
        if match:
            current = match.group(1)
            fields[current] = [match.group(2)]
        elif current and (line.startswith(" ") or line.startswith("\t") or line.lstrip().startswith("-")):
            fields[current].append(line)
    return {key: "\n".join(value).strip() for key, value in fields.items()}


def note_fields_complete(fields: dict[str, str], required: set[str]) -> bool:
    """确认必填字段不只是存在，而且包含真实内容。"""
    return required.issubset(fields) and all(value_is_complete(fields[field]) for field in required)


def field_scalar(raw: str) -> str:
    """去除简单 YAML 引号得到标量。"""
    return raw.strip().strip("\"'").strip()


def field_list(raw: str) -> list[str]:
    """读取常见的行内或多行 YAML 字符串列表。"""
    value = raw.strip()
    if not value:
        return []
    if value.startswith("[") and value.endswith("]"):
        try:
            parsed = json.loads(value.replace("'", '"'))
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if value_is_complete(item)]
        except json.JSONDecodeError:
            value = value[1:-1]
            return [item.strip().strip("\"'") for item in value.split(",") if value_is_complete(item)]
    lines = [line.strip() for line in value.splitlines()]
    listed = [line[1:].strip().strip("\"'") for line in lines if line.startswith("-")]
    return listed or ([field_scalar(value)] if value_is_complete(value) else [])


def value_is_complete(value: Any) -> bool:
    """拒绝空值、占位值和空集合。"""
    if value is None:
        return False
    if isinstance(value, (list, dict, tuple, set)):
        return bool(value)
    normalized = field_scalar(str(value)).lower()
    return normalized not in INCOMPLETE_VALUES


def meaningful_permission(value: Any) -> bool:
    """允许明确的事实引用范围，同时拒绝纯粹的未核验占位。"""
    text = field_scalar(str(value or "")).lower()
    blocked = ("unverified", "not cleared", "not_cleared", "未核验", "待核验", "权限未确认")
    positive = ("允许", "授权", "可在内部", "可用于", "可引用", "cc by", "public domain", "公有领域")
    return value_is_complete(text) and (
        not any(token in text for token in blocked)
        or any(token in text for token in positive)
    )


def meaningful_media_permission(value: Any) -> bool:
    """媒体许可必须明确覆盖图片或图纸本身，事实引用说明不能替代版权许可。"""
    text = field_scalar(str(value or "")).lower()
    blocked = ("unverified", "not cleared", "not_cleared", "未核验", "待核验", "权限未确认")
    return meaningful_permission(text) and not any(token in text for token in blocked)
