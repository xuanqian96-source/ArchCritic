"""实现建筑知识助手的字段标准化、候选检索和真实模型回答。"""

from __future__ import annotations

from functools import lru_cache
import json
import logging
import math
from pathlib import Path
import re
from typing import Any
from uuid import uuid4

from app.config import get_settings
from app.llm.client import get_llm_client
from app.services.knowledge_library import get_library_item, get_library_items
from app.wiki import resolve_wiki_root


RESULT_TOOLS = {
    "case_recommendation",
    "knowledge_query",
    "similar_cases",
    "case_compare",
    "learning_path",
}
SITE_CONTEXTS = ("城市", "校园", "滨水", "历史街区", "社区", "乡村", "郊野", "公园", "山地", "海边")
DIMENSIONS = ("场地", "功能", "流线", "形式", "结构", "材料", "环境", "采光", "入口", "展陈", "运营", "改造")
BUILDING_TYPE_ALIASES = {
    "博物馆": ("博物馆", "museum"),
    "图书馆": ("图书馆", "library", "媒体中心"),
    "美术馆": ("美术馆", "艺术馆", "画廊", "gallery"),
    "学校": ("学校", "小学", "大学", "校园"),
    "剧院": ("剧院", "歌剧院", "opera"),
    "文化中心": ("文化中心", "艺术中心", "文化艺术中心"),
    "酒店": ("酒店", "旅馆", "hotel"),
    "改造建筑": ("改造", "更新", "扩建", "adaptive reuse"),
}

logger = logging.getLogger(__name__)


class KnowledgeAssistantModelError(RuntimeError):
    """表示真实模型不可用或返回了无法校验的结果。"""


def build_knowledge_documents(wiki_dir: str) -> list[dict[str, Any]]:
    """合并浏览目录与治理记录，生成只读检索文档。"""
    wiki_root = resolve_wiki_root(wiki_dir)
    metadata = _load_governance_metadata(str(wiki_root), _governance_version(wiki_root))
    documents: list[dict[str, Any]] = []
    for item in get_library_items(wiki_dir):
        record = metadata.get(item["id"], {})
        area = _normalize_area(str(record.get("scale", "")))
        building_types = _as_list(record.get("building_types"))
        if item["kind"] == "case":
            building_types.extend([str(record.get("building_type", "")), item["category"]])
        searchable_parts = [
            item["id"], item["title"], item["excerpt"], item["category"], item["level_label"],
            str(record.get("location", "")), str(record.get("scale", "")),
            str(record.get("building_type", "")), " ".join(building_types),
            " ".join(_as_list(record.get("stages"))),
            " ".join(_as_list(record.get("dimensions"))),
            " ".join(_as_list(record.get("key_terms"))),
            " ".join(_as_list(record.get("tags"))),
            str(record.get("site_strategy", "")), str(record.get("functional_organization", "")),
            str(record.get("circulation", "")), str(record.get("form_strategy", "")),
            str(record.get("structure_strategy", "")), str(record.get("environmental_response", "")),
            str(record.get("student_explanation", "")),
        ]
        documents.append({
            **item,
            "building_types": list(dict.fromkeys(value for value in building_types if value)),
            "location_raw": str(record.get("location", "")),
            "year_raw": str(record.get("year", "")),
            "scale_raw": str(record.get("scale", "")),
            "area_min_sqm": area[0],
            "area_max_sqm": area[1],
            "area_basis": area[2],
            "metadata_confidence": area[3],
            "site_contexts": _matching_labels(" ".join(searchable_parts), SITE_CONTEXTS),
            "stages": _as_list(record.get("stages")),
            "dimensions": _as_list(record.get("dimensions")),
            "review_status": str(record.get("review_status", "pending")),
            "human_review_confirmed": bool(record.get("human_review_confirmed", False)),
            "search_text": " ".join(searchable_parts).lower(),
        })
    return documents


def extract_conditions(message: str) -> dict[str, Any]:
    """从自然语言中提取可解释的检索条件。"""
    lowered = message.lower()
    building_types = [
        label for label, aliases in BUILDING_TYPE_ALIASES.items()
        if any(alias.lower() in lowered for alias in aliases)
    ]
    area_match = re.search(r"(\d+(?:\.\d+)?)\s*(万)?\s*(?:平方米|平米|㎡|m²|m2|平)(?:左右|上下|以内|以上|以下)?", lowered)
    area_target = None
    if area_match:
        area_target = float(area_match.group(1)) * (10000 if area_match.group(2) else 1)
    stages = []
    if any(word in lowered for word in ("概念", "前期", "构思")):
        stages.append("concept")
    if any(word in lowered for word in ("方案", "深化", "平面")):
        stages.append("scheme")
    if any(word in lowered for word in ("图纸", "表达", "施工图")):
        stages.append("drawing")
    return {
        "building_types": building_types,
        "area_target_sqm": area_target,
        "site_contexts": _matching_labels(message, SITE_CONTEXTS),
        "dimensions": _matching_labels(message, DIMENSIONS),
        "stages": stages,
        "keywords": _query_keywords(message),
    }


