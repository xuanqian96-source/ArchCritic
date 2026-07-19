"""验证内容复核包不会让 AI 草稿绕过人工审核。"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from app.benchmarking.content_review import (
    apply_review_bundle,
    export_review_bundle,
    validate_review_bundle,
)


def write_json(path: Path, records: list[dict]) -> None:
    """写入测试用治理 JSON。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"version": 1, "records": records}, ensure_ascii=False),
        encoding="utf-8",
    )


def build_review_fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    """建立包含知识卡、问答和案例各一条的最小复核工作区。"""
    knowledge_root = tmp_path / "知识库"
    governance_root = knowledge_root / "99维护记录" / "长程Goal治理"
    bundle_root = tmp_path / "复核包"
    write_json(
        governance_root / "knowledge-card-drafts-beginner.json",
        [
            {
                "card_id": "KC-BEG-001",
                "title": "入口组织",
                "level": "beginner",
                "source_record_ids": ["SRC-001"],
                "source_locators": [{"source_id": "SRC-001", "locator": "p.1"}],
                "review_status": "pending",
                "reviewer": "建筑学学科专家待复核",
            }
        ],
    )
    write_json(
        governance_root / "question-drafts-v1.json",
        [
            {
                "question_id": "Q-1-01",
                "question": "入口如何回应到达方向？",
                "level": "beginner",
                "question_type": "evidence_based",
                "expected_source_record_ids": ["SRC-001"],
                "expected_source_locators": ["p.1"],
                "review_status": "pending",
                "reviewer": "建筑学学科专家待复核",
            }
        ],
    )
    write_json(
        governance_root / "public-building-case-drafts-v1.json",
        [
            {
                "case_id": "PBC-001",
                "title": "测试案例",
                "reliable_source_record_ids": ["SRC-001"],
                "depth_evidence_categories": ["site", "space_and_form"],
                "evidence_register": [{"category": "site"}],
                "media_permission_status": "cleared",
                "review_status": "pending",
                "reviewer": "建筑学学科专家待复核",
            }
        ],
    )
    for filename, task_id, task_type in (
        ("case-retrieval-task-drafts-v1.json", "CRT-001", "case_retrieval"),
        ("problem-linkage-task-drafts-v1.json", "PLT-001", "problem_linkage"),
    ):
        write_json(
            governance_root / filename,
            [
                {
                    "task_id": task_id,
                    "task_type": task_type,
                    "problem_category": "case_lookup" if task_type == "case_retrieval" else "site",
                    "query_or_problem": "测试固定任务",
                    "expected_knowledge_card_ids": ["KC-BEG-001"],
                    "expected_case_ids": ["PBC-001"],
                    "required_reason_points": ["理由一", "理由二"],
                    "review_status": "pending",
                    "reviewer": "建筑学学科专家待复核",
                }
            ],
        )
    return knowledge_root, governance_root, bundle_root


def fill_all_sheets(bundle_root: Path) -> None:
    """模拟真实人工填写导出的三张复核表。"""
    for path in bundle_root.glob("*复核表.csv"):
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            fieldnames = reader.fieldnames
            rows = [dict(row) for row in reader]
        for row in rows:
            row["decision"] = "approve"
            row["reviewer"] = "张老师"
            row["reviewed_at"] = "2026-07-20T10:00:00+08:00"
            row["human_review_confirmed"] = "true"
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)


def test_review_bundle_requires_complete_human_decisions(tmp_path):
    """确认空复核表不能回写，完整人工决定可留存复核凭据。"""
    knowledge_root, governance_root, bundle_root = build_review_fixture(tmp_path)
    result = export_review_bundle(knowledge_root, bundle_root)

    assert result["record_count"] == 5
    assert validate_review_bundle(knowledge_root, bundle_root)["valid"] is False
    with pytest.raises(ValueError, match="人工复核"):
        apply_review_bundle(
            knowledge_root,
            bundle_root,
            confirm_human_reviewed=False,
        )

    fill_all_sheets(bundle_root)
    assert validate_review_bundle(knowledge_root, bundle_root)["valid"] is True
    receipt = apply_review_bundle(
        knowledge_root,
        bundle_root,
        confirm_human_reviewed=True,
    )

    assert receipt["approved_count"] == 5
    assert (bundle_root / "复核回写凭据.json").is_file()
    for path in governance_root.glob("*draft*.json"):
        record = json.loads(path.read_text(encoding="utf-8"))["records"][0]
        assert record["review_status"] == "approved"
        assert record["reviewer"] == "张老师"
        assert record["human_review_confirmed"] is True


def test_review_bundle_rejects_changed_draft_snapshot(tmp_path):
    """确认导出后被修改的草稿必须重新生成复核包。"""
    knowledge_root, governance_root, bundle_root = build_review_fixture(tmp_path)
    export_review_bundle(knowledge_root, bundle_root)
    path = governance_root / "question-drafts-v1.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["records"][0]["question"] = "内容已改变"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    fill_all_sheets(bundle_root)

    result = validate_review_bundle(knowledge_root, bundle_root)

    assert result["valid"] is False
    assert any("必须重新导出" in message for message in result["errors"])
