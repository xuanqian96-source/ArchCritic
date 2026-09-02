"""按设计阶段和专项维度分配知识依据，供评图与基准测试共用。"""

from __future__ import annotations

from typing import Any


STAGE_AGENTS = {
    "概念阶段": ["site_agent", "form_agent", "concept_agent"],
    "方案阶段": ["function_agent", "site_agent", "form_agent", "structure_agent"],
    "图纸阶段": [
        "drawing_agent",
        "function_agent",
        "site_agent",
        "form_agent",
        "structure_agent",
    ],
}

AGENT_DIMENSIONS = {
    "function_agent": ("功能", "规范", "功能与流线"),
    "site_agent": ("场地", "场地与回应", "环境回应"),
    "form_agent": ("空间", "形式与构图", "空间与形式", "形式"),
    "structure_agent": ("结构", "规范", "结构与可行性", "无障碍", "消防"),
    "concept_agent": ("概念", "综合", "设计概念", "场地与回应", "形式与构图"),
    "drawing_agent": ("综合", "图面表达"),
}

GENERIC_SOURCE_TYPES = {"规范", "知识卡", "评价维度", "常见问题"}


def resolve_stage_agents(design_stage: str, enabled_agents: list[str] | None = None) -> list[str]:
    """返回当前阶段实际需要知识依据的专项 Agent。"""
    stage = normalize_stage(design_stage)
    allowed = STAGE_AGENTS.get(stage, STAGE_AGENTS["方案阶段"])
    selected = enabled_agents or allowed
    return [item for item in allowed if item in selected and item != "review_agent"]


def prepare_reference_bundle(
    references: list[dict[str, Any]],
    design_stage: str,
    enabled_agents: list[str] | None = None,
    *,
    per_agent_limit: int = 4,
    human_approved_only: bool = False,
) -> list[dict[str, Any]]:
    """为每个专项选择少量相关知识，并生成统一可追溯编号。"""
    eligible = [
        dict(item)
        for item in references
        if not human_approved_only or reference_is_human_approved(item)
    ]
    agents = resolve_stage_agents(design_stage, enabled_agents)
    selected_by_key: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for agent_type in agents:
        ranked = sorted(
            eligible,
            key=lambda item: (
                reference_score_for_agent(item, agent_type),
                str(item.get("title", "")),
            ),
            reverse=True,
        )
        positive = [item for item in ranked if reference_score_for_agent(item, agent_type) > 0]
        for item in positive[:per_agent_limit]:
            key = reference_stable_key(item)
            if key not in selected_by_key:
                selected_by_key[key] = dict(item)
                selected_by_key[key]["applicable_agents"] = []
                order.append(key)
            selected_by_key[key]["applicable_agents"].append(agent_type)

    result = [selected_by_key[key] for key in order]
    for index, item in enumerate(result, start=1):
        item["reference_id"] = f"K{index}"
        item["approval_status"] = (
            "human_approved" if reference_is_human_approved(item) else "legacy_unreviewed"
        )
    return result


def select_references_for_agent(
    references: list[dict[str, Any]], agent_type: str, limit: int = 4
) -> list[dict[str, Any]]:
    """从统一快照中取出当前专项可使用的知识。"""
    explicitly_routed = [
        item for item in references if agent_type in item.get("applicable_agents", [])
    ]
    if explicitly_routed:
        return explicitly_routed[:limit]
    ranked = sorted(
        references,
        key=lambda item: reference_score_for_agent(item, agent_type),
        reverse=True,
    )
    return [item for item in ranked if reference_score_for_agent(item, agent_type) > 0][:limit]


def context_for_agent(context: dict[str, Any], agent_type: str) -> dict[str, Any]:
    """建立当前专项独立上下文，限制知识与辅助裁切图的重复输入。"""
    selected = select_references_for_agent(context.get("references", []), agent_type)
    return {
        **context,
        "references": selected,
        "drawings": select_drawings_for_agent(context.get("drawings", []), agent_type),
        "knowledge_policy": context.get("knowledge_policy", "compatible"),
        "knowledge_target_agent": agent_type,
    }


def select_drawings_for_agent(drawings: list[dict], agent_type: str) -> list[dict]:
    """所有专项保留原图，只把自动裁切图发送给真正需要的专项。"""
    relevant_types = {
        "function_agent": {"plan", "site", "analysis"},
        "site_agent": {"site", "analysis"},
        "form_agent": {"elevation", "render", "analysis"},
        "structure_agent": {"plan", "section", "elevation"},
        "drawing_agent": {"site", "plan", "section", "elevation", "analysis", "render"},
        "concept_agent": {"site", "analysis", "render"},
    }.get(agent_type, set())
    result = []
    for drawing in drawings:
        if not drawing.get("derived_from"):
            result.append(drawing)
            continue
        drawing_type = str(drawing.get("drawing_type", ""))
        base_type = "plan" if drawing_type.startswith("plan-") else drawing_type
        if base_type in relevant_types:
            result.append(drawing)
    return result


def reference_score_for_agent(reference: dict[str, Any], agent_type: str) -> int:
    """按维度、来源类型和正文关键词估计知识对当前专项的适用性。"""
    dimensions = AGENT_DIMENSIONS.get(agent_type, ())
    dimension = str(reference.get("dimension", ""))
    primary_text = " ".join(
        str(reference.get(key, ""))
        for key in ("title", "dimension", "excerpt")
    )
    retrieval_text = str(reference.get("retrieval_text", ""))
    score = 0
    if any(item and item in dimension for item in dimensions):
        score += 20
    elif any(item and item in primary_text for item in dimensions):
        score += 10
    source_type = str(reference.get("source_type", ""))
    if score == 0 and source_type == "案例" and any(
        item and item in retrieval_text for item in dimensions
    ):
        score = 6
    if score > 0 and source_type in GENERIC_SOURCE_TYPES:
        score += 4
    elif score > 0 and source_type == "案例":
        score += 1
    if score > 0 and agent_type == "concept_agent" and source_type == "案例":
        score += 2
    return score


def reference_is_human_approved(reference: dict[str, Any]) -> bool:
    """结构化治理条目只有通过人工复核后才具有 governance_id。"""
    return bool(reference.get("governance_id"))


def reference_stable_key(reference: dict[str, Any]) -> str:
    """生成知识快照内去重键。"""
    governance_id = str(reference.get("governance_id") or "")
    if governance_id:
        return governance_id
    path = str(reference.get("path") or "")
    title = str(reference.get("title") or "")
    return f"{path}::{title}" if path or title else str(id(reference))


def normalize_stage(design_stage: str) -> str:
    """把中英文阶段值归一为三种中文阶段。"""
    value = str(design_stage or "").lower()
    if "concept" in value or "概念" in value:
        return "概念阶段"
    if "drawing" in value or "图纸" in value:
        return "图纸阶段"
    return "方案阶段"
