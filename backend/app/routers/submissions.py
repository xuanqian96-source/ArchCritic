"""提供方案提交、图纸上传与评图接口，供前端验证完整流程。"""

import asyncio
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import PlainTextResponse, StreamingResponse
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.agents.function_agent import (
    FunctionAgent,
    build_image_inputs,
    build_function_agent_context,
    function_agent_report_to_overall,
    validate_function_agent_output,
)
from app.agents.prompts.function_agent_v1 import (
    FUNCTION_AGENT_SYSTEM_PROMPT,
    build_function_agent_user_prompt,
)
from app.agents.scheme_review import is_scheme_stage, iter_scheme_review_events
from app.config import get_settings
from app.database import get_db, get_session_factory
from app.llm.client import get_llm_client
from app.llm.dashscope_files import DashScopeFileClient, DashScopeUploadError
from app.models import (
    AgentEvaluation,
    Attachment,
    ChatMessage,
    DrawingFile,
    OverallReport,
    Project,
    ReportReference,
    Submission,
)
from app.schemas import (
    AttachmentRead,
    ChatMessageCreate,
    ChatMessageRead,
    DrawingFileRead,
    KnowledgeReferenceRead,
    OverallReportRead,
    SubmissionCreate,
    SubmissionRead,
    SubmissionUpdate,
)
from app.wiki import load_wiki_references

router = APIRouter(prefix="/api/submissions", tags=["submissions"])

REAL_LLM_PROVIDERS = {"openai", "dashscope", "gemini"}
ALLOWED_DRAWING_TYPES = {"site", "plan", "analysis", "render"}
ALLOWED_IMAGE_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
}
MAX_UPLOAD_BYTES = 15 * 1024 * 1024
MAX_ATTACHMENT_BYTES = 20 * 1024 * 1024
ALLOWED_ATTACHMENT_TYPES = {
    "application/pdf": ".pdf",
    "application/msword": ".doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "text/plain": ".txt",
}
CANCELLED_SUBMISSIONS: set[int] = set()
MODEL_PRESETS = {
    "mock": "demo",
    "openai": "gpt-4o-mini",
    "dashscope": "qwen3.6-plus",
    "gemini": "gemini-2.5-flash",
}


class EvaluationCancelled(Exception):
    """表示用户主动暂停本次评图。"""


def ensure_evaluation_active(submission_id: int) -> None:
    """在模型调用之间检查用户是否已请求暂停。"""
    if submission_id in CANCELLED_SUBMISSIONS:
        raise EvaluationCancelled()


def resolve_llm_provider(provider: str | None) -> str:
    """解析本次评图使用的模型来源，默认读取环境配置。"""
    settings = get_settings()
    resolved = (provider or settings.llm_provider).strip().lower()
    aliases = {"qwen": "dashscope", "qianwen": "dashscope", "bailian": "dashscope"}
    resolved = aliases.get(resolved, resolved)
    if resolved not in {"mock", *REAL_LLM_PROVIDERS}:
        raise HTTPException(status_code=400, detail=f"暂不支持的模型来源：{resolved}。")
    return resolved


def resolve_llm_model(provider: str, model: str | None) -> str:
    """解析本次评图使用的模型名称。"""
    cleaned_model = (model or "").strip()
    if cleaned_model:
        return cleaned_model
    settings = get_settings()
    if provider == settings.llm_provider.lower() and settings.llm_model:
        return settings.llm_model
    return MODEL_PRESETS.get(provider, settings.llm_model)


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
        status=payload.status,
        enabled_agents=payload.enabled_agents,
        selected_model_provider=payload.selected_model_provider,
        selected_model_name=payload.selected_model_name,
    )
    db.add(submission)
    db.commit()
    db.refresh(submission)
    return submission


@router.patch("/{submission_id}", response_model=SubmissionRead)
async def update_submission(
    submission_id: int, payload: SubmissionUpdate, db: Session = Depends(get_db)
) -> Submission:
    """修改草稿提交、阶段、模型和 Agent 选择。"""
    submission = db.get(Submission, submission_id)
    if submission is None:
        raise HTTPException(status_code=404, detail="未找到对应的方案提交。")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(submission, field, value)
    db.commit()
    db.refresh(submission)
    return submission


