"""先建立不含分数的共享图纸事实清单，供后续专项 Agent 引用。"""

from __future__ import annotations

from typing import Any

from app.agents.function_agent import build_image_inputs, sort_drawings_for_model


EVIDENCE_DIMENSIONS = {
    "function",
    "circulation",
    "site",
    "form",
    "structure",
    "drawing_expression",
    "general",
}
OBSERVATION_TYPES = {"visible", "not_visible", "uncertain"}
CONFIDENCE_VALUES = {"high", "medium", "low"}


DRAWING_EVIDENCE_SYSTEM_PROMPT = """
你是 ArchCritic 的中立图纸证据整理 Agent。你只负责读取本次全部图纸，建立可复核事实清单，不评价优劣、不输出等级、不输出分数，也不猜测教师意见。

规则：
1. 逐张读取图纸；只写能在图纸中定位的事实，来源必须使用给定 D 编号。
2. 不得把效果图氛围、文字概念或案例相似性直接当成功能、结构或合规事实。
3. “未看见”只表示当前提交中没有清楚识别，不能等同于设计一定缺失；此类 observation_type 使用 not_visible 或 uncertain。
4. 同一事实若被多张图相互印证，列出全部来源 D 编号；若图纸之间矛盾，写入 contradictions。
5. 图纸模糊、小字不可读或超出本次图纸范围时降低置信度并写入 missing_information。
6. 输出必须是 JSON 对象，不得输出 Markdown、解释或分数。
7. drawing_coverage 必须逐张返回。对平面图优先核对入口、楼梯、电梯、卫生间、功能标注和公共/后勤流线；对剖面和结构图核对层数、跨度、支撑与空间关系。
8. 项目标题、概念文案和类别名称不属于功能空间事实；优先记录能支撑后续专项核对的实际图纸信息。
""".strip()


class DrawingEvidenceInventoryAgent:
    """调用一次多模态模型生成所有专项共用的中立证据清单。"""

    def __init__(self, llm_client: Any) -> None:
        """保存模型客户端。"""
        self.llm_client = llm_client

    def run(self, context: dict, budget_seconds: float) -> dict:
        """读取全部可用图纸并返回后端归一化后的事实清单。"""
        from app.agents.scheme_review import build_completion_kwargs, create_json_completion

        drawings = build_inventory_drawings(context.get("drawings", []))
        prompt = build_inventory_prompt(context, drawings)
        content = [{"type": "text", "text": prompt}]
        content.extend(
            build_image_inputs(context.get("drawings", []), detail=self.llm_client.image_detail)
        )
        raw = create_json_completion(
            self.llm_client,
            build_completion_kwargs(
                self.llm_client,
                DRAWING_EVIDENCE_SYSTEM_PROMPT,
                content,
                "drawing_evidence_inventory_v1",
                build_inventory_schema([item["drawing_id"] for item in drawings]),
                max(self.llm_client.max_tokens, 3600),
                budget_seconds,
            ),
        )
        return normalize_evidence_inventory(raw, drawings)


def build_inventory_drawings(drawings: list[dict]) -> list[dict]:
    """按实际发送顺序给每张可用图纸分配稳定 D 编号。"""
    result = []
    for index, item in enumerate(sort_drawings_for_model(drawings), start=1):
        if item.get("usable_for_model") is False:
            continue
        result.append(
            {
                "drawing_id": f"D{index}",
                "drawing_type": str(item.get("drawing_type", "")),
                "original_name": str(item.get("original_name", "")),
                "description": str(item.get("description", "")),
            }
        )
    return result


def build_inventory_prompt(context: dict, drawings: list[dict]) -> str:
    """构造不含评分标准和知识答案的中立识图任务。"""
    drawing_lines = "\n".join(
        f"- {item['drawing_id']}：{item['drawing_type']} / {item['original_name']}"
        f"；说明：{item['description'] or '无'}"
        for item in drawings
    )
    return f"""
请为以下建筑设计提交建立共享图纸事实清单。

项目类型：{context.get('building_type', '')}
年级：{context.get('grade', '')}
阶段：{context.get('design_stage', '')}
设计说明：{context.get('description', '')}
评判范围：{context.get('drawing_scope', '')}

【图纸编号】
{drawing_lines or '没有可读取图纸。'}

输出字段：drawing_coverage、facts、contradictions、missing_information。
facts 每项包含 dimension、statement、source_drawing_ids、confidence、observation_type。
dimension 只能是 function、circulation、site、form、structure、drawing_expression、general。
必须为每个 D 编号返回 drawing_coverage。如果图中存在平面图，尝试核对入口、楼梯、电梯、卫生间和功能标注；看不清时记为 uncertain，不得猜测。
""".strip()


