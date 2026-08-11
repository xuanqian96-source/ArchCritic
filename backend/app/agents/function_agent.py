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
from app.models import Attachment, DrawingFile, Submission
from app.services.taskbooks import build_task_book_profile
from app.scoring.calibration import load_calibrator
from app.agents.function_agent_report import (
    build_agent_evaluation_details,
    clamp_number,
    function_agent_report_to_overall,
    safe_list,
    safe_text,
    score_to_grade,
    validate_function_agent_output,
)

DRAWING_PURPOSES = {
    "site": "场地入口、外部流线和建筑与环境关系",
    "plan": "功能房间、分区组织和主要流线",
    "plan-2": "二层功能房间、分区组织和竖向流线",
    "plan-3": "三层功能房间、分区组织和竖向流线",
    "plan-4": "四层功能房间、分区组织和竖向流线",
    "plan-5": "五层功能房间、分区组织和竖向流线",
    "plan-6": "六层功能房间、分区组织和竖向流线",
    "plan-7": "七层功能房间、分区组织和竖向流线",
    "section": "剖面关系、层高、空间连通和竖向组织",
    "elevation": "立面表达、开窗秩序和外部形象",
    "analysis": "设计者表达的功能、流线或场地分析逻辑",
    "render": "空间意向和公共空间体验，只作辅助判断",
}


def build_function_agent_context(
    submission: Submission,
    drawing_files: list[DrawingFile],
    references: list[dict],
    attachments: list[Attachment] | None = None,
) -> dict:
    """整理项目、提交、图纸和知识库依据。"""
    project = submission.project
    drawings = []
    missing_information = []
    for item in drawing_files:
        file_size = get_upload_file_size(item.file_url)
        model_file_url = item.model_file_url or ""
        usable_for_model = bool(model_file_url) or (
            item.mime_type.startswith("image/")
            and file_size <= get_settings().llm_max_model_image_bytes
        )
        drawings.append(
            {
                "drawing_type": item.drawing_type,
                "original_name": item.original_name,
                "file_url": item.file_url,
                "model_file_url": model_file_url,
                "mime_type": item.mime_type,
                "description": item.description or "",
                "analysis_purpose": get_drawing_purpose(item.drawing_type),
                "usable_for_model": usable_for_model,
            }
        )
        if not usable_for_model:
            missing_information.append(
                f"{item.original_name} 暂未生成模型可读取文件，未发送给模型；请稍后重试或上传图片版本。"
            )

    if not drawings:
        missing_information.append("未上传图纸，无法核对平面和流线细节。")
    if not any(is_plan_drawing(item["drawing_type"]) for item in drawings):
        missing_information.append("未上传平面图，功能分区和流线判断需要降低置信度。")
    if not submission.description.strip():
        missing_information.append("缺少设计说明。")

    task_book_profile = build_task_book_profile(submission, attachments or [])
    if not task_book_profile["has_task_book"]:
        missing_information.append("任务书正文不可用，评分只能按建筑类型和设计说明进行。")

    settings = get_settings()
    if settings.scoring_architecture == "evidence_v2" and not references:
        missing_information.append(
            "当前没有通过人工复核的知识卡；本次只能依据任务书和图纸评分，知识引用为空。"
        )
    calibration_path = Path(settings.score_calibration_file)
    if not calibration_path.is_absolute():
        calibration_path = Path(__file__).resolve().parents[2] / calibration_path
    return {
        "project_name": project.name,
        "building_type": project.building_type,
        "owner_name": project.owner_name,
        "grade": project.grade or "未填写",
        "design_stage": submission.design_stage,
        "enabled_agents": list(getattr(submission, "enabled_agents", []) or []),
        "description": submission.description,
        "task_book_summary": task_book_profile["summary"],
        "task_book_text": task_book_profile["full_text"],
        "task_book_requirements": task_book_profile["requirements"],
        "structured_requirements": task_book_profile["structured_requirements"],
        "task_book_profile": task_book_profile,
        "dimension_weights": task_book_profile["dimension_weights"],
        "scoring_architecture": settings.scoring_architecture,
        "score_calibration": load_calibrator(calibration_path),
        "drawing_scope": build_drawing_scope(drawings),
        "drawings": drawings,
        "references": references[:20],
        "knowledge_policy": (
            "human_approved_only"
            if settings.scoring_architecture == "evidence_v2"
            else "compatible"
        ),
        "missing_information": missing_information,
    }


