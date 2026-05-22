"""功能与流线 Agent v1 提示词，供真实模型评图时使用。"""

FUNCTION_AGENT_SYSTEM_PROMPT = """
你是 ArchCritic 的“功能与流线 Agent”，同时具备建筑设计课教师、公共建筑方案评图专家和低年级建筑学教学助教的视角。

你的任务是评价建筑方案的功能满足、功能分区、流线分析和平面丰富性。你必须依据用户提供的任务信息、设计说明、知识库依据和图纸内容进行判断。

评价原则：
1. 不要为了显得专业而编造图纸中不存在的信息。
2. 必须区分“图纸中能看见的内容”和“根据说明推测的内容”。
3. 如果没有任务书，只能评价基础公共建筑功能是否完整，不能断言“已完全满足任务书”。
4. 如果图纸模糊、标注不可读或没有平面图，必须降低置信度，并写入 missing_information 或 uncertain_observations。
5. 平面丰富性只评价平面空间组织、公共空间层次、几何多样性和趣味性，不评价立面表皮风格。
6. 问题必须具体，尽量指出对应的建筑学原因，例如功能缺漏、分区错位、动静干扰、服务流线穿越公共区、入口不清楚、平面过于机械等。
7. 建议必须可执行，适合学生下一轮修改。
8. 必须遵守已上传图纸范围：如果只上传一层平面图，不得因为其他楼层、剖面、总图或完整任务书缺失，就断言整栋建筑功能缺失。
9. 对图纸中看不清、标注无法确认、可能与设计说明冲突的内容，应写入 uncertain_observations，不得直接放入 must_fix。
10. 每条确定性评价都应尽量引用知识库依据编号，例如 [K1]；没有依据时要说明来自图纸观察或设计说明。
11. 输出评价前，必须先在 observed_facts 中列出你从图纸或设计说明确认的事实。只有 observed_facts 中高置信确认的问题，才允许进入 must_fix。
12. 对“楼梯、电梯、卫生间、入口、车库入口、报告厅、服务台”等大功能，如果设计说明明确说有而图纸看不清，应写为“不确定”，不得写成“缺少”。

四项评分：
- 功能满足：0-30 分，评价是否满足任务书和基础功能要求。
- 功能分区：0-25 分，评价功能放置区域是否合理，是否有明显错位或互相干扰。
- 流线分析：0-25 分，评价主要人流、服务流线和内部流线是否顺畅，是否有明显交叉。
- 平面丰富性：0-20 分，评价是否只是机械满足功能，是否具有设计性、趣味性和几何多样性。

你只能输出 JSON/json 对象，不能输出 Markdown、解释文字或代码块。
""".strip()


FUNCTION_AGENT_JSON_SCHEMA = {
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
            "type": "object",
            "additionalProperties": False,
            "required": ["楼梯", "电梯", "卫生间", "主入口", "车库入口", "报告厅", "服务台"],
            "properties": {
                "楼梯": {"type": "string"},
                "电梯": {"type": "string"},
                "卫生间": {"type": "string"},
                "主入口": {"type": "string"},
                "车库入口": {"type": "string"},
                "报告厅": {"type": "string"},
                "服务台": {"type": "string"},
            },
        },
        "confidence": {
            "type": "string",
            "enum": ["high", "medium", "low"],
        },
        "summary": {"type": "string"},
        "sub_scores": {
            "type": "object",
            "additionalProperties": False,
            "required": ["功能满足", "功能分区", "流线分析", "平面丰富性"],
            "properties": {
                "功能满足": {"$ref": "#/$defs/sub_score"},
                "功能分区": {"$ref": "#/$defs/sub_score"},
                "流线分析": {"$ref": "#/$defs/sub_score"},
                "平面丰富性": {"$ref": "#/$defs/sub_score"},
            },
        },
        "must_fix": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 0,
            "maxItems": 4,
        },
        "should_improve": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
            "maxItems": 4,
        },
        "optional_improvements": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
            "maxItems": 4,
        },
        "strengths": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
            "maxItems": 4,
        },
        "missing_information": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 5,
        },
        "uncertain_observations": {
            "type": "array",
            "items": {"type": "string"},
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
                "reason": {"type": "string"},
                "evidence": {"type": "string"},
            },
        }
    },
}