@router.get("/{submission_id}", response_model=SubmissionRead)
async def get_submission(
    submission_id: int, db: Session = Depends(get_db)
) -> Submission:
    """返回一次提交记录。"""
    submission = db.get(Submission, submission_id)
    if submission is None:
        raise HTTPException(status_code=404, detail="未找到对应的方案提交。")
    return submission


@router.post(
    "/{submission_id}/files",
    response_model=DrawingFileRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_submission_file(
    submission_id: int,
    drawing_type: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> DrawingFile:
    """上传并保存某次提交下的一张图纸。"""
    submission = db.get(Submission, submission_id)
    if submission is None:
        raise HTTPException(status_code=404, detail="未找到对应的方案提交。")

    if drawing_type not in ALLOWED_DRAWING_TYPES:
        raise HTTPException(status_code=400, detail="图纸类型不在支持范围内。")

    mime_type = file.content_type or ""
    extension = ALLOWED_IMAGE_TYPES.get(mime_type)
    if extension is None:
        raise HTTPException(status_code=400, detail="当前只支持图片文件。")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="上传文件不能为空。")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="单张图片不能超过 15MB。")

    settings = get_settings()
    relative_path = Path("submissions") / str(submission_id) / f"{uuid4().hex}{extension}"
    target_path = Path(settings.upload_dir) / relative_path
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_bytes(content)

    file_url = f"/uploads/{relative_path.as_posix()}"
    drawing_file = DrawingFile(
        submission_id=submission_id,
        drawing_type=drawing_type,
        original_name=file.filename or "未命名图纸",
        file_url=file_url,
        mime_type=mime_type,
    )

    submission.image_urls = [*(submission.image_urls or []), file_url]
    db.add(drawing_file)
    db.commit()
    db.refresh(drawing_file)
    return drawing_file


@router.get("/{submission_id}/files", response_model=list[DrawingFileRead])
async def list_submission_files(
    submission_id: int, db: Session = Depends(get_db)
) -> list[DrawingFile]:
    """返回某次提交下已上传的图纸列表。"""
    submission = db.get(Submission, submission_id)
    if submission is None:
        raise HTTPException(status_code=404, detail="未找到对应的方案提交。")

    result = db.execute(
        select(DrawingFile)
        .where(DrawingFile.submission_id == submission_id)
        .order_by(DrawingFile.id.asc())
    )
    return list(result.scalars().all())


