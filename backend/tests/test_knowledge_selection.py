"""验证知识依据会按专项分发，并遵守人工审核边界。"""

from app.knowledge_selection import (
    context_for_agent,
    prepare_reference_bundle,
)


def reference(
    title: str,
    dimension: str,
    *,
    governance_id: str = "",
    source_type: str = "知识卡",
) -> dict:
    """构造最小知识引用。"""
    return {
        "reference_id": "",
        "governance_id": governance_id,
        "title": title,
        "dimension": dimension,
        "source_type": source_type,
        "excerpt": title,
        "path": f"/{title}.md",
        "retrieval_text": f"{title}{dimension}",
    }


def test_reference_bundle_routes_each_dimension_to_correct_agent() -> None:
    """确认场地知识不会作为功能 Agent 的主要依据。"""
    bundle = prepare_reference_bundle(
        [
            reference("入口与门厅", "功能与流线", governance_id="KC-001"),
            reference("场地到达", "场地与回应", governance_id="KC-002"),
            reference("结构逻辑", "结构与可行性", governance_id="KC-003"),
        ],
        "方案阶段",
        per_agent_limit=1,
        human_approved_only=True,
    )
    context = {"references": bundle}

    function_refs = context_for_agent(context, "function_agent")["references"]
    site_refs = context_for_agent(context, "site_agent")["references"]

    assert [item["governance_id"] for item in function_refs] == ["KC-001"]
    assert [item["governance_id"] for item in site_refs] == ["KC-002"]
    assert function_refs[0]["reference_id"] != site_refs[0]["reference_id"]


def test_strict_bundle_excludes_legacy_unreviewed_markdown() -> None:
    """确认研究评分模式不会绕过人工复核读取旧知识。"""
    bundle = prepare_reference_bundle(
        [
            reference("旧知识", "功能与流线"),
            reference("人工批准知识", "功能与流线", governance_id="KC-001"),
        ],
        "方案阶段",
        human_approved_only=True,
    )

    assert [item["title"] for item in bundle] == ["人工批准知识"]
    assert bundle[0]["approval_status"] == "human_approved"
