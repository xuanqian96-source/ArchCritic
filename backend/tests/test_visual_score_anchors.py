"""验证视觉锚点校准的输入约束和最终总分回退逻辑。"""

from app.agents.scheme_review import (
    build_scheme_overall_report,
    validate_synthesis_output,
)


def make_specialist_evaluation() -> dict:
    """构造一个可参与旧加权总分的最小专项结果。"""
    return {
        "agent_type": "function_agent",
        "dimension": "功能与流线",
        "score": 80,
        "summary": "功能组织基本完整。",
        "strengths": ["主要功能可识别。"],
        "issues": [],
        "suggestions": ["继续核对交通空间。"],
        "details": {},
    }


def make_synthesis(calibration: dict) -> dict:
    """构造包含视觉校准结果的综合报告。"""
    return {
        "summary": "已完成综合评审。",
        "must_fix": [],
        "should_improve": ["继续深化。"],
        "optional_improvements": ["补充表达。"],
        "strengths": ["整体概念可识别。"],
        "score_calibration": calibration,
    }


def test_valid_visual_calibration_replaces_weighted_score() -> None:
    """有效锚点比较应替换旧加权平均，同时保留原分用于审计。"""
    report = build_scheme_overall_report(
        make_synthesis(
            {
                "valid": True,
                "architecture": "visual_anchor_v1",
                "band": "high",
                "nearest_anchor_ids": ["A-H90"],
                "comparisons": ["当前作品与 A-H90 接近。"],
                "observed_current_quality": ["整体表达完整。"],
                "calibrated_score": 91,
                "confidence": "medium",
                "score_reason": "位于高档中部。",
            }
        ),
        [make_specialist_evaluation()],
        {
            "design_stage": "图纸阶段",
            "dimension_weights": {"function_agent": 100},
            "scoring_architecture": "visual_anchor_v1",
            "visual_score_anchors": [{"anchor_id": "A-H90"}],
        },
    )

    assert report["overall_score"] == 91
    scoring = report["evaluation_context"]["scoring"]
    assert scoring["architecture"] == "visual_anchor_v1"
    assert scoring["raw_weighted_score"] == 80


def test_unknown_anchor_id_disables_visual_calibration() -> None:
    """模型引用未知锚点时必须回退旧总分，不能静默采用不可追溯分数。"""
    normalized = validate_synthesis_output(
        {
            "summary": "已完成综合评审。",
            "must_fix": [],
            "should_improve": ["继续深化。"],
            "optional_improvements": ["补充表达。"],
            "strengths": ["整体概念可识别。"],
            "score_calibration": {
                "observed_current_quality": ["整体表达完整。"],
                "band": "middle",
                "nearest_anchor_ids": ["A-UNKNOWN"],
                "comparisons": ["与未知锚点接近。"],
                "calibrated_score": 82,
                "confidence": "medium",
                "score_reason": "无法追溯。",
            },
        },
        [{"anchor_id": "A-M82"}],
    )

    assert normalized["score_calibration"]["valid"] is False