@router.post(
    "/{submission_id}/attachments",
    response_model=AttachmentRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_submission_attachment(
    submission_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> Attachment:
    """上传任务书等补充资料。"""
    submission = db.get(Submission, submission_id)
    if submission is None:
        raise HTTPException(status_code=404, detail="未找到对应的方案提交。")
    mime_type = file.content_type or ""
    extension = ALLOWED_ATTACHMENT_TYPES.get(mime_type)
    if extension is None:
        raise HTTPException(status_code=400, detail="任务书仅支持 PDF、Word 或文本文件。")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="上传文件不能为空。")
    if len(content) > MAX_ATTACHMENT_BYTES:
        raise HTTPException(status_code=400, detail="单个任务书不能超过 20MB。")
    relative_path = Path("attachments") / str(submission_id) / f"{uuid4().hex}{extension}"
    target_path = Path(get_settings().upload_dir) / relative_path
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_bytes(content)
    attachment = Attachment(
        submission_id=submission_id,
        original_name=file.filename or "未命名任务书",
        file_url=f"/uploads/{relative_path.as_posix()}",
        mime_type=mime_type,
    )
    db.add(attachment)
    db.commit()
    db.refresh(attachment)
    return attachment


@router.get("/{submission_id}/attachments", response_model=list[AttachmentRead])
async def list_submission_attachments(
    submission_id: int, db: Session = Depends(get_db)
) -> list[Attachment]:
    """返回某次提交下的补充资料。"""
    if db.get(Submission, submission_id) is None:
        raise HTTPException(status_code=404, detail="未找到对应的方案提交。")
    result = db.execute(
        select(Attachment)
        .where(Attachment.submission_id == submission_id)
        .order_by(Attachment.id.asc())
    )
    return list(result.scalars().all())


@router.post("/{submission_id}/cancel-evaluation", response_model=SubmissionRead)
async def cancel_submission_evaluation(
    submission_id: int, db: Session = Depends(get_db)
) -> Submission:
    """标记当前评图任务暂停，并在下一个可中断节点停止。"""
    submission = db.get(Submission, submission_id)
    if submission is None:
        raise HTTPException(status_code=404, detail="未找到对应的方案提交。")
    CANCELLED_SUBMISSIONS.add(submission_id)
    submission.status = "cancelled"
    db.commit()
    db.refresh(submission)
    return submission


@router.get("/{submission_id}/report/export", response_class=PlainTextResponse)
async def export_submission_report(
    submission_id: int, db: Session = Depends(get_db)
) -> PlainTextResponse:
    """导出当前报告为 Markdown 文件。"""
    report = await get_submission_report(submission_id, db)
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
    submission_id: int, payload: ChatMessageCreate, db: Session = Depends(get_db)
) -> ChatMessage:
    """保存报告追问，并按当前报告给出可核对的回答。"""
    submission = db.get(Submission, submission_id)
    if submission is None:
        raise HTTPException(status_code=404, detail="未找到对应的方案提交。")
    report = db.execute(
        select(OverallReport).where(OverallReport.submission_id == submission_id)
    ).scalar_one_or_none()
    if report is None:
        answer = "报告仍在生成中，请稍后再继续追问。"
    elif "必须" in payload.content or "修改" in payload.content:
        answer = "本轮必须修改项：" + "；".join(report.must_fix[:3])
    else:
        answer = f"结合本次评分，{report.summary} 建议先复核：" + "；".join(report.should_improve[:2])
    db.add(ChatMessage(submission_id=submission_id, role="user", content=payload.content))
    response = ChatMessage(submission_id=submission_id, role="assistant", content=answer)
    db.add(response)
    db.commit()
    db.refresh(response)
    return response


@router.get("/{submission_id}/chat/messages", response_model=list[ChatMessageRead])
async def list_chat_messages(
    submission_id: int, db: Session = Depends(get_db)
) -> list[ChatMessage]:
    """返回当前提交的全部报告追问记录。"""
    if db.get(Submission, submission_id) is None:
        raise HTTPException(status_code=404, detail="未找到对应的方案提交。")
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
) -> OverallReportRead:
    """为指定提交生成一份评图结果。"""
    query = (
        select(Submission)
        .options(
            selectinload(Submission.project),
            selectinload(Submission.agent_evaluations),
            selectinload(Submission.drawing_files),
            selectinload(Submission.overall_report),
        )
        .where(Submission.id == submission_id)
    )
    result = db.execute(query)
    submission = result.scalar_one_or_none()

    if submission is None:
        raise HTTPException(status_code=404, detail="未找到对应的方案提交。")

    settings = get_settings()
    llm_provider = resolve_llm_provider(provider)
    llm_model = resolve_llm_model(llm_provider, model)
    llm_client = get_llm_client(llm_provider, llm_model)
    references = load_submission_wiki_references(settings.wiki_dir, submission)
    if llm_provider in REAL_LLM_PROVIDERS:
        if llm_provider == "dashscope":
            ensure_dashscope_model_file_urls(db, list(submission.drawing_files), llm_model)
        payload = build_function_agent_context(
            submission, list(submission.drawing_files), references
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
                and is_scheme_stage(submission.design_stage)
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
    submission_id: int, db: Session = Depends(get_db)
) -> OverallReportRead:
    """返回某次提交已经生成的评图报告。"""
    submission = db.get(Submission, submission_id)
    if submission is None:
        raise HTTPException(status_code=404, detail="未找到对应的方案提交。")

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
    submission_id: int, db: Session = Depends(get_db)
) -> list[dict]:
    """从 Wiki 知识库返回当前提交对应的依据条目。"""
    submission = db.get(Submission, submission_id)
    if submission is None:
        raise HTTPException(status_code=404, detail="未找到对应的方案提交。")

    settings = get_settings()
    snapshots = load_report_reference_snapshots(db, submission_id)
    if snapshots:
        return snapshots
    return load_submission_wiki_references(settings.wiki_dir, submission)


