"""验证只有人工批准且许可合格的结构化内容能进入 Wiki 检索。"""

from __future__ import annotations

import json
from pathlib import Path

from app.governed_wiki import collect_governed_references


def write_records(path: Path, records: list[dict]) -> None:
    """写入测试用 records JSON。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"version": 1, "records": records}, ensure_ascii=False),
        encoding="utf-8",
    )


def approved_source() -> dict:
    """生成满足来源审计的第一方记录。"""
    return {
        "source_id": "SRC-PBC-001",
        "source_title": "官方项目页",
        "source_author_or_organization": "测试机构",
        "source_url_or_file": "https://example.com/project",
        "publication_or_project_date": "2020",
        "accessed_at": "2026-07-19T00:00:00+08:00",
        "source_type": "official_project_page",
        "license_or_permission": "可在内部研究中引用项目事实并保留链接",
        "allowed_use": "internal_only",
        "attribution_text": "Source: Test",
        "original_file_hash_or_snapshot_hash": "source-hash",
        "review_status": "approved",
        "reviewer": "来源核验人",
    }


def approved_media() -> dict:
    """生成满足逐图许可审计的媒体记录。"""
    return {
        "media_id": "MEDIA-001",
        "relative_path": "00原始资料/优秀案例/测试案例/photo.jpg",
        "sha256": "media-hash",
        "source_record_id": "SRC-PBC-001",
        "creator_or_rights_holder": "摄影师",
        "license_or_permission": "CC BY 4.0；允许署名后使用",
        "allowed_use": "public_allowed",
        "attribution_text": "摄影师 — CC BY 4.0",
        "review_status": "approved",
        "reviewer": "许可核验人",
    }


def approved_knowledge_card() -> dict:
    """生成完整且人工批准的结构化知识卡。"""
    return {
        "card_id": "KC-BEG-001",
        "title": "场地事实进入设计决定",
        "level": "beginner",
        "learning_objective": "把场地事实转化为设计动作",
        "prerequisites": ["基本场地分析"],
        "building_types": ["公共建筑"],
        "stages": ["scheme"],
        "dimensions": ["场地与回应"],
        "student_explanation": "每条场地信息都应对应一个可解释的设计决定。",
        "key_terms": ["场地", "设计决定"],
        "related_cards": ["KC-BEG-002"],
        "related_cases": ["PBC-001"],
        "self_test": [{"question": "如何转化？", "expected_points": ["对应动作"]}],
        "source_type": "official_project_page",
        "source_record_ids": ["SRC-PBC-001"],
        "source_locators": [{"source_id": "SRC-PBC-001", "locator": "Site paragraph"}],
        "copyright_status": "内部引用项目事实",
        "allowed_use": "internal_only",
        "organizer": "内容整理人",
        "review_status": "approved",
        "reviewer": "张老师",
        "version": "1.0",
        "reviewed_at": "2026-07-20T10:00:00+08:00",
        "review_decision": "approve",
        "human_review_confirmed": True,
    }


def approved_case() -> dict:
    """生成完整、图片许可已清理且人工批准的结构化案例。"""
    return {
        "case_id": "PBC-001",
        "title": "示例公共建筑",
        "architect": "示例建筑师",
        "location": "示例地点",
        "year": "2020",
        "scale": "10000㎡",
        "building_type": "公共文化建筑",
        "reliable_source_record_ids": ["SRC-PBC-001"],
        "media_record_ids": ["MEDIA-001"],
        "site_strategy": "回应主要到达方向。",
        "functional_organization": "围绕公共大厅组织功能。",
        "circulation": "主路径串联主要空间。",
        "spatial_sequence": "由入口进入公共核心。",
        "form_strategy": "体量回应场地边界。",
        "structure_strategy": "结构结论以官方资料为边界。",
        "environmental_response": "利用自然光改善公共空间。",
        "key_drawings": ["总平面", "平面", "剖面"],
        "transferable_lessons": ["先解释场地", "再组织流线", "用剖面核查空间"],
        "application_limits": "只作公共建筑设计方法参考。",
        "related_knowledge_cards": ["KC-BEG-001"],
        "similar_cases": ["PBC-002"],
        "depth_evidence_categories": ["site", "function_and_circulation", "space_and_form"],
        "evidence_register": [
            {"category": "basic_fact", "source_id": "SRC-PBC-001", "locator": "Facts", "supports": "基本信息", "evidence_type": "official_fact"},
            {"category": "site", "source_id": "SRC-PBC-001", "locator": "Site", "supports": "场地", "evidence_type": "official_fact"},
            {"category": "function_and_circulation", "source_id": "SRC-PBC-001", "locator": "Program", "supports": "功能", "evidence_type": "official_fact"},
            {"category": "space_and_form", "source_id": "SRC-PBC-001", "locator": "Form", "supports": "空间", "evidence_type": "official_fact"},
        ],
        "media_permission_status": "cleared",
        "draft_scope": "经人工复核后用于内部检索",
        "review_status": "approved",
        "reviewer": "张老师",
        "version": "1.0",
        "reviewed_at": "2026-07-20T10:00:00+08:00",
        "review_decision": "approve",
        "human_review_confirmed": True,
    }


def test_governed_references_require_human_approval_and_media_permission(tmp_path):
    """确认只有人工批准内容进入检索，案例图片同时保留署名。"""
    governance = tmp_path / "99维护记录" / "长程Goal治理"
    card = approved_knowledge_card()
    pending_card = {**card, "card_id": "KC-BEG-002", "title": "AI 草稿"}
    pending_card["human_review_confirmed"] = False
    write_records(governance / "source-records.json", [approved_source()])
    write_records(governance / "media-manifest.json", [approved_media()])
    write_records(governance / "knowledge-card-drafts-beginner.json", [card, pending_card])
    write_records(governance / "public-building-case-drafts-v1.json", [approved_case()])

    references = collect_governed_references(tmp_path, "方案阶段")

    assert [item["governance_id"] for item in references] == ["KC-BEG-001", "PBC-001"]
    assert references[1]["image_urls"][0]["attribution"] == "摄影师 — CC BY 4.0"
    assert all(item["title"] != "AI 草稿" for item in references)