def build_function_agent_user_prompt(context: dict) -> str:
    """把提交上下文整理成模型可读的用户提示词。"""
    references = "\n".join(
        build_reference_prompt_item(item)
        for item in context["references"]
    )
    drawings = "\n".join(
        f"- {item['drawing_type']}：{item['original_name']}，用于判断 {item['analysis_purpose']}"
        for item in context["drawings"]
    )
    missing = "\n".join(f"- {item}" for item in context["missing_information"])

    return f"""
请评价以下建筑设计提交。你需要真正检查设计说明与图纸内容，并按照四项评分给出结构化结果。

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

【输出要求】
1. 只输出 JSON/json 对象，不要输出 Markdown、代码块或解释。
2. 必须使用下面这个字段结构，字段名不能改：

{{
  "observed_facts": {{
    "楼梯": "看见/未看见/不确定，并说明依据",
    "电梯": "看见/未看见/不确定，并说明依据",
    "卫生间": "看见/未看见/不确定，并说明依据",
    "主入口": "看见/未看见/不确定，并说明依据",
    "车库入口": "看见/未看见/不确定，并说明依据",
    "报告厅": "看见/未看见/不确定，并说明依据",
    "服务台": "看见/未看见/不确定，并说明依据"
  }},
  "confidence": "high/medium/low",
  "summary": "总体评价摘要",
  "sub_scores": {{
    "功能满足": {{
      "score": 0-30,
      "max_score": 30,
      "reason": "依据设计说明/图纸/知识库写具体评价",
      "evidence": "说明来自图纸观察、设计说明或知识库编号"
    }},
    "功能分区": {{
      "score": 0-25,
      "max_score": 25,
      "reason": "依据设计说明/图纸/知识库写具体评价",
      "evidence": "说明来自图纸观察、设计说明或知识库编号"
    }},
    "流线分析": {{
      "score": 0-25,
      "max_score": 25,
      "reason": "依据设计说明/图纸/知识库写具体评价",
      "evidence": "说明来自图纸观察、设计说明或知识库编号"
    }},
    "平面丰富性": {{
      "score": 0-20,
      "max_score": 20,
      "reason": "依据设计说明/图纸/知识库写具体评价",
      "evidence": "说明来自图纸观察、设计说明或知识库编号"
    }}
  }},
  "must_fix": ["已确认的必须修改问题，0-3条；不确定内容不要写在这里"],
  "should_improve": ["建议优化的问题，1-3条"],
  "optional_improvements": ["可选优化，1-3条"],
  "strengths": ["当前优势，1-3条"],
  "missing_information": ["缺少但会影响判断的信息"],
  "uncertain_observations": ["图纸中看不清或只能推测的内容"]
}}

3. sub_scores 里的每一项都要写出建筑学理由和证据，不能只写“较好”“一般”。
4. 如果无法从图纸确认，不要写成确定事实，放入 uncertain_observations。
5. 如果只上传一层平面图，只评价一层能确认的功能和流线；其他楼层缺失只能写入 missing_information。
6. 涉及知识库的判断需要写出依据编号，例如“依据 [K1]，入口与门厅应形成连续过程”。
7. must_fix 只能写“图纸和说明均支持”的确定问题；如果设计说明说有但图纸看不清，必须放入 uncertain_observations。
8. 四项 score 相加应等于总分；不要单独输出 total_score、overall_score 或 grade。
""".strip()


def build_reference_prompt_item(item: dict) -> str:
    """把知识卡片压缩成模型可引用的依据块。"""
    content = (item.get("content") or item.get("excerpt") or "").strip()
    compact_content = "\n".join(
        line.strip()
        for line in content.splitlines()
        if line.strip() and not line.strip().startswith("---")
    )
    if len(compact_content) > 700:
        compact_content = compact_content[:700].rstrip() + "..."
    return (
        f"- {item.get('reference_id') or 'K?'} "
        f"[{item.get('source_type', '依据')} / {item.get('dimension', '通用依据')}] "
        f"{item.get('title', '')}\n"
        f"  可引用观点：{item.get('excerpt', '')}\n"
        f"  卡片内容：{compact_content}"
    )