@router.get("/{submission_id}/evaluate-stream")
async def stream_submission_evaluation(
    submission_id: int,
    provider: str | None = Query(default=None),
    model: str | None = Query(default=None),
) -> StreamingResponse:
    """以 SSE 形式实时返回模型评图输出，并在结束时保存报告。"""
    return StreamingResponse(
        stream_evaluation_events(submission_id, provider, model),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def stream_evaluation_events(
    submission_id: int, provider: str | None = None, model: str | None = None
):
    """生成评图流式事件，供前端对话区实时展示。"""
    session_factory = get_session_factory()
    db = session_factory()
    payload = None
    submission = None
    llm_provider = None
    llm_model = None
    try:
        CANCELLED_SUBMISSIONS.discard(submission_id)
        yield sse_event("status", {"message": "正在准备评图上下文。"})
        submission = load_submission_for_evaluation(db, submission_id)
        settings = get_settings()
        references = load_submission_wiki_references(settings.wiki_dir, submission)

        llm_provider = resolve_llm_provider(provider)
        llm_model = resolve_llm_model(llm_provider, model)
        submission.status = "evaluating"
        submission.selected_model_provider = llm_provider
        submission.selected_model_name = llm_model
        db.commit()
        ensure_evaluation_active(submission_id)
        if llm_provider == "dashscope":
            yield sse_event("status", {"message": "正在上传模型可读取的图纸 URL。"})
            ensure_dashscope_model_file_urls(db, list(submission.drawing_files), llm_model)
        elif llm_provider not in REAL_LLM_PROVIDERS:
            report_data = get_llm_client(llm_provider, llm_model).generate_evaluation(
                {
                    "project_name": submission.project.name,
                    "building_type": submission.project.building_type,
                    "design_stage": submission.design_stage,
                    "description": submission.description,
                }
            )
            save_report_data(db, submission_id, report_data, references)
            overall_report = db.execute(
                select(OverallReport).where(OverallReport.submission_id == submission_id)
            ).scalar_one()
            agent_evaluations = list(
                db.execute(
                    select(AgentEvaluation).where(AgentEvaluation.submission_id == submission_id)
                ).scalars()
            )
            full_report = build_report_response(
                overall_report, agent_evaluations, submission, db
            )
            submission.status = "completed"
            db.commit()
            yield sse_event("final", {"report": full_report.model_dump(mode="json")})
            return

        payload = build_function_agent_context(submission, list(submission.drawing_files), references)
        if is_scheme_stage(submission.design_stage):
            yield sse_event("status", {"message": f"正在调用 {llm_model} 顺序评审方案。"})
            llm_client = get_llm_client(llm_provider, llm_model)
            report_data = None
            for item in iter_scheme_review_events(llm_client, payload):
                ensure_evaluation_active(submission_id)
                if item["event"] == "report":
                    report_data = item["report"]
                    continue
                yield sse_event("agent", item)
            if report_data is None:
                raise RuntimeError("方案阶段多 Agent 未返回综合报告。")
        else:
            yield sse_event("status", {"message": f"正在调用 {llm_model} 读取图纸。"})
            raw_output_parts = []
            for item in stream_function_agent_events(payload, llm_provider, llm_model):
                ensure_evaluation_active(submission_id)
                if item["event"] == "raw":
                    raw_output_parts.append(item["text"])
                else:
                    yield sse_event(item["event"], {"text": item["text"]})
            raw_output = json.loads("".join(raw_output_parts) or "{}")
            report = validate_function_agent_output(raw_output)
            report_data = function_agent_report_to_overall(report, payload)
        save_report_data(db, submission_id, report_data, references)
        overall_report = db.execute(
            select(OverallReport).where(OverallReport.submission_id == submission_id)
        ).scalar_one()
        agent_evaluations = list(
            db.execute(
                select(AgentEvaluation).where(AgentEvaluation.submission_id == submission_id)
            ).scalars()
        )
        full_report = build_report_response(overall_report, agent_evaluations, submission, db)
        submission.status = "completed"
        db.commit()
        yield sse_event("final", {"report": full_report.model_dump(mode="json")})
    except EvaluationCancelled:
        if submission is not None:
            submission.status = "cancelled"
            db.commit()
        yield sse_event("status", {"message": "评图已暂停。"})
    except Exception as exc:
        if submission is not None:
            submission.status = "failed"
            db.commit()
        can_retry_stream = (
            payload is not None
            and submission is not None
            and llm_provider in REAL_LLM_PROVIDERS
            and not is_scheme_stage(submission.design_stage)
        )
        if can_retry_stream:
            yield sse_event(
                "status",
                {"message": "流式输出中断，正在改用非流式结构化评图兜底。"},
            )
            try:
                report_data = get_llm_client(llm_provider, llm_model).generate_evaluation(payload)
                save_report_data(db, submission_id, report_data, payload.get("references", []))
                overall_report = db.execute(
                    select(OverallReport).where(OverallReport.submission_id == submission_id)
                ).scalar_one()
                agent_evaluations = list(
                    db.execute(
                        select(AgentEvaluation).where(AgentEvaluation.submission_id == submission_id)
                    ).scalars()
                )
                full_report = build_report_response(
                    overall_report, agent_evaluations, submission, db
                )
                submission.status = "completed"
                db.commit()
                yield sse_event("final", {"report": full_report.model_dump(mode="json")})
                return
            except Exception as fallback_exc:
                message = (
                    f"{build_model_error_message(exc)}；兜底调用也失败："
                    f"{build_model_error_message(fallback_exc)}"
                )
                yield sse_event("error", {"message": message})
                return
        yield sse_event("error", {"message": build_model_error_message(exc)})
    finally:
        db.close()


def stream_function_agent_events(
    payload: dict, provider: str | None = None, model: str | None = None
):
    """流式调用功能 Agent，边生成边返回文本，结束后解析 JSON。"""
    settings = get_settings()
    llm_provider = resolve_llm_provider(provider)
    llm_model = resolve_llm_model(llm_provider, model)
    llm_client = get_llm_client(llm_provider, llm_model)
    agent = FunctionAgent(
        llm_client.client,
        llm_client.model,
        llm_client.structured_output_mode,
        llm_client.max_tokens,
        llm_client.image_detail,
        llm_client.extra_body,
        llm_client.reasoning_effort,
    )
    content: list[dict] = [
        {"type": "text", "text": build_function_agent_user_prompt(payload)}
    ]
    content.extend(build_image_inputs(payload["drawings"], detail=agent.image_detail))
    create_kwargs = {
        "model": llm_client.model,
        "messages": [
            {"role": "system", "content": FUNCTION_AGENT_SYSTEM_PROMPT},
            {"role": "user", "content": content},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.2,
        "max_tokens": llm_client.max_tokens,
        "stream": True,
        "extra_body": llm_client.extra_body,
    }
    if llm_provider != "gemini":
        create_kwargs["stream_options"] = {"include_usage": True}
    if llm_client.reasoning_effort:
        create_kwargs["reasoning_effort"] = llm_client.reasoning_effort

    stream = llm_client.client.chat.completions.create(**create_kwargs)

    for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        reasoning = getattr(delta, "reasoning_content", None)
        if reasoning:
            yield {"event": "reasoning", "text": reasoning}
        text = delta.content or ""
        if text:
            yield {"event": "raw", "text": text}
            yield {"event": "delta", "text": text}


def sse_event(event: str, data: dict) -> str:
    """把事件和数据格式化为 SSE 文本。"""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def load_submission_for_evaluation(db: Session, submission_id: int) -> Submission:
    """读取评图需要的提交、项目、图纸和既有报告。"""
    submission = db.execute(
        select(Submission)
        .options(
            selectinload(Submission.project),
            selectinload(Submission.agent_evaluations),
            selectinload(Submission.drawing_files),
            selectinload(Submission.overall_report),
        )
        .where(Submission.id == submission_id)
    ).scalar_one_or_none()
    if submission is None:
        raise HTTPException(status_code=404, detail="未找到对应的方案提交。")
    return submission


def ensure_dashscope_model_file_urls(
    db: Session, drawing_files: list[DrawingFile], model: str | None = None
) -> None:
    """确保每张图纸都有百炼可访问的临时 oss:// URL。"""
    settings = get_settings()
    client = DashScopeFileClient(
        settings.dashscope_api_key, model or settings.llm_model, settings.llm_timeout_seconds
    )
    changed = False
    for item in drawing_files:
        if is_model_file_url_valid(item):
            continue
        file_path = local_upload_path(item.file_url)
        if file_path is None:
            raise DashScopeUploadError(
                f"找不到本地图纸文件，无法上传到百炼：{item.original_name}"
            )
        result = client.upload_file(file_path, item.mime_type)
        item.model_file_url = result.url
        item.model_file_expires_at = result.expires_at
        changed = True
    if changed:
        db.commit()


def is_model_file_url_valid(item: DrawingFile) -> bool:
    """判断已缓存的百炼临时 URL 是否仍可复用。"""
    if not item.model_file_url:
        return False
    if item.model_file_expires_at is None:
        return True
    expires_at = item.model_file_expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at > datetime.now(timezone.utc)


def local_upload_path(file_url: str) -> Path | None:
    """把 /uploads 地址转换为本地文件路径。"""
    if not file_url.startswith("/uploads/"):
        return None
    settings = get_settings()
    file_path = (Path(settings.upload_dir) / file_url.removeprefix("/uploads/")).resolve()
    upload_root = Path(settings.upload_dir).resolve()
    if upload_root not in file_path.parents or not file_path.is_file():
        return None
    return file_path


def save_report_data(
    db: Session,
    submission_id: int,
    report_data: dict,
    references: list[dict] | None = None,
) -> None:
    """保存模型生成的综合报告和各 Agent 分项。"""
    db.execute(delete(ReportReference).where(ReportReference.submission_id == submission_id))
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
                details=agent_item.get("details") or {},
            )
        )

    overall_report = OverallReport(
        submission_id=submission_id,
        overall_score=report_data["overall_score"],
        grade=report_data["grade"],
        summary=report_data["summary"],
        must_fix=report_data["must_fix"],
        should_improve=report_data["should_improve"],
        optional_improvements=report_data["optional_improvements"],
        strengths=report_data["strengths"],
    )
    db.add(overall_report)
    db.flush()
    save_reference_snapshots(db, submission_id, overall_report.id, references or [])
    db.commit()


