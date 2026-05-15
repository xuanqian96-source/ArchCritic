"""封装 OpenAI 模型调用，供真实评图 Agent 使用。"""

from app.agents.function_agent import FunctionAgent, function_agent_report_to_overall
from app.llm.base import BaseLLMClient


class OpenAILLMClient(BaseLLMClient):
    """负责调用 OpenAI 兼容接口并返回结构化评图结果。"""

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str | None = None,
        structured_output_mode: str = "json_schema",
        timeout_seconds: int = 90,
        max_tokens: int = 1200,
        image_detail: str = "low",
        extra_body: dict | None = None,
        default_headers: dict | None = None,
    ) -> None:
        """初始化 OpenAI 或 OpenAI 兼容客户端。"""
        import httpx
        from openai import OpenAI

        self.model = model
        self.max_tokens = max_tokens
        self.image_detail = image_detail
        self.extra_body = extra_body
        client_options = {
            "api_key": api_key,
            "http_client": httpx.Client(timeout=timeout_seconds, trust_env=False),
            "max_retries": 0,
        }
        if base_url:
            client_options["base_url"] = base_url
        if default_headers:
            client_options["default_headers"] = default_headers
        self.client = OpenAI(**client_options)
        self.structured_output_mode = structured_output_mode

    def generate_evaluation(self, payload: dict) -> dict:
        """调用功能与流线 Agent，并转换成前端报告结构。"""
        agent = FunctionAgent(
            self.client,
            self.model,
            self.structured_output_mode,
            self.max_tokens,
            self.image_detail,
            self.extra_body,
        )
        report = agent.run(payload)
        return function_agent_report_to_overall(report)
