"""方案阶段多 Agent 提示词，供专项评审和综合汇总使用。"""

import json


SCHEME_SPECIALIST_SPECS = {
    "site_agent": {
        "agent_type": "site_agent",
        "name": "场地 Agent",
        "dimension": "场地与回应",
        "purpose": "核对场地条件、总图组织、入口关系和室外空间回应。",
        "drawing_focus": "优先读取总平面、场地分析图和平面图中的入口关系。",
        "sub_scores": {
            "场地解读": 25,
            "总图组织": 25,
            "入口与到达": 25,
            "环境回应": 25,
        },
        "observed_targets": ["场地边界", "城市到达", "主入口", "后勤入口", "室外空间"],
    },
    "form_agent": {
        "agent_type": "form_agent",
        "name": "几何形式 Agent",
        "dimension": "几何形式",
        "purpose": "核对形体生成逻辑、空间构图、几何秩序和形式与功能的对应。",
        "drawing_focus": "优先读取平面图、分析图和效果图中的几何关系。",
        "sub_scores": {
            "形体生成": 25,
            "空间构图": 25,
            "几何秩序": 25,
            "形式功能协同": 25,
        },
        "observed_targets": ["主要几何关系", "公共空间节点", "形体层次", "入口形象", "功能对应"],
    },
    "structure_agent": {
        "agent_type": "structure_agent",
        "name": "结构 Agent",
        "dimension": "结构与可行性",
        "purpose": "核对结构体系意向、跨度与支撑关系、构造可行性和结构空间协同。",
        "drawing_focus": "优先读取平面图、效果图和说明中可确认的柱网、跨度与大空间。",
        "sub_scores": {
            "结构体系": 30,
            "跨度与支撑": 25,
            "构造可行性": 25,
            "结构空间协同": 20,
        },
        "observed_targets": ["柱网或支撑", "大跨度空间", "悬挑或架空", "竖向交通", "结构说明"],
    },
}


SPECIALIST_SYSTEM_PROMPT = """
你是 ArchCritic 的方案阶段专项评审 Agent，同时具备建筑设计课教师和建筑方案评图助教视角。

你只能评价当前被分配的专项维度。必须依据设计说明、已上传图纸和知识库依据判断，不得把推测写成确定事实。

共同规则：
1. 先在 observed_facts 中写出可确认的事实，再评分。
2. 图纸模糊、标注不可读、专项所需图纸缺失时，写入 missing_information 或 uncertain_observations，并降低置信度。
3. must_fix 只能写图纸或说明能支持的确定问题；无法确认的内容不得作为硬性结论。
4. 只评价已上传图纸覆盖的范围，不把未上传的楼层、剖面或完整任务书缺失直接判成方案错误。
5. 评价要说明建筑学原因，建议要能用于学生下一轮修改。
6. 涉及知识库时尽量引用 [K1] 这类依据编号；没有依据时说明来自图纸观察或设计说明。
7. 输出必须是 JSON/json 对象，不能输出 Markdown、解释文字或代码块。
8. 报告要紧凑：summary 控制在 120 字内；每项 reason 控制在 120 字内；evidence 控制在 80 字内；每个反馈列表优先返回 1-2 条，每条控制在 100 字内。
""".strip()


COMPREHENSIVE_SYSTEM_PROMPT = """
你是 ArchCritic 的“综合评审 Agent”，负责把方案阶段各专项 Agent 的结果整理为正式反馈报告。

综合规则：
1. 只汇总专项 Agent 已给出的事实、分数、问题和建议，不新增未经专项结果支持的图纸事实。
2. 先保留跨专项重复出现或影响后续深化的问题，再保留局部优化建议。
3. 报告语言应严谨、清楚、可执行，区分必须修改、建议优化和可选优化。
4. 如果专项结果存在不确定观察，最终报告不能把它升级成确定性批评。
5. 总结必须覆盖功能与流线、场地回应、几何形式、结构可行性四个角度。
6. 输出必须是 JSON/json 对象，不能输出 Markdown、解释文字或代码块。
""".strip()


def build_specialist_json_schema(spec: dict) -> dict:
    """按专项评分项构造结构化输出格式。"""
    score_names = list(spec["sub_scores"])
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "observed_facts",
            "confidence",
            "summary",
            "sub_scores",
            "must_fix",
            "should_improve",
            "optional_improvements",
            "strengths",
            "missing_information",
            "uncertain_observations",
        ],
        "properties": {
            "observed_facts": {
                "type": "array",
                "items": {"type": "string", "maxLength": 120},
                "minItems": 1,
                "maxItems": 6,
            },
            "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
            "summary": {"type": "string", "maxLength": 240},
            "sub_scores": {
                "type": "object",
                "additionalProperties": False,
                "required": score_names,
                "properties": {
                    name: {"$ref": "#/$defs/sub_score"} for name in score_names
                },
            },
            "must_fix": {
                "type": "array",
                "items": {"type": "string", "maxLength": 200},
                "maxItems": 3,
            },
            "should_improve": {
                "type": "array",
                "items": {"type": "string", "maxLength": 200},
                "minItems": 1,
                "maxItems": 3,
            },
            "optional_improvements": {
                "type": "array",
                "items": {"type": "string", "maxLength": 200},
                "minItems": 1,
                "maxItems": 3,
            },
            "strengths": {
                "type": "array",
                "items": {"type": "string", "maxLength": 200},
                "minItems": 1,
                "maxItems": 3,
            },
            "missing_information": {
                "type": "array",
                "items": {"type": "string", "maxLength": 200},
                "maxItems": 5,
            },
            "uncertain_observations": {
                "type": "array",
                "items": {"type": "string", "maxLength": 200},
                "maxItems": 5,
            },
        },
        "$defs": {
            "sub_score": {
                "type": "object",
                "additionalProperties": False,
                "required": ["score", "max_score", "reason", "evidence"],
                "properties": {
                    "score": {"type": "number"},
                    "max_score": {"type": "number"},
                    "reason": {"type": "string", "maxLength": 240},
                    "evidence": {"type": "string", "maxLength": 160},
                },
            }
        },
    }


