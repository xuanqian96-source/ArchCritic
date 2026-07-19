"""验证长程 Goal 资产盘点不泄漏答案，且能识别关键缺口。"""

from __future__ import annotations

import json
from pathlib import Path

from app.benchmarking.asset_audit import (
    audit_goal_assets,
    find_input_violations,
    score_band,
)
from app.benchmarking.asset_audit_report import render_markdown_report
from app.benchmarking.asset_content_validation import (
    case_draft_has_deep_evidence,
    case_draft_record_is_complete,
    knowledge_card_record_is_complete,
    question_record_is_complete,
)


def write_json(path: Path, value: object) -> None:
    """为测试写入 UTF-8 JSON 固定数据。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def test_input_guard_detects_answers_and_score_hints() -> None:
    """确认输入守卫能找到答案字段、原始编号和分数暗示。"""
    payload = {
        "project_name": "示例（94分）",
        "teacher_score": 94,
        "description": "这是高分样本",
        "nested": {"source": "RAW-001"},
    }
    violations = find_input_violations(payload, {"RAW-001"})
    assert any(item.startswith("forbidden_key:") for item in violations)
    assert any(item.startswith("score_in_text:") for item in violations)
    assert any(item.startswith("answer_hint_in_text:") for item in violations)
    assert any(item.startswith("raw_sample_id_in_text:") for item in violations)


def test_score_bands_use_frozen_boundaries() -> None:
    """确认高中低档统计使用固定边界。"""
    assert score_band(74.99) == "low"
    assert score_band(75) == "mid"
    assert score_band(89.99) == "mid"
    assert score_band(90) == "high"
    assert score_band(None) == "unknown"


def test_audit_reports_incomplete_assets_without_exposing_scores(tmp_path: Path) -> None:
    """确认盘点会报告缺口，但不输出具体教师分。"""
    dataset_root = tmp_path / "dataset"
    prepared_root = dataset_root / ".prepared"
    input_file = prepared_root / "inputs" / "CASE-001" / "input.json"
    write_json(
        input_file,
        {
            "case_id": "CASE-001",
            "project_name": "匿名公共建筑",
            "building_type": "博物馆",
            "design_stage": "scheme",
            "description": "课程设计说明",
            "drawings": [],
        },
    )
    write_json(
        prepared_root / "index.json",
        {
            "cases": [
                {"case_id": "CASE-001", "input_file": "inputs/CASE-001/input.json"}
            ]
        },
    )
    write_json(
        prepared_root / "ground_truth.json",
        {"cases": [{"case_id": "CASE-001", "teacher_score": 93}]},
    )
    raw_case = dataset_root / "原始项目（93分）"
    (raw_case / "图纸").mkdir(parents=True)
    (raw_case / "标注.md").write_text("# 内部标注", encoding="utf-8")

    knowledge_root = tmp_path / "knowledge"
    case_root = knowledge_root / "03优秀案例笔记"
    case_root.mkdir(parents=True)
    (case_root / "待分析案例.md").write_text(
        "---\nstatus: 待分析\n---\n# 待分析案例",
        encoding="utf-8",
    )

    audit = audit_goal_assets(dataset_root, knowledge_root)
    report = render_markdown_report(audit)

    assert audit["dataset"]["band_counts"] == {
        "high": 1,
        "mid": 0,
        "low": 0,
        "unknown": 0,
    }
    assert audit["dataset"]["model_input_violation_count"] == 0
    assert audit["dataset"]["answer_isolation"] == "insufficient_same_prepared_root"
    assert audit["knowledge_base"]["eligible_case_count"] == 0
    assert audit["gates"]["all_asset_gates_passed"] is False
    assert "93" not in report
    assert "当前不具备正式最终盲测" in report


def test_empty_approved_content_is_not_counted(tmp_path: Path) -> None:
    """确认空字段、未核验许可和空白题目不能靠状态字段混入验收。"""
    dataset_root = tmp_path / "dataset"
    knowledge_root = tmp_path / "knowledge"
    case_root = knowledge_root / "03优秀案例笔记"
    case_root.mkdir(parents=True)
    required_names = (
        "case_id", "title", "architect", "location", "year", "scale",
        "building_type", "reliable_source_record_ids", "media_record_ids",
        "site_strategy", "functional_organization", "circulation",
        "spatial_sequence", "form_strategy", "structure_strategy",
        "environmental_response", "key_drawings", "transferable_lessons",
        "application_limits", "related_knowledge_cards", "similar_cases",
        "depth_evidence_categories", "review_status", "reviewer", "version",
    )
    frontmatter = "\n".join(
        f"{name}: {'approved' if name == 'review_status' else ''}" for name in required_names
    )
    (case_root / "空白案例.md").write_text(
        f"---\n{frontmatter}\n---\n# 空白案例", encoding="utf-8"
    )
    maintenance = knowledge_root / "99维护记录" / "长程Goal治理"
    write_json(
        maintenance / "source-records.json",
        {
            "records": [
                {
                    "source_id": "SRC-EMPTY",
                    "source_title": "空白来源",
                    "source_author_or_organization": "测试机构",
                    "source_url_or_file": "https://example.invalid",
                    "publication_or_project_date": "2026",
                    "accessed_at": "2026-07-19T00:00:00+08:00",
                    "source_type": "official_project_page",
                    "license_or_permission": "unverified",
                    "allowed_use": "internal_only",
                    "original_file_hash_or_snapshot_hash": "hash",
                    "review_status": "approved",
                    "reviewer": "测试者",
                }
            ]
        },
    )
    write_json(
        maintenance / "question-worklist.json",
        {
            "records": [
                {
                    "question_id": "Q-1",
                    "level": "beginner",
                    "question_type": "unanswerable",
                    "question": "",
                    "expected_source_record_ids": [],
                    "review_status": "approved",
                    "reviewer": "测试者",
                }
            ]
        },
    )

    audit = audit_goal_assets(dataset_root, knowledge_root)

    assert audit["knowledge_base"]["approved_source_record_count"] == 0
    assert audit["knowledge_base"]["eligible_case_count"] == 0
    assert audit["knowledge_base"]["fixed_question_count"] == 0


def test_structured_knowledge_draft_requires_real_content_and_source() -> None:
    """确认结构化知识卡草稿必须有完整内容并绑定已核验来源。"""
    record = {
        "card_id": "KC-BEG-001",
        "title": "场地分析进入设计决定",
        "level": "beginner",
        "learning_objective": "把场地事实转化为设计动作",
        "prerequisites": ["场地分析"],
        "building_types": ["公共建筑"],
        "stages": ["concept"],
        "dimensions": ["场地"],
        "student_explanation": "每条场地信息都应对应一个设计决定。",
        "key_terms": ["语境"],
        "related_cards": ["KC-BEG-002"],
        "related_cases": ["PBC-001"],
        "self_test": [{"question": "场地信息如何进入设计？", "expected_points": ["对应动作"]}],
        "source_type": "government_guidance",
        "source_record_ids": ["SRC-CORE-001"],
        "source_locators": [{"source_id": "SRC-CORE-001", "locator": "paragraph 39"}],
        "copyright_status": "OGL v3.0",
        "allowed_use": "public_allowed",
        "organizer": "测试整理人",
        "review_status": "pending",
        "reviewer": "待复核",
        "version": "0.1",
    }
    assert knowledge_card_record_is_complete(record, {"SRC-CORE-001"}) is True
    record["student_explanation"] = ""
    assert knowledge_card_record_is_complete(record, {"SRC-CORE-001"}) is False


def test_question_draft_separates_evidence_and_unanswerable_sources() -> None:
    """确认有依据题必须绑定来源，无依据题必须保持来源为空。"""
    record = {
        "question_id": "Q-BEG-01",
        "level": "beginner",
        "question_type": "evidence_based",
        "question": "场地分析如何进入设计？",
        "expected_answer_points": ["转化为具体设计动作"],
        "expected_source_record_ids": ["SRC-CORE-001"],
        "expected_source_locators": ["Context paragraphs 39-45"],
        "forbidden_behaviors": ["编造规范条文"],
        "review_status": "pending",
        "reviewer": "待复核",
        "version": "0.1",
    }
    assert question_record_is_complete(record, {"SRC-CORE-001"}) is True
    record["question_type"] = "unanswerable"
    assert question_record_is_complete(record, {"SRC-CORE-001"}) is False
    record["expected_source_record_ids"] = []
    record["expected_source_locators"] = []
    assert question_record_is_complete(record, {"SRC-CORE-001"}) is True


def test_case_draft_requires_traceable_multidimensional_evidence() -> None:
    """确认案例草稿至少覆盖三个维度，且每条证据都来自已审核来源。"""
    record = {
        "case_id": "PBC-001",
        "title": "示例博物馆",
        "architect": "示例建筑师",
        "location": "示例地点",
        "year": "2020",
        "scale": "10000㎡",
        "building_type": "博物馆",
        "reliable_source_record_ids": ["SRC-PBC-001"],
        "media_record_ids": ["MEDIA-001"],
        "site_strategy": "回应场地路径",
        "functional_organization": "围绕公共厅组织",
        "circulation": "主路径串联展厅",
        "spatial_sequence": "由入口进入核心空间",
        "form_strategy": "体量回应环境",
        "structure_strategy": "结构结论待图纸复核",
        "environmental_response": "以自然光组织展览空间",
        "key_drawings": ["总平面", "平面", "剖面"],
        "transferable_lessons": ["先解释场地", "再组织流线", "用剖面核对空间"],
        "application_limits": "只作设计方法参考",
        "related_knowledge_cards": ["KC-BEG-002"],
        "similar_cases": ["PBC-002"],
        "depth_evidence_categories": ["site", "function_and_circulation", "space_and_form"],
        "evidence_register": [
            {"category": "basic_fact", "source_id": "SRC-PBC-001", "locator": "Project details", "supports": "基本信息", "evidence_type": "official_fact"},
            {"category": "site", "source_id": "SRC-PBC-001", "locator": "Site paragraph", "supports": "场地策略", "evidence_type": "official_fact"},
            {"category": "function_and_circulation", "source_id": "SRC-PBC-001", "locator": "Program paragraph", "supports": "功能组织", "evidence_type": "disciplinary_inference"},
            {"category": "space_and_form", "source_id": "SRC-PBC-001", "locator": "Form paragraph", "supports": "空间形式", "evidence_type": "official_fact"},
        ],
        "media_permission_status": "not_cleared",
        "draft_scope": "仅供内部学科复核",
        "review_status": "pending",
        "reviewer": "学科专家待复核",
        "version": "0.1",
    }
    assert case_draft_record_is_complete(record, {"SRC-PBC-001"}) is True
    assert case_draft_has_deep_evidence(record) is True
    record["depth_evidence_categories"] = ["site", "space_and_form"]
    assert case_draft_record_is_complete(record, {"SRC-PBC-001"}) is True
    assert case_draft_has_deep_evidence(record) is False
    record["evidence_register"][1]["source_id"] = "SRC-UNKNOWN"
    assert case_draft_record_is_complete(record, {"SRC-PBC-001"}) is False


def test_structured_content_needs_human_confirmation_for_formal_count(tmp_path: Path) -> None:
    """确认只改 approved 状态仍不能把 AI 草稿计为正式内容。"""
    dataset_root = tmp_path / "dataset"
    knowledge_root = tmp_path / "knowledge"
    maintenance = knowledge_root / "99维护记录" / "长程Goal治理"
    source = {
        "source_id": "SRC-CORE-001",
        "source_title": "测试来源",
        "source_author_or_organization": "测试机构",
        "source_url_or_file": "https://example.com/source",
        "publication_or_project_date": "2026",
        "accessed_at": "2026-07-19T00:00:00+08:00",
        "source_type": "government_guidance",
        "license_or_permission": "允许在内部研究中引用",
        "allowed_use": "internal_only",
        "original_file_hash_or_snapshot_hash": "hash",
        "review_status": "approved",
        "reviewer": "来源核验人",
    }
    card = {
        "card_id": "KC-BEG-001", "title": "测试知识卡", "level": "beginner",
        "learning_objective": "建立证据意识", "prerequisites": ["基础阅读"],
        "building_types": ["公共建筑"], "stages": ["scheme"],
        "dimensions": ["功能"], "student_explanation": "结论应有来源。",
        "key_terms": ["证据"], "related_cards": ["KC-BEG-002"],
        "related_cases": ["PBC-001"],
        "self_test": [{"question": "为何要证据？", "expected_points": ["可复核"]}],
        "source_type": "government_guidance", "source_record_ids": ["SRC-CORE-001"],
        "source_locators": [{"source_id": "SRC-CORE-001", "locator": "p.1"}],
        "copyright_status": "内部引用", "allowed_use": "internal_only",
        "organizer": "整理人", "review_status": "approved", "reviewer": "张老师",
        "version": "1.0", "human_review_confirmed": False,
    }
    write_json(maintenance / "source-records.json", {"records": [source]})
    write_json(maintenance / "knowledge-card-drafts-beginner.json", {"records": [card]})

    before = audit_goal_assets(dataset_root, knowledge_root)
    card["human_review_confirmed"] = True
    write_json(maintenance / "knowledge-card-drafts-beginner.json", {"records": [card]})
    after = audit_goal_assets(dataset_root, knowledge_root)

    assert before["knowledge_base"]["eligible_knowledge_card_count"] == 0
    assert after["knowledge_base"]["eligible_knowledge_card_count"] == 1
