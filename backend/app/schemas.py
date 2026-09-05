"""定义接口收发的数据结构，供路由和前端联调用。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class AuthRegister(BaseModel):
    """本地注册时使用的数据结构。"""

    username: str = Field(..., min_length=3, max_length=12, pattern=r"^[A-Za-z0-9]+$")
    password: str = Field(..., min_length=8, max_length=128)
    display_name: str = Field(..., min_length=1, max_length=12)
    invitation_code: str = Field(default="", max_length=128)

    model_config = {"str_strip_whitespace": True}


class AuthLogin(BaseModel):
    """本地登录时使用的数据结构。"""

    username: str = Field(..., min_length=3, max_length=12, pattern=r"^[A-Za-z0-9]+$")
    password: str = Field(..., min_length=1, max_length=128)

    model_config = {"str_strip_whitespace": True}


class AuthUserRead(BaseModel):
    """返回当前登录用户的公开信息。"""

    id: int
    username: str
    display_name: str
    role: str


class AuthAccountAvailabilityRead(BaseModel):
    """返回账号是否可以注册。"""

    available: bool


class AuthProfileUpdate(BaseModel):
    """修改本地账户昵称。"""

    display_name: str = Field(..., min_length=1, max_length=12)

    model_config = {"str_strip_whitespace": True}


class AuthPasswordUpdate(BaseModel):
    """修改本地账户密码。"""

    current_password: str = Field(..., min_length=1, max_length=128)
    new_password: str = Field(..., min_length=8, max_length=128)


class FeedbackCreate(BaseModel):
    """用户提交问题反馈时使用的数据结构。"""

    content: str = Field(..., min_length=5, max_length=2000)

    model_config = {"str_strip_whitespace": True}


class FeedbackRead(BaseModel):
    """返回反馈保存结果。"""

    id: int
    status: str
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class ProjectCreate(BaseModel):
    """创建项目时使用的数据结构。"""

    name: str = Field(..., min_length=1, max_length=200)
    building_type: str = Field(..., min_length=1, max_length=100)
    owner_name: str = Field(..., min_length=1, max_length=100)
    grade: str = Field(default="", max_length=100)
    site_location: str = Field(default="", max_length=200)
    course_name: str = Field(default="", max_length=200)


class ProjectUpdate(BaseModel):
    """修改项目时使用的数据结构。"""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    building_type: str | None = Field(default=None, min_length=1, max_length=100)
    owner_name: str | None = Field(default=None, min_length=1, max_length=100)
    grade: str | None = Field(default=None, max_length=100)
    site_location: str | None = Field(default=None, max_length=200)
    course_name: str | None = Field(default=None, max_length=200)


class ProjectRead(BaseModel):
    """返回项目信息时使用的数据结构。"""

    id: int
    name: str
    building_type: str
    owner_name: str
    grade: str = ""
    site_location: str = ""
    course_name: str = ""
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class SubmissionCreate(BaseModel):
    """创建提交记录时使用的数据结构。"""

    project_id: int
    title: str = Field(..., min_length=1, max_length=200)
    design_stage: str = Field(..., min_length=1, max_length=50)
    description: str = Field(default="")
    image_urls: list[str] = Field(default_factory=list)
    status: str = Field(default="draft", max_length=30)
    enabled_agents: list[str] = Field(default_factory=list)
    selected_model_provider: str = Field(default="mock", max_length=50)
    selected_model_name: str = Field(default="demo", max_length=100)


class SubmissionUpdate(BaseModel):
    """修改草稿提交时使用的数据结构。"""

    title: str | None = Field(default=None, min_length=1, max_length=200)
    design_stage: str | None = Field(default=None, min_length=1, max_length=50)
    description: str | None = None
    image_urls: list[str] | None = None
    status: str | None = Field(default=None, max_length=30)
    enabled_agents: list[str] | None = None
    selected_model_provider: str | None = Field(default=None, max_length=50)
    selected_model_name: str | None = Field(default=None, max_length=100)


class SubmissionRead(BaseModel):
    """返回提交记录时使用的数据结构。"""

    id: int
    project_id: int
    title: str
    design_stage: str
    description: str
    image_urls: list[str]
    status: str = "draft"
    enabled_agents: list[str] = Field(default_factory=list)
    selected_model_provider: str = "mock"
    selected_model_name: str = "demo"
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class DrawingFileRead(BaseModel):
    """返回图纸文件信息时使用的数据结构。"""

    id: int
    submission_id: int
    drawing_type: str
    original_name: str
    file_url: str
    mime_type: str
    description: str = ""
    sort_order: int = 0
    model_file_url: str = ""
    model_file_expires_at: datetime | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class DrawingFileUpdate(BaseModel):
    """修改图纸类型、说明和排序时使用的数据结构。"""

    drawing_type: str | None = Field(default=None, max_length=50)
    description: str | None = Field(default=None, max_length=200)
    sort_order: int | None = None


class BatchDeleteFiles(BaseModel):
    """批量删除图纸时使用的数据结构。"""

    file_ids: list[int] = Field(default_factory=list)


class AttachmentRead(BaseModel):
    """返回任务书等补充资料时使用的数据结构。"""

    id: int
    submission_id: int
    original_name: str
    file_url: str
    mime_type: str
    extraction_status: str = "pending"
    extracted_text_preview: str = ""
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class ChatMessageCreate(BaseModel):
    """提交报告追问时使用的数据结构。"""

    content: str = Field(..., min_length=1, max_length=1000)
    tool: Literal["none", "drawing_review", "issue_explanation", "knowledge_recommendation"] = "none"


class ChatCitationRead(BaseModel):
    """报告助手回答下方的一张可点击知识卡或案例卡。"""

    id: str
    title: str


class ChatMessageRead(BaseModel):
    """返回报告追问消息时使用的数据结构。"""

    id: int
    role: str
    content: str
    tool: str = "none"
    citations: list[ChatCitationRead] = Field(default_factory=list)
    report_updated: bool = False
    updated_report: "OverallReportRead | None" = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class KnowledgeReferenceRead(BaseModel):
    """返回知识库依据时使用的数据结构。"""

    reference_id: str = ""
    library_item_id: str = ""
    title: str
    source_type: str
    excerpt: str
    dimension: str
    path: str
    content: str = ""
    display_content: str = ""
    image_urls: list[dict] = Field(default_factory=list)


class AgentEvaluationRead(BaseModel):
    """返回单个评图视角结果时使用的数据结构。"""

    agent_type: str
    dimension: str
    score: float
    summary: str
    strengths: list[str]
    issues: list[str]
    suggestions: list[str]
    details: dict = Field(default_factory=dict)

    model_config = {"from_attributes": True}


class FeedbackItemRead(BaseModel):
    """返回一条带知识引用的报告反馈。"""

    text: str
    reference_ids: list[str] = Field(default_factory=list)


class OverallReportRead(BaseModel):
    """返回评图汇总结果时使用的数据结构。"""

    id: int
    submission_id: int
    overall_score: float
    grade: str
    summary: str
    must_fix: list[str]
    should_improve: list[str]
    optional_improvements: list[str]
    strengths: list[str]
    agent_evaluations: list[AgentEvaluationRead]
    references: list[KnowledgeReferenceRead] = Field(default_factory=list)
    feedback: dict[str, list[FeedbackItemRead]] = Field(default_factory=dict)
    evaluation_context: dict = Field(default_factory=dict)


class SubmissionHistoryRead(BaseModel):
    """返回历史版本追踪信息时使用的数据结构。"""

    id: int
    title: str
    design_stage: str
    created_at: datetime | None = None
    overall_score: float | None = None
    grade: str | None = None
    summary: str = ""
    must_fix: list[str] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    dimension_scores: dict[str, float] = Field(default_factory=dict)


class ProjectOverviewRead(BaseModel):
    """返回项目列表所需的轻量版本摘要，避免前端逐项目重复请求。"""

    project: ProjectRead
    submissions: list[SubmissionRead] = Field(default_factory=list)
    history: list[SubmissionHistoryRead] = Field(default_factory=list)


class SubmissionWorkspaceRead(BaseModel):
    """一次返回进入工作台所需的数据，减少页面切换时的请求轮次。"""

    project: ProjectRead
    submission: SubmissionRead
    drawings: list[DrawingFileRead] = Field(default_factory=list)
    attachments: list[AttachmentRead] = Field(default_factory=list)
    history: list[SubmissionHistoryRead] = Field(default_factory=list)
    report: OverallReportRead | None = None
    chat_messages: list[ChatMessageRead] = Field(default_factory=list)


class EvaluationRequest(BaseModel):
    """传给演示模型的评图上下文结构。"""

    project_name: str
    building_type: str
    design_stage: str
    description: str
