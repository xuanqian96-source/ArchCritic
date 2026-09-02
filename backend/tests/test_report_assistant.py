"""验证报告助手异常降级不会留下孤立问题或伪造图纸结论。"""

from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

from app.database import get_session_factory, init_db
from app.main import app
from app.models import OverallReport
from app.routers import submission_reports
from app.services.report_assistant import (
    _extract_partial_answer,
    _remove_confirmed_false_claims,
    build_report_assistant_fallback,
)


def test_report_assistant_fallback_keeps_stable_answer():
    """模型或图纸准备失败时仍返回可保存的报告回答。"""
    report = SimpleNamespace(
        summary="当前方案需要继续完善无障碍流线。",
        must_fix=["补充连续无障碍路径"],
        should_improve=["明确后勤与公共流线边界"],
    )

    ordinary = build_report_assistant_fallback(report, "下一步修改什么", "none")
    drawing_review = build_report_assistant_fallback(report, "图中明明有电梯", "drawing_review")

    assert ordinary["answer"]
    assert ordinary["citations"] == []
    assert ordinary["report_update"] is None
    assert "暂不维持或修改原判断" in drawing_review["answer"]


def test_confirmed_false_claim_is_removed_from_all_report_sections():
    """图纸确认原判断错误后，总评、反馈、专项和小分理由不能继续保留旧说法。"""
    report = SimpleNamespace(
        summary="方案缺少垂直交通。整体空间关系清楚。",
        must_fix=["缺少垂直交通，必须补充电梯。", "补充消防疏散标注。"],
        should_improve=["进一步优化入口。"],
        optional_improvements=[],
        strengths=[],
    )
    evaluation = SimpleNamespace(
        summary="未设置电梯。",
        issues=["缺少垂直交通。"],
        suggestions=["补充电梯。"],
        strengths=[],
        details={"sub_scores": {"垂直交通": {"reason": "未设置电梯。"}}},
    )

    changed = _remove_confirmed_false_claims(
        report,
        [evaluation],
        ["缺少垂直交通", "未设置电梯"],
        "图纸已确认设置电梯。",
    )

    assert changed
    assert report.summary == "整体空间关系清楚。"
    assert report.must_fix == ["补充消防疏散标注。"]
    assert evaluation.summary == "图纸已确认设置电梯。"
    assert evaluation.issues == []
    assert evaluation.details["sub_scores"]["垂直交通"]["reason"] == ""


def test_report_stream_extracts_partial_answer():
    """报告 JSON 尚未结束时也能逐步显示 answer。"""
    assert _extract_partial_answer('{"answer":"正在核对\\n电梯') == "正在核对\n电梯"


@pytest.mark.asyncio
async def test_report_chat_stream_returns_delta_and_final(monkeypatch):
    """报告追问接口应先返回增量正文，再返回完整保存结果。"""
    init_db()

    def fake_worker(submission_id, content, tool, on_delta=None):
        del content
        if on_delta:
            on_delta("正在核对")
            on_delta("图纸")
        return {
            "id": 101,
            "role": "assistant",
            "content": "正在核对图纸",
            "tool": tool,
            "citations": [],
            "report_updated": False,
            "updated_report": None,
            "created_at": "2026-09-01T00:00:00",
        }

    monkeypatch.setattr(submission_reports, "_process_report_chat_in_worker", fake_worker)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        project = await client.post("/api/projects", json={
            "name": "流式报告测试",
            "building_type": "社区活动中心",
            "owner_name": "测试用户",
            "grade": "大三",
        })
        submission = await client.post("/api/submissions", json={
            "project_id": project.json()["id"],
            "title": "第一次提交",
            "design_stage": "concept",
            "description": "测试流式报告追问。",
            "image_urls": [],
        })
        submission_id = submission.json()["id"]
        with get_session_factory()() as db:
            db.add(OverallReport(
                submission_id=submission_id,
                overall_score=80,
                grade="良好",
                summary="测试报告。",
                must_fix=[],
                should_improve=[],
                optional_improvements=[],
                strengths=[],
                evaluation_context={},
            ))
            db.commit()
        response = await client.post(
            f"/api/submissions/{submission_id}/chat/stream",
            json={"content": "请复核图纸", "tool": "drawing_review"},
        )

    assert response.status_code == 200
    assert 'event: delta\ndata: "正在核对"' in response.text
    assert 'event: delta\ndata: "图纸"' in response.text
    assert 'event: final' in response.text