COMPREHENSIVE_JSON_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "summary",
        "must_fix",
        "should_improve",
        "optional_improvements",
        "strengths",
    ],
    "properties": {
        "summary": {"type": "string", "maxLength": 360},
        "must_fix": {
            "type": "array",
            "items": {"type": "string", "maxLength": 240},
            "maxItems": 4,
        },
        "should_improve": {
            "type": "array",
            "items": {"type": "string", "maxLength": 240},
            "minItems": 1,
            "maxItems": 4,
        },
        "optional_improvements": {
            "type": "array",
            "items": {"type": "string", "maxLength": 240},
            "minItems": 1,
            "maxItems": 4,
        },
        "strengths": {
            "type": "array",
            "items": {"type": "string", "maxLength": 240},
            "minItems": 1,
            "maxItems": 4,
        },
    },
}


def build_specialist_user_prompt(context: dict, spec: dict) -> str:
    """整理专项 Agent 读取的图文上下文。"""
    references = "\n".join(build_reference_prompt_item(item) for item in context["references"])
    drawings = "\n".join(
        f"- {item['drawing_type']}：{item['original_name']}，用于判断 {item['analysis_purpose']}"
        for item in context["drawings"]
    )
    missing = "\n".join(f"- {item}" for item in context["missing_information"])
    scores = "\n".join(
        f"- {name}：0-{max_score} 分" for name, max_score in spec["sub_scores"].items()
    )
    targets = "、".join(spec["observed_targets"])
    score_shape = ",\n    ".join(
        f'"{name}": {{"score": 0-{max_score}, "max_score": {max_score}, '
        f'"reason": "评价理由", "evidence": "图纸/说明/知识依据"}}'
        for name, max_score in spec["sub_scores"].items()
    )
    return f"""
请完成“{spec["name"]}”专项评审。

【专项边界】
{spec["purpose"]}
{spec["drawing_focus"]}
本专项必须重点核对：{targets}。

【项目信息】
项目名称：{context["project_name"]}
建筑类型：{context["building_type"]}
提交人：{context["owner_name"]}
年级：{context["grade"]}
设计阶段：{context["design_stage"]}

【任务书要求或摘要】
{context["task_book_summary"]}

【设计说明】
{context["description"]}

【已上传图纸】
{drawings or "未上传图纸。"}

【评判边界】
{context["drawing_scope"]}

【知识库依据】
{references or "当前没有可用知识库依据。"}

【已知缺失信息】
{missing or "暂无。"}

【评分项】
{scores}

【输出结构】
只输出 JSON/json 对象，字段名保持如下：
写得简洁，避免长段落；reason 和 evidence 只保留能支撑评分的关键依据。
{{
  "observed_facts": ["图纸或说明中已确认的专项事实"],
  "confidence": "high/medium/low",
  "summary": "专项评价摘要",
  "sub_scores": {{
    {score_shape}
  }},
  "must_fix": ["已确认的必须修改问题"],
  "should_improve": ["建议优化的问题"],
  "optional_improvements": ["可选优化"],
  "strengths": ["当前优势"],
  "missing_information": ["影响判断的缺失信息"],
  "uncertain_observations": ["看不清或只能推测的观察"]
}}
""".strip()


def build_comprehensive_user_prompt(context: dict, specialist_evaluations: list[dict]) -> str:
    """整理综合评审 Agent 读取的专项结果。"""
    compact_reviews = [
        {
            "agent_type": item["agent_type"],
            "dimension": item["dimension"],
            "score": item["score"],
            "summary": item["summary"],
            "strengths": item["strengths"][:3],
            "issues": item["issues"][:4],
            "suggestions": item["suggestions"][:4],
        }
        for item in specialist_evaluations
    ]
    return f"""
请把以下方案阶段专项评审结果整理为正式反馈报告。

【项目信息】
项目名称：{context["project_name"]}
建筑类型：{context["building_type"]}
设计阶段：{context["design_stage"]}
设计说明：{context["description"]}

【专项结果】
{json.dumps(compact_reviews, ensure_ascii=False, indent=2)}

【输出结构】
只输出 JSON/json 对象：
写成报告摘要，不重复粘贴专项 Agent 的长段原文。
{{
  "summary": "覆盖四个专项视角的总体反馈摘要",
  "must_fix": ["会阻碍方案继续深化的确定问题"],
  "should_improve": ["下一轮优先优化项"],
  "optional_improvements": ["可选深化项"],
  "strengths": ["可以保留并继续发展的优势"]
}}
""".strip()


def build_reference_prompt_item(item: dict) -> str:
    """把知识卡片压缩成可引用依据。"""
    content = (item.get("content") or item.get("excerpt") or "").strip()
    compact_content = "\n".join(
        line.strip()
        for line in content.splitlines()
        if line.strip() and not line.strip().startswith("---")
    )
    if len(compact_content) > 460:
        compact_content = compact_content[:460].rstrip() + "..."
    return (
        f"- {item.get('reference_id') or 'K?'} "
        f"[{item.get('source_type', '依据')} / {item.get('dimension', '通用依据')}] "
        f"{item.get('title', '')}\n"
        f"  可引用观点：{item.get('excerpt', '')}\n"
        f"  卡片内容：{compact_content}"
    )
