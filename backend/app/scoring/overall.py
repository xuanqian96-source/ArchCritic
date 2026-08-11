"""合并专项原始分、任务书符合度与教师校准，生成最终评分审计记录。"""

from __future__ import annotations

from collections import defaultdict

from app.scoring.calibration import predict_calibrated_score
from app.services.taskbooks import calculate_weighted_score


CONFIDENCE_RANK = {"low": 1, "medium": 2, "high": 3}
COMPLIANCE_VALUES = {"met": 1.0, "partly_met": 0.65, "not_met": 0.35}
REQUIREMENT_WEIGHTS = {"required": 1.0, "flexible_required": 0.6}
COMPLIANCE_SHARE = 0.15


def build_evidence_score(
    evaluations: list[dict],
    weights: dict[str, float],
    structured_requirements: list[dict],
    calibrator: dict | None,
    independent_checks: list[dict] | None = None,
) -> dict:
    """生成原始质量分、任务书符合分、校准分和不确定区间。"""
    quality_score = calculate_weighted_score(evaluations, weights)
    requirement_checks = (
        validate_independent_checks(independent_checks, structured_requirements)
        if independent_checks is not None
        else aggregate_requirement_checks(evaluations, structured_requirements)
    )
    compliance_score = calculate_compliance_score(requirement_checks)
    raw_score = quality_score
    if compliance_score is not None:
        raw_score = round(
            quality_score * (1 - COMPLIANCE_SHARE)
            + compliance_score * COMPLIANCE_SHARE,
            1,
        )
    final_score = predict_calibrated_score(raw_score, calibrator)
    half_width = calculate_interval_half_width(evaluations, requirement_checks, calibrator)
    return {
        "architecture": "evidence_v2",
        "quality_score": quality_score,
        "compliance_score": compliance_score,
        "raw_score": raw_score,
        "calibrated_score": final_score,
        "score_interval": [
            round(max(0.0, final_score - half_width), 1),
            round(min(100.0, final_score + half_width), 1),
        ],
        "calibrator_version": (calibrator or {}).get("version", "not_configured"),
        "calibration_sample_count": int((calibrator or {}).get("sample_count", 0)),
        "requirement_checks": requirement_checks,
        "requirement_audit": build_requirement_audit(
            requirement_checks, structured_requirements
        ),
    }


def validate_independent_checks(checks: list[dict], requirements: list[dict]) -> list[dict]:
    """只接受当前任务书中真实存在的独立核对结果。"""
    rules = {item["id"]: item for item in requirements}
    validated = []
    seen = set()
    for item in checks or []:
        requirement_id = str(item.get("requirement_id") or item.get("id") or "")
        if requirement_id not in rules or requirement_id in seen:
            continue
        status = str(item.get("status") or "uncertain")
        confidence = str(item.get("confidence") or "low")
        if status not in {*COMPLIANCE_VALUES, "uncertain", "not_applicable"}:
            status = "uncertain"
        if confidence not in CONFIDENCE_RANK:
            confidence = "low"
        validated.append(
            {
                **rules[requirement_id],
                "status": status,
                "evidence": str(item.get("evidence") or "")[:220],
                "confidence": confidence,
                "evidence_fact_ids": list(item.get("evidence_fact_ids") or [])[:6],
            }
        )
        seen.add(requirement_id)
    return sorted(validated, key=lambda item: item["id"])


def build_requirement_audit(checks: list[dict], requirements: list[dict]) -> dict:
    """记录任务书规则是否真正得到可靠核对。"""
    scored_levels = set(REQUIREMENT_WEIGHTS)
    expected = [item for item in requirements if item.get("level") in scored_levels]
    checked = [
        item
        for item in checks
        if item.get("level") in scored_levels
        and item.get("status") in COMPLIANCE_VALUES
        and item.get("confidence") != "low"
    ]
    return {
        "required_or_flexible_count": len(expected),
        "confidently_checked_count": len(checked),
        "confident_check_rate": (
            round(len(checked) / len(expected), 3) if expected else None
        ),
        "missing_or_uncertain_count": max(0, len(expected) - len(checked)),
        "compliance_share": COMPLIANCE_SHARE,
    }


def aggregate_requirement_checks(
    evaluations: list[dict], structured_requirements: list[dict]
) -> list[dict]:
    """按任务书编号去重；同置信度冲突时标记为不确定，不重复扣分。"""
    rules = {item["id"]: item for item in structured_requirements}
    grouped = defaultdict(list)
    for evaluation in evaluations:
        details = evaluation.get("details") or {}
        for check in details.get("requirement_checks") or []:
            if check.get("requirement_id") in rules:
                grouped[check["requirement_id"]].append(check)
    results = []
    for requirement_id, checks in grouped.items():
        highest_rank = max(CONFIDENCE_RANK.get(item.get("confidence"), 2) for item in checks)
        strongest = [
            item for item in checks
            if CONFIDENCE_RANK.get(item.get("confidence"), 2) == highest_rank
        ]
        statuses = {item.get("status") for item in strongest}
        chosen = strongest[0]
        status = chosen.get("status", "uncertain") if len(statuses) == 1 else "uncertain"
        rule = rules[requirement_id]
        results.append(
            {
                **rule,
                "status": status,
                "evidence": chosen.get("evidence", ""),
                "confidence": chosen.get("confidence", "medium"),
            }
        )
    return sorted(results, key=lambda item: item["id"])


def calculate_compliance_score(checks: list[dict]) -> float | None:
    """只让已确认的强制与弹性要求影响符合度，选配和参考项不扣分。"""
    weighted_values = []
    for item in checks:
        weight = REQUIREMENT_WEIGHTS.get(item.get("level"))
        value = COMPLIANCE_VALUES.get(item.get("status"))
        if weight is None or value is None or item.get("confidence") == "low":
            continue
        weighted_values.append((value, weight))
    if not weighted_values:
        return None
    total_weight = sum(weight for _, weight in weighted_values)
    return round(sum(value * weight for value, weight in weighted_values) / total_weight * 100, 1)


def calculate_interval_half_width(
    evaluations: list[dict], checks: list[dict], calibrator: dict | None
) -> float:
    """根据识图置信度、缺失信息和小样本校准残差给出保守区间。"""
    if not evaluations:
        return 12.0
    confidence_penalty = sum(
        {"high": 0.0, "medium": 1.2, "low": 3.0}.get(
            str((item.get("details") or {}).get("confidence", "medium")), 1.2
        )
        for item in evaluations
    ) / len(evaluations)
    missing_count = sum(
        len((item.get("details") or {}).get("missing_information") or [])
        + len((item.get("details") or {}).get("uncertain_observations") or [])
        for item in evaluations
    )
    uncertain_checks = len([item for item in checks if item.get("status") == "uncertain"])
    calibration_mae = float((calibrator or {}).get("training_mae", 0.0))
    width = 4.0 + confidence_penalty + min(3.0, missing_count * 0.35)
    width += min(2.0, uncertain_checks * 0.4) + min(3.0, calibration_mae * 0.35)
    return round(max(4.0, min(15.0, width)), 1)
