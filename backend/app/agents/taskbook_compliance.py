"""独立核对任务书强制与弹性要求，供总分层计算符合度。"""

from __future__ import annotations

import json
from typing import Any

from app.services.taskbook_rules import scorable_requirements


COMPLIANCE_STATUSES = {"met", "partly_met", "not_met", "uncertain", "not_applicable"}
CONFIDENCE_VALUES = {"high", "medium", "low"}


TASKBOOK_COMPLIANCE_SYSTEM_PROMPT = """
你是 ArchCritic 的独立任务书核对 Agent。你只核对结构化要求与共享图纸事实，不评价设计优劣，不输出分数，不猜测教师评分。

规则：
1. 只核对给定的 requirement_id，每条必须返回一次。
2. met 或 partly_met 必须引用共享事实中真实存在的 E 编号。
3. “未看见”、图纸模糊或未上传不等于不满足；这些情况返回 uncertain，不得扣分。
4. not_met 只能用于高置信直接矛盾，不得根据常识或案例补齐结论。
5. 数值与合规性无法从现有材料复核时返回 uncertain。
6. 任务书要求与当前阶段明显无关时才返回 not_applicable。
7. 只输出 JSON 对象，不得输出 Markdown、分数或额外说明。
""".strip()


class TaskbookComplianceAgent:
    """使用共享事实执行一次独立任务书核对。"""

    def __init__(self, llm_client: Any) -> None:
        """保存模型客户端。"""
        self.llm_client = llm_client

    def run(self, context: dict, budget_seconds: float) -> dict:
        """核对可计分要求；无此类要求时不调用模型。"""
        from app.agents.scheme_review import build_completion_kwargs, create_json_completion

        requirements = scorable_requirements(context.get("structured_requirements") or [])
        if not requirements:
            return build_empty_compliance_result()
        raw = create_json_completion(
            self.llm_client,
            build_completion_kwargs(
                self.llm_client,
                TASKBOOK_COMPLIANCE_SYSTEM_PROMPT,
                [{"type": "text", "text": build_compliance_prompt(context, requirements)}],
                "taskbook_compliance_v1",
                build_compliance_schema([item["id"] for item in requirements]),
                max(self.llm_client.max_tokens, 2200),
                budget_seconds,
            ),
        )
        return normalize_compliance_output(
            raw, requirements, context.get("evidence_inventory") or {}
        )


def build_empty_compliance_result() -> dict:
    """返回无可计分要求时的完整审计结构。"""
    return {
        "version": "taskbook_compliance_v1",
        "checks": [],
        "expected_count": 0,
        "returned_count": 0,
        "confident_count": 0,
        "invalid_requirement_ids": [],
        "invalid_evidence_fact_ids": [],
    }


def build_compliance_prompt(context: dict, requirements: list[dict]) -> str:
    """构造只包含可计分任务书条款与共享事实的紧凑提示词。"""
    inventory = context.get("evidence_inventory") or {}
    template = [
        {
            "requirement_id": item["id"],
            "status": "uncertain",
            "evidence_fact_ids": [],
            "evidence": "根据现有图纸事实填写",
            "confidence": "low",
        }
        for item in requirements
    ]
    return f"""
请核对当前提交是否满足任务书的强制与弹性要求。

年级：{context.get('grade', '')}
阶段：{context.get('design_stage', '')}
评判边界：{context.get('drawing_scope', '')}

【待核对要求】
{json.dumps(requirements, ensure_ascii=False, indent=2)}

【共享图纸事实】
{json.dumps(inventory.get('facts') or [], ensure_ascii=False, indent=2)}

【识图边界】
{json.dumps(inventory.get('missing_information') or [], ensure_ascii=False, indent=2)}

输出仅包含 checks，并严格保留下列 requirement_id：
{json.dumps(template, ensure_ascii=False, indent=2)}
status 只能是 met、partly_met、not_met、uncertain、not_applicable。
""".strip()


def build_compliance_schema(requirement_ids: list[str]) -> dict:
    """按当前任务书编号构造结构化输出约束。"""
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["checks"],
        "properties": {
            "checks": {
                "type": "array",
                "minItems": len(requirement_ids),
                "maxItems": len(requirement_ids),
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "requirement_id", "status", "evidence_fact_ids", "evidence", "confidence"
                    ],
                    "properties": {
                        "requirement_id": {"type": "string", "enum": requirement_ids},
                        "status": {"type": "string", "enum": sorted(COMPLIANCE_STATUSES)},
                        "evidence_fact_ids": {
                            "type": "array",
                            "maxItems": 6,
                            "items": {"type": "string", "pattern": "^E[1-9][0-9]*$"},
                        },
                        "evidence": {"type": "string", "maxLength": 220},
                        "confidence": {"type": "string", "enum": sorted(CONFIDENCE_VALUES)},
                    },
                },
            }
        },
    }


def normalize_compliance_output(raw: Any, requirements: list[dict], inventory: dict) -> dict:
    """校验任务书和事实编号，未返回条款统一降为不确定。"""
    payload = raw if isinstance(raw, dict) else {}
    rules = {item["id"]: item for item in requirements}
    facts = {
        str(item.get("fact_id")): item
        for item in inventory.get("facts") or []
        if item.get("fact_id")
    }
    by_id = {}
    invalid_rules = set()
    invalid_facts = set()
    for item in payload.get("checks") or []:
        if not isinstance(item, dict):
            continue
        requirement_id = str(item.get("requirement_id") or "")
        if requirement_id not in rules:
            if requirement_id:
                invalid_rules.add(requirement_id)
            continue
        status = str(item.get("status") or "uncertain")
        if status not in COMPLIANCE_STATUSES:
            status = "uncertain"
        fact_ids = []
        for raw_id in item.get("evidence_fact_ids") or []:
            fact_id = str(raw_id or "").upper()
            if fact_id in facts and fact_id not in fact_ids:
                fact_ids.append(fact_id)
            elif fact_id:
                invalid_facts.add(fact_id)
        confidence = str(item.get("confidence") or "low")
        if confidence not in CONFIDENCE_VALUES:
            confidence = "low"
        if status in {"met", "partly_met"} and not fact_ids:
            status = "uncertain"
            confidence = "low"
        if status == "not_met" and confidence != "high":
            status = "uncertain"
        by_id[requirement_id] = {
            **rules[requirement_id],
            "requirement_id": requirement_id,
            "status": status,
            "evidence_fact_ids": fact_ids[:6],
            "evidence": str(item.get("evidence") or "未提供可复核依据。")[:220],
            "confidence": confidence,
        }
    checks = [by_id.get(item["id"]) or build_uncertain_check(item) for item in requirements]
    return {
        "version": "taskbook_compliance_v1",
        "checks": checks,
        "expected_count": len(requirements),
        "returned_count": len(by_id),
        "confident_count": len(
            [item for item in checks if item["confidence"] != "low" and item["status"] != "uncertain"]
        ),
        "invalid_requirement_ids": sorted(invalid_rules),
        "invalid_evidence_fact_ids": sorted(invalid_facts),
    }


def build_uncertain_check(requirement: dict) -> dict:
    """为模型漏掉的要求生成不扣分的审计记录。"""
    return {
        **requirement,
        "requirement_id": requirement["id"],
        "status": "uncertain",
        "evidence_fact_ids": [],
        "evidence": "模型未返回该条核对结果，系统按不确定处理且不扣分。",
        "confidence": "low",
    }
