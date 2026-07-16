"""报告与追问接口，负责评图结果读取、导出、演示评图和报告问答。"""

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.agents.function_agent import build_function_agent_context
from app.agents.scheme_review import is_multi_agent_stage
from app.config import get_settings
from app.database import get_db
from app.llm.client import get_llm_client
from app.models import AgentEvaluation, ChatMessage, OverallReport, Submission, User
from app.schemas import ChatMessageCreate, ChatMessageRead, KnowledgeReferenceRead, OverallReportRead, SubmissionRead
from app.services.auth import get_current_user, require_owned_submission
from app.routers.submission_common import CANCELLED_SUBMISSIONS, REAL_LLM_PROVIDERS, resolve_llm_model, resolve_llm_provider
from app.routers.submission_crud import refresh_submission_attachments
from app.routers.submission_report_data import build_model_error_message, build_report_response, load_report_reference_snapshots, load_submission_wiki_references, save_report_data
from app.routers.submission_stream import ensure_dashscope_model_file_urls

router = APIRouter(prefix="/api/submissions", tags=["submissions"])

@router.post("/{submission_id}/cancel-evaluation", response_model=SubmissionRead)
async def cancel_submission_evaluation(
    submission_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Submission:
    """标记当前评图任务暂停，并在下一个可中断节点停止。"""
    submission = require_owned_submission(db, submission_id, user)
    CANCELLED_SUBMISSIONS.add(submission_id)
    submission.status = "cancelled"
    db.commit()
    db.refresh(submission)
    return submission


@router.get("/{submission_id}/report/export", response_class=PlainTextResponse)
async def export_submission_report(
    submission_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PlainTextResponse:
    """导出当前报告为 Markdown 文件。"""
    report = await get_submission_report(submission_id, db, user)
    sections = [
        f"# ArchCritic 评图报告\n\n综合评分：{report.overall_score}\n\n{report.summary}",
        "## 必须修改\n" + "\n".join(f"- {item}" for item in report.must_fix),
        "## 重点优化\n" + "\n".join(f"- {item}" for item in report.should_improve),
        "## 建议关注\n" + "\n".join(f"- {item}" for item in report.optional_improvements),
    ]
    return PlainTextResponse(
        "\n\n".join(sections),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="archcritic-report-{submission_id}.md"'},
    )


def build_chat_fallback_answer(report: OverallReport | None, content: str) -> str:
    """根据已生成报告构造稳定的本地追问回答。"""
    if report is None:
        return "报告仍在生成中，请稍后再继续追问。"
    if "必须" in content or "修改" in content:
        items = report.must_fix[:3] or ["当前报告没有明确列出必须修改项。"]
        return "本轮必须修改项：" + "；".join(items)
    items = report.should_improve[:2] or report.must_fix[:2] or ["建议先复核总评中提到的主要问题。"]
    return f"结合本次评分，{report.summary} 建议先复核：" + "；".join(items)


def build_chat_prompt(
    submission: Submission,
    report: OverallReport,
    content: str,
    db: Session,
) -> str:
    """把项目、报告和追问整理为模型可直接回答的文本。"""
    evaluations = db.execute(
        select(AgentEvaluation).where(AgentEvaluation.submission_id == submission.id)
    ).scalars().all()
    dimension_lines = [
        f"- {item.dimension}：{round(item.score)}分。{item.summary}"
        for item in evaluations[:6]
    ]
    return "\n".join([
        f"项目名称：{submission.project.name}",
        f"设计阶段：{submission.design_stage}",
        f"综合评分：{round(report.overall_score)}，等级：{report.grade}",
        f"总评：{report.summary}",
        "主要评分维度：",
        "\n".join(dimension_lines) or "- 暂无专项评分。",
        "必须修改：" + "；".join(report.must_fix[:5]),
        "重点优化：" + "；".join(report.should_improve[:5]),
        "用户追问：" + content,
    ])


def generate_chat_answer(
    submission: Submission,
    report: OverallReport | None,
    payload: ChatMessageCreate,
    db: Session,
) -> str:
    """优先调用用户选择的模型回答，失败时回退到稳定本地回答。"""
    fallback = build_chat_fallback_answer(report, payload.content)
    if report is None:
        return fallback
    try:
        provider = resolve_llm_provider(payload.model_provider or submission.selected_model_provider)
        model = resolve_llm_model(provider, payload.model_name or submission.selected_model_name)
        if provider not in REAL_LLM_PROVIDERS:
            return fallback
        llm_client = get_llm_client(provider, model)
        create_kwargs = {
            "model": llm_client.model,
            "messages": [
                {
                    "role": "system",
                    "content": "你是 ArchCritic 的评图报告助手。只根据给定报告回答，语气简洁，必须用中文。可以用 **加粗** 标注重点，但不要使用复杂 Markdown 表格。",
                },
                {"role": "user", "content": build_chat_prompt(submission, report, payload.content, db)},
            ],
            "temperature": 0.3,
            "max_tokens": min(llm_client.max_tokens, 800),
        }
        if llm_client.extra_body:
            create_kwargs["extra_body"] = llm_client.extra_body
        if llm_client.reasoning_effort:
            create_kwargs["reasoning_effort"] = llm_client.reasoning_effort
        try:
            response = llm_client.client.chat.completions.create(**create_kwargs)
        except TypeError:
            create_kwargs.pop("extra_body", None)
            create_kwargs.pop("reasoning_effort", None)
            response = llm_client.client.chat.completions.create(**create_kwargs)
        answer = response.choices[0].message.content if response.choices else ""
        return answer.strip() or fallback
    except Exception:
        return fallback


@router.post("/{submission_id}/chat", response_model=ChatMessageRead)
async def create_chat_message(
    submission_id: int,
    payload: ChatMessageCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ChatMessage:
    """保存报告追问，并按当前报告给出可核对的回答。"""
    submission = require_owned_submission(db, submission_id, user)
    report = db.execute(
        select(OverallReport).where(OverallReport.submission_id == submission_id)
    ).scalar_one_or_none()
    answer = generate_chat_answer(submission, report, payload, db)
    db.add(ChatMessage(submission_id=submission_id, role="user", content=payload.content))
    response = ChatMessage(submission_id=submission_id, role="assistant", content=answer)
    db.add(response)
    db.commit()
    db.refresh(response)
    return response


@router.get("/{submission_id}/chat/messages", response_model=list[ChatMessageRead])
async def list_chat_messages(
    submission_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ChatMessage]:
    """返回当前提交的全部报告追问记录。"""
    require_owned_submission(db, submission_id, user)
    result = db.execute(
        select(ChatMessage)
        .where(ChatMessage.submission_id == submission_id)
        .order_by(ChatMessage.id.asc())
    )
    return list(result.scalars().all())


@router.post("/{submission_id}/evaluate-demo", response_model=OverallReportRead)
async def evaluate_submission_demo(
    submission_id: int,
    provider: str | None = Query(default=None),
    model: str | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> OverallReportRead:
    """为指定提交生成一份评图结果。"""
    query = (
        select(Submission)
        .options(
            selectinload(Submission.project),
            selectinload(Submission.agent_evaluations),
            selectinload(Submission.drawing_files),
            selectinload(Submission.attachments),
            selectinload(Submission.overall_report),
        )
        .where(Submission.id == submission_id)
    )
    result = db.execute(query)
    submission = result.scalar_one_or_none()

    if submission is None or submission.project.user_id != user.id:
        raise HTTPException(status_code=404, detail="未找到对应的方案提交。")
    refresh_submission_attachments(db, list(submission.attachments))

    settings = get_settings()
    llm_provider = resolve_llm_provider(provider)
    llm_model = resolve_llm_model(llm_provider, model)
    llm_client = get_llm_client(llm_provider, llm_model)
    references = load_submission_wiki_references(settings.wiki_dir, submission)
    if llm_provider in REAL_LLM_PROVIDERS:
        if llm_provider == "dashscope":
            ensure_dashscope_model_file_urls(db, list(submission.drawing_files), llm_model)
        payload = build_function_agent_context(
            submission,
            list(submission.drawing_files),
            references,
            list(submission.attachments),
        )
    else:
        payload = {
            "project_name": submission.project.name,
            "building_type": submission.project.building_type,
            "design_stage": submission.design_stage,
            "description": submission.description,
        }
    try:
        report_data = await asyncio.wait_for(
            asyncio.to_thread(llm_client.generate_evaluation, payload),
            timeout=(
                settings.llm_review_timeout_seconds + 15
                if llm_provider in REAL_LLM_PROVIDERS
                and is_multi_agent_stage(submission.design_stage)
                else settings.llm_timeout_seconds + 15
            ),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=build_model_error_message(exc),
        ) from exc

    save_report_data(db, submission_id, report_data, references)

    overall_report = db.execute(
        select(OverallReport).where(OverallReport.submission_id == submission_id)
    ).scalar_one()
    agent_evaluations = list(
        db.execute(
            select(AgentEvaluation).where(AgentEvaluation.submission_id == submission_id)
        ).scalars()
    )

    return build_report_response(overall_report, agent_evaluations, submission, db)


@router.get("/{submission_id}/report", response_model=OverallReportRead)
async def get_submission_report(
    submission_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> OverallReportRead:
    """返回某次提交已经生成的评图报告。"""
    submission = require_owned_submission(db, submission_id, user)

    overall_report = db.execute(
        select(OverallReport).where(OverallReport.submission_id == submission_id)
    ).scalar_one_or_none()
    if overall_report is None:
        raise HTTPException(status_code=404, detail="该提交还没有生成评图报告。")

    agent_evaluations = list(
        db.execute(
            select(AgentEvaluation).where(AgentEvaluation.submission_id == submission_id)
        ).scalars()
    )
    return build_report_response(overall_report, agent_evaluations, submission, db)


@router.get("/{submission_id}/references", response_model=list[KnowledgeReferenceRead])
async def list_submission_references(
    submission_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[dict]:
    """从 Wiki 知识库返回当前提交对应的依据条目。"""
    submission = require_owned_submission(db, submission_id, user)

    settings = get_settings()
    snapshots = load_report_reference_snapshots(db, submission_id)
    if snapshots:
        return snapshots
    return load_submission_wiki_references(settings.wiki_dir, submission)