def build_report_response(
    overall_report: OverallReport,
    agent_evaluations: list[AgentEvaluation],
    submission: Submission | None = None,
    db: Session | None = None,
) -> OverallReportRead:
    """把数据库中的报告和分项评价整理成接口返回结构。"""
    references = []
    if submission is not None:
        if db is not None:
            references = load_report_reference_snapshots(db, submission.id)
        if not references:
            settings = get_settings()
            references = load_submission_wiki_references(settings.wiki_dir, submission)

    return OverallReportRead(
        id=overall_report.id,
        submission_id=overall_report.submission_id,
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
                "details": item.details or {},
            }
            for item in agent_evaluations
        ],
        references=references,
        feedback=build_feedback_items(
            {
                "must_fix": overall_report.must_fix,
                "should_improve": overall_report.should_improve,
                "optional_improvements": overall_report.optional_improvements,
                "strengths": overall_report.strengths,
            },
            references,
        ),
    )


def build_feedback_items(feedback: dict[str, list[str]], references: list[dict]) -> dict:
    """把报告反馈中的知识编号整理成前端可点击引用。"""
    valid_reference_ids = {
        str(item.get("reference_id", "")).upper()
        for item in references
        if item.get("reference_id")
    }
    return {
        category: [
            {
                "text": str(text),
                "reference_ids": extract_reference_ids(str(text), valid_reference_ids),
            }
            for text in items or []
        ]
        for category, items in feedback.items()
    }


