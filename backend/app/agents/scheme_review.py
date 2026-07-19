"""阶段化多 Agent 编排，负责顺序评审和综合报告整理。"""

import json
from time import monotonic
from typing import Any, Iterator

from app.agents.function_agent import (
    FunctionAgent,
    build_agent_evaluation_details,
    build_image_inputs,
    clamp_number,
    extract_json_text,
    function_agent_report_to_overall,
    safe_list,
    safe_text,
    score_to_grade,
)
from app.agents.prompts.scheme_agents_v1 import (
    COMPREHENSIVE_JSON_SCHEMA,
    COMPREHENSIVE_SYSTEM_PROMPT,
    SCHEME_SPECIALIST_SPECS,
    SPECIALIST_SYSTEM_PROMPT,
    build_comprehensive_user_prompt,
    build_specialist_json_schema,
    build_specialist_user_prompt,
)
from app.services.taskbooks import build_task_book_snapshot, calculate_weighted_score
from app.scoring.overall import build_evidence_score


FUNCTION_STEP = {
    "agent_type": "function_agent",
    "name": "功能与流线 Agent",
    "dimension": "功能与流线",
}
REVIEW_STEP = {
    "agent_type": "review_agent",
    "name": "综合评审 Agent",
    "dimension": "综合评审",
}
STAGE_AGENT_ORDER = {
    "概念阶段": ["site_agent", "form_agent", "concept_agent", "review_agent"],
    "方案阶段": ["function_agent", "site_agent", "form_agent", "structure_agent", "review_agent"],
    "图纸阶段": ["drawing_agent", "function_agent", "site_agent", "form_agent", "structure_agent", "review_agent"],
}


class ModelOutputTruncatedError(ValueError):
    """表示模型输出被长度上限截断。"""


def resolve_review_stage(design_stage: str) -> str:
    """把前端和接口阶段名称归一为三种评图阶段。"""
    normalized = str(design_stage or "").strip().lower()
    if normalized == "concept" or "概念" in normalized:
        return "概念阶段"
    if normalized == "drawing" or "图纸" in normalized:
        return "图纸阶段"
    return "方案阶段"


def is_multi_agent_stage(design_stage: str) -> bool:
    """判断当前阶段是否使用阶段化多 Agent 编排。"""
    normalized = str(design_stage or "").strip().lower()
    return normalized in {"concept", "scheme", "drawing"} or any(
        keyword in normalized for keyword in ("概念", "方案", "图纸")
    )


def generate_scheme_review(llm_client: Any, context: dict) -> dict:
    """兼容旧调用，顺序执行当前阶段 Agent 并返回最终报告。"""
    final_report = None
    for item in iter_scheme_review_events(llm_client, context):
        if item["event"] == "report":
            final_report = item["report"]
    if final_report is None:
        raise RuntimeError("阶段化多 Agent 未生成最终报告。")
    return final_report


