"""定义接口收发的数据结构，供路由和前端联调用。"""

from datetime import datetime

from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    """创建项目时使用的数据结构。"""

    name: str = Field(..., min_length=1, max_length=200)
    building_type: str = Field(..., min_length=1, max_length=100)
    owner_name: str = Field(..., min_length=1, max_length=100)
    grade: str = Field(default="", max_length=100)


class ProjectRead(BaseModel):
    """返回项目信息时使用的数据结构。"""

    id: int
    name: str
    building_type: str
    owner_name: str
    grade: str = ""
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class SubmissionCreate(BaseModel):
    """创建提交记录时使用的数据结构。"""

    project_id: int
    title: str = Field(..., min_length=1, max_length=200)
    design_stage: str = Field(..., min_length=1, max_length=50)
    description: str = Field(..., min_length=1)
    image_urls: list[str] = Field(default_factory=list)


class SubmissionRead(BaseModel):
    """返回提交记录时使用的数据结构。"""

    id: int
    project_id: int
    title: str
    design_stage: str
    description: str
    image_urls: list[str]
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class DrawingFileRead(BaseModel):
    """返回图纸文件信息时使用的数据结构。"""

    id: int
    submission_id: int
    drawing_type: str
    original_name: str
    file_url: str
    mime_type: str
    model_file_url: str = ""
    model_file_expires_at: datetime | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class KnowledgeReferenceRead(BaseModel):
    """返回知识库依据时使用的数据结构。"""

    reference_id: str = ""
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

    model_config = {"from_attributes": True}


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


class SubmissionHistoryRead(BaseModel):
    """返回历史版本追踪信息时使用的数据结构。"""

    id: int
    title: str
    design_stage: str
    created_at: datetime | None = None
    overall_score: float | None = None
    grade: str | None = None


class EvaluationRequest(BaseModel):
    """传给演示模型的评图上下文结构。"""

    project_name: str
    building_type: str
    design_stage: str
    description: str
