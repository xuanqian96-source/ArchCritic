"""验证项目接口可以创建并返回项目列表。"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.database import init_db
from app.main import app


@pytest.mark.asyncio
async def test_create_and_list_projects():
    """确认项目接口支持新增和列表查询。"""
    init_db()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        create_response = await client.post(
            "/api/projects",
            json={
                "name": "演示评图项目",
                "building_type": "公共建筑",
                "owner_name": "测试用户",
                "grade": "大三建筑学",
            },
        )
        project_id = create_response.json()["id"]
        list_response = await client.get("/api/projects")
        history_response = await client.get(f"/api/projects/{project_id}/history")

    assert create_response.status_code == 201
    created_project = create_response.json()
    assert created_project["name"] == "演示评图项目"
    assert created_project["building_type"] == "公共建筑"
    assert created_project["owner_name"] == "测试用户"
    assert created_project["grade"] == "大三建筑学"

    assert list_response.status_code == 200
    projects = list_response.json()
    assert len(projects) == 1
    assert projects[0]["id"] == created_project["id"]

    assert history_response.status_code == 200
    assert history_response.json() == []


@pytest.mark.asyncio
async def test_delete_project_removes_related_submissions():
    """确认删除项目会同时删除该项目下的提交版本。"""
    init_db()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        project_response = await client.post(
            "/api/projects",
            json={
                "name": "待删除项目",
                "building_type": "公共建筑",
                "owner_name": "测试用户",
                "grade": "大三建筑学",
            },
        )
        project_id = project_response.json()["id"]
        submission_response = await client.post(
            "/api/submissions",
            json={
                "project_id": project_id,
                "title": "V1",
                "design_stage": "方案阶段",
                "description": "用于测试项目删除。",
            },
        )
        submission_id = submission_response.json()["id"]

        delete_response = await client.delete(f"/api/projects/{project_id}")
        project_after_delete = await client.get(f"/api/projects/{project_id}")
        submission_after_delete = await client.get(f"/api/submissions/{submission_id}")

    assert delete_response.status_code == 200
    assert delete_response.json()["deleted"] == [project_id]
    assert delete_response.json()["submissions"] == [submission_id]
    assert project_after_delete.status_code == 404
    assert submission_after_delete.status_code == 404
