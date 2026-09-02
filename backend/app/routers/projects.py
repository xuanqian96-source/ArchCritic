"""提供项目创建、摘要、历史与列表接口，供前端项目管理页面调用。"""

from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AgentEvaluation, Attachment, DrawingFile, OverallReport, Project, Submission, User
from app.schemas import ProjectCreate, ProjectOverviewRead, ProjectRead, ProjectUpdate, SubmissionHistoryRead, SubmissionRead
from app.services.auth import get_current_user, require_owned_project
from app.services.submission_cleanup import delete_submission_tree

router = APIRouter(prefix="/api/projects", tags=["projects"])

@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: ProjectCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Project:
    """为当前登录用户创建一个新项目。"""
    project = Project(
        name=payload.name,
        building_type=payload.building_type,
        owner_name=payload.owner_name,
        grade=payload.grade,
        site_location=payload.site_location,
        course_name=payload.course_name,
        user_id=user.id,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.patch("/{project_id}", response_model=ProjectRead)
async def update_project(
    project_id: int,
    payload: ProjectUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Project:
    """修改项目基础信息。"""
    project = require_owned_project(db, project_id, user)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(project, field, value)
    db.commit()
    db.refresh(project)
    return project


@router.delete("/{project_id}")
async def delete_project(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """删除项目及其全部提交版本。"""
    project = require_owned_project(db, project_id, user)
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
    user: User = Depends(get_current_user),
) -> Project:
    """继承已有项目的基础信息，可指定某个历史提交版本。"""
    source = require_owned_project(db, project_id, user)
    project = Project(
        name=source.name,
        building_type=source.building_type,
        owner_name=source.owner_name,
        grade=source.grade,
        site_location=source.site_location,
        course_name=source.course_name,
        user_id=user.id,
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
                extracted_text=attachment.extracted_text,
                extraction_status=attachment.extraction_status,
            ))
    db.commit()
    db.refresh(project)
    return project


@router.get("", response_model=list[ProjectRead])
async def list_projects(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[Project]:
    """返回当前已创建的项目列表。"""
    result = db.execute(
        select(Project).where(Project.user_id == user.id).order_by(Project.id.desc())
    )
    return list(result.scalars().all())


def build_history_item(
    submission: Submission,
    report: OverallReport | None,
    scores: list[AgentEvaluation],
) -> SubmissionHistoryRead:
    """把一次提交及其报告整理为轻量历史摘要。"""
    return SubmissionHistoryRead(
        id=submission.id,
        title=submission.title,
        design_stage=submission.design_stage,
        created_at=submission.created_at,
        overall_score=report.overall_score if report else None,
        grade=report.grade if report else None,
        summary=report.summary if report else "",
        must_fix=report.must_fix if report else [],
        strengths=report.strengths if report else [],
        dimension_scores={item.dimension: item.score for item in scores},
    )


def load_project_history_items(db: Session, project_id: int) -> list[SubmissionHistoryRead]:
    """用固定数量查询读取一个项目的全部历史摘要。"""
    rows = db.execute(
        select(Submission, OverallReport)
        .outerjoin(OverallReport, OverallReport.submission_id == Submission.id)
        .where(Submission.project_id == project_id)
        .order_by(Submission.id.asc())
    ).all()
    submission_ids = [submission.id for submission, _ in rows]
    score_groups: dict[int, list[AgentEvaluation]] = defaultdict(list)
    if submission_ids:
        evaluations = db.execute(
            select(AgentEvaluation).where(AgentEvaluation.submission_id.in_(submission_ids))
        ).scalars()
        for evaluation in evaluations:
            score_groups[evaluation.submission_id].append(evaluation)
    return [
        build_history_item(submission, report, score_groups[submission.id])
        for submission, report in rows
    ]


@router.get("/overview", response_model=list[ProjectOverviewRead])
async def list_project_overview(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ProjectOverviewRead]:
    """一次返回全部项目的版本摘要，供首页和继承列表共用。"""
    projects = list(db.execute(
        select(Project).where(Project.user_id == user.id).order_by(Project.id.desc())
    ).scalars())
    project_ids = [project.id for project in projects]
    if not project_ids:
        return []

    submissions = list(db.execute(
        select(Submission)
        .where(Submission.project_id.in_(project_ids))
        .order_by(Submission.id.desc())
    ).scalars())
    submission_ids = [submission.id for submission in submissions]
    reports = list(db.execute(
        select(OverallReport).where(OverallReport.submission_id.in_(submission_ids))
    ).scalars()) if submission_ids else []
    evaluations = list(db.execute(
        select(AgentEvaluation).where(AgentEvaluation.submission_id.in_(submission_ids))
    ).scalars()) if submission_ids else []

    submissions_by_project: dict[int, list[Submission]] = defaultdict(list)
    reports_by_submission = {report.submission_id: report for report in reports}
    scores_by_submission: dict[int, list[AgentEvaluation]] = defaultdict(list)
    for submission in submissions:
        submissions_by_project[submission.project_id].append(submission)
    for evaluation in evaluations:
        scores_by_submission[evaluation.submission_id].append(evaluation)

    return [
        ProjectOverviewRead(
            project=project,
            submissions=submissions_by_project[project.id],
            history=[
                build_history_item(
                    submission,
                    reports_by_submission.get(submission.id),
                    scores_by_submission[submission.id],
                )
                for submission in reversed(submissions_by_project[project.id])
            ],
        )
        for project in projects
    ]


@router.get("/{project_id}", response_model=ProjectRead)
async def get_project(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Project:
    """返回单个项目详情。"""
    return require_owned_project(db, project_id, user)


@router.get("/{project_id}/submissions", response_model=list[SubmissionRead])
async def list_project_submissions(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[Submission]:
    """返回一个项目下的所有提交记录。"""
    require_owned_project(db, project_id, user)

    result = db.execute(
        select(Submission)
        .where(Submission.project_id == project_id)
        .order_by(Submission.id.desc())
    )
    return list(result.scalars().all())


@router.get("/{project_id}/history", response_model=list[SubmissionHistoryRead])
async def list_project_history(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[SubmissionHistoryRead]:
    """返回一个项目下用于历史版本追踪的提交和分数。"""
    require_owned_project(db, project_id, user)

    return load_project_history_items(db, project_id)
