"""报告与追问接口，负责评图结果读取、导出、演示评图和报告问答。"""

import asyncio
import json
import logging
import threading
from typing import Callable

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse, Response, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
from starlette.concurrency import run_in_threadpool

from app.agents.function_agent import build_function_agent_context
from app.agents.scheme_review import is_multi_agent_stage
from app.config import get_settings
from app.database import get_db, get_session_factory
from app.llm.client import get_llm_client
from app.models import AgentEvaluation, ChatMessage, OverallReport, Submission, User
from app.schemas import ChatMessageCreate, ChatMessageRead, KnowledgeReferenceRead, OverallReportRead, SubmissionRead, SubmissionWorkspaceRead
from app.services.auth import get_current_user, require_owned_submission
from app.services.drawing_preprocess import add_preprocessed_model_drawings
from app.services.report_assistant import apply_report_assistant_update, build_report_assistant_fallback, generate_report_assistant_answer
from app.services.report_pdf import build_report_pdf, build_report_pdf_snapshot
from app.routers.submission_common import CANCELLED_SUBMISSIONS, REAL_LLM_PROVIDERS, resolve_llm_model, resolve_llm_provider
from app.routers.submission_crud import refresh_submission_attachments
from app.routers.projects import load_project_history_items
from app.routers.submission_report_data import build_model_error_message, build_report_response, load_report_reference_snapshots, load_submission_wiki_references, save_report_data
from app.routers.submission_stream import ensure_dashscope_model_file_urls

router = APIRouter(prefix="/api/submissions", tags=["submissions"])
LOGGER = logging.getLogger(__name__)


def _process_report_chat_in_worker(
    submission_id: int,
    content: str,
    tool: str,
    on_delta: Callable[[str], None] | None = None,
) -> dict:
    """在独立会话中生成、修订并保存回答，断开页面后仍可完成落库。"""
    session_factory = get_session_factory()
    with session_factory() as worker_db:
        submission = worker_db.execute(
            select(Submission)
            .options(
                selectinload(Submission.project),
                selectinload(Submission.drawing_files),
                selectinload(Submission.attachments),
            )
            .where(Submission.id == submission_id)
        ).scalar_one()
        report = worker_db.execute(
            select(OverallReport).where(OverallReport.submission_id == submission_id)
        ).scalar_one()
        assistant_model = get_settings().llm_assistant_model
        ensure_dashscope_model_file_urls(
            worker_db, list(submission.drawing_files), assistant_model
        )
        try:
            result = generate_report_assistant_answer(
                submission, report, content, tool, worker_db, on_delta,
            )
        except Exception:
            LOGGER.exception("报告助手后台处理失败，已使用报告内容生成稳定回答")
            result = build_report_assistant_fallback(report, content, tool)
        report_updated = apply_report_assistant_update(
            report, result.get("report_update"), content, worker_db,
        )
        response = ChatMessage(
            submission_id=submission_id,
            role="assistant",
            content=str(result["answer"]),
            tool=tool,
            citations=result.get("citations") or [],
            report_updated=report_updated,
        )
        worker_db.add(response)
        worker_db.commit()
        worker_db.refresh(response)
        updated_report = None
        if report_updated:
            evaluations = list(worker_db.execute(
                select(AgentEvaluation).where(AgentEvaluation.submission_id == submission_id)
            ).scalars())
            updated_report = build_report_response(report, evaluations, submission, worker_db)
        return ChatMessageRead(
            id=response.id,
            role=response.role,
            content=response.content,
            tool=response.tool,
            citations=response.citations,
            report_updated=response.report_updated,
            updated_report=updated_report,
            created_at=response.created_at,
        ).model_dump(mode="json")


