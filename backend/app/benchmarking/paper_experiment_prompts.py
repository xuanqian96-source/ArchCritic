"""论文四条件实验中的直接评审与结构化提示词单模型评审。"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from app.agents.function_agent import (
    build_image_inputs,
    clamp_number,
    extract_json_text,
    safe_list,
    safe_text,
    score_to_grade,
)
from app.agents.scheme_review import build_response_format


CONDITION_NAMES = {
    "c0_direct": "通用多模态大模型直接评审",
    "c1_structured_single": "结构化提示词增强的单模型评审",
    "c2_multi_agent": "多 Agent 专项协同评审",
    "c3_multi_agent_knowledge": "知识增强多 Agent 评审",
}


SINGLE_MODEL_REPORT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "overall_score",
        "summary",
        "observed_facts",
        "must_fix",
        "should_improve",
        "optional_improvements",
        "strengths",
    ],
    "properties": {
        "overall_score": {"type": "number"},
        "summary": {"type": "string"},
        "observed_facts": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 16,
        },
        "must_fix": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 8,
        },
        "should_improve": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 8,
        },
        "optional_improvements": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 8,
        },
        "strengths": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 8,
        },
    },
}


DIRECT_SYSTEM_PROMPT = """
你是一名建筑设计课教师。请根据本次提供的原始课程任务书和全部学生成果图，直接给出一次完整评图。
只评价图纸能够支持的内容，不要假设你知道学生身份、原始成绩或人工标注。
输出必须是一个 JSON 对象，不要输出 Markdown 或其他解释。
""".strip()


STRUCTURED_SYSTEM_PROMPT = """
你是一名建筑设计课教师，正在完成一次结构化的单模型评审。你必须独立读取原始任务书和全部成果图，
从功能与流线、场地与回应、几何形式、结构与可行性、图面表达五个方面形成综合判断。

评审规则：
1. 先识别图纸中能够确认的事实，再评价。
2. 严格区分“看见”“未见”“不确定”，看不清的内容不能写成确定缺失。
3. 修改意见必须指出具体对象、问题及其影响，不能只写笼统评价。
4. 当前是大二建筑设计课最终成果，不得用施工图深度要求代替课程评价。
5. 评分须参考给出的课程分档锚点，但不得猜测当前作品属于哪个已知样本。
6. 只进行一次模型调用，不使用多 Agent、工具规划或外部知识库。
7. 输出必须是一个 JSON 对象，不要输出 Markdown 或其他解释。
""".strip()


def build_single_model_user_prompt(context: dict[str, Any], structured: bool) -> str:
    """生成两种单模型条件的用户提示词。"""
    drawings = "\n".join(
        f"- {item['original_name']}：原始成果图第 {index} 页"
        for index, item in enumerate(context.get("drawings", []), start=1)
    )
    common = f"""
【基本信息】
建筑类型：{context["building_type"]}
年级：{context["grade"]}
设计阶段：{context["design_stage"]}

【原始任务书】
{context.get("task_book_text") or context.get("task_book_summary") or "未提供任务书。"}

【原始成果图】
{drawings or "未提供成果图。"}

【输出字段】
{{
  "overall_score": 0到100的总分,
  "summary": "总体评价",
  "observed_facts": ["从图纸中确认的事实"],
  "must_fix": ["必须优先修改的问题"],
  "should_improve": ["建议修改的问题"],
  "optional_improvements": ["可选深化建议"],
  "strengths": ["方案优势"]
}}
""".strip()
    if not structured:
        return (
            common
            + "\n\n请直接给出评图结果。除上述输出字段外，不提供额外评价维度、评分锚点或专业提示。"
        )
    anchors = context.get("score_band_guidance") or "未提供课程分档锚点。"
    return (
        common
        + f"""

【课程分档锚点】
{anchors}

【结构化评审要求】
- observed_facts 必须是图纸中能定位的事实。
- must_fix 只放证据充分、会影响方案成立或课程要求的问题。
- should_improve 放重要但不构成硬性否定的问题。
- 优点、问题和建议都要具体到空间、流线、场地、结构或图面对象。
- 综合分应与五个专业维度的整体判断一致。
""".rstrip()
    )


def run_single_model_condition(
    llm_client: Any,
    context: dict[str, Any],
    structured: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """调用一次千问并返回统一报告和调用审计。"""
    system_prompt = STRUCTURED_SYSTEM_PROMPT if structured else DIRECT_SYSTEM_PROMPT
    user_prompt = build_single_model_user_prompt(context, structured)
    content: list[dict[str, Any]] = [{"type": "text", "text": user_prompt}]
    content.extend(build_image_inputs(context["drawings"], detail=llm_client.image_detail))
    request = {
        "model": llm_client.model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": content},
        ],
        "response_format": build_response_format(
            llm_client.structured_output_mode,
            "paper_single_model_report",
            SINGLE_MODEL_REPORT_SCHEMA,
        ),
        "temperature": 0.2,
        "max_tokens": max(llm_client.max_tokens, 3000),
        "timeout": llm_client.review_timeout_seconds,
    }
    if llm_client.extra_body:
        request["extra_body"] = llm_client.extra_body
    response = llm_client.client.chat.completions.create(**request)
    raw_text = response.choices[0].message.content or "{}"
    raw = json.loads(extract_json_text(raw_text))
    score = round(clamp_number(raw.get("overall_score"), 0, 100), 1)
    observed_facts = safe_list(raw.get("observed_facts"), "模型未返回明确图纸事实。")
    report = {
        "overall_score": score,
        "grade": score_to_grade(score),
        "summary": safe_text(raw.get("summary"), "模型未返回总体评价。"),
        "must_fix": normalize_optional_list(raw.get("must_fix")),
        "should_improve": normalize_optional_list(raw.get("should_improve")),
        "optional_improvements": normalize_optional_list(raw.get("optional_improvements")),
        "strengths": normalize_optional_list(raw.get("strengths")),
        "agent_evaluations": [
            {
                "agent_type": "single_model",
                "dimension": "单模型综合评审",
                "score": score,
                "summary": safe_text(raw.get("summary"), "单模型综合评审完成。"),
                "strengths": normalize_optional_list(raw.get("strengths")),
                "issues": normalize_optional_list(raw.get("must_fix")),
                "suggestions": normalize_optional_list(raw.get("should_improve")),
                "details": {
                    "observed_facts": observed_facts,
                    "prompt_mode": "structured" if structured else "direct",
                },
            }
        ],
        "evaluation_context": {
            "design_stage": context.get("design_stage", ""),
            "enabled_agents": ["single_model"],
            "experiment_condition": (
                "c1_structured_single" if structured else "c0_direct"
            ),
            "score_band_guidance_used": structured,
            "knowledge_references": [],
        },
    }
    usage = getattr(response, "usage", None)
    audit = {
        "system_prompt": system_prompt,
        "user_prompt": user_prompt,
        "raw_response": raw_text,
        "prompt_sha256": hashlib.sha256(
            (system_prompt + "\n" + user_prompt).encode("utf-8")
        ).hexdigest(),
        "input_tokens": getattr(usage, "prompt_tokens", None),
        "output_tokens": getattr(usage, "completion_tokens", None),
        "total_tokens": getattr(usage, "total_tokens", None),
    }
    return report, audit


def normalize_optional_list(value: Any) -> list[str]:
    """保留模型真实列表，空列表不注入占位评价。"""
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()][:8]
