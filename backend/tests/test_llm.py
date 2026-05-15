"""验证演示模型客户端可以生成结构化评图结果。"""

from app.config import get_settings
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


def test_dashscope_provider_requires_api_key(monkeypatch):
    """确认百炼模型未配置 Key 时会给出明确提示。"""
    monkeypatch.setenv("DASHSCOPE_API_KEY", "")
    monkeypatch.setenv("LLM_PROVIDER", "dashscope")
    get_settings.cache_clear()

    try:
        get_llm_client("dashscope")
    except ValueError as exc:
        assert "百炼 API Key" in str(exc)
    else:
        raise AssertionError("未配置百炼 Key 时不应创建模型客户端。")
    finally:
        get_settings.cache_clear()