def iter_scheme_review_events(llm_client: Any, context: dict) -> Iterator[dict]:
    """按阶段和用户选择顺序产出 Agent 事件与最终报告。"""
    started_at = monotonic()
    specialist_evaluations = []
    agent_order = resolve_enabled_agent_order(context)
    use_evidence_v2 = context.get("scoring_architecture") == "evidence_v2"
    for agent_type in [item for item in agent_order if item != "review_agent"]:
        spec = get_agent_spec(agent_type)
        yield build_agent_event("start", spec, f"开始核对{spec['dimension']}。")
        ensure_review_budget(llm_client, started_at)
        if use_evidence_v2:
            from app.agents.evidence_review import EvidenceSpecialistAgent

            evaluation = EvidenceSpecialistAgent(llm_client, agent_type).run(
                context, remaining_seconds(llm_client, started_at)
            )
        elif agent_type == "function_agent":
            function_agent = FunctionAgent(
                llm_client.client,
                llm_client.model,
                llm_client.structured_output_mode,
                llm_client.max_tokens,
                llm_client.image_detail,
                llm_client.extra_body,
                llm_client.reasoning_effort,
            )
            function_report = function_agent.run(context)
            evaluation = function_agent_report_to_overall(function_report, context)["agent_evaluations"][0]
        else:
            report = SchemeSpecialistAgent(llm_client, spec).run(
                context, remaining_seconds(llm_client, started_at)
            )
            evaluation = specialist_report_to_evaluation(spec, report)
        specialist_evaluations.append(evaluation)
        yield build_agent_event("done", spec, f"{spec['dimension']}专项评审完成。")

    if not specialist_evaluations:
        raise ValueError("当前阶段至少需要启用一个专项 Agent。")
    if "review_agent" in agent_order:
        yield build_agent_event("start", REVIEW_STEP, "正在汇总已完成的专项结果并生成反馈报告。")
        ensure_review_budget(llm_client, started_at)
        synthesis = ComprehensiveReviewAgent(llm_client).run(
            context,
            specialist_evaluations,
            remaining_seconds(llm_client, started_at),
        )
        yield build_agent_event("done", REVIEW_STEP, "综合反馈报告已整理完成。")
    else:
        synthesis = build_local_synthesis(specialist_evaluations)
    report = build_scheme_overall_report(synthesis, specialist_evaluations, context)
    yield {"event": "report", "report": report}


def resolve_enabled_agent_order(context: dict) -> list[str]:
    """按阶段白名单过滤用户选择，避免前端显示与后端执行不一致。"""
    stage_order = STAGE_AGENT_ORDER[resolve_review_stage(context.get("design_stage", ""))]
    selected = context.get("enabled_agents") or stage_order
    return [agent for agent in stage_order if agent in selected]


def get_agent_spec(agent_type: str) -> dict:
    """返回统一的 Agent 显示信息和评分规则。"""
    if agent_type == "function_agent":
        return FUNCTION_STEP
    return SCHEME_SPECIALIST_SPECS[agent_type]


def build_agent_event(status: str, spec: dict, message: str) -> dict:
    """生成可供前端展示的 Agent 进度事件。"""
    return {
        "event": "agent",
        "status": status,
        "agent_type": spec["agent_type"],
        "agent_name": spec["name"],
        "message": message,
    }


def remaining_seconds(llm_client: Any, started_at: float) -> float:
    """返回综合评审剩余可用秒数。"""
    return max(1.0, llm_client.review_timeout_seconds - (monotonic() - started_at))


def ensure_review_budget(llm_client: Any, started_at: float) -> None:
    """超过总时限时立即停止后续 Agent。"""
    if remaining_seconds(llm_client, started_at) <= 1.0:
        raise TimeoutError("多 Agent 评审已达到总时限。")


class SchemeSpecialistAgent:
    """调用当前阶段的一个专项 Agent。"""

    def __init__(self, llm_client: Any, spec: dict) -> None:
        """保存模型客户端和专项规则。"""
        self.llm_client = llm_client
        self.spec = spec

    def run(self, context: dict, budget_seconds: float) -> dict:
        """读取图文输入并返回专项评审结果。"""
        content = [{"type": "text", "text": build_specialist_user_prompt(context, self.spec)}]
        content.extend(build_image_inputs(context["drawings"], detail=self.llm_client.image_detail))
        create_kwargs = build_completion_kwargs(
            self.llm_client,
            SPECIALIST_SYSTEM_PROMPT,
            content,
            f"{self.spec['agent_type']}_report",
            build_specialist_json_schema(self.spec),
            self.llm_client.max_tokens,
            budget_seconds,
        )
        raw_output = create_json_completion(self.llm_client, create_kwargs)
        return validate_specialist_output(self.spec, raw_output)


