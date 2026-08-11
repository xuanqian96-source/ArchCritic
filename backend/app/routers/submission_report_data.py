"""报告数据服务，集中保存评分、知识快照并生成稳定的接口结构。"""

import asyncio
import json
import re

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.llm.dashscope_files import DashScopeUploadError
from app.models import AgentEvaluation, OverallReport, ReportReference, Submission
from app.knowledge_selection import prepare_reference_bundle
from app.schemas import OverallReportRead
from app.wiki import load_wiki_references

def save_report_data(
    db: Session,
    submission_id: int,
    report_data: dict,
    references: list[dict] | None = None,
) -> None:
    """保存模型生成的综合报告和各 Agent 分项。"""
    db.execute(delete(ReportReference).where(ReportReference.submission_id == submission_id))
    db.execute(
        delete(AgentEvaluation).where(AgentEvaluation.submission_id == submission_id)
    )
    db.execute(delete(OverallReport).where(OverallReport.submission_id == submission_id))

    for agent_item in report_data["agent_evaluations"]:
        db.add(
            AgentEvaluation(
                submission_id=submission_id,
                agent_type=agent_item["agent_type"],
                dimension=agent_item["dimension"],
                score=agent_item["score"],
                summary=agent_item["summary"],
                strengths=agent_item["strengths"],
                issues=agent_item["issues"],
                suggestions=agent_item["suggestions"],
                details=agent_item.get("details") or {},
            )
        )

    overall_report = OverallReport(
        submission_id=submission_id,
        overall_score=report_data["overall_score"],
        grade=report_data["grade"],
        summary=report_data["summary"],
        must_fix=report_data["must_fix"],
        should_improve=report_data["should_improve"],
        optional_improvements=report_data["optional_improvements"],
        strengths=report_data["strengths"],
        evaluation_context=report_data.get("evaluation_context") or {},
    )
    db.add(overall_report)
    db.flush()
    save_reference_snapshots(db, submission_id, overall_report.id, references or [])
    db.commit()


def build_report_response(
    overall_report: OverallReport,
    agent_evaluations: list[AgentEvaluation],
    submission: Submission | None = None,
    db: Session | None = None,
) -> OverallReportRead:
    """把数据库中的报告和分项评价整理成接口返回结构。"""
    references = []
    if submission is not None:
        if db is not None:
            references = load_report_reference_snapshots(db, submission.id)
        if not references:
            settings = get_settings()
            references = load_submission_wiki_references(settings.wiki_dir, submission)

    return OverallReportRead(
        id=overall_report.id,
        submission_id=overall_report.submission_id,
        overall_score=overall_report.overall_score,
        grade=overall_report.grade,
        summary=overall_report.summary,
        must_fix=overall_report.must_fix,
        should_improve=overall_report.should_improve,
        optional_improvements=overall_report.optional_improvements,
        strengths=overall_report.strengths,
        agent_evaluations=[
            {
                "agent_type": item.agent_type,
                "dimension": item.dimension,
                "score": item.score,
                "summary": item.summary,
                "strengths": item.strengths,
                "issues": item.issues,
                "suggestions": item.suggestions,
                "details": item.details or {},
            }
            for item in agent_evaluations
        ],
        references=references,
        feedback=build_feedback_items(
            {
                "must_fix": overall_report.must_fix,
                "should_improve": overall_report.should_improve,
                "optional_improvements": overall_report.optional_improvements,
                "strengths": overall_report.strengths,
            },
            references,
        ),
        evaluation_context=overall_report.evaluation_context or {},
    )


def build_feedback_items(feedback: dict[str, list[str]], references: list[dict]) -> dict:
    """把报告反馈中的知识编号整理成前端可点击引用。"""
    valid_reference_ids = {
        str(item.get("reference_id", "")).upper()
        for item in references
        if item.get("reference_id")
    }
    return {
        category: [
            {
                "text": str(text),
                "reference_ids": extract_reference_ids(str(text), valid_reference_ids),
            }
            for text in items or []
        ]
        for category, items in feedback.items()
    }


