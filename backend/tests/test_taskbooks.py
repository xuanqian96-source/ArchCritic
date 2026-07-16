"""验证任务书正文提取、阶段 Agent 和动态评分权重。"""

from types import SimpleNamespace

from app.agents.scheme_review import build_scheme_overall_report, resolve_enabled_agent_order
from app.services.taskbooks import build_task_book_profile, extract_task_book_text


def build_submission(stage: str, grade: str, agents: list[str]):
    """构造任务书评分需要的最小提交对象。"""
    return SimpleNamespace(
        design_stage=stage,
        enabled_agents=agents,
        project=SimpleNamespace(grade=grade, building_type="教学建筑"),
    )


def build_attachment(text: str):
    """构造已成功提取正文的任务书附件。"""
    return SimpleNamespace(
        original_name="课程任务书.txt",
        extracted_text=text,
        extraction_status="ready",
    )


def test_task_book_text_and_requirements_change_scheme_weights():
    """确认低年级且结构不作要求时，结构占比会真实降低。"""
    text = "课程设计要求：重点完成设计概念、功能分区和公共空间体验。\n结构部分不作要求，也不计入课程评分。"
    extracted = extract_task_book_text(text.encode("utf-8"), ".txt")
    submission = build_submission(
        "方案阶段",
        "大二建筑学",
        ["function_agent", "site_agent", "form_agent", "structure_agent", "review_agent"],
    )
    profile = build_task_book_profile(submission, [build_attachment(extracted)])

    assert profile["has_task_book"] is True
    assert profile["requirements"]
    assert profile["dimension_weights"]["structure_agent"] < 10
    assert sum(profile["dimension_weights"].values()) == 100
    assert any("降低结构" in reason for reason in profile["weight_reasons"])


def test_concept_and_drawing_stages_only_run_matching_agents():
    """确认后端阶段白名单与前端展示的概念、图纸 Agent 一致。"""
    concept = resolve_enabled_agent_order({
        "design_stage": "概念阶段",
        "enabled_agents": ["concept_agent", "drawing_agent", "site_agent", "review_agent"],
    })
    drawing = resolve_enabled_agent_order({
        "design_stage": "图纸阶段",
        "enabled_agents": ["drawing_agent", "concept_agent", "function_agent", "review_agent"],
    })

    assert concept == ["site_agent", "concept_agent", "review_agent"]
    assert drawing == ["drawing_agent", "function_agent", "review_agent"]


def test_report_total_uses_task_book_weights_and_keeps_snapshot():
    """确认报告总分按任务书权重计算，并保存本次评分依据。"""
    evaluations = [
        {"agent_type": "function_agent", "dimension": "功能与流线", "score": 90, "summary": "功能清楚", "strengths": [], "issues": [], "suggestions": []},
        {"agent_type": "structure_agent", "dimension": "结构与构造", "score": 50, "summary": "结构待深化", "strengths": [], "issues": [], "suggestions": []},
    ]
    synthesis = {
        "summary": "已按任务书完成评审。",
        "must_fix": [],
        "should_improve": ["继续深化。"],
        "optional_improvements": [],
        "strengths": ["概念明确。"],
    }
    context = {
        "design_stage": "方案阶段",
        "enabled_agents": ["function_agent", "structure_agent"],
        "dimension_weights": {"function_agent": 90, "structure_agent": 10},
        "task_book_profile": {
            "has_task_book": True,
            "source_files": ["课程任务书.txt"],
            "summary": "重点考查功能，结构不作要求。",
            "requirements": ["重点考查功能。"],
            "dimension_weights": {"function_agent": 90, "structure_agent": 10},
            "weight_reasons": ["降低结构占比。"],
        },
    }
    report = build_scheme_overall_report(synthesis, evaluations, context)

    assert report["overall_score"] == 86
    assert report["evaluation_context"]["task_book"]["source_files"] == ["课程任务书.txt"]
    assert report["evaluation_context"]["dimension_weights"]["function_agent"] == 90
