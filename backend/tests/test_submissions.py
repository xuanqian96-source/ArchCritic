"""验证提交方案与演示评图接口的基础流程。"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.database import init_db
from app.main import app


@pytest.mark.asyncio
async def test_create_submission_and_generate_demo_report():
    """确认提交方案后可以拿到演示评图结果。"""
    init_db()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        project_response = await client.post(
            "/api/projects",
            json={
                "name": "城市阅读展亭",
                "building_type": "小型公共建筑",
                "owner_name": "学生甲",
            },
        )
        project_id = project_response.json()["id"]

        submission_response = await client.post(
            "/api/submissions",
            json={
                "project_id": project_id,
                "title": "第一次方案提交",
                "design_stage": "concept",
                "description": "一个面向街角公共空间的小型阅读展亭，强调轻量结构和开放界面。",
                "image_urls": [
                    "https://example.com/diagram-1.png",
                    "https://example.com/diagram-2.png",
                ],
            },
        )
        submission_id = submission_response.json()["id"]

        evaluation_response = await client.post(
            f"/api/submissions/{submission_id}/evaluate-demo"
        )

    assert submission_response.status_code == 201
    created_submission = submission_response.json()
    assert created_submission["design_stage"] == "concept"

    assert evaluation_response.status_code == 200
    report = evaluation_response.json()
    assert report["submission_id"] == submission_id
    assert report["overall_score"] >= 0
    assert len(report["must_fix"]) > 0
    assert len(report["strengths"]) > 0
    assert len(report["agent_evaluations"]) > 0
