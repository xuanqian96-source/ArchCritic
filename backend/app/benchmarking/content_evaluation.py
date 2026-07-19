"""验证并执行固定案例检索与评图问题联动任务。"""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any


REQUIRED_FIELDS = {
    "task_id",
    "task_type",
    "query_or_problem",
    "design_stage",
    "building_type",
    "problem_category",
    "expected_knowledge_card_ids",
    "expected_case_ids",
    "acceptable_case_ids",
    "required_reason_points",
    "forbidden_behaviors",
    "review_status",
    "reviewer",
    "version",
}
TASK_TYPES = {"case_retrieval", "problem_linkage"}
STAGES = {"concept", "scheme", "drawing", "all"}
LINKAGE_CATEGORIES = {
    "site",
    "function_and_circulation",
    "space_and_form",
    "structure_and_environment",
    "representation_and_evidence",
}


def evaluation_task_is_complete(
    record: dict[str, Any],
    known_card_ids: set[str],
    known_case_ids: set[str],
) -> bool:
    """检查固定任务结构、引用编号和验收口径是否完整。"""
    if not REQUIRED_FIELDS <= record.keys():
        return False
    scalar_fields = (
        "task_id",
        "task_type",
        "query_or_problem",
        "design_stage",
        "building_type",
        "problem_category",
        "reviewer",
        "version",
    )
    if not all(str(record.get(field, "")).strip() for field in scalar_fields):
        return False
    if record["task_type"] not in TASK_TYPES or record["design_stage"] not in STAGES:
        return False
    if record.get("review_status") not in {"draft", "pending", "approved", "rejected"}:
        return False
    card_ids = string_set(record.get("expected_knowledge_card_ids"))
    expected_cases = string_set(record.get("expected_case_ids"))
    acceptable_cases = string_set(record.get("acceptable_case_ids"))
    if not expected_cases or not expected_cases <= acceptable_cases:
        return False
    if not card_ids <= known_card_ids or not acceptable_cases <= known_case_ids:
        return False
    if len(record.get("required_reason_points", [])) < 2:
        return False
    if not record.get("forbidden_behaviors"):
        return False
    if record["task_type"] == "case_retrieval":
        return (
            bool(re.fullmatch(r"CRT-[0-9]{3}", record["task_id"]))
            and record["problem_category"] == "case_lookup"
            and len(acceptable_cases) >= 4
        )
    return (
        bool(re.fullmatch(r"PLT-[0-9]{3}", record["task_id"]))
        and record["problem_category"] in LINKAGE_CATEGORIES
        and bool(card_ids)
    )


def summarize_evaluation_tasks(
    records: list[dict[str, Any]],
    known_card_ids: set[str],
    known_case_ids: set[str],
) -> dict[str, Any]:
    """生成固定任务的结构、覆盖和人工审核状态摘要。"""
    valid = [
        item
        for item in records
        if evaluation_task_is_complete(item, known_card_ids, known_case_ids)
    ]
    return {
        "task_count": len(records),
        "valid_task_count": len(valid),
        "case_retrieval_count": sum(item.get("task_type") == "case_retrieval" for item in records),
        "problem_linkage_count": sum(item.get("task_type") == "problem_linkage" for item in records),
        "linkage_category_counts": {
            category: sum(item.get("problem_category") == category for item in records)
            for category in sorted(LINKAGE_CATEGORIES)
        },
        "approved_human_task_count": sum(
            item.get("review_status") == "approved"
            and item.get("human_review_confirmed") is True
            for item in valid
        ),
        "all_structurally_valid": len(valid) == len(records),
    }


def run_retrieval_evaluation(
    wiki_root: Path,
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    """只对人工批准的固定任务运行本地检索，不调用外部模型。"""
    from app.wiki import load_wiki_references

    unapproved = [
        item["task_id"]
        for item in records
        if item.get("review_status") != "approved"
        or item.get("human_review_confirmed") is not True
    ]
    if unapproved:
        raise ValueError("固定任务尚未全部人工批准，不能运行正式检索验收。")
    results = []
    for task in records:
        references = load_wiki_references(
            str(wiki_root),
            task["design_stage"],
            limit=20,
            query_context={
                "building_type": task["building_type"],
                "design_stage": task["design_stage"],
                "description": task["query_or_problem"],
            },
        )
        results.append(evaluate_task_result(task, references))
    case_results = [item for item in results if item["task_type"] == "case_retrieval"]
    linkage_results = [item for item in results if item["task_type"] == "problem_linkage"]
    return {
        "contains_teacher_scores": False,
        "contains_annotation_answers": False,
        "task_count": len(results),
        "case_retrieval_pass_count": sum(item["passed"] for item in case_results),
        "problem_linkage_pass_count": sum(item["passed"] for item in linkage_results),
        "all_passed": all(item["passed"] for item in results),
        "results": results,
    }


def evaluate_task_result(
    task: dict[str, Any], references: list[dict[str, Any]]
) -> dict[str, Any]:
    """按固定编号计算案例前五相关数或知识—案例联动覆盖率。"""
    governed = [
        item for item in references if str(item.get("governance_id", "")).strip()
    ]
    case_ids = [
        item["governance_id"]
        for item in governed
        if str(item["governance_id"]).startswith("PBC-")
    ]
    card_ids = [
        item["governance_id"]
        for item in governed
        if str(item["governance_id"]).startswith("KC-")
    ]
    if task["task_type"] == "case_retrieval":
        top_five = case_ids[:5]
        relevant = sum(item in set(task["acceptable_case_ids"]) for item in top_five)
        primary_hit = bool(set(task["expected_case_ids"]) & set(top_five))
        return {
            "task_id": task["task_id"],
            "task_type": task["task_type"],
            "retrieved_case_ids": top_five,
            "relevant_in_top_five": relevant,
            "primary_hit": primary_hit,
            "passed": relevant >= 4 and primary_hit,
        }
    expected_cards = set(task["expected_knowledge_card_ids"])
    expected_cases = set(task["expected_case_ids"])
    matched = len(expected_cards & set(card_ids[:10])) + len(expected_cases & set(case_ids[:5]))
    denominator = len(expected_cards) + len(expected_cases)
    rate = matched / denominator if denominator else 0.0
    return {
        "task_id": task["task_id"],
        "task_type": task["task_type"],
        "retrieved_knowledge_card_ids": card_ids[:10],
        "retrieved_case_ids": case_ids[:5],
        "linked_relevance_rate": round(rate, 4),
        "passed": rate >= 0.85,
    }


def load_evaluation_tasks(governance_root: Path) -> list[dict[str, Any]]:
    """读取两类固定任务草稿。"""
    paths = (
        governance_root / "case-retrieval-task-drafts-v1.json",
        governance_root / "problem-linkage-task-drafts-v1.json",
    )
    records = []
    for path in paths:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data.get("records"), list):
            raise ValueError(f"固定任务格式错误：{path}")
        records.extend(data["records"])
    return records


def string_set(value: Any) -> set[str]:
    """把字符串数组安全转换为集合。"""
    if not isinstance(value, list):
        return set()
    return {str(item) for item in value if str(item).strip()}
