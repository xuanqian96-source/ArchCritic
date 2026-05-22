"""功能与流线真实 Agent，负责整理输入、调用模型并校验评图结果。"""

import json
from pathlib import Path
from typing import Any

from app.agents.image_payload import build_model_image_data_url
from app.agents.prompts.function_agent_v1 import (
    FUNCTION_AGENT_JSON_SCHEMA,
    FUNCTION_AGENT_SYSTEM_PROMPT,
    build_function_agent_user_prompt,
)
from app.config import get_settings
from app.models import DrawingFile, Submission


SUB_SCORE_LIMITS = {
    "功能满足": 30,
    "功能分区": 25,
    "流线分析": 25,
    "平面丰富性": 20,
}

DRAWING_PURPOSES = {
    "site": "场地入口、外部流线和建筑与环境关系",
    "plan": "功能房间、分区组织和主要流线",
    "analysis": "设计者表达的功能、流线或场地分析逻辑",
    "render": "空间意向和公共空间体验，只作辅助判断",
}


def build_function_agent_context(
    submission: Submission,
    drawing_files: list[DrawingFile],
    references: list[dict],
) -> dict:
    """整理项目、提交、图纸和知识库依据。"""
    project = submission.project
    drawings = []
    missing_information = []
    for item in drawing_files:
        file_size = get_upload_file_size(item.file_url)
        model_file_url = item.model_file_url or ""
        usable_for_model = bool(model_file_url) or (
            file_size <= get_settings().llm_max_model_image_bytes
        )
        drawings.append(
            {
                "drawing_type": item.drawing_type,
                "original_name": item.original_name,
                "file_url": item.file_url,
                "model_file_url": model_file_url,
                "mime_type": item.mime_type,
                "analysis_purpose": DRAWING_PURPOSES.get(item.drawing_type, "建筑设计判断"),
                "usable_for_model": usable_for_model,
            }
        )
        if not usable_for_model:
            missing_information.append(
                f"{item.original_name} 文件过大，未发送给模型；请压缩后重新上传。"
            )

    if not drawings:
        missing_information.append("未上传图纸，无法核对平面和流线细节。")
    if not any(item["drawing_type"] == "plan" for item in drawings):
        missing_information.append("未上传平面图，功能分区和流线判断需要降低置信度。")
    if not submission.description.strip():
        missing_information.append("缺少设计说明。")

    return {
        "project_name": project.name,
        "building_type": project.building_type,
        "owner_name": project.owner_name,
        "grade": project.grade or "未填写",
        "design_stage": submission.design_stage,
        "description": submission.description,
        "task_book_summary": build_task_book_summary(project.building_type),
        "drawing_scope": build_drawing_scope(drawings),
        "drawings": drawings,
        "references": references[:6],
        "missing_information": missing_information,
    }


def build_task_book_summary(building_type: str) -> str:
    """根据项目类型生成第一版任务书摘要兜底。"""
    if "公共" in building_type:
        return (
            "当前未上传完整任务书。按小型公共建筑兜底判断，应至少关注入口门厅、"
            "主要公共活动空间、辅助管理空间、卫生间、后勤服务和必要交通空间。"
        )
    return "当前未上传完整任务书，只能按建筑类型和设计说明核对基础功能。"


def build_drawing_scope(drawings: list[dict]) -> str:
    """说明本次评图只能依据哪些图纸范围。"""
    if not drawings:
        return "本次未上传图纸，只能依据文字说明做低置信度评价。"
    drawing_types = {item["drawing_type"] for item in drawings}
    if drawing_types == {"plan"}:
        return (
            "本次只上传了一层平面图。只能评价这一层中可见的功能、分区和流线；"
            "不得把未上传的其他楼层、剖面、总平面或完整任务书缺失直接判为方案错误。"
        )
    if "plan" in drawing_types:
        return (
            "本次包含平面图，可评价已上传图纸中能确认的功能、分区和流线；"
            "未上传楼层或未显示区域只能作为缺失信息提示。"
        )
    return "本次未上传平面图，功能分区和流线判断需要降低置信度。"


