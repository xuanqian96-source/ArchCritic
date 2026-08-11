"""调用证据优先专项 Agent，并转换为前端兼容的专项评审数据。"""

from __future__ import annotations

from typing import Any

from app.agents.function_agent import build_agent_evaluation_details
from app.agents.prompts.evidence_agents_v2 import (
    EVIDENCE_SPECIALIST_SYSTEM_PROMPT,
    build_evidence_json_schema,
    build_evidence_user_prompt,
    get_evidence_spec,
)
from app.scoring.evidence import normalize_evidence_output


class EvidenceSpecialistAgent:
    """让模型只生成证据与等级，再由后端换算专项分。"""

    def __init__(self, llm_client: Any, agent_type: str) -> None:
        """保存模型客户端和专项定义。"""
        self.llm_client = llm_client
        self.spec = get_evidence_spec(agent_type)

    def run(self, context: dict, budget_seconds: float) -> dict:
        """调用多模态模型并返回后端确定性计分后的专项评价。"""
        from app.agents.scheme_review import build_completion_kwargs, create_json_completion

        prompt, requirements = build_evidence_user_prompt(context, self.spec)
        content = [{"type": "text", "text": prompt}]
        create_kwargs = build_completion_kwargs(
            self.llm_client,
            EVIDENCE_SPECIALIST_SYSTEM_PROMPT,
            content,
            f"{self.spec['agent_type']}_evidence_v2",
            build_evidence_json_schema(self.spec, requirements),
            max(self.llm_client.max_tokens, 3200),
            budget_seconds,
        )
        raw_output = create_json_completion(self.llm_client, create_kwargs)
        report = normalize_evidence_output(
            self.spec,
            raw_output,
            requirements,
            context.get("references", []),
            context.get("evidence_inventory") or {},
        )
        return evidence_report_to_evaluation(self.spec, report)


def evidence_report_to_evaluation(spec: dict, report: dict) -> dict:
    """在旧报告字段中保留新证据记录、等级与任务书核对结果。"""
    details = build_agent_evaluation_details(report)
    details.update(
        {
            "evidence_records": report["evidence_records"],
            "criterion_assessments": report["criterion_assessments"],
            "requirement_checks": report["requirement_checks"],
            "knowledge_uses": report["knowledge_uses"],
            "invalid_knowledge_reference_ids": report["invalid_knowledge_reference_ids"],
            "provided_reference_ids": report["provided_reference_ids"],
            "invalid_evidence_fact_ids": report["invalid_evidence_fact_ids"],
            "evidence_inventory_version": report["evidence_inventory_version"],
            "score_source": "backend_level_mapping_v1",
        }
    )
    return {
        "agent_type": spec["agent_type"],
        "dimension": spec["dimension"],
        "score": report["overall_score"],
        "summary": report["summary"],
        "strengths": report["strengths"],
        "issues": report["must_fix"],
        "suggestions": report["should_improve"],
        "details": details,
    }
