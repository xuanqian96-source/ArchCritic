"""校验模型证据输出，并用固定建筑学等级表换算专项分数。"""

from __future__ import annotations

import re
from typing import Any


LEVEL_PERCENTAGES = {0: 30.0, 1: 50.0, 2: 65.0, 3: 78.0, 4: 92.0}
LEVEL_LABELS = {0: "严重不足", 1: "较弱", 2: "基本成立", 3: "良好", 4: "优秀"}
CONFIDENCE_VALUES = {"high", "medium", "low"}
REQUIREMENT_STATUSES = {"met", "partly_met", "not_met", "uncertain", "not_applicable"}
SCOPE_STATUSES = {"verified", "partly_verified", "unverifiable"}
KNOWLEDGE_USE_TYPES = {"rubric_support", "boundary_limit", "case_inspiration"}
KNOWLEDGE_EFFECTS = {"support", "limit", "context_only"}


def normalize_evidence_output(
    spec: dict,
    raw_output: dict,
    requirements: list[dict],
    references: list[dict] | None = None,
    evidence_inventory: dict | None = None,
) -> dict:
    """把模型的事实与等级转换为兼容旧报告的专项评价。"""
    if not isinstance(raw_output, dict):
        raw_output = {}
    assessments = normalize_assessment_mapping(raw_output.get("criterion_assessments"))
    sub_scores = {}
    normalized_assessments = {}
    total_score = 0.0
    valid_reference_ids = {
        str(item.get("reference_id", "")).upper(): item
        for item in references or []
        if item.get("reference_id")
    }
    invalid_reference_ids: set[str] = set()
    inventory_facts = {
        str(item.get("fact_id")): item
        for item in (evidence_inventory or {}).get("facts", [])
        if item.get("fact_id")
    }
    invalid_fact_ids: set[str] = set()
    for name, max_score in spec["sub_scores"].items():
        item = assessments.get(name) or {}
        level = clamp_level(item.get("level"))
        scope_status = normalize_scope_status(item.get("scope_status"))
        evidence_fact_ids = normalize_fact_ids(
            item.get("evidence_fact_ids"), inventory_facts, invalid_fact_ids
        )
        level = apply_evidence_level_cap(
            level,
            item,
            scope_status,
            evidence_fact_ids,
            inventory_facts,
        )
        score = round(max_score * LEVEL_PERCENTAGES[level] / 100, 1)
        total_score += score
        reason = safe_text(item.get("reason"), "该项证据不足，需要继续核对。")
        evidence = safe_text(item.get("evidence"), "未提供可定位的图纸或说明依据。")
        confidence = normalize_confidence(item.get("confidence"))
        criterion_reference_ids = normalize_reference_ids(
            item.get("knowledge_reference_ids"),
            valid_reference_ids,
            invalid_reference_ids,
        )
        sub_scores[name] = {
            "score": score,
            "max_score": max_score,
            "reason": reason,
            "evidence": evidence,
        }
        normalized_assessments[name] = {
            "level": level,
            "level_label": LEVEL_LABELS[level],
            "reason": reason,
            "evidence": evidence,
            "confidence": confidence,
            "scope_status": scope_status,
            "knowledge_reference_ids": criterion_reference_ids,
            "evidence_fact_ids": evidence_fact_ids,
        }

    facts = normalize_fact_records(raw_output.get("observed_facts"))
    must_fix, demoted, uncertain_feedback = normalize_must_fix(raw_output.get("must_fix"))
    should_improve = safe_string_list(raw_output.get("should_improve"))
    should_improve = (should_improve + demoted)[:4]
    uncertain = safe_string_list(raw_output.get("uncertain_observations"))
    uncertain = (uncertain + uncertain_feedback)[:6]
    knowledge_uses = normalize_knowledge_uses(
        raw_output.get("knowledge_uses"),
        spec,
        valid_reference_ids,
        invalid_reference_ids,
    )
    return {
        "overall_score": round(total_score, 1),
        "confidence": normalize_confidence(raw_output.get("confidence")),
        "summary": safe_text(raw_output.get("summary"), f"{spec['dimension']}证据审查完成。"),
        "observed_facts": [item["statement"] for item in facts],
        "evidence_records": facts,
        "criterion_assessments": normalized_assessments,
        "knowledge_uses": knowledge_uses,
        "provided_reference_ids": list(valid_reference_ids),
        "invalid_knowledge_reference_ids": sorted(invalid_reference_ids),
        "invalid_evidence_fact_ids": sorted(invalid_fact_ids),
        "evidence_inventory_version": (evidence_inventory or {}).get("version", "not_available"),
        "sub_scores": sub_scores,
        "requirement_checks": normalize_requirement_checks(
            raw_output.get("requirement_checks"), requirements
        ),
        "must_fix": must_fix,
        "should_improve": should_improve or ["建议补充能验证当前专项判断的图纸证据。"],
        "optional_improvements": safe_string_list(raw_output.get("optional_improvements"))
        or ["可继续深化专项表达。"],
        "strengths": safe_string_list(raw_output.get("strengths"))
        or ["方案具备继续深化的基础。"],
        "missing_information": safe_string_list(raw_output.get("missing_information")),
        "uncertain_observations": uncertain,
    }


