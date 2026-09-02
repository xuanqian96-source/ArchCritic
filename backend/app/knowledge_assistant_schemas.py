"""定义建筑知识助手接口结构，与评图报告问答保持相互独立。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


KnowledgeAssistantTool = Literal[
    "none",
    "case_recommendation",
    "knowledge_query",
    "learning_path",
    "current_card_qa",
]


class KnowledgeAssistantContext(BaseModel):
    """描述用户提问时所在的知识库界面。"""

    view: Literal["overview", "detail"] = "overview"
    current_card_id: str | None = Field(default=None, max_length=30)
    main_tab: Literal["all", "knowledge", "case"] = "all"
    category: str = Field(default="全部", max_length=100)
    previous_result_set_id: str | None = Field(default=None, max_length=36)


class KnowledgeAssistantChatCreate(BaseModel):
    """提交一轮知识助手提问。"""

    conversation_id: str = Field(..., min_length=36, max_length=36)
    tool: KnowledgeAssistantTool = "none"
    message: str = Field(..., min_length=1, max_length=2000)
    context: KnowledgeAssistantContext = Field(default_factory=KnowledgeAssistantContext)


class KnowledgeRecommendationRead(BaseModel):
    """返回一张经过后端校验的推荐卡片。"""

    id: str
    kind: Literal["knowledge", "case"]
    reason: str
    matched_fields: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    score: float = 0
    review_status: str = "pending"
    human_review_confirmed: bool = False


class KnowledgeCitationRead(BaseModel):
    """返回可点击的知识卡或案例卡引用。"""

    id: str
    title: str


class KnowledgeAssistantChatRead(BaseModel):
    """返回一轮回答、引用和前端应执行的界面动作。"""

    answer: str
    intent: KnowledgeAssistantTool
    clarification_required: bool = False
    extracted_conditions: dict = Field(default_factory=dict)
    recommendations: list[KnowledgeRecommendationRead] = Field(default_factory=list)
    citations: list[KnowledgeCitationRead] = Field(default_factory=list)
    result_set_id: str | None = None
    ui_action: Literal[
        "none", "show_assistant_results", "update_assistant_results", "focus_current_card"
    ] = "none"


class KnowledgeAssistantMessageRead(BaseModel):
    """返回已保存的知识助手消息。"""

    id: int
    role: Literal["user", "assistant"]
    content: str
    tool: str
    result: dict = Field(default_factory=dict)
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class KnowledgeConversationRead(BaseModel):
    """返回历史会话列表中的一条摘要。"""

    id: str
    title: str
    selected_tool: str
    message_count: int = 0
    updated_at: datetime | None = None
