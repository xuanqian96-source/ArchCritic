"""验证知识库治理清单的数量、授权默认和不覆盖策略。"""

from __future__ import annotations

import json
from pathlib import Path

from app.benchmarking.knowledge_governance import initialize_knowledge_governance


def test_initialization_creates_fixed_worklists_without_claiming_permission(
    tmp_path: Path,
) -> None:
    """确认槽位数量满足规划，但未核验资料不会被标为可用。"""
    knowledge_root = tmp_path / "knowledge"
    media_root = knowledge_root / "00原始资料" / "优秀案例" / "示例博物馆"
    media_root.mkdir(parents=True)
    (media_root / "平面图.jpg").write_bytes(b"example-image")
    notes_root = knowledge_root / "03优秀案例笔记"
    notes_root.mkdir(parents=True)
    (notes_root / "示例博物馆.md").write_text("# 示例博物馆\n", encoding="utf-8")

    result = initialize_knowledge_governance(knowledge_root)

    assert result["source_slots"] == 3
    assert result["media_records"] == 1
    assert result["case_slots"] == 1
    assert result["knowledge_card_slots"] == 60
    assert result["question_slots"] == 30
    media_manifest = json.loads(
        (
            knowledge_root
            / "99维护记录"
            / "长程Goal治理"
            / "media-manifest.json"
        ).read_text(encoding="utf-8")
    )
    assert media_manifest["records"][0]["license_or_permission"] == "unverified"
    assert media_manifest["records"][0]["allowed_use"] == "not_cleared"
    assert len({item["media_id"] for item in media_manifest["records"]}) == 1


def test_initialization_preserves_existing_human_records(tmp_path: Path) -> None:
    """确认重复执行不会覆盖人工填写的授权记录。"""
    knowledge_root = tmp_path / "knowledge"
    governance_root = knowledge_root / "99维护记录" / "长程Goal治理"
    governance_root.mkdir(parents=True)
    source_file = governance_root / "source-records.json"
    source_file.write_text('{"records":[{"source_id":"HUMAN"}]}', encoding="utf-8")

    result = initialize_knowledge_governance(knowledge_root)

    assert result["preserved_existing_files"] == 1
    assert json.loads(source_file.read_text(encoding="utf-8"))["records"][0]["source_id"] == "HUMAN"
