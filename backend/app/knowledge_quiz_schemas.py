"""定义知识测试逐题作答接口结构，与知识助手和评图接口保持独立。"""

from pydantic import BaseModel, Field, field_validator


class KnowledgeQuizAnswerCreate(BaseModel):
    """提交一道知识测试题的文字或选项答案。"""

    question_id: str = Field(..., min_length=3, max_length=80)
    answer: str | list[str]

    @field_validator("answer")
    @classmethod
    def validate_answer(cls, value: str | list[str]) -> str | list[str]:
        """拒绝空答案和异常长的简答内容。"""
        if isinstance(value, str):
            normalized = value.strip()
            if not normalized:
                raise ValueError("请先填写答案。")
            if len(normalized) > 3000:
                raise ValueError("答案不能超过 3000 个字符。")
            return normalized
        normalized_options = [str(item).strip() for item in value if str(item).strip()]
        if not normalized_options:
            raise ValueError("请至少选择一个答案。")
        if len(normalized_options) > 10:
            raise ValueError("选择的答案数量过多。")
        return normalized_options
