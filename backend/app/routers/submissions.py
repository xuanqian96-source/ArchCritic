"""提供方案提交、图纸上传与评图接口，供前端验证完整流程。"""

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
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
from app.config import get_settings
from app.database import get_db, get_session_factory
from app.llm.client import get_llm_client
from app.llm.dashscope_files import DashScopeFileClient
from app.models import AgentEvaluation, DrawingFile, OverallReport, Project, Submission
from app.schemas import (
    DrawingFileRead,
    KnowledgeReferenceRead,
    OverallReportRead,
    SubmissionCreate,
    SubmissionRead,
)
from app.wiki import load_wiki_references

router = APIRouter(prefix="/api/submissions", tags=["submissions"])

ALLOWED_DRAWING_TYPES = {"site", "plan", "analysis", "render"}
ALLOWED_IMAGE_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024


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
        raise HTTPException(status_code=400, detail="单张图片不能超过 10MB。")

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


@router.post("/{submission_id}/evaluate-demo", response_model=OverallReportRead)
async def evaluate_submission_demo(
    submission_id: int, db: Session = Depends(get_db)
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
    llm_client = get_llm_client(settings.llm_provider)
    references = load_wiki_references(settings.wiki_dir, submission.design_stage)
    if settings.llm_provider.lower() in {"openai", "dashscope"}:
        if settings.llm_provider.lower() == "dashscope":
            ensure_dashscope_model_file_urls(db, list(submission.drawing_files))
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
            timeout=settings.llm_timeout_seconds + 15,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=build_model_error_message(exc),
        ) from exc

    save_report_data(db, submission_id, report_data)

    overall_report = db.execute(
        select(OverallReport).where(OverallReport.submission_id == submission_id)
    ).scalar_one()
    agent_evaluations = list(
        db.execute(
            select(AgentEvaluation).where(AgentEvaluation.submission_id == submission_id)
        ).scalars()
    )

    return build_report_response(overall_report, agent_evaluations, submission)


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
    return build_report_response(overall_report, agent_evaluations, submission)


@router.get("/{submission_id}/references", response_model=list[KnowledgeReferenceRead])
async def list_submission_references(
    submission_id: int, db: Session = Depends(get_db)
) -> list[dict]:
    """从 Wiki 知识库返回当前提交对应的依据条目。"""
    submission = db.get(Submission, submission_id)
    if submission is None:
        raise HTTPException(status_code=404, detail="未找到对应的方案提交。")

    settings = get_settings()
    return load_wiki_references(settings.wiki_dir, submission.design_stage)


