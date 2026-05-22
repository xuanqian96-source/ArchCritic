"""根据配置返回具体模型客户端，并提供演示评图结果。"""

from app.config import get_settings
from app.llm.base import BaseLLMClient


class MockLLMClient(BaseLLMClient):
    """生成稳定的演示评图结果，便于前端联调和可视化验证。"""

    def generate_evaluation(self, payload: dict) -> dict:
        """根据输入文本长度和阶段返回一份演示评图结果。"""
        description = payload["description"].strip()
        description_bonus = min(len(description) // 30, 8)
        stage_bonus = {"concept": 4, "scheme": 6, "drawing": 8}.get(
            payload["design_stage"], 5
        )
        overall_score = min(60 + description_bonus + stage_bonus, 92)

        return {
            "overall_score": overall_score,
            "grade": self._score_to_grade(overall_score),
            "summary": (
                f"{payload['project_name']} 的表达已经具备基本完整性，"
                "目前适合用来验证系统的提交流程和结果展示。"
            ),
            "must_fix": [
                "需要补充更明确的功能分区依据。",
                "需要把主要空间关系表达得更清楚。",
            ],
            "should_improve": [
                "建议补充一张说明核心流线的示意图。",
                "建议把设计阶段目标写得更具体。",
            ],
            "optional_improvements": [
                "可以增加材料或结构意向说明。",
                "可以补充与周边环境关系的表达。",
            ],
            "strengths": [
                "项目主题已经可以被快速理解。",
                "说明文字具备基础的逻辑顺序。",
            ],
            "agent_evaluations": [
                {
                    "agent_type": "site_agent",
                    "dimension": "场地与回应",
                    "score": max(overall_score - 3, 55),
                    "summary": "已经能看出项目与环境的基本关系，但回应策略还偏粗略。",
                    "strengths": ["项目定位清晰。"],
                    "issues": ["缺少更具体的环境分析证据。"],
                    "suggestions": ["补充场地约束和入口关系说明。"],
                },
                {
                    "agent_type": "function_agent",
                    "dimension": "功能与流线",
                    "score": overall_score,
                    "summary": "功能设想已有雏形，但流线表达仍需加强。",
                    "strengths": ["描述中已经体现使用场景。"],
                    "issues": ["主要空间先后关系仍不够明确。"],
                    "suggestions": ["用更短的话说明主要使用路径。"],
                },
                {
                    "agent_type": "form_agent",
                    "dimension": "形式与构图",
                    "score": min(overall_score + 2, 95),
                    "summary": "整体形象表达较完整，适合用于界面展示验证。",
                    "strengths": ["主题形象较容易建立记忆点。"],
                    "issues": ["形式依据还可以更具体。"],
                    "suggestions": ["把形体策略和功能联系起来说明。"],
                },
                {
                    "agent_type": "structure_agent",
                    "dimension": "结构与可行性",
                    "score": max(overall_score - 5, 55),
                    "summary": "结构逻辑目前可用于概念表达，但还需要和空间尺度进一步对应。",
                    "strengths": ["方案具备继续深化的基础。"],
                    "issues": ["结构跨度、柱网或支撑方式尚未充分说明。"],
                    "suggestions": ["补充结构体系意向和主要空间跨度说明。"],
                },
            ],
        }

    def _score_to_grade(self, score: int) -> str:
        """按分数返回简单等级。"""
        if score >= 85:
            return "A"
        if score >= 75:
            return "B"
        if score >= 65:
            return "C"
        return "D"


def get_llm_client(
    provider: str | None = None, model: str | None = None
) -> BaseLLMClient:
    """根据配置返回对应的模型客户端。"""
    settings = get_settings()
    resolved_provider = (provider or settings.llm_provider).lower()
    resolved_model = model or settings.llm_model

    if resolved_provider == "mock":
        return MockLLMClient()

    if resolved_provider == "openai":
        if not settings.openai_api_key:
            raise ValueError("当前未配置 OpenAI API Key，无法启用真实模型。")
        from app.llm.openai_client import OpenAILLMClient

        return OpenAILLMClient(
            settings.openai_api_key,
            resolved_model,
            timeout_seconds=settings.llm_timeout_seconds,
            agent_timeout_seconds=settings.llm_agent_timeout_seconds,
            review_timeout_seconds=settings.llm_review_timeout_seconds,
            max_tokens=settings.llm_max_tokens,
            image_detail=settings.llm_image_detail,
        )

    if resolved_provider == "dashscope":
        if not settings.dashscope_api_key:
            raise ValueError("当前未配置百炼 API Key，无法启用百炼模型。")
        from app.llm.openai_client import OpenAILLMClient

        return OpenAILLMClient(
            settings.dashscope_api_key,
            resolved_model,
            settings.dashscope_base_url,
            "json_object",
            timeout_seconds=settings.llm_timeout_seconds,
            agent_timeout_seconds=settings.llm_agent_timeout_seconds,
            review_timeout_seconds=settings.llm_review_timeout_seconds,
            max_tokens=settings.llm_max_tokens,
            image_detail=settings.llm_image_detail,
            extra_body={"enable_thinking": False},
            default_headers={"X-DashScope-OssResourceResolve": "enable"},
        )

    if resolved_provider == "gemini":
        if not settings.gemini_api_key:
            raise ValueError("当前未配置 Gemini API Key，无法启用 Gemini 模型。")
        from app.llm.openai_client import OpenAILLMClient

        return OpenAILLMClient(
            settings.gemini_api_key,
            resolved_model,
            settings.gemini_base_url,
            "json_object",
            timeout_seconds=settings.llm_timeout_seconds,
            agent_timeout_seconds=settings.llm_agent_timeout_seconds,
            review_timeout_seconds=settings.llm_review_timeout_seconds,
            max_tokens=settings.llm_max_tokens,
            image_detail=settings.llm_image_detail,
            reasoning_effort="none",
        )

    raise ValueError(f"暂不支持的模型提供方：{resolved_provider}")