def build_inventory_schema(drawing_ids: list[str]) -> dict:
    """按本次真实图纸编号构造严格输出结构。"""
    drawing_id_schema = (
        {"type": "string", "enum": drawing_ids}
        if drawing_ids
        else {"type": "string", "maxLength": 16}
    )
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["drawing_coverage", "facts", "contradictions", "missing_information"],
        "properties": {
            "drawing_coverage": {
                "type": "array",
                "maxItems": max(1, len(drawing_ids)),
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["drawing_id", "readable", "note"],
                    "properties": {
                        "drawing_id": drawing_id_schema,
                        "readable": {"type": "boolean"},
                        "note": {"type": "string", "maxLength": 160},
                    },
                },
            },
            "facts": {
                "type": "array",
                "minItems": 1 if drawing_ids else 0,
                "maxItems": 28,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "dimension", "statement", "source_drawing_ids", "confidence",
                        "observation_type",
                    ],
                    "properties": {
                        "dimension": {"type": "string", "enum": sorted(EVIDENCE_DIMENSIONS)},
                        "statement": {"type": "string", "maxLength": 220},
                        "source_drawing_ids": {
                            "type": "array",
                            "minItems": 1,
                            "maxItems": 6,
                            "items": drawing_id_schema,
                        },
                        "confidence": {"type": "string", "enum": sorted(CONFIDENCE_VALUES)},
                        "observation_type": {
                            "type": "string",
                            "enum": sorted(OBSERVATION_TYPES),
                        },
                    },
                },
            },
            "contradictions": {
                "type": "array",
                "maxItems": 8,
                "items": {"type": "string", "maxLength": 220},
            },
            "missing_information": {
                "type": "array",
                "maxItems": 8,
                "items": {"type": "string", "maxLength": 220},
            },
        },
    }


def normalize_evidence_inventory(raw: Any, drawings: list[dict]) -> dict:
    """只保留真实图纸编号，并由后端重新分配 E 事实编号。"""
    payload = raw if isinstance(raw, dict) else {}
    valid_drawings = {item["drawing_id"]: item for item in drawings}
    coverage = []
    for item in payload.get("drawing_coverage") or []:
        if not isinstance(item, dict) or item.get("drawing_id") not in valid_drawings:
            continue
        coverage.append(
            {
                "drawing_id": item["drawing_id"],
                "readable": bool(item.get("readable")),
                "note": safe_text(item.get("note"), "未说明可读性。"),
            }
        )
    covered_ids = {item["drawing_id"] for item in coverage}
    for drawing in drawings:
        if drawing["drawing_id"] in covered_ids:
            continue
        coverage.append(
            {
                "drawing_id": drawing["drawing_id"],
                "readable": None,
                "note": "模型未返回该图的逐张可读性，系统保留为未核实。",
            }
        )
    facts = []
    for item in payload.get("facts") or []:
        if not isinstance(item, dict):
            continue
        statement = safe_text(item.get("statement"), "")
        sources = list(
            dict.fromkeys(
                str(value) for value in item.get("source_drawing_ids") or []
                if str(value) in valid_drawings
            )
        )
        if not statement or not sources:
            continue
        dimension = str(item.get("dimension") or "general")
        confidence = str(item.get("confidence") or "medium")
        observation_type = str(item.get("observation_type") or "uncertain")
        facts.append(
            {
                "fact_id": f"E{len(facts) + 1}",
                "dimension": dimension if dimension in EVIDENCE_DIMENSIONS else "general",
                "statement": statement,
                "source_drawing_ids": sources[:6],
                "confidence": confidence if confidence in CONFIDENCE_VALUES else "medium",
                "observation_type": (
                    observation_type
                    if observation_type in OBSERVATION_TYPES
                    else "uncertain"
                ),
            }
        )
        if len(facts) >= 28:
            break
    return {
        "version": "drawing_evidence_inventory_v1",
        "drawings": drawings,
        "drawing_coverage": coverage,
        "facts": facts,
        "contradictions": safe_list(payload.get("contradictions"), 8),
        "missing_information": normalize_missing_information(
            payload.get("missing_information"), 8
        ),
    }


def safe_text(value: Any, fallback: str) -> str:
    """把模型文本压缩为有限非空字符串。"""
    text = str(value or "").strip()
    return text[:240] if text else fallback


def safe_list(value: Any, limit: int) -> list[str]:
    """归一化模型短文本列表。"""
    if not isinstance(value, list):
        return []
    return [str(item).strip()[:240] for item in value if str(item).strip()][:limit]


def normalize_missing_information(value: Any, limit: int) -> list[str]:
    """兼容 JSON-object 模式把缺失信息返回为结构化对象。"""
    result = []
    for item in value if isinstance(value, list) else []:
        if isinstance(item, dict):
            statement = safe_text(item.get("statement"), "")
            dimension = str(item.get("dimension") or "general")
            sources = ",".join(str(source) for source in item.get("source_drawing_ids") or [])
            if statement:
                result.append(f"[{dimension}] {statement}（来源：{sources or '未标明'}）"[:240])
        else:
            text = str(item).strip()
            if text:
                result.append(text[:240])
        if len(result) >= limit:
            break
    return result
