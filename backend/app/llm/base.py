"""定义评图模型客户端的统一接口，供具体模型实现继承。"""

from abc import ABC, abstractmethod


class BaseLLMClient(ABC):
    """定义统一的评图结果生成接口。"""

    @abstractmethod
    def generate_evaluation(self, payload: dict) -> dict:
        """根据输入信息生成结构化评图结果。"""
