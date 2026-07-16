"""验证功能与流线 Agent 的输出校验和报告转换。"""

from types import SimpleNamespace

from app.agents.function_agent import (
    build_function_agent_context,
    build_image_inputs,
    function_agent_report_to_overall,
    validate_function_agent_output,
)
from app.agents.prompts.function_agent_v1 import build_function_agent_user_prompt
from app.agents.prompts.scheme_agents_v1 import SCHEME_SPECIALIST_SPECS, build_specialist_user_prompt
from app.routers.submissions import build_model_error_message


def test_validate_function_agent_output_clamps_scores():
    """确认模型分数会被限制在四项合法范围内。"""
    report = validate_function_agent_output(
        {
            "summary": "方案具备基础功能，但流线和分区仍需优化。",
            "confidence": "medium",
            "sub_scores": {
                "功能满足": {"score": 35, "reason": "基础功能较完整", "evidence": "说明文字"},
                "功能分区": {"score": 20, "reason": "分区基本清楚", "evidence": "图纸观察"},
                "流线分析": {"score": -3, "reason": "主流线不清", "evidence": "图纸观察"},
                "平面丰富性": {"score": 15, "reason": "有一定变化", "evidence": "平面关系"},
            },
            "must_fix": ["补充服务流线。"],
            "should_improve": ["明确入口层级。"],
            "optional_improvements": ["增加分析图。"],
            "strengths": ["公共空间有组织意图。"],
            "missing_information": [],
            "uncertain_observations": ["图纸小字不可读。"],
        }
    )

    assert report["sub_scores"]["功能满足"]["score"] == 30
    assert report["sub_scores"]["流线分析"]["score"] == 0
    assert report["overall_score"] == 65
    assert report["grade"] == "C"


def test_function_agent_report_to_overall_contains_dimensions():
    """确认功能 Agent 结果能转换成前端报告结构。"""
    report = validate_function_agent_output(
        {
            "summary": "功能与流线评价完成。",
            "confidence": "medium",
            "sub_scores": {
                "功能满足": {"score": 24, "reason": "基础功能基本完整", "evidence": "说明文字"},
                "功能分区": {"score": 20, "reason": "分区较清楚", "evidence": "图纸观察"},
                "流线分析": {"score": 18, "reason": "主流线基本成立", "evidence": "图纸观察"},
                "平面丰富性": {"score": 14, "reason": "有空间变化", "evidence": "平面组织"},
            },
            "must_fix": ["后勤流线需要补充。"],
            "should_improve": ["公共空间节点可以更明确。"],
            "optional_improvements": ["补充任务书核对表。"],
            "strengths": ["功能框架较完整。"],
            "missing_information": [],
            "uncertain_observations": [],
        }
    )
    overall = function_agent_report_to_overall(report)

    dimensions = [item["dimension"] for item in overall["agent_evaluations"]]
    assert overall["overall_score"] == 76
    assert "功能与流线" in dimensions
    assert "功能满足" in dimensions
    assert "平面丰富性" in dimensions
    assert "流线分析" in overall["agent_evaluations"][0]["details"]["sub_scores"]


def test_build_image_inputs_keeps_all_usable_drawings_in_priority_order():
    """确认模型输入不再只取第一张图，并优先发送平面图。"""
    image_inputs = build_image_inputs(
        [
            {
                "drawing_type": "render",
                "model_file_url": "oss://render.png",
                "file_url": "/uploads/render.png",
                "mime_type": "image/png",
                "usable_for_model": True,
            },
            {
                "drawing_type": "plan",
                "model_file_url": "oss://plan.png",
                "file_url": "/uploads/plan.png",
                "mime_type": "image/png",
                "usable_for_model": True,
            },
            {
                "drawing_type": "site",
                "model_file_url": "oss://site.png",
                "file_url": "/uploads/site.png",
                "mime_type": "image/png",
                "usable_for_model": True,
            },
        ]
    )

    urls = [item["image_url"]["url"] for item in image_inputs]
    assert urls == ["oss://plan.png", "oss://site.png", "oss://render.png"]


def test_drawing_description_is_included_in_model_prompts():
    """确认单张图纸说明会进入功能 Agent 和方案阶段专项 Agent 提示词。"""
    submission = SimpleNamespace(
        project=SimpleNamespace(
            name="社区活动中心",
            building_type="社区活动中心",
            owner_name="测试用户",
            grade="大三",
        ),
        design_stage="方案阶段",
        description="项目总说明",
    )
    drawing = SimpleNamespace(
        drawing_type="section",
        original_name="剖面图.png",
        file_url="/uploads/not-exists.png",
        model_file_url="oss://section.png",
        mime_type="image/png",
        description="剖面重点说明架空层与报告厅的竖向关系。",
    )
    context = build_function_agent_context(submission, [drawing], [])

    function_prompt = build_function_agent_user_prompt(context)
    scheme_prompt = build_specialist_user_prompt(context, SCHEME_SPECIALIST_SPECS["structure_agent"])

    assert "图纸说明：剖面重点说明架空层与报告厅的竖向关系。" in function_prompt
    assert "图纸说明：剖面重点说明架空层与报告厅的竖向关系。" in scheme_prompt


def test_observed_facts_demote_uncertain_must_fix():
    """确认不确定观察不会被保留为必须修改。"""
    report = validate_function_agent_output(
        {
            "summary": "功能与流线评价完成。",
            "confidence": "medium",
            "observed_facts": {"楼梯": "不确定，图纸局部较模糊。"},
            "sub_scores": {
                "功能满足": {"score": 20, "reason": "基础功能基本完整", "evidence": "图纸观察"},
                "功能分区": {"score": 20, "reason": "分区较清楚", "evidence": "图纸观察"},
                "流线分析": {"score": 18, "reason": "主流线基本成立", "evidence": "图纸观察"},
                "平面丰富性": {"score": 14, "reason": "有空间变化", "evidence": "平面组织"},
            },
            "must_fix": ["缺少楼梯，需要补充垂直交通。"],
            "should_improve": ["公共空间节点可以更明确。"],
            "optional_improvements": ["补充任务书核对表。"],
            "strengths": ["功能框架较完整。"],
            "missing_information": [],
            "uncertain_observations": [],
        }
    )
    overall = function_agent_report_to_overall(report, {"description": ""})

    assert overall["must_fix"] == []
    assert "楼梯与设计说明存在冲突" in overall["agent_evaluations"][0]["issues"][0]


def test_build_model_error_message_for_quota():
    """确认额度不足会返回清楚的中文提示。"""
    message = build_model_error_message(Exception("insufficient_quota"))

    assert "额度不足" in message


def test_validate_function_agent_output_accepts_dashscope_shape():
    """确认百炼返回的近似结构也能转成标准报告。"""
    report = validate_function_agent_output(
        {
            "scores": {
                "功能满足": 20,
                "功能分区": 18,
                "流线分析": 15,
                "平面丰富性": 16,
            },
            "comments": {
                "功能满足": "基础功能基本出现，但卫生间等配套无法确认。",
                "功能分区": "分区有逻辑，但后勤靠近安静功能。",
                "流线分析": "服务入口和后勤流线不够明确。",
                "平面丰富性": "平面具有一定几何变化。",
            },
            "missing_information": ["缺少详细平面图。"],
            "uncertain_observations": ["无法确认内部流线。"],
        }
    )

    assert report["overall_score"] == 69
    assert report["grade"] == "C"
    assert report["sub_scores"]["流线分析"]["score"] == 15
    assert "流线分析" in report["must_fix"][0]
