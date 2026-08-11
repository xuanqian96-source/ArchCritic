"""验证共享图纸事实清单只保留真实图纸与可追溯事实。"""

from app.agents.evidence_inventory import normalize_evidence_inventory


def test_inventory_reassigns_fact_ids_and_rejects_fake_drawings() -> None:
    """确认模型不能引用本次未发送的图纸编号。"""
    drawings = [
        {
            "drawing_id": "D1",
            "drawing_type": "plan",
            "original_name": "首层平面.png",
            "description": "",
        },
        {
            "drawing_id": "D2",
            "drawing_type": "section",
            "original_name": "剖面.png",
            "description": "",
        },
    ]
    inventory = normalize_evidence_inventory(
        {
            "drawing_coverage": [
                {"drawing_id": "D1", "readable": True, "note": "可读"},
                {"drawing_id": "D99", "readable": True, "note": "虚构"},
            ],
            "facts": [
                {
                    "dimension": "circulation",
                    "statement": "平面可见一处楼梯。",
                    "source_drawing_ids": ["D1", "D99"],
                    "confidence": "high",
                    "observation_type": "visible",
                },
                {
                    "dimension": "form",
                    "statement": "只引用虚构图纸。",
                    "source_drawing_ids": ["D99"],
                    "confidence": "high",
                    "observation_type": "visible",
                },
            ],
            "contradictions": [],
            "missing_information": [],
        },
        drawings,
    )

    assert [item["drawing_id"] for item in inventory["drawing_coverage"]] == ["D1", "D2"]
    assert inventory["drawing_coverage"][1]["readable"] is None
    assert inventory["facts"] == [
        {
            "fact_id": "E1",
            "dimension": "circulation",
            "statement": "平面可见一处楼梯。",
            "source_drawing_ids": ["D1"],
            "confidence": "high",
            "observation_type": "visible",
        }
    ]