def get_upload_file_size(file_url: str) -> int:
    """读取上传文件大小，无法读取时按可用处理。"""
    if not file_url.startswith("/uploads/"):
        return 0
    settings = get_settings()
    file_path = (Path(settings.upload_dir) / file_url.removeprefix("/uploads/")).resolve()
    upload_root = Path(settings.upload_dir).resolve()
    if upload_root not in file_path.parents or not file_path.is_file():
        return 0
    return file_path.stat().st_size


class FunctionAgent:
    """调用 GPT 多模态模型生成功能与流线评图报告。"""

    def __init__(
        self,
        client: Any,
        model: str,
        structured_output_mode: str = "json_schema",
        max_tokens: int = 1200,
        image_detail: str = "low",
        extra_body: dict | None = None,
        reasoning_effort: str | None = None,
    ) -> None:
        """保存 OpenAI 客户端和模型名称。"""
        self.client = client
        self.model = model
        self.structured_output_mode = structured_output_mode
        self.max_tokens = max_tokens
        self.image_detail = image_detail
        self.extra_body = extra_body
        self.reasoning_effort = reasoning_effort

    def run(self, context: dict) -> dict:
        """调用模型并返回校验后的报告数据。"""
        content: list[dict] = [
            {
                "type": "text",
                "text": build_function_agent_user_prompt(context),
            }
        ]
        content.extend(build_image_inputs(context["drawings"], detail=self.image_detail))

        create_kwargs = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": FUNCTION_AGENT_SYSTEM_PROMPT},
                {"role": "user", "content": content},
            ],
            "response_format": build_response_format(self.structured_output_mode),
            "temperature": 0.2,
            "max_tokens": self.max_tokens,
        }
        if self.extra_body:
            create_kwargs["extra_body"] = self.extra_body
        if self.reasoning_effort:
            create_kwargs["reasoning_effort"] = self.reasoning_effort

        try:
            response = self.client.chat.completions.create(**create_kwargs)
        except Exception as exc:
            if "enable_thinking" not in str(exc):
                raise
            create_kwargs.pop("extra_body", None)
            response = self.client.chat.completions.create(**create_kwargs)
        raw_content = response.choices[0].message.content or "{}"
        raw_output = json.loads(extract_json_text(raw_content))
        return validate_function_agent_output(raw_output)


def build_image_inputs(drawings: list[dict], detail: str = "low") -> list[dict]:
    """把所有可用图纸转换为模型可读取的图片输入。"""
    image_inputs = []
    for item in sort_drawings_for_model(drawings):
        if item.get("usable_for_model") is False:
            continue
        image_url = item.get("model_file_url") or file_url_to_data_url(
            item["file_url"], item["mime_type"]
        )
        if not image_url:
            continue
        payload = {"url": image_url}
        if image_url.startswith("data:"):
            payload["detail"] = detail
        image_inputs.append(
            {
                "type": "image_url",
                "image_url": payload,
            }
        )
    return image_inputs


def sort_drawings_for_model(drawings: list[dict]) -> list[dict]:
    """按评图重要性排序图纸，优先让模型先看到平面图。"""
    priority = {"plan": 0, "site": 1, "analysis": 2, "render": 3}
    return sorted(
        drawings,
        key=lambda item: priority.get(str(item.get("drawing_type", "")), 99),
    )


def build_response_format(mode: str) -> dict:
    """根据供应商能力选择结构化输出参数。"""
    if mode == "json_object":
        return {"type": "json_object"}
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "function_agent_report",
            "strict": True,
            "schema": FUNCTION_AGENT_JSON_SCHEMA,
        },
    }


def extract_json_text(content: str) -> str:
    """从模型文本中提取 JSON 对象，兼容代码块或前后解释。"""
    stripped = content.strip()
    if stripped.startswith("```"):
        stripped = stripped.removeprefix("```json").removeprefix("```").strip()
        stripped = stripped.removesuffix("```").strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        return stripped

    start = stripped.find("{")
    end = stripped.rfind("}")
    if start >= 0 and end > start:
        return stripped[start : end + 1]
    return stripped


def file_url_to_data_url(file_url: str, mime_type: str) -> str:
    """把 /uploads 地址对应的本地文件转换为 data URL。"""
    if not file_url.startswith("/uploads/"):
        return ""

    settings = get_settings()
    relative_path = file_url.removeprefix("/uploads/")
    file_path = (Path(settings.upload_dir) / relative_path).resolve()
    upload_root = Path(settings.upload_dir).resolve()
    if not file_path.is_file() or upload_root not in file_path.parents:
        return ""

    return build_model_image_data_url(file_path, mime_type, get_settings().llm_image_max_side)


