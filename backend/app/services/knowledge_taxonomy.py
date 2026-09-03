"""统一知识卡主题分类和自测题抽取，供浏览、评图与学习测试共用。"""

from __future__ import annotations

import re
from typing import Any


KNOWLEDGE_CATEGORIES = ["规范", "场地", "功能", "空间", "结构", "概念", "综合"]
DIFFICULTY_LABELS = {
    "beginner": "入门",
    "advanced": "进阶",
    "master": "研习",
}
GENERIC_ANSWER_PLACEHOLDER = "应说明具体设计对象、可观察图纸证据、判断依据和可以执行的修改，不以抽象口号代替分析。"

CATEGORY_TERMS = {
    "规范": ("规范", "防火", "消防", "疏散", "无障碍", "安全底线"),
    "场地": ("场地", "环境回应", "环境", "城市", "街道", "室外", "滨水", "历史与场所", "新旧关系"),
    "功能": ("功能", "流线", "运营组织", "展陈", "声环境", "导视", "可达", "服务空间"),
    "空间": ("空间", "形式", "形态", "剖面", "采光", "尺度", "围合", "构图", "几何"),
    "结构": ("结构", "建造", "构造", "材料", "技术", "设备", "机电", "跨度", "荷载"),
    "概念": ("概念", "方法", "证据", "设计策略", "分析", "迁移", "Parti", "综合自检"),
    "综合": ("综合评审", "社会包容", "公共性", "治理", "长期运营", "适应性", "公平", "日常使用"),
}

CATEGORY_AGENTS = {
    "规范": ["function_agent", "structure_agent"],
    "场地": ["site_agent"],
    "功能": ["function_agent"],
    "空间": ["form_agent"],
    "结构": ["structure_agent"],
    "概念": ["concept_agent"],
    "综合": ["review_agent"],
}


def classify_knowledge_card(fields: dict[str, str], title: str, excerpt: str) -> str:
    """根据现有维度和正文摘要生成稳定的七类主分类。"""
    item_id = str(fields.get("card_id", "")).upper()
    if item_id.startswith("KC-NOR-") or fields.get("category") == "规范应用":
        return "规范"
    dimensions = _list_field(fields, "dimensions")
    searchable = " ".join([title, excerpt, *dimensions])
    scores = {
        category: sum(4 if term in dimensions else 1 for term in terms if term in searchable)
        for category, terms in CATEGORY_TERMS.items()
    }
    # 研习卡中大量内容属于公共性与运营，显式命中时优先进入综合类。
    if scores["综合"] >= 2:
        scores["综合"] += 3
    return max(KNOWLEDGE_CATEGORIES, key=lambda category: (scores[category], -KNOWLEDGE_CATEGORIES.index(category)))


def build_quiz_item(item: dict[str, Any], content: str) -> dict[str, Any] | None:
    """从知识卡已有自测和答案章节抽取一道可判定的学习测试题。"""
    section = _extract_test_section(content)
    if not section:
        return None
    lines = [line.rstrip() for line in section.splitlines() if line.strip()]
    prompt = next((_clean_prompt(line) for line in lines if _is_prompt_line(line)), "")
    if not prompt:
        prompt = next((_clean_prompt(line) for line in lines if not line.startswith("#")), "")
    if not prompt:
        return None
    answer_section = _extract_answer_section(content)
    reference_points = _extract_list_points(answer_section)[:6]
    if not reference_points:
        reference_points = [
            _clean_prompt(line)
            for line in lines
            if re.match(r"^\s{2,}[-*]\s+", line) and _clean_prompt(line)
        ][:6]
    if not reference_points and answer_section:
        reference_points = [
            _clean_prompt(line)
            for line in answer_section.splitlines()
            if _clean_prompt(line) and not line.lstrip().startswith("#")
        ][:6]
    if reference_points == [GENERIC_ANSWER_PLACEHOLDER]:
        return None
    # 没有经过知识卡作者明确填写的答案时不进入正式测试，避免用摘要冒充答案。
    if not reference_points:
        return None
    return {
        "id": f"Q-{item['id']}",
        "card_id": item["id"],
        "card_title": item["title"],
        "category": item["category"],
        "difficulty": item["level"],
        "difficulty_label": item["level_label"],
        "prompt": prompt,
        "reference_points": reference_points,
    }


def _extract_test_section(content: str) -> str:
    """读取观察自测或规范检查章节。"""
    match = re.search(
        r"(?ms)^##\s+(?:观察或自测任务|设计检查问题)\s*\n+(.+?)(?=^##\s+|\Z)",
        content,
    )
    return match.group(1).strip() if match else ""


def _extract_answer_section(content: str) -> str:
    """读取知识卡作者明确填写的答案或参考答案章节。"""
    match = re.search(
        r"(?ms)^##\s+(?:答案要点|参考答案)\s*\n+(.+?)(?=^##\s+|\Z)",
        content,
    )
    return match.group(1).strip() if match else ""


def _extract_list_points(section: str) -> list[str]:
    """把答案章节中的列表项转换成独立、可展示的答案要点。"""
    return [
        _clean_prompt(line)
        for line in section.splitlines()
        if re.match(r"^\s*(?:[-*]|\d+[.)])\s+", line) and _clean_prompt(line)
    ]


def _is_prompt_line(line: str) -> bool:
    """识别章节中的第一条真实问题或任务。"""
    if re.match(r"^\s{2,}[-*]\s+", line):
        return False
    return bool(re.match(r"^(?:[-*]|\d+[.)])\s+", line))


def _clean_prompt(line: str) -> str:
    """移除列表编号和少量 Markdown 标记。"""
    value = re.sub(r"^(?:\s*[-*]|\s*\d+[.)])\s+", "", line).strip()
    return re.sub(r"[*_`]", "", value)


def _list_field(fields: dict[str, str], name: str) -> list[str]:
    """读取简单前置区中的列表字段。"""
    raw = fields.get(name, "")
    return [line.lstrip()[1:].strip().strip("\"'") for line in raw.splitlines() if line.lstrip().startswith("-")]