def extract_reference_ids(text: str, valid_reference_ids: set[str]) -> list[str]:
    """从反馈文本中提取本次报告真实存在的知识编号。"""
    ids = re.findall(r"\[(K\d+)\]", text, flags=re.IGNORECASE)
    seen: set[str] = set()
    reference_ids = []
    for item in ids:
        normalized = item.upper()
        if normalized in valid_reference_ids and normalized not in seen:
            seen.add(normalized)
            reference_ids.append(normalized)
    return reference_ids


def save_reference_snapshots(
    db: Session,
    submission_id: int,
    report_id: int,
    references: list[dict],
) -> None:
    """保存本次评图实际使用的知识库依据快照。"""
    for index, item in enumerate(references, start=1):
        db.add(
            ReportReference(
                submission_id=submission_id,
                report_id=report_id,
                position=index,
                reference_id=str(item.get("reference_id") or f"K{index}"),
                title=str(item.get("title") or ""),
                source_type=str(item.get("source_type") or ""),
                excerpt=str(item.get("excerpt") or ""),
                dimension=str(item.get("dimension") or ""),
                path=str(item.get("path") or ""),
                content=str(item.get("content") or ""),
                display_content=str(item.get("display_content") or ""),
                image_urls=item.get("image_urls") or [],
            )
        )


