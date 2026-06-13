"""提供项目创建与列表接口，供前端项目管理页面调用。"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AgentEvaluation, Attachment, ChatMessage, DrawingFile, OverallReport, Project, ReportReference, Submission, User
from app.schemas import ProjectCreate, ProjectRead, ProjectUpdate, SubmissionHistoryRead, SubmissionRead

router = APIRouter(prefix="/api/projects", tags=["projects"])


def delete_submission_tree(db: Session, submission_id: int) -> None:
    """删除一个提交版本关联的报告、图纸记录和追问记录。"""
    db.execute(delete(ReportReference).where(ReportReference.submission_id == submission_id))
    db.execute(delete(ChatMessage).where(ChatMessage.submission_id == submission_id))
    db.execute(delete(Attachment).where(Attachment.submission_id == submission_id))
    db.execute(delete(DrawingFile).where(DrawingFile.submission_id == submission_id))
    db.execute(delete(AgentEvaluation).where(AgentEvaluation.submission_id == submission_id))
    db.execute(delete(OverallReport).where(OverallReport.submission_id == submission_id))
    db.execute(delete(Submission).where(Submission.id == submission_id))


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: ProjectCreate, db: Session = Depends(get_db)
) -> Project:
    """创建一个新的演示项目。"""
    owner = User(name=payload.owner_name, role="student")
    db.add(owner)
    db.flush()

    project = Project(
        name=payload.name,
        building_type=payload.building_type,
        owner_name=payload.owner_name,
        grade=payload.grade,
        site_location=payload.site_location,
        course_name=payload.course_name,
        user_id=owner.id,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.patch("/{project_id}", response_model=ProjectRead)
async def update_project(
    project_id: int, payload: ProjectUpdate, db: Session = Depends(get_db)
) -> Project:
    """修改项目基础信息。"""
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在。")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(project, field, value)
    db.commit()
    db.refresh(project)
    return project


@router.delete("/{project_id}")
async def delete_project(project_id: int, db: Session = Depends(get_db)) -> dict:
    """删除项目及其全部提交版本。"""
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在。")
    submission_ids = list(db.execute(
        select(Submission.id).where(Submission.project_id == project_id)
    ).scalars().all())
    for submission_id in submission_ids:
        delete_submission_tree(db, submission_id)
    db.delete(project)
    db.commit()
    return {"deleted": [project_id], "submissions": submission_ids}


@router.post("/{project_id}/clone", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
async def clone_project(
    project_id: int,
    source_submission_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
) -> Project:
    """继承已有项目的基础信息，可指定某个历史提交版本。"""
    source = db.get(Project, project_id)
    if source is None:
        raise HTTPException(status_code=404, detail="项目不存在。")
    owner = User(name=source.owner_name, role="student")
    db.add(owner)
    db.flush()
    project = Project(
        name=source.name,
        building_type=source.building_type,
        owner_name=source.owner_name,
        grade=source.grade,
        site_location=source.site_location,
        course_name=source.course_name,
        user_id=owner.id,
    )
    db.add(project)
    db.flush()
    if source_submission_id is not None:
        source_submission = db.get(Submission, source_submission_id)
        if source_submission is None or source_submission.project_id != source.id:
            raise HTTPException(status_code=404, detail="项目版本不存在。")
    else:
        source_submission = db.execute(
            select(Submission)
            .where(Submission.project_id == source.id)
            .order_by(Submission.id.desc())
        ).scalars().first()
    if source_submission is not None:
        submission = Submission(
            project_id=project.id,
            title=source_submission.title,
            design_stage=source_submission.design_stage,
            description=source_submission.description,
            image_urls=list(source_submission.image_urls or []),
            status="draft",
            enabled_agents=list(source_submission.enabled_agents or []),
            selected_model_provider=source_submission.selected_model_provider,
            selected_model_name=source_submission.selected_model_name,
        )
        db.add(submission)
        db.flush()
        source_drawings = db.execute(
            select(DrawingFile).where(DrawingFile.submission_id == source_submission.id)
        ).scalars()
        for drawing in source_drawings:
            db.add(DrawingFile(
                submission_id=submission.id,
                drawing_type=drawing.drawing_type,
                original_name=drawing.original_name,
                file_url=drawing.file_url,
                mime_type=drawing.mime_type,
                description=drawing.description,
                sort_order=drawing.sort_order,
            ))
        source_attachments = db.execute(
            select(Attachment).where(Attachment.submission_id == source_submission.id)
        ).scalars()
        for attachment in source_attachments:
            db.add(Attachment(
                submission_id=submission.id,
                original_name=attachment.original_name,
                file_url=attachment.file_url,
                mime_type=attachment.mime_type,
            ))
    db.commit()
    db.refresh(project)
    return project


@router.get("", response_model=list[ProjectRead])
async def list_projects(db: Session = Depends(get_db)) -> list[Project]:
    """返回当前已创建的项目列表。"""
    result = db.execute(select(Project).order_by(Project.id.desc()))
    return list(result.scalars().all())


@router.get("/{project_id}", response_model=ProjectRead)
async def get_project(project_id: int, db: Session = Depends(get_db)) -> Project:
    """返回单个项目详情。"""
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在。")
    return project


@router.get("/{project_id}/submissions", response_model=list[SubmissionRead])
async def list_project_submissions(
    project_id: int, db: Session = Depends(get_db)
) -> list[Submission]:
    """返回一个项目下的所有提交记录。"""
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在。")

    result = db.execute(
        select(Submission)
        .where(Submission.project_id == project_id)
        .order_by(Submission.id.desc())
    )
    return list(result.scalars().all())


@router.get("/{project_id}/history", response_model=list[SubmissionHistoryRead])
async def list_project_history(
    project_id: int, db: Session = Depends(get_db)
) -> list[SubmissionHistoryRead]:
    """返回一个项目下用于历史版本追踪的提交和分数。"""
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在。")

    rows = db.execute(
        select(Submission, OverallReport)
        .outerjoin(OverallReport, OverallReport.submission_id == Submission.id)
        .where(Submission.project_id == project_id)
        .order_by(Submission.id.asc())
    ).all()

    items = []
    for submission, report in rows:
        scores = db.execute(
            select(AgentEvaluation).where(AgentEvaluation.submission_id == submission.id)
        ).scalars()
        items.append(SubmissionHistoryRead(
            id=submission.id,
            title=submission.title,
            design_stage=submission.design_stage,
            created_at=submission.created_at,
            overall_score=report.overall_score if report else None,
            grade=report.grade if report else None,
            summary=report.summary if report else "",
            dimension_scores={item.dimension: item.score for item in scores},
        ))
    return items
