"""报告助手：组合报告、任务书、真实图纸与知识库，生成可追溯问答。"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.function_agent import build_function_agent_context, build_image_inputs
from app.config import get_settings
from app.llm.client import get_llm_client
from app.models import AgentEvaluation, ChatMessage, OverallReport, Submission
from app.routers.submission_report_data import load_report_reference_snapshots
from app.services.drawing_preprocess import add_preprocessed_model_drawings
from app.services.knowledge_assistant import PUBLIC_CARD_ID_PATTERN, retrieve_knowledge_candidates


LOGGER = logging.getLogger(__name__)
REPORT_CHAT_TOOLS = {"none", "drawing_review", "issue_explanation", "knowledge_recommendation"}


def generate_report_assistant_answer(
    submission: Submission,
    report: OverallReport,
    content: str,
    tool: str,
    db: Session,
    on_answer_delta: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """调用多模态模型回答，并返回经过校验的知识引用与报告修订建议。"""
    tool = tool if tool in REPORT_CHAT_TOOLS else "none"
    settings = get_settings()
    provider = "dashscope"
    model = settings.llm_assistant_model

    references = load_report_reference_snapshots(db, submission.id)
    context = build_function_agent_context(
        submission, list(submission.drawing_files), references, list(submission.attachments)
    )
    add_preprocessed_model_drawings(context, provider, model)
    retrieval_content = content
    if tool == "knowledge_recommendation":
        recent_questions = list(reversed(list(db.execute(
            select(ChatMessage.content)
            .where(
                ChatMessage.submission_id == submission.id,
                ChatMessage.role == "user",
                ChatMessage.tool == "knowledge_recommendation",
            )
            .order_by(ChatMessage.id.desc())
            .limit(4)
        ).scalars())))
        retrieval_content = "；".join(recent_questions or [content])
    candidates = _retrieve_candidates(tool, retrieval_content, settings.wiki_dir)
    candidate_by_id = {item["id"]: item for item in candidates}
    llm_client = get_llm_client(provider, model)
    prompt = _build_prompt(submission, report, content, tool, context, candidates, db)
    user_content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    user_content.extend(build_image_inputs(context["drawings"], detail=llm_client.image_detail))
    create_kwargs: dict[str, Any] = {
        "model": llm_client.model,
        "messages": [
            {"role": "system", "content": _system_prompt(tool, len(user_content) - 1)},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0.2,
        "max_tokens": min(llm_client.max_tokens, 1500),
        "response_format": {"type": "json_object"},
        "timeout": settings.llm_timeout_seconds,
    }
    extra_body = dict(llm_client.extra_body or {})
    if provider == "dashscope" and tool in {"none", "issue_explanation", "knowledge_recommendation"}:
        extra_body["enable_search"] = True
    if extra_body:
        create_kwargs["extra_body"] = extra_body
    if llm_client.reasoning_effort:
        create_kwargs["reasoning_effort"] = llm_client.reasoning_effort
    try:
        payload = _create_json_completion(llm_client, create_kwargs, on_answer_delta)
    except Exception:
        LOGGER.exception("报告助手调用多模态模型失败")
        return {"answer": _fallback_answer(report, content, tool), "citations": [], "report_update": None}

    answer = str(payload.get("answer", "")).strip() or _fallback_answer(report, content, tool)
    selected_ids = [str(value).upper() for value in payload.get("recommendation_ids", [])]
    selected_ids.extend(value.upper() for value in PUBLIC_CARD_ID_PATTERN.findall(answer))
    citations = []
    for item_id in dict.fromkeys(selected_ids):
        candidate = candidate_by_id.get(item_id)
        if candidate:
            citations.append({"id": item_id, "title": candidate["title"]})
    answer = PUBLIC_CARD_ID_PATTERN.sub("", answer)
    answer = re.sub(r"\s+([，。；：、])", r"\1", answer).strip()
    report_update = payload.get("report_update") if payload.get("finding") == "report_needs_correction" else None
    if tool != "drawing_review" or len(user_content) <= 1 or not isinstance(report_update, dict):
        report_update = None
    return {"answer": answer, "citations": citations, "report_update": report_update}


def apply_report_assistant_update(
    report: OverallReport,
    report_update: dict[str, Any] | None,
    question: str,
    db: Session,
) -> bool:
    """在确认图纸证据支持时限幅修订报告，并保留修订记录。"""
    if not report_update or not str(report_update.get("reason", "")).strip():
        return False
    previous_score = float(report.overall_score)
    changed = False
    requested_score = report_update.get("overall_score")
    if isinstance(requested_score, (int, float)):
        report.overall_score = max(0, min(100, max(previous_score - 8, min(previous_score + 8, float(requested_score)))))
        from app.agents.function_agent_report import score_to_grade
        report.grade = score_to_grade(report.overall_score)
        changed = report.overall_score != previous_score
    for field in ("summary",):
        value = report_update.get(field)
        if isinstance(value, str) and value.strip():
            setattr(report, field, value.strip()[:2000])
            changed = True
    for field in ("must_fix", "should_improve", "optional_improvements", "strengths"):
        value = report_update.get(field)
        if isinstance(value, list):
            setattr(report, field, [str(item).strip()[:500] for item in value if str(item).strip()][:12])
            changed = True
    evaluations = {
        item.agent_type: item for item in db.execute(
            select(AgentEvaluation).where(AgentEvaluation.submission_id == report.submission_id)
        ).scalars()
    }
    for update in report_update.get("agent_updates", []):
        if not isinstance(update, dict):
            continue
        evaluation = evaluations.get(str(update.get("agent_type", "")))
        if evaluation is None:
            continue
        score = update.get("score")
        if isinstance(score, (int, float)):
            evaluation.score = max(0, min(100, max(evaluation.score - 10, min(evaluation.score + 10, float(score)))))
            changed = True
        for field in ("summary",):
            value = update.get(field)
            if isinstance(value, str) and value.strip():
                setattr(evaluation, field, value.strip()[:1200])
                changed = True
        for field in ("issues", "suggestions", "strengths"):
            value = update.get(field)
            if isinstance(value, list):
                setattr(evaluation, field, [str(item).strip()[:500] for item in value if str(item).strip()][:10])
                changed = True
        sub_score_updates = update.get("sub_score_updates")
        if isinstance(sub_score_updates, dict):
            details = dict(evaluation.details or {})
            sub_scores = dict(details.get("sub_scores") or {})
            for name, raw_update in sub_score_updates.items():
                if name not in sub_scores or not isinstance(raw_update, dict):
                    continue
                current = dict(sub_scores[name]) if isinstance(sub_scores[name], dict) else {"score": sub_scores[name]}
                if isinstance(raw_update.get("score"), (int, float)):
                    current["score"] = raw_update["score"]
                if str(raw_update.get("reason", "")).strip():
                    current["reason"] = str(raw_update["reason"]).strip()[:1000]
                sub_scores[name] = current
                changed = True
            details["sub_scores"] = sub_scores
            evaluation.details = details
    invalid_claims = [str(item).strip() for item in report_update.get("invalid_claims", []) if str(item).strip()]
    if invalid_claims:
        replacement = str(report_update.get("replacement_statement", "")).strip()
        changed = _remove_confirmed_false_claims(report, evaluations.values(), invalid_claims, replacement) or changed
    if not changed:
        return False
    audit = dict(report.evaluation_context or {})
    revisions = list(audit.get("assistant_revisions") or [])
    revisions.append({
        "question": question[:500],
        "previous_score": previous_score,
        "updated_score": report.overall_score,
        "reason": str(report_update.get("reason", "图纸复核确认原报告需要修正。"))[:1000],
    })
    audit["assistant_revisions"] = revisions[-20:]
    report.evaluation_context = audit
    db.commit()
    return True


def _remove_confirmed_false_claims(
    report: OverallReport,
    evaluations: Any,
    invalid_claims: list[str],
    replacement: str,
) -> bool:
    """清除模型已用图纸确认错误的原报告短句，避免只改分数而保留旧判断。"""
    changed = False

    def clean_text(value: Any, fallback: str = "") -> str:
        nonlocal changed
        original = str(value or "")
        sentences = re.split(r"(?<=[。！？；])", original)
        kept = [sentence for sentence in sentences if not any(claim in sentence for claim in invalid_claims)]
        cleaned = "".join(kept).strip()
        if cleaned != original.strip():
            changed = True
            return cleaned or fallback
        return original

    def clean_value(value: Any) -> Any:
        if isinstance(value, str):
            return clean_text(value)
        if isinstance(value, list):
            return [cleaned for item in value if (cleaned := clean_value(item)) not in ("", None, [], {})]
        if isinstance(value, dict):
            return {key: clean_value(item) for key, item in value.items()}
        return value

    report.summary = clean_text(report.summary, replacement)
    for field in ("must_fix", "should_improve", "optional_improvements", "strengths"):
        setattr(report, field, clean_value(getattr(report, field)))
    for evaluation in evaluations:
        evaluation.summary = clean_text(evaluation.summary, replacement)
        for field in ("issues", "suggestions", "strengths"):
            setattr(evaluation, field, clean_value(getattr(evaluation, field)))
        evaluation.details = clean_value(dict(evaluation.details or {}))
    return changed


def _retrieve_candidates(tool: str, content: str, wiki_dir: str) -> list[dict[str, Any]]:
    """为解释和学习推荐准备当前知识库中的真实候选。"""
    if tool == "drawing_review":
        return []
    retrieval_tool = "learning_path" if tool == "knowledge_recommendation" else "knowledge_query"
    _, candidates = retrieve_knowledge_candidates(wiki_dir, retrieval_tool, content)
    return candidates


def _build_prompt(
    submission: Submission,
    report: OverallReport,
    content: str,
    tool: str,
    context: dict[str, Any],
    candidates: list[dict[str, Any]],
    db: Session,
) -> str:
    """整理报告、专项评分、任务书、图纸目录和知识候选。"""
    evaluations = list(db.execute(
        select(AgentEvaluation).where(AgentEvaluation.submission_id == submission.id)
    ).scalars())
    report_payload = {
        "overall_score": report.overall_score,
        "grade": report.grade,
        "summary": report.summary,
        "must_fix": report.must_fix,
        "should_improve": report.should_improve,
        "optional_improvements": report.optional_improvements,
        "strengths": report.strengths,
        "agent_evaluations": [{
            "agent_type": item.agent_type,
            "dimension": item.dimension,
            "score": item.score,
            "summary": item.summary,
            "issues": item.issues,
            "suggestions": item.suggestions,
            "details": item.details,
        } for item in evaluations],
    }
    candidate_payload = [{
        "id": item["id"], "kind": item["kind"], "title": item["title"],
        "category": item["category"], "excerpt": item["excerpt"],
    } for item in candidates]
    history_rows = list(reversed(list(db.execute(
        select(ChatMessage)
        .where(ChatMessage.submission_id == submission.id)
        .order_by(ChatMessage.id.desc())
        .limit(12)
    ).scalars())))
    if history_rows and history_rows[-1].role == "user" and history_rows[-1].content.strip() == content.strip():
        history_rows = history_rows[:-1]
    history_payload = [{
        "role": item.role,
        "content": item.content,
        "tool": item.tool,
        "citations": item.citations,
    } for item in history_rows]
    return "\n".join([
        f"工具：{tool}",
        f"项目：{submission.project.name}；类型：{submission.project.building_type}；阶段：{submission.design_stage}",
        f"设计说明：{submission.description}",
        f"任务书摘要：{context.get('task_book_summary', '')}",
        f"图纸范围：{context.get('drawing_scope', '')}",
        "图纸目录：" + json.dumps([{k: item.get(k, "") for k in ("original_name", "drawing_type", "description", "analysis_purpose")} for item in context["drawings"]], ensure_ascii=False),
        "当前报告：" + json.dumps(report_payload, ensure_ascii=False),
        "当前报告会话历史：" + json.dumps(history_payload, ensure_ascii=False),
        "知识库候选：" + json.dumps(candidate_payload, ensure_ascii=False),
        "用户问题：" + content,
    ])


def _system_prompt(tool: str, image_count: int) -> str:
    """按工具生成严格的多模态回答规则。"""
    common = (
        "你是 ArchCritic 评图报告助手。你已收到当前提交的报告、任务书、图纸目录以及"
        f"{image_count} 张真实图纸图像。必须结合可见图纸回答，不能声称无法查看用户图纸。"
        "如果局部确实看不清，要指出具体图纸和信息缺口，不能把看不清当作不存在。"
        "可以结合建筑学通识和给定知识库候选补充解释；不得捏造规范条文、项目事实或卡片编号。"
        "必须返回 JSON，字段为 answer、finding、recommendation_ids、report_update。"
        "answer 用简洁中文；卡片编号只写入 recommendation_ids，不写进 answer。"
    )
    rules = {
        "drawing_review": (
            "当前执行图纸复核。只处理用户本轮质疑的单个判断，不要总结项目，也不要罗列无关扣分项。"
            "第一句话必须直接回答用户提出的事实问题；随后说明在哪张图、什么位置看到了什么。"
            "必须区分某个构件存在与完整系统成立，例如看到电梯不等于已经证明入口、无障碍路线、"
            "电梯厅、门宽和无障碍卫生间形成连续系统，但也不能因系统信息不完整就声称电梯不存在。"
            "逐一核对用户质疑、原报告判断和图纸证据，不得要求用户重新提供本次已经上传的图纸。"
            "finding 只能是 report_correct、report_needs_correction 或 insufficient。"
            "只有图纸清楚证明原判断错误时才返回 report_update；否则必须为 null。"
            "一旦确认原判断错误，不能只改分数：report_update 必须同步给出所有受影响的 summary、"
            "四类反馈完整数组和 agent_updates；受影响专项的小分要在 sub_score_updates 中更新分数与理由。"
            "invalid_claims 必须逐条复制报告中已经被图纸推翻的原短语，replacement_statement 写正确事实，"
            "确保旧错误不会继续出现在总评、反馈、专项说明、小分理由或建议中。"
            "report_update 可包含 reason、overall_score、summary、四类反馈数组、agent_updates、"
            "invalid_claims 和 replacement_statement，不得因用户主张直接加分，也不得修改无关内容。"
        ),
        "issue_explanation": (
            "当前执行问题解释。结合报告扣分点、专项证据、图纸、建筑学知识和知识库给出更具体解释；"
            "finding 写 explanation，report_update 必须为 null。"
        ),
        "knowledge_recommendation": (
            "当前执行知识推荐。根据任务、图纸和报告薄弱点选择所有真正相关的候选卡片；"
            "把编号完整写入 recommendation_ids，finding 写 recommendation，report_update 必须为 null。"
        ),
        "none": "执行普通报告追问，结合图纸、报告和建筑学通识回答；finding 写 explanation，report_update 必须为 null。",
    }
    return common + rules[tool]


def _fallback_answer(report: OverallReport, content: str, tool: str = "none") -> str:
    """模型暂不可用时返回基于报告的明确降级回答。"""
    if tool == "drawing_review":
        return "这次没有完成有效的图纸复核，因此我暂不维持或修改原判断。你的质疑已经保留，请稍后重新发起图纸复核。"
    if "必须" in content or "修改" in content:
        items = report.must_fix[:3] or ["当前报告没有列出必须修改项。"]
        return "本轮必须修改项：" + "；".join(items)
    items = report.should_improve[:2] or report.must_fix[:2] or ["建议先核对总评中的主要问题。"]
    return f"结合本次报告，{report.summary} 建议先关注：" + "；".join(items)


def build_report_assistant_fallback(report: OverallReport, content: str, tool: str = "none") -> dict[str, Any]:
    """图纸准备或模型调用异常时返回可保存的稳定回答，避免前端只看到调用失败。"""
    return {"answer": _fallback_answer(report, content, tool), "citations": [], "report_update": None}


def _extract_json(content: str) -> str:
    """从模型回答中提取 JSON 对象。"""
    start, end = content.find("{"), content.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("missing json object")
    return content[start:end + 1]


def _create_json_completion(
    llm_client: Any,
    create_kwargs: dict[str, Any],
    on_answer_delta: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """解析报告助手 JSON；格式不完整时用更短的回答要求重试一次。"""
    current_kwargs = dict(create_kwargs)
    last_error: Exception | None = None
    for attempt in range(2):
        request_kwargs = dict(current_kwargs)
        try:
            streaming = on_answer_delta is not None and attempt == 0
            if streaming:
                request_kwargs["stream"] = True
            try:
                response = llm_client.client.chat.completions.create(**request_kwargs)
            except TypeError:
                for key in ("response_format", "extra_body", "reasoning_effort"):
                    request_kwargs.pop(key, None)
                response = llm_client.client.chat.completions.create(**request_kwargs)
            if streaming:
                raw_content = ""
                emitted_answer = ""
                finish_reason = ""
                for chunk in response:
                    choice = chunk.choices[0] if chunk.choices else None
                    if choice is None:
                        continue
                    finish_reason = getattr(choice, "finish_reason", "") or finish_reason
                    raw_content += str(getattr(choice.delta, "content", "") or "")
                    partial_answer = _extract_partial_answer(raw_content)
                    if len(partial_answer) > len(emitted_answer):
                        on_answer_delta(partial_answer[len(emitted_answer):])
                        emitted_answer = partial_answer
                if finish_reason == "length":
                    raise json.JSONDecodeError("模型 JSON 输出达到长度上限", "", 0)
                return json.loads(_extract_json(raw_content))
            choice = response.choices[0]
            if getattr(choice, "finish_reason", "") == "length":
                raise json.JSONDecodeError("模型 JSON 输出达到长度上限", "", 0)
            return json.loads(_extract_json(str(choice.message.content or "")))
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt:
                break
            current_kwargs = {
                **create_kwargs,
                "messages": [
                    *create_kwargs["messages"],
                    {
                        "role": "user",
                        "content": (
                            "上一次格式不完整。请重新返回一个紧凑且完整的 JSON 对象，不要解释或使用 Markdown。"
                            "answer 不超过 500 个中文字符，只回答本轮问题；没有报告修订时 report_update 必须为 null。"
                        ),
                    },
                ],
                "max_tokens": max(int(create_kwargs.get("max_tokens") or 1500), 2200),
            }
    if last_error is not None:
        raise last_error
    raise ValueError("模型没有返回可解析内容")


def _extract_partial_answer(content: str) -> str:
    """从尚未结束的报告 JSON 流中安全提取 answer 文字。"""
    match = re.search(r'"answer"\s*:\s*"', content)
    if not match:
        return ""
    encoded = content[match.end():]
    escaped = False
    end = len(encoded)
    for index, char in enumerate(encoded):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
        elif char == '"':
            end = index
            break
    fragment = encoded[:end]
    if fragment.endswith("\\"):
        fragment = fragment[:-1]
    try:
        return json.loads(f'"{fragment}"')
    except json.JSONDecodeError:
        return fragment.replace("\\n", "\n").replace('\\"', '"').replace("\\\\", "\\")
