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
        "overall_score",
        "grade",
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
        "overall_score": {"type": "number", "minimum": 0, "maximum": 100},
        "grade": {"type": "string"},
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
            "minItems": 1,
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
        f"- [{item.get('source_type', '依据')}] {item.get('title', '')}：{item.get('excerpt', '')}"
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

【知识库依据】
{references or "当前没有可用知识库依据。"}

【已知缺失信息】
{missing or "暂无。"}

【输出要求】
1. 只输出 JSON/json 对象，不要输出 Markdown、代码块或解释。
2. 必须使用下面这个字段结构，字段名不能改：

{{
  "scores": {{
    "功能满足": 0-30,
    "功能分区": 0-25,
    "流线分析": 0-25,
    "平面丰富性": 0-20
  }},
  "comments": {{
    "功能满足": "依据设计说明/图纸/知识库写具体评价",
    "功能分区": "依据设计说明/图纸/知识库写具体评价",
    "流线分析": "依据设计说明/图纸/知识库写具体评价",
    "平面丰富性": "依据设计说明/图纸/知识库写具体评价"
  }},
  "must_fix": ["必须修改的问题，1-3条"],
  "should_improve": ["建议优化的问题，1-3条"],
  "optional_improvements": ["可选优化，1-3条"],
  "strengths": ["当前优势，1-3条"],
  "missing_information": ["缺少但会影响判断的信息"],
  "uncertain_observations": ["图纸中看不清或只能推测的内容"]
}}

3. comments 里的每一项都要写出建筑学理由，不能只写“较好”“一般”。
4. 如果无法从图纸确认，不要写成确定事实，放入 uncertain_observations。
5. scores 四项相加应等于总分；不要单独输出 total_score。
""".strip()