class ComprehensiveReviewAgent:
    """汇总专项结果并生成正式反馈报告。"""

    def __init__(self, llm_client: Any) -> None:
        """保存模型客户端。"""
        self.llm_client = llm_client

    def run(
        self,
        context: dict,
        specialist_evaluations: list[dict],
        budget_seconds: float,
    ) -> dict:
        """调用综合评审 Agent。"""
        content = [
            {
                "type": "text",
                "text": build_comprehensive_user_prompt(context, specialist_evaluations),
            }
        ]
        create_kwargs = build_completion_kwargs(
            self.llm_client,
            COMPREHENSIVE_SYSTEM_PROMPT,
            content,
            "scheme_review_report",
            COMPREHENSIVE_JSON_SCHEMA,
            self.llm_client.max_tokens,
            budget_seconds,
        )
        return validate_synthesis_output(create_json_completion(self.llm_client, create_kwargs))


def build_completion_kwargs(
    llm_client: Any,
    system_prompt: str,
    content: list[dict],
    schema_name: str,
    schema: dict,
    max_tokens: int,
    budget_seconds: float,
) -> dict:
    """构造 OpenAI 兼容结构化调用参数。"""
    timeout_seconds = max(1.0, min(llm_client.agent_timeout_seconds, budget_seconds))
    create_kwargs = {
        "model": llm_client.model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": content},
        ],
        "response_format": build_response_format(
            llm_client.structured_output_mode, schema_name, schema
        ),
        "temperature": 0.2,
        "max_tokens": max_tokens,
        "timeout": timeout_seconds,
    }
    if llm_client.extra_body:
        create_kwargs["extra_body"] = llm_client.extra_body
    if llm_client.reasoning_effort:
        create_kwargs["reasoning_effort"] = llm_client.reasoning_effort
    return create_kwargs


def create_json_completion(llm_client: Any, create_kwargs: dict) -> dict:
    """调用模型并解析 JSON，兼容部分供应商参数差异。"""
    response = None
    for attempt in range(2):
        try:
            response = llm_client.client.chat.completions.create(**create_kwargs)
            break
        except Exception as exc:
            if "enable_thinking" in str(exc):
                create_kwargs.pop("extra_body", None)
                continue
            if attempt == 0 and type(exc).__name__ in {
                "APIConnectionError", "APITimeoutError", "ConnectError", "ReadTimeout"
            }:
                continue
            raise
    if response is None:
        raise RuntimeError("模型连接重试后仍未返回结果。")
    choice = response.choices[0]
    if getattr(choice, "finish_reason", "") == "length":
        raise ModelOutputTruncatedError("模型 JSON 输出达到长度上限，报告未返回完整。")
    content = choice.message.content or "{}"
    return json.loads(extract_json_text(content))


def build_response_format(mode: str, schema_name: str, schema: dict) -> dict:
    """按供应商能力选择结构化输出参数。"""
    if mode == "json_object":
        return {"type": "json_object"}
    return {
        "type": "json_schema",
        "json_schema": {"name": schema_name, "strict": True, "schema": schema},
    }


def validate_specialist_output(spec: dict, raw_output: dict) -> dict:
    """校验专项分数和反馈字段。"""
    normalized_scores = {}
    total_score = 0.0
    raw_scores = raw_output.get("sub_scores") or {}
    for name, max_score in spec["sub_scores"].items():
        item = raw_scores.get(name) or {}
        score = clamp_number(item.get("score"), 0, max_score)
        total_score += score
        normalized_scores[name] = {
            "score": score,
            "max_score": max_score,
            "reason": safe_text(item.get("reason"), "该项需要继续核对。"),
            "evidence": safe_text(item.get("evidence"), "模型未提供明确依据。"),
        }
    return {
        "overall_score": round(total_score, 1),
        "confidence": safe_text(raw_output.get("confidence"), "medium"),
        "summary": safe_text(raw_output.get("summary"), f"{spec['dimension']}专项评审完成。"),
        "observed_facts": safe_list(raw_output.get("observed_facts"), "图纸事实仍需核对。"),
        "sub_scores": normalized_scores,
        "must_fix": safe_list(raw_output.get("must_fix"), "", allow_empty=True),
        "should_improve": safe_list(raw_output.get("should_improve"), "建议补充专项表达。"),
        "optional_improvements": safe_list(
            raw_output.get("optional_improvements"), "可继续深化专项说明。"
        ),
        "strengths": safe_list(raw_output.get("strengths"), "方案具备继续深化的基础。"),
        "missing_information": safe_list(
            raw_output.get("missing_information"), "", allow_empty=True
        ),
        "uncertain_observations": safe_list(
            raw_output.get("uncertain_observations"), "", allow_empty=True
        ),
    }


