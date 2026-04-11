"""封装 OpenAI 模型调用，供后续接入真实评图能力。"""

from app.llm.base import BaseLLMClient


class OpenAILLMClient(BaseLLMClient):
    """负责调用 OpenAI 接口并返回基础结果。"""

    def __init__(self, api_key: str, model: str) -> None:
        """初始化 OpenAI 客户端。"""
        from openai import OpenAI

        self.model = model
        self.client = OpenAI(api_key=api_key)

    def generate_evaluation(self, payload: dict) -> dict:
        """将文本发送给 OpenAI，并包装成基础结构。"""
        prompt = (
            "你是一位建筑设计课教师，请根据以下信息给出简短评价：\n"
            f"项目名称：{payload['project_name']}\n"
            f"建筑类型：{payload['building_type']}\n"
            f"设计阶段：{payload['design_stage']}\n"
            f"设计说明：{payload['description']}\n"
        )
        response = self.client.responses.create(
            model=self.model,
            input=prompt,
        )
        output_text = response.output_text or "模型已返回结果，但未生成文本。"
        return {
            "overall_score": 75,
            "grade": "B",
            "summary": output_text,
            "must_fix": ["请补充更明确的功能分区说明。"],
            "should_improve": ["建议继续加强图文对应关系。"],
            "optional_improvements": ["可增加环境策略示意。"],
            "strengths": ["已有较清晰的项目意图表达。"],
            "agent_evaluations": [
                {
                    "agent_type": "openai_general",
                    "dimension": "综合判断",
                    "score": 75,
                    "summary": output_text,
                    "strengths": ["模型已识别项目核心描述。"],
                    "issues": ["当前仍为基础通用输出。"],
                    "suggestions": ["后续可替换为更细的多维度 Prompt。"],
                }
            ],
        }
