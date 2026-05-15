"""验证功能与流线 Agent 的输出校验和报告转换。"""

from app.agents.function_agent import (
    function_agent_report_to_overall,
    validate_function_agent_output,
)
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
