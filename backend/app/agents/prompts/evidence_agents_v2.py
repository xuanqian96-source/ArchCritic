"""新版证据优先专项提示词：模型只识图和判等级，不直接生成数值分数。"""

from __future__ import annotations

import json

from app.agents.prompts.scheme_agents_v1 import (
    SCHEME_SPECIALIST_SPECS,
    build_drawing_prompt_item,
    build_reference_prompt_item,
)
from app.services.taskbook_rules import relevant_requirements


FUNCTION_EVIDENCE_SPEC = {
    "agent_type": "function_agent",
    "name": "功能与流线 Agent",
    "dimension": "功能与流线",
    "purpose": "核对任务书核心功能、分区关系、公共与后勤流线和平面空间层次。",
    "drawing_focus": "优先读取各层平面、总平面、剖面和设计说明中的功能与交通关系。",
    "sub_scores": {
        "功能满足": 30,
        "功能分区": 25,
        "流线分析": 25,
        "平面丰富性": 20,
    },
    "observed_targets": [
        "主要功能房间", "主入口", "楼梯与电梯", "卫生间", "公共流线", "后勤流线",
    ],
}


EVIDENCE_SPECIALIST_SYSTEM_PROMPT = """
你是 ArchCritic 的建筑设计证据审查 Agent。你的职责只有两项：读取图纸事实；依据当前年级和阶段，把每个专项标准判为 0-4 级。你不得输出 0-100 数值分，也不得猜测教师最终成绩。

证据规则：
1. 每个判断必须引用共享图纸事实清单中的 E 编号；事实层没有支持时就标为低置信或不确定，不得重新猜图。
2. 当前评价是建筑设计课程过程评图，不是施工图合规审查。不得用当前阶段未要求的构造深度压低等级。
3. 任务书强制要求可核对符合度；弹性要求按实际需要核对；选配、参考和一般说明均不得作为缺失扣分。
4. 同一缺失只记录一次。未上传楼层或图纸范围外内容只能写为信息边界，不能断言方案缺失。
5. 必须修改问题必须同时具备高置信度和明确证据，否则放入建议或不确定观察。
6. 等级 4：专项逻辑鲜明，跨图纸相互印证，明显达到当前年级优秀成果；允许后续深化细节。
7. 等级 3：专项主线清楚且大部分有证据，存在局部但不破坏主线的问题。
8. 等级 2：基本框架成立，但证据闭环、空间转译或图纸完整度一般。
9. 等级 1：关键关系薄弱、矛盾或明显不完整，只具备有限基础。
10. 等级 0：缺少当前专项关键成果，或有高置信核心问题使专项难以成立。
11. 知识依据只能解释评价标准或限制结论，不能代替图纸事实。案例只能作为启发，不能因为学生方案不像案例就扣分。
12. 等级 4 必须有至少两处相互印证的直接图纸证据；只有单张图、效果图、设计说明或知识观点时，最高判为 3 级。
13. 未上传、看不清或只能从效果图推测时，scope_status 必须为 unverifiable，不能以“缺失设计”扣分，也不能给 4 级。
14. knowledge_uses 只记录真实使用的知识编号、作用和对应标准；不得自造 K 编号。
15. 输出必须是 JSON 对象，不得输出 Markdown、说明文字或代码块。
16. 保持紧凑：摘要不超过120字；每个理由和证据不超过80字；各反馈列表优先1-2条。
""".strip()


def get_evidence_spec(agent_type: str) -> dict:
    """返回功能或其他专项统一使用的证据评分定义。"""
    if agent_type == "function_agent":
        return FUNCTION_EVIDENCE_SPEC
    return SCHEME_SPECIALIST_SPECS[agent_type]


