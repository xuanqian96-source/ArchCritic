"""最终评分步骤的视觉锚点校准提示词与结构化输出定义。"""

from __future__ import annotations

import json


VISUAL_CALIBRATION_SYSTEM_PROMPT = """
你是 ArchCritic 的综合评审 Agent，同时负责建筑设计课课程尺度校准。

本轮输入包含两类图像：
1. 当前待评作品的全部匿名展板；
2. 已知教师原始成绩的匿名视觉锚点展板。

必须严格执行以下步骤：
1. 先依据当前作品图纸和专项 Agent 结果，概括当前作品可确认的整体质量证据。
2. 再按低档、中档、高档顺序读取锚点；锚点只表示同类课程作品的大致评分尺度，不是当前作品答案。
3. 先判断当前作品最接近哪个档位，再与该档及相邻档锚点逐项比较。
4. 比较至少覆盖概念与空间一致性、场地回应、功能组织、技术完成度、图面表达中的三个方面。
5. 在档位内部确定相对位置后再给出总分，不得把专项分数简单平均，也不得默认回到 78—82 分。
6. 当前作品明显弱于最低锚点或强于最高锚点时可以谨慎外推，但必须说明依据。
7. 低档对应 75 分及以下，中档对应 76—85 分，高档对应 86 分及以上；边界作品允许结合相邻档比较。
8. 图纸看不清或课程过程信息缺失时降低置信度，不得把推测写成确定事实。
9. 反馈内容只汇总专项 Agent 已确认的问题；视觉比较只用于整体质量定位和总分校准，不新增无依据的硬性问题。
10. 输出必须是 JSON 对象，不得输出 Markdown、解释文字或代码块。
""".strip()


VISUAL_SCORE_CALIBRATION_JSON_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "observed_current_quality",
        "band",
        "nearest_anchor_ids",
        "comparisons",
        "calibrated_score",
        "confidence",
        "score_reason",
    ],
    "properties": {
        "observed_current_quality": {
            "type": "array",
            "items": {"type": "string", "maxLength": 180},
            "minItems": 2,
            "maxItems": 6,
        },
        "band": {
            "type": "string",
            "enum": ["low", "middle", "high"],
        },
        "nearest_anchor_ids": {
            "type": "array",
            "items": {"type": "string", "maxLength": 32},
            "minItems": 1,
            "maxItems": 3,
        },
        "comparisons": {
            "type": "array",
            "items": {"type": "string", "maxLength": 220},
            "minItems": 2,
            "maxItems": 6,
        },
        "calibrated_score": {
            "type": "number",
            "minimum": 0,
            "maximum": 100,
        },
        "confidence": {
            "type": "string",
            "enum": ["high", "medium", "low"],
        },
        "score_reason": {"type": "string", "maxLength": 320},
    },
}


def build_visual_calibration_user_prompt(
    context: dict,
    specialist_evaluations: list[dict],
) -> str:
    """整理必要专项证据和锚点目录，避免反馈字段挤占视觉评分输出。"""
    compact_reviews = [
        {
            "dimension": item["dimension"],
            "score": item["score"],
            "summary": item["summary"],
            "strengths": item["strengths"][:1],
            "issues": item["issues"][:1],
        }
        for item in specialist_evaluations
    ]
    anchors = [
        {
            "anchor_id": item["anchor_id"],
            "band": item["band"],
            "teacher_score": item["teacher_score"],
            "display_title": item["display_title"],
        }
        for item in context.get("visual_score_anchors") or []
    ]
    return f"""
请只完成当前作品的视觉锚点总分校准，不要重复生成综合反馈报告。

【项目信息】
项目名称：{context["project_name"]}
建筑类型：{context["building_type"]}
年级：{context["grade"]}
设计阶段：{context["design_stage"]}

【课程任务书摘要】
{context["task_book_summary"]}

【专项 Agent 结果】
{json.dumps(compact_reviews, ensure_ascii=False, indent=2)}

【视觉锚点目录】
{json.dumps(anchors, ensure_ascii=False, indent=2)}

图像输入顺序是：先给出当前待评作品的全部展板，再逐份给出视觉锚点。每份锚点图像前都有包含锚点编号、档位和教师原始成绩的文字标签。

请先记录当前作品的整体质量证据，再判断档位、选择最接近的锚点、完成跨档或档内比较，最后输出总分。专项 Agent 的数值只作辅助证据，不得直接求平均。

只输出以下七项：observed_current_quality、band、nearest_anchor_ids、comparisons、calibrated_score、confidence、score_reason。
""".strip()