def validate_function_agent_output(raw_output: dict) -> dict:
    """检查字段、分数和列表，避免模型输出破坏前端报告。"""
    raw_output = normalize_model_output(raw_output)
    sub_scores = raw_output.get("sub_scores") or {}
    normalized_sub_scores = {}
    total_score = 0.0

    for name, max_score in SUB_SCORE_LIMITS.items():
        item = sub_scores.get(name) or {}
        score = clamp_number(item.get("score", 0), 0, max_score)
        total_score += score
        normalized_sub_scores[name] = {
            "score": score,
            "max_score": max_score,
            "reason": safe_text(item.get("reason"), "该项需要继续核对。"),
            "evidence": safe_text(item.get("evidence"), "模型未提供明确依据。"),
        }

    overall_score = round(total_score, 1)
    return {
        "overall_score": overall_score,
        "grade": score_to_grade(overall_score),
        "confidence": raw_output.get("confidence", "medium"),
        "summary": safe_text(raw_output.get("summary"), "已完成当前提交的功能与流线评图。"),
        "observed_facts": safe_observed_facts(raw_output.get("observed_facts")),
        "sub_scores": normalized_sub_scores,
        "must_fix": build_must_fix_list(raw_output, normalized_sub_scores),
        "should_improve": safe_list(raw_output.get("should_improve"), "建议进一步明确功能分区与主要流线。"),
        "optional_improvements": safe_list(raw_output.get("optional_improvements"), "可以补充更清晰的分析图。"),
        "strengths": safe_list(raw_output.get("strengths"), "方案已具备可继续深化的基础。"),
        "missing_information": safe_list(raw_output.get("missing_information"), "", allow_empty=True),
        "uncertain_observations": safe_list(
            raw_output.get("uncertain_observations"), "", allow_empty=True
        ),
    }


def normalize_model_output(raw_output: dict) -> dict:
    """兼容百炼等模型返回的近似 JSON 结构。"""
    if "sub_scores" in raw_output:
        return raw_output

    scores = raw_output.get("scores")
    comments = raw_output.get("comments", {})
    if not isinstance(scores, dict):
        return raw_output

    sub_scores = {}
    for name, max_score in SUB_SCORE_LIMITS.items():
        score = scores.get(name, 0)
        comment = comments.get(name, "")
        sub_scores[name] = {
            "score": score,
            "max_score": max_score,
            "reason": comment or "模型未提供该项详细理由。",
            "evidence": comment or "模型未提供该项明确依据。",
        }

    summary = raw_output.get("summary") or build_summary_from_comments(comments)
    normalized = {
        **raw_output,
        "summary": summary,
        "sub_scores": sub_scores,
    }
    return normalized


def build_summary_from_comments(comments: dict) -> str:
    """从四项评价理由中生成报告摘要兜底。"""
    if not isinstance(comments, dict) or not comments:
        return "已完成当前提交的功能与流线评图。"
    first_comment = next((str(value).strip() for value in comments.values() if value), "")
    if not first_comment:
        return "已完成当前提交的功能与流线评图。"
    return first_comment[:160]


def build_issue_fallback(sub_scores: dict) -> str:
    """根据最低分维度生成必须修改兜底问题。"""
    if not sub_scores:
        return "需要补充任务书和图纸依据。"
    weakest_name, weakest_item = min(
        sub_scores.items(), key=lambda item: item[1]["score"] / item[1]["max_score"]
    )
    reason = weakest_item.get("reason") or "该项问题较明显。"
    return f"{weakest_name}需要优先修改：{reason[:120]}"


def build_must_fix_list(raw_output: dict, sub_scores: dict) -> list[str]:
    """兼容旧模型输出，同时允许模型明确返回空的必须修改项。"""
    if "must_fix" in raw_output:
        return safe_list(raw_output.get("must_fix"), "", allow_empty=True)
    return safe_list(raw_output.get("must_fix"), build_issue_fallback(sub_scores))