def retrieve_knowledge_candidates(
    wiki_dir: str,
    tool: str,
    message: str,
    current_card_id: str | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """根据工具和用户条件检索真实存在的候选卡片。"""
    conditions = extract_conditions(message)
    documents = build_knowledge_documents(wiki_dir)
    current = next((item for item in documents if item["id"] == current_card_id), None)
    ranked: list[tuple[float, dict[str, Any], list[str], list[str]]] = []
    for document in documents:
        if tool in {"similar_cases", "case_compare"} and document["kind"] != "case":
            continue
        if tool == "knowledge_query" and document["kind"] != "knowledge":
            continue
        score, matched, limitations = _score_document(document, conditions, tool, current)
        ranked.append((score, document, matched, limitations))
    ranked.sort(key=lambda value: (-value[0], value[1]["id"]))

    limits = {"case": 8, "knowledge": 8}
    if tool == "case_recommendation":
        limits = {"case": 10, "knowledge": 6}
    elif tool == "learning_path":
        limits = {"case": 6, "knowledge": 8}
    selected: list[dict[str, Any]] = []
    counts = {"case": 0, "knowledge": 0}
    for score, document, matched, limitations in ranked:
        kind = document["kind"]
        if counts[kind] >= limits[kind]:
            continue
        counts[kind] += 1
        selected.append({
            **document,
            "retrieval_score": round(score, 4),
            "matched_fields": matched,
            "limitations": limitations,
        })
        if len(selected) >= sum(limits.values()):
            break
    return conditions, selected


def generate_knowledge_answer(
    tool: str,
    message: str,
    context: dict[str, Any],
    history: list[dict[str, str]],
    wiki_dir: str,
) -> dict[str, Any]:
    """调用后端默认真实模型，并校验回答中的全部卡片编号。"""
    settings = get_settings()
    if settings.llm_provider.lower() == "mock":
        raise KnowledgeAssistantModelError("当前服务器仍使用演示模型，AI 助手暂不可用。请先配置默认真实模型。")
    conditions, candidates = retrieve_knowledge_candidates(
        wiki_dir, tool, message, context.get("current_card_id")
    )
    current_detail = None
    if context.get("current_card_id"):
        current_detail = get_library_item(wiki_dir, str(context["current_card_id"]))
    candidate_by_id = {candidate["id"]: candidate for candidate in candidates}
    model_payload = _call_model(
        tool, message, conditions, candidates, current_detail, history
    )
    clarification_required = bool(model_payload.get("clarification_required", False))
    recommendations = []
    if not clarification_required:
        for raw in model_payload.get("recommendations", []):
            item_id = str(raw.get("id", "")).upper()
            candidate = candidate_by_id.get(item_id)
            if not candidate or any(item["id"] == item_id for item in recommendations):
                continue
            recommendations.append({
                "id": item_id,
                "kind": candidate["kind"],
                "reason": str(raw.get("reason", "")).strip() or _default_reason(candidate),
                "matched_fields": candidate["matched_fields"],
                "limitations": _clean_list(raw.get("limitations")) or candidate["limitations"],
                "score": candidate["retrieval_score"],
                "review_status": candidate["review_status"],
                "human_review_confirmed": candidate["human_review_confirmed"],
            })
    answer = str(model_payload.get("answer", "")).strip()
    if not answer:
        raise KnowledgeAssistantModelError("AI 返回内容不完整，请重试。")
    should_show_results = tool in RESULT_TOOLS and bool(recommendations)
    result_set_id = str(uuid4()) if should_show_results else None
    citations = [
        {"id": item["id"], "title": candidate_by_id[item["id"]]["title"]}
        for item in recommendations
    ]
    return {
        "answer": answer,
        "intent": tool,
        "clarification_required": clarification_required,
        "extracted_conditions": conditions,
        "recommendations": recommendations,
        "citations": citations,
        "result_set_id": result_set_id,
        "ui_action": "show_assistant_results" if should_show_results else "none",
    }


def _call_model(
    tool: str,
    message: str,
    conditions: dict[str, Any],
    candidates: list[dict[str, Any]],
    current_detail: dict[str, Any] | None,
    history: list[dict[str, str]],
) -> dict[str, Any]:
    """向 OpenAI 兼容客户端发送受约束的知识助手请求。"""
    try:
        llm_client = get_llm_client()
    except ValueError as exc:
        raise KnowledgeAssistantModelError(str(exc)) from exc
    if not hasattr(llm_client, "client"):
        raise KnowledgeAssistantModelError("当前默认模型不能用于知识助手。")
    candidate_lines = []
    for item in candidates:
        candidate_lines.append(json.dumps({
            "id": item["id"], "kind": item["kind"], "title": item["title"],
            "category": item["category"], "level": item["level_label"],
            "excerpt": item["excerpt"], "building_types": item["building_types"],
            "location": item["location_raw"], "scale": item["scale_raw"],
            "site_contexts": item["site_contexts"], "matched_fields": item["matched_fields"],
            "limitations": item["limitations"], "review_status": item["review_status"],
        }, ensure_ascii=False))
    current_text = ""
    if current_detail:
        current_text = str(current_detail.get("content", ""))[:7000]
    system_prompt = (
        "你是 ArchCritic 建筑知识导航与学习教练，不评分、不替代教师。"
        "只使用给定当前卡片和候选卡回答，不得创造任何卡片编号、书名、规范条文、结构或材料事实。"
        "待复核内容只能作为学习候选，并要用克制语气说明。"
        "必须返回 JSON 对象，字段为 answer、clarification_required、recommendations。"
        "recommendations 是数组，每项只有 id、reason、limitations；id 必须来自候选列表。"
        "普通问答、问题拆解和当前卡片问答可以返回空 recommendations。"
        "回答使用简洁中文，不使用 Markdown 表格。"
    )
    user_prompt = "\n".join([
        f"当前工具：{tool}",
        f"提取条件：{json.dumps(conditions, ensure_ascii=False)}",
        f"用户问题：{message}",
        "当前卡片正文：" + (current_text or "无"),
        "候选卡片：",
        *candidate_lines,
    ])
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history[-10:])
    messages.append({"role": "user", "content": user_prompt})
    create_kwargs: dict[str, Any] = {
        "model": llm_client.model,
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": min(llm_client.max_tokens, 1400),
        "timeout": get_settings().knowledge_assistant_timeout_seconds,
        "response_format": {"type": "json_object"},
    }
    if llm_client.extra_body:
        create_kwargs["extra_body"] = llm_client.extra_body
    if llm_client.reasoning_effort:
        create_kwargs["reasoning_effort"] = llm_client.reasoning_effort
    try:
        try:
            response = llm_client.client.chat.completions.create(**create_kwargs)
        except TypeError:
            for key in ("response_format", "extra_body", "reasoning_effort"):
                create_kwargs.pop(key, None)
            response = llm_client.client.chat.completions.create(**create_kwargs)
    except Exception as exc:
        logger.exception("建筑知识助手调用默认模型失败")
        raise KnowledgeAssistantModelError("AI 助手调用失败，请稍后重试。") from exc
    content = response.choices[0].message.content if response.choices else ""
    try:
        return json.loads(_extract_json(str(content or "")))
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise KnowledgeAssistantModelError("AI 返回格式不完整，请重试。") from exc


