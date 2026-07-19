"""把任务书条目转换为可审计规则，供证据 Agent 和评分层共同使用。"""

from __future__ import annotations

import re


REQUIREMENT_DIMENSION_KEYWORDS = {
    "function_agent": (
        "功能", "面积", "房间", "展览", "阅览", "档案", "服务", "流线", "分区",
        "楼梯", "电梯", "卫生间", "入口", "交通空间",
    ),
    "site_agent": ("基地", "场地", "道路", "景观", "城市", "室外", "总图", "总平面"),
    "form_agent": ("形体", "体量", "空间", "立面", "形式", "几何", "空间序列"),
    "structure_agent": ("结构", "柱网", "跨度", "框架", "构造", "支撑", "承重"),
    "concept_agent": ("概念", "立意", "主题", "叙事", "创意", "构思"),
    "drawing_agent": (
        "成果", "图纸", "总平面图", "平面图", "立面图", "剖面图", "构造图",
        "透视图", "模型", "比例", "标注", "图面", "排版",
    ),
}


def build_structured_requirements(lines: list[str]) -> list[dict]:
    """为任务书代表性条目补充约束等级、核对专项和证据方式。"""
    requirements = []
    for index, raw_line in enumerate(dict.fromkeys(lines), start=1):
        text = str(raw_line).strip()
        if not text:
            continue
        agent_types = infer_requirement_agents(text)
        requirements.append(
            {
                "id": f"R-{index:03d}",
                "text": text,
                "level": infer_requirement_level(text),
                "dimension": agent_types[0] if agent_types else "general",
                "agent_types": agent_types,
                "verification_mode": infer_verification_mode(text),
            }
        )
    return requirements


def infer_requirement_level(text: str) -> str:
    """识别条目是强制、弹性、选配、参考还是一般说明。"""
    if re.search(r"选配|可选|可不设|鼓励(?:设置|采用)|自愿", text):
        return "optional"
    if re.search(r"仅供参考|供参考|参考值|建议值", text):
        return "reference"
    if re.search(r"按需|根据需要|视.{0,8}情况|结合.{0,12}(?:设置|确定)", text):
        return "flexible_required"
    if re.search(
        r"必须|应当|应满足|须|不得|不应|不少于|不低于|不高于|至少|"
        r"设计要求|设计内容|主要功能|建筑面积|建筑高度|结构形式|成果要求|"
        r"总平面图|平面图|立面图|剖面图|构造图",
        text,
    ):
        return "required"
    return "informational"


def infer_requirement_agents(text: str) -> list[str]:
    """按条目关键词确定最适合核对的一个或多个专项 Agent。"""
    scores = {
        agent_type: sum(text.count(keyword) for keyword in keywords)
        for agent_type, keywords in REQUIREMENT_DIMENSION_KEYWORDS.items()
    }
    highest = max(scores.values(), default=0)
    if highest <= 0:
        return []
    agents = [agent_type for agent_type, score in scores.items() if score == highest]
    return agents[:2]


def infer_verification_mode(text: str) -> str:
    """区分需要量化、图纸观察或文本资料才能核对的要求。"""
    if re.search(r"\d|平方米|平米|㎡|米|m\b|比例|不高于|不少于|至少", text, re.I):
        return "quantitative"
    if any(
        keyword in text
        for keyword in (
            "场地", "入口", "流线", "分区", "空间", "结构", "柱网", "图纸", "平面",
            "立面", "剖面", "总图", "总平面", "透视", "模型", "图面", "标注",
        )
    ):
        return "visual"
    return "document"


def relevant_requirements(requirements: list[dict], agent_type: str) -> list[dict]:
    """返回当前专项真正需要核对的任务书规则。"""
    matched = []
    for item in requirements:
        agent_types = item.get("agent_types") or []
        if item.get("dimension") == "general" or agent_type in agent_types:
            matched.append(item)
    return matched[:12]
