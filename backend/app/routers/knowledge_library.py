"""提供知识库浏览、建筑知识助手会话和缩略图接口。"""

import asyncio
import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.knowledge_assistant_schemas import (
    KnowledgeAssistantChatCreate,
    KnowledgeAssistantChatRead,
    KnowledgeConversationRead,
    KnowledgeAssistantMessageRead,
)
from app.knowledge_quiz_schemas import KnowledgeQuizAnswerCreate
from app.models import KnowledgeAssistantMessage, KnowledgeConversation, User
from app.services.auth import get_current_user
from app.services.knowledge_assistant import KnowledgeAssistantModelError, generate_knowledge_answer
from app.services.knowledge_library import build_library_payload, get_library_item, render_library_thumbnail
from app.services.knowledge_quiz import build_knowledge_quiz_bank, evaluate_quiz_answer


router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


@router.get("")
async def list_knowledge_library(_: User = Depends(get_current_user)) -> dict:
    """返回学习浏览页所需的知识卡和案例卡目录。"""
    return build_library_payload(get_settings().wiki_dir)


@router.get("/quiz")
async def list_knowledge_quiz(_: User = Depends(get_current_user)) -> dict:
    """返回不含正确答案、可按难度进入的多题型知识测试题库。"""
    return build_knowledge_quiz_bank(get_settings().wiki_dir)


@router.post("/quiz/answer")
async def answer_knowledge_quiz(
    payload: KnowledgeQuizAnswerCreate,
    _: User = Depends(get_current_user),
) -> dict:
    """判定一道知识测试题，提交后才返回正确答案和解析。"""
    result = evaluate_quiz_answer(
        get_settings().wiki_dir,
        payload.question_id,
        payload.answer,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="知识测试题不存在或已停止使用。")
    return result


def _get_owned_conversation(
    db: Session,
    conversation_id: str,
    user: User,
    create: bool = False,
    selected_tool: str = "none",
) -> KnowledgeConversation:
    """读取当前用户会话；首次提问时允许创建。"""
    try:
        normalized_id = str(UUID(conversation_id))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="知识助手会话编号无效。") from exc
    conversation = db.get(KnowledgeConversation, normalized_id)
    if conversation is not None and conversation.user_id != user.id:
        raise HTTPException(status_code=404, detail="知识助手会话不存在。")
    if conversation is None:
        if not create:
            raise HTTPException(status_code=404, detail="知识助手会话不存在。")
        conversation = KnowledgeConversation(
            id=normalized_id,
            user_id=user.id,
            selected_tool=selected_tool,
        )
        db.add(conversation)
        db.flush()
    return conversation


