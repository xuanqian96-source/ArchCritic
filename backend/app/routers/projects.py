"""提供项目创建与列表接口，供前端项目管理页面调用。"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import OverallReport, Project, Submission, User
from app.schemas import ProjectCreate, ProjectRead, SubmissionHistoryRead, SubmissionRead

router = APIRouter(prefix="/api/projects", tags=["projects"])


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
        user_id=owner.id,
    )
    db.add(project)
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

    return [
        SubmissionHistoryRead(
            id=submission.id,
            title=submission.title,
            design_stage=submission.design_stage,
            created_at=submission.created_at,
            overall_score=report.overall_score if report else None,
            grade=report.grade if report else None,
        )
        for submission, report in rows
    ]