def extract_reference_ids(text: str, valid_reference_ids: set[str]) -> list[str]:
    """从反馈文本中提取本次报告真实存在的知识编号。"""
    ids = re.findall(r"\[(K\d+)\]", text, flags=re.IGNORECASE)
    seen: set[str] = set()
    reference_ids = []
    for item in ids:
        normalized = item.upper()
        if normalized in valid_reference_ids and normalized not in seen:
            seen.add(normalized)
            reference_ids.append(normalized)
    return reference_ids


def save_reference_snapshots(
    db: Session,
    submission_id: int,
    report_id: int,
    references: list[dict],
) -> None:
    """保存本次评图实际使用的知识库依据快照。"""
    for index, item in enumerate(references, start=1):
        db.add(
            ReportReference(
                submission_id=submission_id,
                report_id=report_id,
                position=index,
                reference_id=str(item.get("reference_id") or f"K{index}"),
                title=str(item.get("title") or ""),
                source_type=str(item.get("source_type") or ""),
                excerpt=str(item.get("excerpt") or ""),
                dimension=str(item.get("dimension") or ""),
                path=str(item.get("path") or ""),
                content=str(item.get("content") or ""),
                display_content=str(item.get("display_content") or ""),
                image_urls=item.get("image_urls") or [],
            )
        )


def load_report_reference_snapshots(db: Session, submission_id: int) -> list[dict]:
    """读取一次评图保存下来的知识库依据快照。"""
    rows = db.execute(
        select(ReportReference)
        .where(ReportReference.submission_id == submission_id)
        .order_by(ReportReference.position.asc(), ReportReference.id.asc())
    ).scalars()
    return [
        {
            "reference_id": item.reference_id,
            "title": item.title,
            "source_type": item.source_type,
            "excerpt": item.excerpt,
            "dimension": item.dimension,
            "path": item.path,
            "content": item.content,
            "display_content": item.display_content,
            "image_urls": item.image_urls,
        }
        for item in rows
    ]


def load_submission_wiki_references(wiki_dir: str, submission: Submission) -> list[dict]:
    """根据提交上下文从完整 Wiki 中检索相关知识依据。"""
    project = submission.project
    references = load_wiki_references(
        wiki_dir,
        submission.design_stage,
        limit=40,
        query_context={
            "project_name": project.name,
            "building_type": project.building_type,
            "design_stage": submission.design_stage,
            "description": submission.description,
            "drawing_types": [item.drawing_type for item in submission.drawing_files],
        },
    )
    settings = get_settings()
    return prepare_reference_bundle(
        references,
        submission.design_stage,
        list(getattr(submission, "enabled_agents", []) or []),
        human_approved_only=settings.scoring_architecture == "evidence_v2",
    )


def build_model_error_message(exc: Exception) -> str:
    """把模型调用异常转换成前端可读的中文提示。"""
    message = str(exc)
    if isinstance(exc, DashScopeUploadError) or "百炼临时存储失败" in message:
        return f"图纸上传到百炼临时 URL 失败：{message}"
    if isinstance(exc, json.JSONDecodeError) or "Expecting value" in message:
        return "千问已返回内容，但结构化 JSON 不完整或格式错误，系统未能解析成报告。"
    if "模型 JSON 输出达到长度上限" in message:
        return "模型评审内容过长，报告在返回时被截断。"
    if isinstance(exc, asyncio.TimeoutError) or "timed out" in message.lower():
        return "真实模型评图调用超时：已停止等待模型返回。"
    if "ReadTimeout" in message or "APITimeoutError" in message:
        return "千问流式输出超时：模型读取图纸或生成报告时间过长。"
    if "APIStatusError" in message or "BadRequest" in message:
        return f"千问接口拒绝本次请求：{message[:240]}"
    if "insufficient_quota" in message or "exceeded your current quota" in message:
        return "真实模型评图调用失败：OpenAI API 额度不足或计费未启用，请检查 Platform 余额和 Billing 设置。"
    if "Connection error" in message or "APIConnectionError" in message:
        return "真实模型评图调用失败：后端无法连接模型 API，请检查网络或代理设置。"
    if "invalid_api_key" in message or "Incorrect API key" in message:
        return "真实模型评图调用失败：API Key 无效，请重新配置。"
    return f"真实模型评图调用失败：{message[:240] or '模型服务暂时不可用。'}"