def _score_document(
    document: dict[str, Any],
    conditions: dict[str, Any],
    tool: str,
    current: dict[str, Any] | None,
) -> tuple[float, list[str], list[str]]:
    """计算一张卡片的本地可解释相关度。"""
    score = 0.1
    matched: list[str] = []
    limitations: list[str] = []
    search_text = document["search_text"]
    type_matches = [value for value in conditions["building_types"] if value.lower() in search_text]
    if type_matches:
        score += 6
        matched.append("建筑类型")
    elif conditions["building_types"] and document["kind"] == "case":
        limitations.append("建筑类型不完全一致")
    target_area = conditions["area_target_sqm"]
    if target_area and document["area_min_sqm"]:
        midpoint = (document["area_min_sqm"] + document["area_max_sqm"]) / 2
        closeness = max(0, 1 - abs(math.log(max(midpoint, 1) / target_area)) / 2.2)
        score += closeness * 5
        if closeness >= 0.72:
            matched.append("规模")
        else:
            limitations.append(f"规模为{document['scale_raw'] or '未明确'}")
    elif target_area and document["kind"] == "case":
        limitations.append("规模数据不足")
    for field, label, weight in (
        (conditions["site_contexts"], "场地", 2.5),
        (conditions["dimensions"], "关注问题", 2.0),
        (conditions["stages"], "设计阶段", 1.5),
    ):
        if field and any(value.lower() in search_text for value in field):
            score += weight
            matched.append(label)
    keyword_hits = sum(keyword.lower() in search_text for keyword in conditions["keywords"])
    score += min(keyword_hits, 6) * 0.8
    if keyword_hits:
        matched.append("关键词")
    if current:
        if document["id"] in current.get("related_ids", []):
            score += 5
            matched.append("关联卡片")
        if tool == "similar_cases" and document["category"] == current["category"]:
            score += 3
            matched.append("同类案例")
        if document["id"] == current["id"]:
            score -= 20
    if tool == "case_recommendation" and document["kind"] == "case":
        score += 2
    if tool in {"knowledge_query", "learning_path"} and document["kind"] == "knowledge":
        score += 1.5
    if document["human_review_confirmed"]:
        score += 0.5
    else:
        limitations.append("内容待专业复核")
    return score, list(dict.fromkeys(matched)), list(dict.fromkeys(limitations))