@router.get("/{submission_id}/workspace", response_model=SubmissionWorkspaceRead)
async def get_submission_workspace(
    submission_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SubmissionWorkspaceRead:
    """一次返回进入工作台所需的项目、文件、历史和报告。"""
    submission = require_owned_submission(db, submission_id, user)
    refresh_submission_attachments(db, list(submission.attachments))
    overall_report = db.execute(
        select(OverallReport).where(OverallReport.submission_id == submission_id)
    ).scalar_one_or_none()
    report = None
    if overall_report is not None:
        evaluations = list(db.execute(
            select(AgentEvaluation).where(AgentEvaluation.submission_id == submission_id)
        ).scalars())
        report = build_report_response(overall_report, evaluations, submission, db)
    messages = list(db.execute(
        select(ChatMessage)
        .where(ChatMessage.submission_id == submission_id)
        .order_by(ChatMessage.id.asc())
    ).scalars())
    return SubmissionWorkspaceRead(
        project=submission.project,
        submission=submission,
        drawings=list(submission.drawing_files),
        attachments=list(submission.attachments),
        history=load_project_history_items(db, submission.project_id),
        report=report,
        chat_messages=messages,
    )

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


@router.get("/{submission_id}/report/export")
async def export_submission_report(
    submission_id: int,
    format: str = Query(default="pdf", pattern="^(pdf|markdown)$"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    """导出当前报告，默认生成适合阅读和保存的 PDF。"""
    submission = require_owned_submission(db, submission_id, user)
    report = await get_submission_report(submission_id, db, user)
    if format == "pdf":
        pdf_submission = build_report_pdf_snapshot(submission)
        pdf_bytes = await run_in_threadpool(build_report_pdf, pdf_submission, report)
        return Response(
            pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="archcritic-report-{submission_id}.pdf"'},
        )
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


@router.post("/{submission_id}/chat", response_model=ChatMessageRead)
async def create_chat_message(
    submission_id: int,
    payload: ChatMessageCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ChatMessageRead:
    """保存报告追问，并结合报告、知识库和当前图纸回答。"""
    submission = require_owned_submission(db, submission_id, user)
    report = db.execute(
        select(OverallReport).where(OverallReport.submission_id == submission_id)
    ).scalar_one_or_none()
    if report is None:
        raise HTTPException(status_code=409, detail="报告仍在生成中，请稍后再继续追问。")
    # 先保存用户问题，切页或模型等待期间重新进入报告也不会丢失。
    db.add(ChatMessage(
        submission_id=submission_id, role="user", content=payload.content.strip(), tool=payload.tool,
    ))
    db.commit()
    result = await run_in_threadpool(
        _process_report_chat_in_worker,
        submission_id, payload.content.strip(), payload.tool,
    )
    return ChatMessageRead.model_validate(result)


@router.post("/{submission_id}/chat/stream")
async def stream_chat_message(
    submission_id: int,
    payload: ChatMessageCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    """流式返回报告回答，最终结果和可能的报告修订仍完整保存。"""
    submission = require_owned_submission(db, submission_id, user)
    report = db.execute(
        select(OverallReport).where(OverallReport.submission_id == submission_id)
    ).scalar_one_or_none()
    if report is None:
        raise HTTPException(status_code=409, detail="报告仍在生成中，请稍后再继续追问。")
    db.add(ChatMessage(
        submission_id=submission_id, role="user", content=payload.content.strip(), tool=payload.tool,
    ))
    db.commit()

    async def event_stream():
        events: asyncio.Queue[tuple[str, object]] = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def emit(event: str, value: object) -> None:
            loop.call_soon_threadsafe(events.put_nowait, (event, value))

        def run_model() -> None:
            try:
                result = _process_report_chat_in_worker(
                    submission_id, payload.content.strip(), payload.tool,
                    lambda value: emit("delta", value),
                )
                emit("final", result)
            except Exception:
                LOGGER.exception("报告助手流式处理失败")
                emit("error", "AI 助手调用失败，请稍后重试。")

        # 独立守护线程不会随页面停止读取而中断，最终回答仍会保存到会话。
        threading.Thread(target=run_model, name=f"report-chat-{submission_id}", daemon=True).start()
        while True:
            event, data = await events.get()
            yield f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
            if event in {"final", "error"}:
                break

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


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
        add_preprocessed_model_drawings(payload, llm_provider, llm_model)
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