def function_agent_report_to_overall(report: dict, context: dict | None = None) -> dict:
    """把功能 Agent 结果转换成当前前端使用的综合报告结构。"""
    if context:
        report = demote_conflicting_must_fix(report, context)
    sub_scores = report["sub_scores"]
    issues = report["must_fix"] + report.get("uncertain_observations", [])[:2]
    suggestions = report["should_improve"]
    return {
        "overall_score": report["overall_score"],
        "grade": report["grade"],
        "summary": report["summary"],
        "must_fix": report["must_fix"],
        "should_improve": report["should_improve"],
        "optional_improvements": report["optional_improvements"],
        "strengths": report["strengths"],
        "agent_evaluations": [
            {
                "agent_type": "function_agent",
                "dimension": "功能与流线",
                "score": report["overall_score"],
                "summary": report["summary"],
                "strengths": report["strengths"],
                "issues": issues,
                "suggestions": suggestions,
            },
            *[
                {
                    "agent_type": f"function_agent_{index}",
                    "dimension": name,
                    "score": item["score"],
                    "summary": item["reason"],
                    "strengths": [item["evidence"]],
                    "issues": [],
                    "suggestions": [],
                }
                for index, (name, item) in enumerate(sub_scores.items(), start=1)
            ],
        ],
    }


def demote_conflicting_must_fix(report: dict, context: dict) -> dict:
    """把与设计说明冲突的“必须修改”降级为不确定观察。"""
    description = str(context.get("description", ""))
    observed_facts = report.get("observed_facts") or {}
    confirmed_keywords = {
        "楼梯": ["楼梯", "楼电梯", "交通核心"],
        "电梯": ["电梯", "楼电梯", "交通核心"],
        "卫生间": ["卫生间", "洗手间", "厕所", "公共卫生间"],
        "车库入口": ["车库入口", "地下车库", "车行入口"],
        "报告厅": ["报告厅", "Auditorium"],
        "服务台": ["服务台", "吧台", "Service Desk"],
    }
    negative_words = ("缺少", "缺乏", "未见", "没有", "无明确", "不明确", "需补充")
    kept_must_fix = []
    uncertain = list(report.get("uncertain_observations", []))
    for issue in report.get("must_fix", []):
        issue_text = str(issue)
        conflict_keyword = next(
            (
                label
                for label, aliases in confirmed_keywords.items()
                if label in issue_text
                and any(word in issue_text for word in negative_words)
                and (
                    any(alias in description for alias in aliases)
                    or observed_fact_blocks_must_fix(observed_facts, label)
                )
            ),
            "",
        )
        if conflict_keyword:
            uncertain.append(
                f"{conflict_keyword}与设计说明存在冲突：设计说明提到已设置，但模型在图纸中未能高置信确认；应补充更清楚的标注或局部图，不宜直接判为必须修改。"
            )
        else:
            kept_must_fix.append(issue_text)

    return {
        **report,
        "must_fix": kept_must_fix[:4],
        "uncertain_observations": uncertain[:5],
    }


def clamp_number(value: Any, minimum: float, maximum: float) -> float:
    """把模型返回的分数限制在合法区间。"""
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = minimum
    return round(max(minimum, min(number, maximum)), 1)


def score_to_grade(score: float) -> str:
    """按总分返回等级。"""
    if score >= 85:
        return "A"
    if score >= 75:
        return "B"
    if score >= 65:
        return "C"
    return "D"


def safe_text(value: Any, fallback: str) -> str:
    """保证文本字段不为空。"""
    if isinstance(value, str) and value.strip():
        return value.strip()
    return fallback


def safe_list(value: Any, fallback: str, allow_empty: bool = False) -> list[str]:
    """保证列表字段为字符串列表。"""
    if isinstance(value, list):
        items = [str(item).strip() for item in value if str(item).strip()]
        if items or allow_empty:
            return items[:5]
    return [] if allow_empty else [fallback]


def safe_observed_facts(value: Any) -> dict:
    """保证图纸事实识别字段是可读字典。"""
    if not isinstance(value, dict):
        return {}
    return {
        str(key).strip(): str(item).strip()
        for key, item in value.items()
        if str(key).strip() and str(item).strip()
    }


def observed_fact_blocks_must_fix(observed_facts: dict, label: str) -> bool:
    """判断事实识别是否不支持把对应内容写入必须修改。"""
    fact = str(observed_facts.get(label, ""))
    if "未看见" in fact:
        return False
    return "看见" in fact or "不确定" in fact