def normalize_scope_status(value: Any) -> str:
    """把证据覆盖范围归一为三种状态。"""
    normalized = str(value or "partly_verified").strip().lower()
    return normalized if normalized in SCOPE_STATUSES else "partly_verified"


def apply_evidence_level_cap(
    level: int,
    item: dict,
    scope_status: str,
    evidence_fact_ids: list[str] | None = None,
    inventory_facts: dict[str, dict] | None = None,
) -> int:
    """高等级必须由直接、可定位且相互印证的证据支持。"""
    confidence = normalize_confidence(item.get("confidence"))
    evidence = safe_text(item.get("evidence"), "")
    if scope_status == "unverifiable" or confidence == "low":
        return min(level, 2)
    if scope_status == "partly_verified" or confidence == "medium":
        return min(level, 3)
    fact_ids = evidence_fact_ids or []
    fact_sources = {
        source
        for fact_id in fact_ids
        for source in (inventory_facts or {}).get(fact_id, {}).get("source_drawing_ids", [])
    }
    source_count = len(fact_sources) if fact_ids else count_distinct_evidence_sources(evidence)
    if level >= 4 and source_count < 2:
        return 3
    return level


def normalize_fact_ids(
    value: Any,
    inventory_facts: dict[str, dict],
    invalid_fact_ids: set[str],
) -> list[str]:
    """只保留共享事实清单中真实存在的 E 编号。"""
    result = []
    for raw in value if isinstance(value, list) else []:
        fact_id = str(raw or "").strip().upper()
        if fact_id in inventory_facts and fact_id not in result:
            result.append(fact_id)
        elif fact_id:
            invalid_fact_ids.add(fact_id)
    return result[:6]


def count_distinct_evidence_sources(evidence: str) -> int:
    """粗略统计证据中可定位的不同图纸或文字来源。"""
    patterns = re.findall(
        r"(?:board[_\s-]?\d+|图纸\s*\d+|平面图|总平面|剖面图|立面图|分析图|设计说明|任务书)",
        evidence,
        flags=re.IGNORECASE,
    )
    return len({item.lower().replace(" ", "") for item in patterns})


def normalize_reference_ids(
    value: Any,
    valid_reference_ids: dict[str, dict],
    invalid_reference_ids: set[str],
) -> list[str]:
    """只保留本次知识快照中真实存在的编号。"""
    result = []
    for raw in value if isinstance(value, list) else []:
        reference_id = str(raw or "").strip().upper()
        if reference_id in valid_reference_ids and reference_id not in result:
            result.append(reference_id)
        elif reference_id:
            invalid_reference_ids.add(reference_id)
    return result[:3]


def normalize_knowledge_uses(
    value: Any,
    spec: dict,
    valid_reference_ids: dict[str, dict],
    invalid_reference_ids: set[str],
) -> list[dict]:
    """校验知识编号与用途，案例只允许作为背景启发。"""
    results = []
    criteria = set(spec["sub_scores"])
    for item in value if isinstance(value, list) else []:
        if not isinstance(item, dict):
            continue
        reference_id = str(item.get("reference_id") or "").strip().upper()
        reference = valid_reference_ids.get(reference_id)
        if reference is None:
            if reference_id:
                invalid_reference_ids.add(reference_id)
            continue
        criterion = str(item.get("criterion") or "").strip()
        use_type = str(item.get("use_type") or "").strip()
        effect = str(item.get("effect") or "").strip()
        if criterion not in criteria or use_type not in KNOWLEDGE_USE_TYPES:
            continue
        if effect not in KNOWLEDGE_EFFECTS:
            continue
        if reference.get("source_type") == "案例":
            use_type = "case_inspiration"
            effect = "context_only"
        results.append(
            {
                "reference_id": reference_id,
                "criterion": criterion,
                "use_type": use_type,
                "claim": safe_text(item.get("claim"), "知识仅作为评价边界。"),
                "effect": effect,
            }
        )
    return results[:8]