def _normalize_area(raw: str) -> tuple[float | None, float | None, str, str]:
    """把自由文本规模转换为面积范围、口径和可信度。"""
    if not raw:
        return None, None, "unknown", "low"
    values: list[float] = []
    for value, unit in re.findall(r"(\d[\d,]*(?:\.\d+)?)\s*(万)?\s*(?:m²|㎡|平方米|m2)", raw, flags=re.I):
        number = float(value.replace(",", "")) * (10000 if unit else 1)
        values.append(number)
    if not values:
        return None, None, "unknown", "low"
    lowered = raw.lower()
    basis = "exhibition" if "展览" in raw else "site" if "用地" in raw or "site area" in lowered else "floor_area"
    confidence = "low" if "待核对" in raw else "medium" if len(values) > 1 else "high"
    return min(values), max(values), basis, confidence


def _governance_version(wiki_root: Path) -> tuple[int, ...]:
    """返回治理 JSON 修改时间，内容更新时自动刷新缓存。"""
    root = wiki_root / ".archcritic" / "长程Goal治理"
    return tuple(path.stat().st_mtime_ns for path in sorted(root.glob("*drafts*.json"))) if root.is_dir() else ()


@lru_cache(maxsize=4)
def _load_governance_metadata(wiki_root: str, version: tuple[int, ...]) -> dict[str, dict[str, Any]]:
    """读取案例和知识卡治理记录，并按稳定编号建立索引。"""
    del version
    governance_root = Path(wiki_root) / ".archcritic" / "长程Goal治理"
    records: dict[str, dict[str, Any]] = {}
    for path in sorted(governance_root.glob("*drafts*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for record in payload.get("records", []):
            item_id = record.get("case_id") or record.get("card_id")
            if item_id:
                records[str(item_id)] = record
    return records


def _matching_labels(text: str, labels: tuple[str, ...]) -> list[str]:
    """返回文字中出现的领域标签。"""
    return [label for label in labels if label in text]


def _query_keywords(message: str) -> list[str]:
    """提取适合全文匹配的中英文关键词。"""
    words = re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}|[\u4e00-\u9fff]{2,6}", message)
    stop = {"现在", "一个", "大概", "左右", "哪些", "推荐", "案例", "知识", "设计", "我想", "需要"}
    return list(dict.fromkeys(word for word in words if word not in stop))[:18]


def _as_list(value: Any) -> list[str]:
    """把治理记录中的标量或列表统一为字符串列表。"""
    if isinstance(value, list):
        return [str(item) for item in value if item]
    return [str(value)] if value else []


def _clean_list(value: Any) -> list[str]:
    """清理模型返回的简短字符串列表。"""
    return [str(item).strip()[:120] for item in value if str(item).strip()] if isinstance(value, list) else []


def _default_reason(candidate: dict[str, Any]) -> str:
    """模型遗漏理由时根据已匹配字段生成可核对短说明。"""
    fields = "、".join(candidate["matched_fields"][:3]) or "主题"
    return f"这张卡片与当前需求的{fields}相关。"


def _extract_json(content: str) -> str:
    """从可能带代码围栏的回答中提取 JSON 对象。"""
    start = content.find("{")
    end = content.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("missing json object")
    return content[start:end + 1]