def specialist_report_to_evaluation(spec: dict, report: dict) -> dict:
    """把专项报告转换成数据库和前端共用结构。"""
    return {
        "agent_type": spec["agent_type"],
        "dimension": spec["dimension"],
        "score": report["overall_score"],
        "summary": report["summary"],
        "strengths": report["strengths"],
        "issues": report["must_fix"],
        "suggestions": report["should_improve"],
        "details": build_agent_evaluation_details(report),
    }


def validate_synthesis_output(raw_output: dict) -> dict:
    """保证综合报告字段完整。"""
    return {
        "summary": safe_text(raw_output.get("summary"), "已完成当前阶段综合评审。"),
        "must_fix": safe_list(raw_output.get("must_fix"), "", allow_empty=True),
        "should_improve": safe_list(raw_output.get("should_improve"), "建议按专项结果继续深化。"),
        "optional_improvements": safe_list(
            raw_output.get("optional_improvements"), "可以补充更完整的表达材料。"
        ),
        "strengths": safe_list(raw_output.get("strengths"), "方案具备继续深化的基础。"),
    }


def build_local_synthesis(specialist_evaluations: list[dict]) -> dict:
    """未启用综合 Agent 时，按专项原文生成不扩写的稳定摘要。"""
    return {
        "summary": "；".join(item["summary"] for item in specialist_evaluations)[:360],
        "must_fix": [issue for item in specialist_evaluations for issue in item["issues"]][:4],
        "should_improve": [item for evaluation in specialist_evaluations for item in evaluation["suggestions"]][:4],
        "optional_improvements": [],
        "strengths": [item for evaluation in specialist_evaluations for item in evaluation["strengths"]][:4],
    }


def build_scheme_overall_report(
    synthesis: dict,
    specialist_evaluations: list[dict],
    context: dict | None = None,
) -> dict:
    """按任务书动态权重合并专项分数和综合报告。"""
    evaluation_context = context or {}
    weights = evaluation_context.get("dimension_weights") or {}
    score_audit = None
    if evaluation_context.get("scoring_architecture") == "evidence_v2":
        score_audit = build_evidence_score(
            specialist_evaluations,
            weights,
            evaluation_context.get("structured_requirements") or [],
            evaluation_context.get("score_calibration"),
        )
        overall_score = score_audit["calibrated_score"]
    else:
        overall_score = calculate_weighted_score(specialist_evaluations, weights)
    review_evaluation = {
        "agent_type": REVIEW_STEP["agent_type"],
        "dimension": REVIEW_STEP["dimension"],
        "score": overall_score,
        "summary": synthesis["summary"],
        "strengths": synthesis["strengths"],
        "issues": synthesis["must_fix"],
        "suggestions": synthesis["should_improve"],
        "details": {"score_audit": score_audit} if score_audit else {},
    }
    include_review = not context or "review_agent" in resolve_enabled_agent_order(evaluation_context)
    return {
        "overall_score": overall_score,
        "grade": score_to_grade(overall_score),
        "summary": synthesis["summary"],
        "must_fix": synthesis["must_fix"],
        "should_improve": synthesis["should_improve"],
        "optional_improvements": synthesis["optional_improvements"],
        "strengths": synthesis["strengths"],
        "agent_evaluations": [
            *specialist_evaluations,
            *([review_evaluation] if include_review else []),
        ],
        "evaluation_context": {
            "design_stage": evaluation_context.get("design_stage", ""),
            "enabled_agents": resolve_enabled_agent_order(evaluation_context) if context else [],
            "task_book": build_task_book_snapshot(evaluation_context.get("task_book_profile") or {}),
            "dimension_weights": weights,
            "scoring": score_audit or {"architecture": "legacy_v1"},
        },
    }
