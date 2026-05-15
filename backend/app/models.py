"""定义系统基础数据表，供数据库和接口模块共同使用。"""

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    """保存项目拥有者等基础用户信息。"""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(50), default="student")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    projects: Mapped[list["Project"]] = relationship(back_populates="owner")


class Project(Base):
    """保存评图项目的基础信息。"""

    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    building_type: Mapped[str] = mapped_column(String(100))
    owner_name: Mapped[str] = mapped_column(String(100))
    grade: Mapped[str] = mapped_column(String(100), default="")
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    owner: Mapped[User | None] = relationship(back_populates="projects")
    submissions: Mapped[list["Submission"]] = relationship(back_populates="project")


class Submission(Base):
    """保存一次方案提交的说明、阶段和图像地址。"""

    __tablename__ = "submissions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    title: Mapped[str] = mapped_column(String(200))
    design_stage: Mapped[str] = mapped_column(String(50))
    description: Mapped[str] = mapped_column(Text)
    image_urls: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    project: Mapped[Project] = relationship(back_populates="submissions")
    agent_evaluations: Mapped[list["AgentEvaluation"]] = relationship(
        back_populates="submission"
    )
    drawing_files: Mapped[list["DrawingFile"]] = relationship(
        back_populates="submission"
    )
    overall_report: Mapped["OverallReport | None"] = relationship(
        back_populates="submission", uselist=False
    )


class DrawingFile(Base):
    """保存一次方案提交中上传的图纸文件。"""

    __tablename__ = "drawing_files"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    submission_id: Mapped[int] = mapped_column(ForeignKey("submissions.id"))
    drawing_type: Mapped[str] = mapped_column(String(50))
    original_name: Mapped[str] = mapped_column(String(255))
    file_url: Mapped[str] = mapped_column(String(500))
    mime_type: Mapped[str] = mapped_column(String(100))
    model_file_url: Mapped[str] = mapped_column(String(500), default="")
    model_file_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    submission: Mapped[Submission] = relationship(back_populates="drawing_files")


class AgentEvaluation(Base):
    """保存单个评图视角的结构化评价结果。"""

    __tablename__ = "agent_evaluations"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    submission_id: Mapped[int] = mapped_column(ForeignKey("submissions.id"))
    agent_type: Mapped[str] = mapped_column(String(100))
    dimension: Mapped[str] = mapped_column(String(100))
    score: Mapped[float] = mapped_column(Float)
    summary: Mapped[str] = mapped_column(Text)
    strengths: Mapped[list[str]] = mapped_column(JSON, default=list)
    issues: Mapped[list[str]] = mapped_column(JSON, default=list)
    suggestions: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    submission: Mapped[Submission] = relationship(back_populates="agent_evaluations")


class OverallReport(Base):
    """保存一次提交的汇总评价结果。"""

    __tablename__ = "overall_reports"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    submission_id: Mapped[int] = mapped_column(ForeignKey("submissions.id"), unique=True)
    overall_score: Mapped[float] = mapped_column(Float)
    grade: Mapped[str] = mapped_column(String(20))
    summary: Mapped[str] = mapped_column(Text)
    must_fix: Mapped[list[str]] = mapped_column(JSON, default=list)
    should_improve: Mapped[list[str]] = mapped_column(JSON, default=list)
    optional_improvements: Mapped[list[str]] = mapped_column(JSON, default=list)
    strengths: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    submission: Mapped[Submission] = relationship(back_populates="overall_report")
