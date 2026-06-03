"""验证新版前端会调用的项目、资料、报告和追问接口。"""

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import get_settings
from app.database import init_db
from app.main import app


@pytest.mark.asyncio
async def test_frontend_v1_complete_api_flow(tmp_path, monkeypatch):
    """串行验证新版前端完整业务流程。"""
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    get_settings.cache_clear()
    init_db()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        project_response = await client.post(
            "/api/projects",
            json={
                "name": "美术馆方案",
                "building_type": "公共建筑",
                "owner_name": "前端工程师",
                "grade": "三年级",
                "site_location": "上海市徐汇滨江",
                "course_name": "建筑设计课",
            },
        )
        project_id = project_response.json()["id"]
        submission_response = await client.post(
            "/api/submissions",
            json={
                "project_id": project_id,
                "title": "方案阶段提交",
                "design_stage": "方案阶段",
                "description": "公共文化建筑，重点关注展厅流线。",
                "enabled_agents": ["site_agent", "function_agent"],
            },
        )
        submission_id = submission_response.json()["id"]
        upload_response = await client.post(
            f"/api/submissions/{submission_id}/files",
            data={"drawing_type": "site"},
            files={"file": ("site.png", b"image-bytes", "image/png")},
        )
        drawing = upload_response.json()
        patch_response = await client.patch(
            f"/api/files/{drawing['id']}",
            json={"drawing_type": "analysis", "description": "基地交通分析图"},
        )
        attachment_response = await client.post(
            f"/api/submissions/{submission_id}/attachments",
            files={"file": ("taskbook.pdf", b"pdf-bytes", "application/pdf")},
        )
        report_response = await client.post(
            f"/api/submissions/{submission_id}/evaluate-demo"
        )
        export_response = await client.get(
            f"/api/submissions/{submission_id}/report/export"
        )
        chat_response = await client.post(
            f"/api/submissions/{submission_id}/chat",
            json={"content": "列出必须修改项"},
        )
        chat_list_response = await client.get(
            f"/api/submissions/{submission_id}/chat/messages"
        )
        clone_response = await client.post(f"/api/projects/{project_id}/clone")
        clone_id = clone_response.json()["id"]
        clone_submissions_response = await client.get(
            f"/api/projects/{clone_id}/submissions"
        )
        clone_submission_id = clone_submissions_response.json()[0]["id"]
        clone_files_response = await client.get(
            f"/api/submissions/{clone_submission_id}/files"
        )
        inherited_file_id = clone_files_response.json()[0]["id"]
        delete_clone_response = await client.delete(f"/api/files/{inherited_file_id}")
        source_files_response = await client.get(
            f"/api/submissions/{submission_id}/files"
        )
        source_path = Path(tmp_path / drawing["file_url"].removeprefix("/uploads/"))
        source_exists_after_clone_delete = source_path.is_file()
        cancel_response = await client.post(
            f"/api/submissions/{submission_id}/cancel-evaluation"
        )
        batch_delete_response = await client.post(
            "/api/files/batch-delete", json={"file_ids": [drawing["id"]]}
        )

    monkeypatch.delenv("UPLOAD_DIR", raising=False)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    get_settings.cache_clear()

    assert project_response.status_code == 201
    assert submission_response.status_code == 201
    assert upload_response.status_code == 201
    assert patch_response.json()["description"] == "基地交通分析图"
    assert attachment_response.status_code == 201
    assert report_response.status_code == 200
    assert export_response.status_code == 200
    assert "# ArchCritic 评图报告" in export_response.text
    assert chat_response.status_code == 200
    assert len(chat_list_response.json()) == 2
    assert clone_response.status_code == 201
    assert len(clone_submissions_response.json()) == 1
    assert len(clone_files_response.json()) == 1
    assert delete_clone_response.status_code == 200
    assert len(source_files_response.json()) == 1
    assert source_exists_after_clone_delete
    assert cancel_response.json()["status"] == "cancelled"
    assert batch_delete_response.json()["deleted"] == [drawing["id"]]
    assert not source_path.is_file()
