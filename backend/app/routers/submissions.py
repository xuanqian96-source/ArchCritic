"""提供方案提交与演示评图接口，供前端验证完整流程。"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.database import get_db
from app.llm.client import get_llm_client
from app.models import AgentEvaluation, OverallReport, Project, Submission
from app.schemas import OverallReportRead, SubmissionCreate, SubmissionRead

router = APIRouter(prefix="/api/submissions", tags=["submissions"])


@router.post("", response_model=SubmissionRead, status_code=status.HTTP_201_CREATED)
async def create_submission(
    payload: SubmissionCreate, db: Session = Depends(get_db)
) -> Submission:
    """创建一次新的方案提交记录。"""
    project = db.get(Project, payload.project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在，无法提交方案。")

    submission = Submission(
        project_id=payload.project_id,
        title=payload.title,
        design_stage=payload.design_stage,
        description=payload.description,
        image_urls=payload.image_urls,
    )
    db.add(submission)
    db.commit()
    db.refresh(submission)
    return submission


@router.post("/{submission_id}/evaluate-demo", response_model=OverallReportRead)
async def evaluate_submission_demo(
    submission_id: int, db: Session = Depends(get_db)
) -> OverallReportRead:
    """为指定提交生成一份演示评图结果。"""
    query = (
        select(Submission)
        .options(
            selectinload(Submission.project),
            selectinload(Submission.agent_evaluations),
            selectinload(Submission.overall_report),
        )
        .where(Submission.id == submission_id)
    )
    result = db.execute(query)
    submission = result.scalar_one_or_none()

    if submission is None:
        raise HTTPException(status_code=404, detail="未找到对应的方案提交。")

    settings = get_settings()
    llm_client = get_llm_client(settings.llm_provider)
    payload = {
        "project_name": submission.project.name,
        "building_type": submission.project.building_type,
        "design_stage": submission.design_stage,
        "description": submission.description,
    }
    report_data = llm_client.generate_evaluation(payload)

    db.execute(
        delete(AgentEvaluation).where(AgentEvaluation.submission_id == submission_id)
    )
    db.execute(delete(OverallReport).where(OverallReport.submission_id == submission_id))

    for agent_item in report_data["agent_evaluations"]:
        db.add(
            AgentEvaluation(
                submission_id=submission_id,
                agent_type=agent_item["agent_type"],
                dimension=agent_item["dimension"],
                score=agent_item["score"],
                summary=agent_item["summary"],
                strengths=agent_item["strengths"],
                issues=agent_item["issues"],
                suggestions=agent_item["suggestions"],
            )
        )

    db.add(
        OverallReport(
            submission_id=submission_id,
            overall_score=report_data["overall_score"],
            grade=report_data["grade"],
            summary=report_data["summary"],
            must_fix=report_data["must_fix"],
            should_improve=report_data["should_improve"],
            optional_improvements=report_data["optional_improvements"],
            strengths=report_data["strengths"],
        )
    )
    db.commit()

    overall_report = db.execute(
        select(OverallReport).where(OverallReport.submission_id == submission_id)
    ).scalar_one()
    agent_evaluations = list(
        db.execute(
            select(AgentEvaluation).where(AgentEvaluation.submission_id == submission_id)
        ).scalars()
    )

    return OverallReportRead(
        submission_id=submission_id,
        overall_score=overall_report.overall_score,
        grade=overall_report.grade,
        summary=overall_report.summary,
        must_fix=overall_report.must_fix,
        should_improve=overall_report.should_improve,
        optional_improvements=overall_report.optional_improvements,
        strengths=overall_report.strengths,
        agent_evaluations=[
            {
                "agent_type": item.agent_type,
                "dimension": item.dimension,
                "score": item.score,
                "summary": item.summary,
                "strengths": item.strengths,
                "issues": item.issues,
                "suggestions": item.suggestions,
            }
            for item in agent_evaluations
        ],
    )