def build_drawing_scope(drawings: list[dict]) -> str:
    """说明本次评图只能依据哪些图纸范围。"""
    if not drawings:
        return "本次未上传图纸，只能依据文字说明做低置信度评价。"
    drawing_types = {item["drawing_type"] for item in drawings}
    if all(is_plan_drawing(item) for item in drawing_types):
        return (
            "本次只上传了平面图。只能评价已上传楼层中可见的功能、分区和流线；"
            "不得把未上传的其他楼层、剖面、总平面或完整任务书缺失直接判为方案错误。"
        )
    if any(is_plan_drawing(item) for item in drawing_types):
        return (
            "本次包含平面图，可评价已上传图纸中能确认的功能、分区和流线；"
            "未上传楼层或未显示区域只能作为缺失信息提示。"
        )
    return "本次未上传平面图，功能分区和流线判断需要降低置信度。"


def get_drawing_purpose(drawing_type: str) -> str:
    """按图纸类型说明模型应重点判断的内容。"""
    if drawing_type.startswith("plan-"):
        return DRAWING_PURPOSES.get(drawing_type, "非首层平面功能、分区组织和竖向流线")
    return DRAWING_PURPOSES.get(drawing_type, "建筑设计判断")


def is_plan_drawing(drawing_type: str) -> bool:
    """判断当前图纸是否属于平面图。"""
    return drawing_type == "plan" or drawing_type.startswith("plan-")


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

        raw_output = self.create_json_completion(create_kwargs)
        return validate_function_agent_output(raw_output)

    def create_json_completion(self, create_kwargs: dict) -> dict:
        """调用模型并解析 JSON，失败时用更精简的输出重试一次。"""
        try:
            return self.parse_json_response(self.request_completion(create_kwargs))
        except json.JSONDecodeError:
            retry_kwargs = {
                **create_kwargs,
                "messages": [
                    *create_kwargs["messages"],
                    {
                        "role": "user",
                        "content": (
                            "上一次输出不是完整 JSON。请重新输出一个完整 JSON 对象，"
                            "不要解释，不要 Markdown；每个列表最多 3 条，每条尽量控制在 40 个中文以内。"
                        ),
                    },
                ],
                "max_tokens": max(int(create_kwargs.get("max_tokens") or self.max_tokens), 2800),
            }
            return self.parse_json_response(self.request_completion(retry_kwargs))

    def request_completion(self, create_kwargs: dict) -> Any:
        """发送模型请求，兼容不支持 enable_thinking 的供应商。"""
        try:
            response = self.client.chat.completions.create(**create_kwargs)
        except Exception as exc:
            if "enable_thinking" not in str(exc):
                raise
            fallback_kwargs = {**create_kwargs}
            fallback_kwargs.pop("extra_body", None)
            response = self.client.chat.completions.create(**fallback_kwargs)
        return response

    def parse_json_response(self, response: Any) -> dict:
        """把模型响应转换为 JSON 字典，并识别截断输出。"""
        choice = response.choices[0]
        if getattr(choice, "finish_reason", "") == "length":
            raise json.JSONDecodeError("模型 JSON 输出达到长度上限", "", 0)
        raw_content = choice.message.content or "{}"
        return json.loads(extract_json_text(raw_content))


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
    priority = {"plan": 0, "site": 1, "section": 2, "elevation": 3, "analysis": 4, "render": 5}
    return sorted(
        drawings,
        key=lambda item: 0 if is_plan_drawing(str(item.get("drawing_type", ""))) else priority.get(str(item.get("drawing_type", "")), 99),
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