def normalize_assessment_mapping(value: Any) -> dict:
    """兼容部分 JSON-object 模型把具名评分项返回为数组的情况。"""
    if isinstance(value, dict):
        return value
    if not isinstance(value, list):
        return {}
    result = {}
    for item in value:
        if not isinstance(item, dict):
            continue
        name = str(item.get("criterion") or item.get("name") or "").strip()
        if name:
            result[name] = item
    return result


def clamp_level(value: Any) -> int:
    """把模型等级限制为 0 到 4 的整数。"""
    try:
        return max(0, min(4, int(round(float(value)))))
    except (TypeError, ValueError):
        return 2


def normalize_confidence(value: Any) -> str:
    """把置信度归一为高、中、低三个英文枚举。"""
    normalized = str(value or "medium").strip().lower()
    return normalized if normalized in CONFIDENCE_VALUES else "medium"


def normalize_fact_records(value: Any) -> list[dict]:
    """保留事实文本、来源和置信度，便于历史报告复核。"""
    records = []
    for item in value or []:
        if isinstance(item, str):
            statement = item.strip()
            source = "模型未标明来源"
            confidence = "medium"
        elif isinstance(item, dict):
            statement = safe_text(item.get("statement"), "")
            source = safe_text(item.get("source"), "模型未标明来源")
            confidence = normalize_confidence(item.get("confidence"))
        else:
            continue
        if statement:
            records.append(
                {"statement": statement[:180], "source": source[:160], "confidence": confidence}
            )
    return records[:8]


def normalize_must_fix(value: Any) -> tuple[list[str], list[str], list[str]]:
    """只有高置信且有证据的问题进入必须修改，其余自动降级。"""
    confirmed = []
    demoted = []
    uncertain = []
    for item in value or []:
        if isinstance(item, str):
            demoted.append(f"需进一步核对：{item.strip()}")
            continue
        if not isinstance(item, dict):
            continue
        text = safe_text(item.get("text"), "")
        evidence = safe_text(item.get("evidence"), "")
        confidence = normalize_confidence(item.get("confidence"))
        if not text:
            continue
        if confidence == "high" and evidence:
            confirmed.append(text)
        elif confidence == "medium":
            demoted.append(f"需复核后优先处理：{text}")
        else:
            uncertain.append(f"低置信观察：{text}")
    return confirmed[:4], demoted[:4], uncertain[:4]


def normalize_requirement_checks(value: Any, requirements: list[dict]) -> list[dict]:
    """丢弃不存在的规则编号，防止模型自行发明任务书约束。"""
    by_id = {item["id"]: item for item in requirements}
    checks = []
    for item in value or []:
        if not isinstance(item, dict):
            continue
        requirement_id = str(item.get("requirement_id") or "")
        requirement = by_id.get(requirement_id)
        status = str(item.get("status") or "uncertain")
        if not requirement or status not in REQUIREMENT_STATUSES:
            continue
        checks.append(
            {
                "requirement_id": requirement_id,
                "text": requirement["text"],
                "level": requirement["level"],
                "dimension": requirement["dimension"],
                "verification_mode": requirement["verification_mode"],
                "status": status,
                "evidence": safe_text(item.get("evidence"), "未提供核对依据。")[:200],
                "confidence": normalize_confidence(item.get("confidence")),
            }
        )
    returned_ids = {item["requirement_id"] for item in checks}
    for requirement in requirements:
        if requirement["id"] in returned_ids:
            continue
        checks.append(
            {
                "requirement_id": requirement["id"],
                "text": requirement["text"],
                "level": requirement["level"],
                "dimension": requirement["dimension"],
                "verification_mode": requirement["verification_mode"],
                "status": "uncertain",
                "evidence": "模型未返回该条任务书核对结果，系统按不确定处理且不扣分。",
                "confidence": "low",
            }
        )
    return checks[:12]


def safe_text(value: Any, fallback: str) -> str:
    """把模型文本压缩为非空字符串。"""
    text = str(value or "").strip()
    return text[:360] if text else fallback


def safe_string_list(value: Any) -> list[str]:
    """把模型列表转换为有限长度的非空文本列表。"""
    if not isinstance(value, list):
        return []
    return [str(item).strip()[:240] for item in value if str(item).strip()][:6]