def load_report_reference_snapshots(db: Session, submission_id: int) -> list[dict]:
    """读取一次评图保存下来的知识库依据快照。"""
    rows = db.execute(
        select(ReportReference)
        .where(ReportReference.submission_id == submission_id)
        .order_by(ReportReference.position.asc(), ReportReference.id.asc())
    ).scalars()
    return [
        {
            "reference_id": item.reference_id,
            "title": item.title,
            "source_type": item.source_type,
            "excerpt": item.excerpt,
            "dimension": item.dimension,
            "path": item.path,
            "content": item.content,
            "display_content": item.display_content,
            "image_urls": item.image_urls,
        }
        for item in rows
    ]


def load_submission_wiki_references(wiki_dir: str, submission: Submission) -> list[dict]:
    """根据提交上下文从完整 Wiki 中检索相关知识依据。"""
    project = submission.project
    return load_wiki_references(
        wiki_dir,
        submission.design_stage,
        query_context={
            "project_name": project.name,
            "building_type": project.building_type,
            "design_stage": submission.design_stage,
            "description": submission.description,
            "drawing_types": [item.drawing_type for item in submission.drawing_files],
        },
    )


def build_model_error_message(exc: Exception) -> str:
    """把模型调用异常转换成前端可读的中文提示。"""
    message = str(exc)
    if isinstance(exc, DashScopeUploadError) or "百炼临时存储失败" in message:
        return f"图纸上传到百炼临时 URL 失败：{message}"
    if isinstance(exc, json.JSONDecodeError) or "Expecting value" in message:
        return "千问已返回内容，但结构化 JSON 不完整或格式错误，系统未能解析成报告。"
    if "模型 JSON 输出达到长度上限" in message:
        return "模型评审内容过长，报告在返回时被截断。"
    if isinstance(exc, asyncio.TimeoutError) or "timed out" in message.lower():
        return "真实模型评图调用超时：已停止等待模型返回。"
    if "ReadTimeout" in message or "APITimeoutError" in message:
        return "千问流式输出超时：模型读取图纸或生成报告时间过长。"
    if "APIStatusError" in message or "BadRequest" in message:
        return f"千问接口拒绝本次请求：{message[:240]}"
    if "insufficient_quota" in message or "exceeded your current quota" in message:
        return "真实模型评图调用失败：OpenAI API 额度不足或计费未启用，请检查 Platform 余额和 Billing 设置。"
    if "Connection error" in message or "APIConnectionError" in message:
        return "真实模型评图调用失败：后端无法连接模型 API，请检查网络或代理设置。"
    if "invalid_api_key" in message or "Incorrect API key" in message:
        return "真实模型评图调用失败：API Key 无效，请重新配置。"
    return f"真实模型评图调用失败：{message[:240] or '模型服务暂时不可用。'}"
