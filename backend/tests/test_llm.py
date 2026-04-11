"""验证演示模型客户端可以生成结构化评图结果。"""

from app.llm.client import get_llm_client


def test_mock_llm_returns_structured_report():
    """确认演示模型能返回前端可展示的数据结构。"""
    client = get_llm_client("mock")
    report = client.generate_evaluation(
        {
            "project_name": "演示项目",
            "building_type": "教学建筑",
            "design_stage": "scheme",
            "description": "关注流线和开放空间的教学楼方案。",
        }
    )

    assert report["overall_score"] >= 0
    assert len(report["must_fix"]) > 0
    assert len(report["agent_evaluations"]) > 0
