"""方案阶段多 Agent 编排，负责顺序评审和综合报告整理。"""

import json
from time import monotonic
from typing import Any, Iterator

from app.agents.function_agent import (
    FunctionAgent,
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
SCHEME_AGENT_ORDER = [
    FUNCTION_STEP,
    SCHEME_SPECIALIST_SPECS["site_agent"],
    SCHEME_SPECIALIST_SPECS["form_agent"],
    SCHEME_SPECIALIST_SPECS["structure_agent"],
    REVIEW_STEP,
]


class ModelOutputTruncatedError(ValueError):
    """表示模型输出被长度上限截断。"""


def is_scheme_stage(design_stage: str) -> bool:
    """判断当前提交是否属于方案阶段。"""
    normalized = str(design_stage or "").strip().lower()
    return normalized == "scheme" or "方案" in normalized


def generate_scheme_review(llm_client: Any, context: dict) -> dict:
    """顺序执行方案阶段 Agent 并返回最终报告。"""
    final_report = None
    for item in iter_scheme_review_events(llm_client, context):
        if item["event"] == "report":
            final_report = item["report"]
    if final_report is None:
        raise RuntimeError("方案阶段多 Agent 未生成最终报告。")
    return final_report


def iter_scheme_review_events(llm_client: Any, context: dict) -> Iterator[dict]:
    """按 Agent 顺序产出进度事件和最终报告。"""
    started_at = monotonic()
    specialist_evaluations = []
    function_agent = FunctionAgent(
        llm_client.client,
        llm_client.model,
        llm_client.structured_output_mode,
        min(llm_client.max_tokens, 1600),
        llm_client.image_detail,
        llm_client.extra_body,
        llm_client.reasoning_effort,
    )

    yield build_agent_event("start", FUNCTION_STEP, "开始核对功能、分区和流线。")
    ensure_review_budget(llm_client, started_at)
    function_report = function_agent.run(context)
    function_overall = function_agent_report_to_overall(function_report, context)
    specialist_evaluations.append(function_overall["agent_evaluations"][0])
    yield build_agent_event("done", FUNCTION_STEP, "功能与流线专项评审完成。")

    for spec in (
        SCHEME_SPECIALIST_SPECS["site_agent"],
        SCHEME_SPECIALIST_SPECS["form_agent"],
        SCHEME_SPECIALIST_SPECS["structure_agent"],
    ):
        yield build_agent_event("start", spec, f"开始核对{spec['dimension']}。")
        ensure_review_budget(llm_client, started_at)
        report = SchemeSpecialistAgent(llm_client, spec).run(
            context, remaining_seconds(llm_client, started_at)
        )
        specialist_evaluations.append(specialist_report_to_evaluation(spec, report))
        yield build_agent_event("done", spec, f"{spec['dimension']}专项评审完成。")

    yield build_agent_event("start", REVIEW_STEP, "正在汇总四个专项结果并生成反馈报告。")
    ensure_review_budget(llm_client, started_at)
    synthesis = ComprehensiveReviewAgent(llm_client).run(
        context,
        specialist_evaluations,
        remaining_seconds(llm_client, started_at),
    )
    report = build_scheme_overall_report(synthesis, specialist_evaluations)
    yield build_agent_event("done", REVIEW_STEP, "综合反馈报告已整理完成。")
    yield {"event": "report", "report": report}


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
        raise TimeoutError("方案阶段评审已达到总时限。")


class SchemeSpecialistAgent:
    """调用一个方案阶段专项 Agent。"""

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
    try:
        response = llm_client.client.chat.completions.create(**create_kwargs)
    except Exception as exc:
        if "enable_thinking" not in str(exc):
            raise
        create_kwargs.pop("extra_body", None)
        response = llm_client.client.chat.completions.create(**create_kwargs)
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
        "issues": report["must_fix"] + report["uncertain_observations"][:2],
        "suggestions": report["should_improve"],
    }


def validate_synthesis_output(raw_output: dict) -> dict:
    """保证综合报告字段完整。"""
    return {
        "summary": safe_text(raw_output.get("summary"), "已完成方案阶段综合评审。"),
        "must_fix": safe_list(raw_output.get("must_fix"), "", allow_empty=True),
        "should_improve": safe_list(raw_output.get("should_improve"), "建议按专项结果继续深化。"),
        "optional_improvements": safe_list(
            raw_output.get("optional_improvements"), "可以补充更完整的表达材料。"
        ),
        "strengths": safe_list(raw_output.get("strengths"), "方案具备继续深化的基础。"),
    }


def build_scheme_overall_report(synthesis: dict, specialist_evaluations: list[dict]) -> dict:
    """合并专项分数和综合报告。"""
    overall_score = round(
        sum(item["score"] for item in specialist_evaluations) / len(specialist_evaluations),
        1,
    )
    review_evaluation = {
        "agent_type": REVIEW_STEP["agent_type"],
        "dimension": REVIEW_STEP["dimension"],
        "score": overall_score,
        "summary": synthesis["summary"],
        "strengths": synthesis["strengths"],
        "issues": synthesis["must_fix"],
        "suggestions": synthesis["should_improve"],
    }
    return {
        "overall_score": overall_score,
        "grade": score_to_grade(overall_score),
        "summary": synthesis["summary"],
        "must_fix": synthesis["must_fix"],
        "should_improve": synthesis["should_improve"],
        "optional_improvements": synthesis["optional_improvements"],
        "strengths": synthesis["strengths"],
        "agent_evaluations": [*specialist_evaluations, review_evaluation],
    }