@router.post("/assistant/chat", response_model=KnowledgeAssistantChatRead)
async def chat_with_knowledge_assistant(
    payload: KnowledgeAssistantChatCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """使用默认真实模型回答，并只允许推荐后端候选中的卡片。"""
    conversation = _get_owned_conversation(
        db, payload.conversation_id, user, create=True, selected_tool=payload.tool
    )
    history_rows = list(db.execute(
        select(KnowledgeAssistantMessage)
        .where(KnowledgeAssistantMessage.conversation_id == conversation.id)
        .order_by(KnowledgeAssistantMessage.id.desc())
        .limit(20)
    ).scalars().all())
    history = [
        {"role": row.role, "content": row.content}
        for row in reversed(history_rows)
        if row.role in {"user", "assistant"}
    ]
    # 用户消息先落库，模型较慢或失败时也能在重新打开后看到已发送内容。
    conversation.selected_tool = payload.tool
    db.add(KnowledgeAssistantMessage(
        conversation_id=conversation.id,
        role="user",
        content=payload.message.strip(),
        tool=payload.tool,
    ))
    db.commit()
    try:
        settings = get_settings()
        result = await asyncio.to_thread(
            generate_knowledge_answer,
            payload.tool,
            payload.message.strip(),
            payload.context.model_dump(),
            history,
            settings.wiki_dir,
        )
    except KnowledgeAssistantModelError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    db.add(KnowledgeAssistantMessage(
        conversation_id=conversation.id,
        role="assistant",
        content=result["answer"],
        tool=payload.tool,
        result=result,
    ))
    db.commit()
    return result


@router.post("/assistant/chat/stream")
async def stream_knowledge_assistant(
    payload: KnowledgeAssistantChatCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    """流式返回回答文字，结束时附带经过校验的完整推荐结果。"""
    conversation = _get_owned_conversation(db, payload.conversation_id, user, create=True, selected_tool=payload.tool)
    history_rows = list(db.execute(
        select(KnowledgeAssistantMessage)
        .where(KnowledgeAssistantMessage.conversation_id == conversation.id)
        .order_by(KnowledgeAssistantMessage.id.desc()).limit(20)
    ).scalars().all())
    history = [{"role": row.role, "content": row.content} for row in reversed(history_rows) if row.role in {"user", "assistant"}]
    conversation.selected_tool = payload.tool
    db.add(KnowledgeAssistantMessage(conversation_id=conversation.id, role="user", content=payload.message.strip(), tool=payload.tool))
    db.commit()

    async def event_stream():
        queue: asyncio.Queue[tuple[str, object]] = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def emit_delta(value: str) -> None:
            loop.call_soon_threadsafe(queue.put_nowait, ("delta", value))

        async def run_model() -> None:
            try:
                settings = get_settings()
                result = await asyncio.to_thread(
                    generate_knowledge_answer, payload.tool, payload.message.strip(),
                    payload.context.model_dump(), history, settings.wiki_dir, emit_delta,
                )
                await queue.put(("final", result))
            except KnowledgeAssistantModelError as exc:
                await queue.put(("error", str(exc)))
            except Exception:
                await queue.put(("error", "AI 助手调用失败，请稍后重试。"))

        task = asyncio.create_task(run_model())
        try:
            while True:
                event, data = await queue.get()
                if event == "final":
                    result = data if isinstance(data, dict) else {}
                    db.add(KnowledgeAssistantMessage(
                        conversation_id=conversation.id, role="assistant",
                        content=str(result.get("answer", "")), tool=payload.tool, result=result,
                    ))
                    db.commit()
                yield f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
                if event in {"final", "error"}:
                    break
        finally:
            if not task.done():
                task.cancel()

    return StreamingResponse(event_stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/assistant/conversations", response_model=list[KnowledgeConversationRead])
async def list_knowledge_assistant_conversations(
    query: str = Query(default="", max_length=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[dict]:
    """返回当前账户的历史会话，支持按首条问题搜索。"""
    conversations = list(db.execute(
        select(KnowledgeConversation).where(KnowledgeConversation.user_id == user.id)
        .order_by(KnowledgeConversation.updated_at.desc()).limit(50)
    ).scalars().all())
    results = []
    normalized_query = query.strip().lower()
    for conversation in conversations:
        messages = list(db.execute(
            select(KnowledgeAssistantMessage).where(KnowledgeAssistantMessage.conversation_id == conversation.id)
            .order_by(KnowledgeAssistantMessage.id.asc())
        ).scalars().all())
        first_user = next((item.content for item in messages if item.role == "user"), "新会话")
        if normalized_query and normalized_query not in first_user.lower():
            continue
        results.append({
            "id": conversation.id,
            "title": first_user[:36],
            "selected_tool": conversation.selected_tool,
            "message_count": len(messages),
            "updated_at": conversation.updated_at or conversation.created_at,
        })
    return results


@router.get(
    "/assistant/conversations/{conversation_id}/messages",
    response_model=list[KnowledgeAssistantMessageRead],
)
async def list_knowledge_assistant_messages(
    conversation_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[KnowledgeAssistantMessage]:
    """返回当前账户最近的知识助手消息。"""
    conversation = _get_owned_conversation(db, conversation_id, user)
    rows = list(db.execute(
        select(KnowledgeAssistantMessage)
        .where(KnowledgeAssistantMessage.conversation_id == conversation.id)
        .order_by(KnowledgeAssistantMessage.id.desc())
        .limit(40)
    ).scalars().all())
    return list(reversed(rows))


@router.get("/thumbnail/{asset_path:path}")
async def read_knowledge_library_thumbnail(
    asset_path: str,
    _: User = Depends(get_current_user),
) -> Response:
    """按需返回总览卡片使用的轻量 WebP 预览图。"""
    content = render_library_thumbnail(get_settings().wiki_dir, asset_path)
    if content is None:
        raise HTTPException(status_code=404, detail="知识库预览图不存在。")
    return Response(content=content, media_type="image/webp", headers={"Cache-Control": "private, max-age=3600"})


@router.get("/{item_id}")
async def read_knowledge_library_item(
    item_id: str,
    _: User = Depends(get_current_user),
) -> dict:
    """返回一张知识卡或案例卡的正文、图片和关联编号。"""
    item = get_library_item(get_settings().wiki_dir, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="知识库条目不存在。")
    return item
