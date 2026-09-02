"""验证演示模式和百炼双模型配置。"""

from app.config import get_settings
from app.llm.client import get_llm_client
from app.routers.submission_common import resolve_llm_model


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


def test_qwen_review_and_assistant_models_are_separated(monkeypatch):
    """确认评图与两类助手使用各自固定的千问模型。"""
    monkeypatch.setenv("LLM_PROVIDER", "dashscope")
    monkeypatch.setenv("LLM_MODEL", "qwen3.8-max")
    monkeypatch.setenv("LLM_ASSISTANT_MODEL", "qwen3.7-plus")
    get_settings.cache_clear()

    try:
        settings = get_settings()
        assert settings.llm_model == "qwen3.8-max"
        assert settings.llm_assistant_model == "qwen3.7-plus"
        assert resolve_llm_model("dashscope", "qwen3.6-plus") == "qwen3.8-max"
    finally:
        get_settings.cache_clear()


def test_dashscope_client_keeps_requested_qwen_model(monkeypatch):
    """确认百炼客户端不会把指定模型改回旧值。"""
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    monkeypatch.setenv("LLM_PROVIDER", "dashscope")
    get_settings.cache_clear()

    try:
        review_client = get_llm_client("dashscope", "qwen3.8-max")
        assistant_client = get_llm_client("dashscope", "qwen3.7-plus")
        assert review_client.model == "qwen3.8-max"
        assert assistant_client.model == "qwen3.7-plus"
        assert review_client.extra_body == {"enable_thinking": False}
        assert assistant_client.extra_body == {"enable_thinking": False}
    finally:
        get_settings.cache_clear()