def build_evidence_json_schema(spec: dict, requirements: list[dict] | None = None) -> dict:
    """构造不含数值分数的严格模型输出结构。"""
    criteria = list(spec["sub_scores"])
    requirement_ids = [str(item["id"]) for item in requirements or []][:12]
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "observed_facts", "confidence", "summary", "criterion_assessments",
            "knowledge_uses", "requirement_checks", "must_fix", "should_improve", "optional_improvements",
            "strengths", "missing_information", "uncertain_observations",
        ],
        "properties": {
            "observed_facts": {
                "type": "array",
                "minItems": 1,
                "maxItems": 8,
                "items": {"$ref": "#/$defs/fact"},
            },
            "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
            "summary": {"type": "string", "maxLength": 240},
            "criterion_assessments": {
                "type": "object",
                "additionalProperties": False,
                "required": criteria,
                "properties": {
                    name: {"$ref": "#/$defs/assessment"} for name in criteria
                },
            },
            "knowledge_uses": {
                "type": "array",
                "maxItems": 8,
                "items": {"$ref": "#/$defs/knowledge_use"},
            },
            "requirement_checks": {
                "type": "array",
                "minItems": len(requirement_ids),
                "maxItems": 12,
                "items": {"$ref": "#/$defs/requirement_check"},
            },
            "must_fix": {
                "type": "array",
                "maxItems": 3,
                "items": {"$ref": "#/$defs/confirmed_problem"},
            },
            "should_improve": string_list_schema(1, 3),
            "optional_improvements": string_list_schema(1, 3),
            "strengths": string_list_schema(1, 3),
            "missing_information": string_list_schema(0, 5),
            "uncertain_observations": string_list_schema(0, 5),
        },
        "$defs": {
            "fact": {
                "type": "object",
                "additionalProperties": False,
                "required": ["statement", "source", "confidence"],
                "properties": {
                    "statement": {"type": "string", "maxLength": 180},
                    "source": {"type": "string", "maxLength": 160},
                    "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                },
            },
            "assessment": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "level", "reason", "evidence", "confidence", "scope_status",
                    "knowledge_reference_ids", "evidence_fact_ids",
                ],
                "properties": {
                    "level": {"type": "integer", "minimum": 0, "maximum": 4},
                    "reason": {"type": "string", "maxLength": 240},
                    "evidence": {"type": "string", "maxLength": 180},
                    "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                    "scope_status": {
                        "type": "string",
                        "enum": ["verified", "partly_verified", "unverifiable"],
                    },
                    "knowledge_reference_ids": {
                        "type": "array",
                        "maxItems": 3,
                        "items": {"type": "string", "pattern": "^K[1-9][0-9]*$"},
                    },
                    "evidence_fact_ids": {
                        "type": "array",
                        "maxItems": 6,
                        "items": {"type": "string", "pattern": "^E[1-9][0-9]*$"},
                    },
                },
            },
            "knowledge_use": {
                "type": "object",
                "additionalProperties": False,
                "required": ["reference_id", "criterion", "use_type", "claim", "effect"],
                "properties": {
                    "reference_id": {"type": "string", "pattern": "^K[1-9][0-9]*$"},
                    "criterion": {"type": "string", "maxLength": 60},
                    "use_type": {
                        "type": "string",
                        "enum": ["rubric_support", "boundary_limit", "case_inspiration"],
                    },
                    "claim": {"type": "string", "maxLength": 180},
                    "effect": {
                        "type": "string",
                        "enum": ["support", "limit", "context_only"],
                    },
                },
            },
            "requirement_check": {
                "type": "object",
                "additionalProperties": False,
                "required": ["requirement_id", "status", "evidence", "confidence"],
                "properties": {
                    "requirement_id": (
                        {"type": "string", "enum": requirement_ids}
                        if requirement_ids
                        else {"type": "string", "maxLength": 16}
                    ),
                    "status": {
                        "type": "string",
                        "enum": ["met", "partly_met", "not_met", "uncertain", "not_applicable"],
                    },
                    "evidence": {"type": "string", "maxLength": 200},
                    "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                },
            },
            "confirmed_problem": {
                "type": "object",
                "additionalProperties": False,
                "required": ["text", "evidence", "confidence"],
                "properties": {
                    "text": {"type": "string", "maxLength": 200},
                    "evidence": {"type": "string", "maxLength": 180},
                    "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                },
            },
        },
    }


def string_list_schema(min_items: int, max_items: int) -> dict:
    """生成统一的短文本列表 JSON Schema。"""
    return {
        "type": "array",
        "minItems": min_items,
        "maxItems": max_items,
        "items": {"type": "string", "maxLength": 220},
    }


def build_evidence_user_prompt(context: dict, spec: dict) -> tuple[str, list[dict]]:
    """整理专项图文、任务书规则和 0-4 级判断任务。"""
    requirements = relevant_requirements(
        context.get("structured_requirements") or [], spec["agent_type"]
    )
    references = "\n".join(
        build_reference_prompt_item(item) for item in context.get("references", [])
    )
    drawings = "\n".join(
        build_drawing_prompt_item(item) for item in context.get("drawings", [])
    )
    missing = "\n".join(f"- {item}" for item in context.get("missing_information", []))
    criteria = "\n".join(f"- {name}" for name in spec["sub_scores"])
    requirement_json = json.dumps(requirements, ensure_ascii=False, indent=2)
    evidence_inventory = json.dumps(
        context.get("evidence_inventory") or {}, ensure_ascii=False, indent=2
    )
    return f"""
请完成“{spec['name']}”证据审查。只判事实、任务书符合状态和 0-4 级，不输出数值分数。

【专项边界】
{spec['purpose']}
{spec['drawing_focus']}
重点观察：{'、'.join(spec['observed_targets'])}。

【项目与课程阶段】
项目：{context['project_name']}
建筑类型：{context['building_type']}
年级：{context['grade']}
阶段：{context['design_stage']}
设计说明：{context['description']}

【任务书正文】
{context.get('task_book_text') or '未提供任务书正文。'}

【本专项需核对的结构化规则】
{requirement_json if requirements else '没有分配到本专项的明确规则；不得自行发明要求。'}
level 含义：required=强制，flexible_required=弹性，optional=选配，reference=参考，informational=说明。
选配、参考和一般说明即使未满足，也只能记录，不得降低 criterion_assessments 等级。

【已上传图纸目录】
{drawings or '未上传图纸。'}
评判边界：{context['drawing_scope']}

【共享图纸事实清单】
{evidence_inventory}
专项判断必须优先引用清单中的 E 编号。清单未支持的判断只能标为 partly_verified 或 unverifiable；不得自行增加 E 编号。

【知识依据】
{references or '当前没有可用知识依据。'}

【已知缺失信息】
{missing or '暂无。'}

【需要判定的专项标准】
{criteria}

输出 JSON 字段：observed_facts、confidence、summary、criterion_assessments、knowledge_uses、requirement_checks、must_fix、should_improve、optional_improvements、strengths、missing_information、uncertain_observations。
criterion_assessments 中每项写 level(0-4)、reason、evidence、confidence、scope_status、knowledge_reference_ids、evidence_fact_ids。
scope_status：verified=有跨图纸直接证据；partly_verified=只有单一或不完整证据；unverifiable=当前材料无法判断。
knowledge_uses 只写实际参与判断的知识；没有使用时返回空数组。案例知识的 effect 必须是 context_only。
requirement_checks 只允许使用上方给出的规则 id；状态只能是 met、partly_met、not_met、uncertain、not_applicable。
本专项有结构化规则时，必须为每个规则 id 返回一条 requirement_checks；无法从现有材料判断时返回 uncertain，不得省略。
must_fix 每项写 text、evidence、confidence；证据不清楚时不要硬写为必须修改。
""".strip(), requirements