@router.get("/{submission_id}/evaluate-stream")
async def stream_submission_evaluation(submission_id: int) -> StreamingResponse:
    """以 SSE 形式实时返回模型评图输出，并在结束时保存报告。"""
    return StreamingResponse(
        stream_evaluation_events(submission_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def stream_evaluation_events(submission_id: int):
    """生成评图流式事件，供前端对话区实时展示。"""
    session_factory = get_session_factory()
    db = session_factory()
    try:
        yield sse_event("status", {"message": "正在准备评图上下文。"})
        submission = load_submission_for_evaluation(db, submission_id)
        settings = get_settings()
        references = load_wiki_references(settings.wiki_dir, submission.design_stage)

        if settings.llm_provider.lower() == "dashscope":
            yield sse_event("status", {"message": "正在上传模型可读取的图纸 URL。"})
            ensure_dashscope_model_file_urls(db, list(submission.drawing_files))
        elif settings.llm_provider.lower() not in {"openai", "dashscope"}:
            report_data = get_llm_client(settings.llm_provider).generate_evaluation(
                {
                    "project_name": submission.project.name,
                    "building_type": submission.project.building_type,
                    "design_stage": submission.design_stage,
                    "description": submission.description,
                }
            )
            save_report_data(db, submission_id, report_data)
            yield sse_event("final", {"report": report_data})
            return

        payload = build_function_agent_context(
            submission, list(submission.drawing_files), references
        )
        yield sse_event("status", {"message": "正在调用 Qwen3.6-Plus 读取图纸。"})
        raw_output_parts = []
        for item in stream_function_agent_events(payload):
            if item["event"] == "raw":
                raw_output_parts.append(item["text"])
            else:
                yield sse_event(item["event"], {"text": item["text"]})
        raw_output = json.loads("".join(raw_output_parts) or "{}")
        report = validate_function_agent_output(raw_output)
        report_data = function_agent_report_to_overall(report)
        save_report_data(db, submission_id, report_data)
        yield sse_event("final", {"report": report_data})
    except Exception as exc:
        yield sse_event("error", {"message": build_model_error_message(exc)})
    finally:
        db.close()


def stream_function_agent_events(payload: dict):
    """流式调用功能 Agent，边生成边返回文本，结束后解析 JSON。"""
    settings = get_settings()
    llm_client = get_llm_client(settings.llm_provider)
    agent = FunctionAgent(
        llm_client.client,
        llm_client.model,
        llm_client.structured_output_mode,
        llm_client.max_tokens,
        llm_client.image_detail,
        llm_client.extra_body,
    )
    content: list[dict] = [
        {"type": "text", "text": build_function_agent_user_prompt(payload)}
    ]
    content.extend(build_image_inputs(payload["drawings"], detail=agent.image_detail))
    stream = llm_client.client.chat.completions.create(
        model=llm_client.model,
        messages=[
            {"role": "system", "content": FUNCTION_AGENT_SYSTEM_PROMPT},
            {"role": "user", "content": content},
        ],
        response_format={"type": "json_object"},
        temperature=0.2,
        max_tokens=llm_client.max_tokens,
        stream=True,
        stream_options={"include_usage": True},
        extra_body=llm_client.extra_body,
    )

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
    db: Session, drawing_files: list[DrawingFile]
) -> None:
    """确保每张图纸都有百炼可访问的临时 oss:// URL。"""
    settings = get_settings()
    client = DashScopeFileClient(
        settings.dashscope_api_key, settings.llm_model, settings.llm_timeout_seconds
    )
    changed = False
    for item in drawing_files:
        if is_model_file_url_valid(item):
            continue
        file_path = local_upload_path(item.file_url)
        if file_path is None:
            continue
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


def save_report_data(db: Session, submission_id: int, report_data: dict) -> None:
    """保存模型生成的综合报告和各 Agent 分项。"""
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


def build_report_response(
    overall_report: OverallReport,
    agent_evaluations: list[AgentEvaluation],
    submission: Submission | None = None,
) -> OverallReportRead:
    """把数据库中的报告和分项评价整理成接口返回结构。"""
    references = []
    if submission is not None:
        settings = get_settings()
        references = load_wiki_references(settings.wiki_dir, submission.design_stage)

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
            }
            for item in agent_evaluations
        ],
        references=references,
    )


def build_model_error_message(exc: Exception) -> str:
    """把模型调用异常转换成前端可读的中文提示。"""
    message = str(exc)
    if isinstance(exc, asyncio.TimeoutError) or "timed out" in message.lower():
        return "真实模型评图调用超时：已停止等待模型返回。请稍后重试，或把图纸压缩到更小尺寸后再评图。"
    if "insufficient_quota" in message or "exceeded your current quota" in message:
        return "真实模型评图调用失败：OpenAI API 额度不足或计费未启用，请检查 Platform 余额和 Billing 设置。"
    if "Connection error" in message or "APIConnectionError" in message:
        return "真实模型评图调用失败：后端无法连接 OpenAI API，请检查网络或代理设置。"
    if "invalid_api_key" in message or "Incorrect API key" in message:
        return "真实模型评图调用失败：OpenAI API Key 无效，请重新配置。"
    return "真实模型评图调用失败：模型服务暂时不可用，请稍后重试。"
