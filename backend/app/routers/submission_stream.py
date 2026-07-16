"""流式评图接口，负责阶段事件、多 Agent 调用和模型图纸准备。"""

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.agents.function_agent import FunctionAgent, build_image_inputs, build_function_agent_context, function_agent_report_to_overall, validate_function_agent_output
from app.agents.prompts.function_agent_v1 import FUNCTION_AGENT_SYSTEM_PROMPT, build_function_agent_user_prompt
from app.agents.scheme_review import is_multi_agent_stage, iter_scheme_review_events
from app.config import get_settings
from app.database import get_db, get_session_factory
from app.llm.client import get_llm_client
from app.llm.dashscope_files import DashScopeFileClient, DashScopeUploadError
from app.models import AgentEvaluation, DrawingFile, OverallReport, Project, Submission, User
from app.services.auth import get_current_user, require_owned_submission
from app.services.uploads import resolve_local_upload
from app.routers.submission_common import CANCELLED_SUBMISSIONS, EvaluationCancelled, REAL_LLM_PROVIDERS, ensure_evaluation_active, resolve_llm_model, resolve_llm_provider
from app.routers.submission_crud import refresh_submission_attachments
from app.routers.submission_report_data import build_model_error_message, build_report_response, load_submission_wiki_references, save_report_data

router = APIRouter(prefix="/api/submissions", tags=["submissions"])

@router.post("/{submission_id}/evaluate-stream")
async def stream_submission_evaluation(
    submission_id: int,
    provider: str | None = Query(default=None),
    model: str | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    """以 SSE 形式实时返回模型评图输出，并在结束时保存报告。"""
    require_owned_submission(db, submission_id, user)
    return StreamingResponse(
        stream_evaluation_events(submission_id, user.id, provider, model),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def stream_evaluation_events(
    submission_id: int,
    user_id: int,
    provider: str | None = None,
    model: str | None = None,
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
        yield sse_event("stage", {
            "stage_id": "read_inputs",
            "status": "start",
            "message": "正在读取项目信息、任务书和图纸。",
        })
        yield sse_event("status", {"message": "正在准备评图上下文。"})
        submission = load_submission_for_evaluation(db, submission_id, user_id)
        yield sse_event("stage", {
            "stage_id": "read_inputs",
            "status": "done",
            "message": "项目资料读取完成。",
        })
        settings = get_settings()
        yield sse_event("stage", {
            "stage_id": "knowledge",
            "status": "start",
            "message": "正在匹配当前阶段的专项知识库依据。",
        })
        references = load_submission_wiki_references(settings.wiki_dir, submission)
        yield sse_event("stage", {
            "stage_id": "knowledge",
            "status": "done",
            "message": "知识库依据已准备完成。",
        })

        llm_provider = resolve_llm_provider(provider)
        llm_model = resolve_llm_model(llm_provider, model)
        submission.status = "evaluating"
        submission.selected_model_provider = llm_provider
        submission.selected_model_name = llm_model
        db.commit()
        ensure_evaluation_active(submission_id)
        yield sse_event("stage", {
            "stage_id": "model_input",
            "status": "start",
            "message": "正在准备模型可读取的图文输入。",
        })
        if llm_provider == "dashscope":
            yield sse_event("status", {"message": "正在上传模型可读取的图纸 URL。"})
            ensure_dashscope_model_file_urls(db, list(submission.drawing_files), llm_model)
            yield sse_event("stage", {
                "stage_id": "model_input",
                "status": "done",
                "message": "模型图纸 URL 已准备完成。",
            })
        elif llm_provider not in REAL_LLM_PROVIDERS:
            yield sse_event("stage", {
                "stage_id": "model_input",
                "status": "done",
                "message": "演示模型输入已准备完成。",
            })
            report_data = get_llm_client(llm_provider, llm_model).generate_evaluation(
                {
                    "project_name": submission.project.name,
                    "building_type": submission.project.building_type,
                    "design_stage": submission.design_stage,
                    "description": submission.description,
                }
            )
            yield sse_event("stage", {
                "stage_id": "report",
                "status": "start",
                "message": "正在生成并保存评图报告。",
            })
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
            yield sse_event("stage", {
                "stage_id": "report",
                "status": "done",
                "message": "评图报告已保存。",
            })
            yield sse_event("final", {"report": full_report.model_dump(mode="json")})
            return
        else:
            yield sse_event("stage", {
                "stage_id": "model_input",
                "status": "done",
                "message": "模型图文输入已准备完成。",
            })

        payload = build_function_agent_context(
            submission,
            list(submission.drawing_files),
            references,
            list(submission.attachments),
        )
        if is_multi_agent_stage(submission.design_stage):
            yield sse_event("status", {"message": f"正在调用 {llm_model} 按当前阶段顺序评审。"})
            llm_client = get_llm_client(llm_provider, llm_model)
            report_data = None
            for item in iter_scheme_review_events(llm_client, payload):
                ensure_evaluation_active(submission_id)
                if item["event"] == "report":
                    report_data = item["report"]
                    continue
                yield sse_event("agent", item)
            if report_data is None:
                raise RuntimeError("阶段化多 Agent 未返回综合报告。")
        else:
            yield sse_event("status", {"message": f"正在调用 {llm_model} 读取图纸。"})
            yield sse_event("agent", {
                "status": "start",
                "agent_type": "function_agent",
                "agent_name": "功能与流线 Agent",
                "message": "开始读取图纸并进行专项评审。",
            })
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
            yield sse_event("agent", {
                "status": "done",
                "agent_type": "function_agent",
                "agent_name": "功能与流线 Agent",
                "message": "专项评审完成。",
            })
        yield sse_event("stage", {
            "stage_id": "report",
            "status": "start",
            "message": "正在生成并保存评图报告。",
        })
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
        yield sse_event("stage", {
            "stage_id": "report",
            "status": "done",
            "message": "评图报告已保存。",
        })
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
            and not is_multi_agent_stage(submission.design_stage)
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


def load_submission_for_evaluation(
    db: Session,
    submission_id: int,
    user_id: int,
) -> Submission:
    """读取评图需要的提交、项目、图纸和既有报告。"""
    submission = db.execute(
        select(Submission)
        .options(
            selectinload(Submission.project),
            selectinload(Submission.agent_evaluations),
            selectinload(Submission.drawing_files),
            selectinload(Submission.attachments),
            selectinload(Submission.overall_report),
        )
        .join(Project, Project.id == Submission.project_id)
        .where(Submission.id == submission_id, Project.user_id == user_id)
    ).scalar_one_or_none()
    if submission is None:
        raise HTTPException(status_code=404, detail="未找到对应的方案提交。")
    refresh_submission_attachments(db, list(submission.attachments))
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
        file_path = resolve_local_upload(item.file_url)
        if file_path is None or not file_path.is_file():
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
