"""验证独立任务书核对层不接受伪造规则或图纸事实编号。"""

from app.agents.taskbook_compliance import normalize_compliance_output
from app.services.taskbook_rules import build_structured_requirements, scorable_requirements


def test_compliance_layer_keeps_only_real_rules_and_evidence() -> None:
    """确认缺少证据的肯定结论会降为不确定。"""
    requirements = scorable_requirements(
        build_structured_requirements(
            [
                "主要功能必须包含展示和服务空间。",
                "结构形式应采用框架结构。",
            ]
        )
    )
    inventory = {
        "facts": [
            {
                "fact_id": "E1",
                "statement": "平面图可见展示和服务空间。",
                "source_drawing_ids": ["D1"],
            }
        ]
    }
    result = normalize_compliance_output(
        {
            "checks": [
                {
                    "requirement_id": requirements[0]["id"],
                    "status": "met",
                    "evidence_fact_ids": ["E1"],
                    "evidence": "E1 可复核。",
                    "confidence": "high",
                },
                {
                    "requirement_id": requirements[1]["id"],
                    "status": "not_met",
                    "evidence_fact_ids": ["E99"],
                    "evidence": "无直接证据。",
                    "confidence": "medium",
                },
                {
                    "requirement_id": "R-999",
                    "status": "met",
                    "evidence_fact_ids": ["E1"],
                    "evidence": "伪造规则。",
                    "confidence": "high",
                },
            ]
        },
        requirements,
        inventory,
    )

    assert result["checks"][0]["status"] == "met"
    assert result["checks"][1]["status"] == "uncertain"
    assert result["invalid_requirement_ids"] == ["R-999"]
    assert result["invalid_evidence_fact_ids"] == ["E99"]
