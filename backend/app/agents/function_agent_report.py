"""功能 Agent 报告校验与转换，隔离模型输出兼容和评分数据整理。"""

from typing import Any

SUB_SCORE_LIMITS = {
    "功能满足": 30,
    "功能分区": 25,
    "流线分析": 25,
    "平面丰富性": 20,
}
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
                "details": build_agent_evaluation_details(report),
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


def build_agent_evaluation_details(report: dict) -> dict:
    """保留专项评分卡片需要的细节。"""
    return {
        "confidence": report.get("confidence", "medium"),
        "observed_facts": report.get("observed_facts") or {},
        "sub_scores": report.get("sub_scores") or {},
        "must_fix": report.get("must_fix") or [],
        "should_improve": report.get("should_improve") or [],
        "optional_improvements": report.get("optional_improvements") or [],
        "missing_information": report.get("missing_information") or [],
        "uncertain_observations": report.get("uncertain_observations") or [],
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
