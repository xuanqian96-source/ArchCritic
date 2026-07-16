"""验证提交方案与演示评图接口的基础流程。"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import get_settings
from app.database import init_db
from app.main import app
from app.routers import submission_crud, submissions
from app.routers.submissions import build_feedback_items


@pytest.mark.asyncio
async def test_create_submission_and_generate_demo_report(monkeypatch):
    """确认提交方案后可以拿到演示评图结果。"""
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    get_settings.cache_clear()
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
                "grade": "大三建筑学",
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
        report_response = await client.get(f"/api/submissions/{submission_id}/report")

    assert submission_response.status_code == 201
    created_submission = submission_response.json()
    assert created_submission["design_stage"] == "concept"

    assert evaluation_response.status_code == 200
    report = evaluation_response.json()
    assert report["submission_id"] == submission_id
    assert report["id"] >= 1
    assert report["overall_score"] >= 0
    assert len(report["must_fix"]) > 0
    assert len(report["strengths"]) > 0
    assert len(report["agent_evaluations"]) > 0

    assert report_response.status_code == 200
    assert report_response.json()["submission_id"] == submission_id
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_upload_and_list_submission_files(tmp_path, monkeypatch):
    """确认图纸可以上传保存，并能按提交记录查询。"""
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setattr(submission_crud, "convert_pdf_to_png", lambda _content, target_path: target_path.write_bytes(b"fake-png"))
    get_settings.cache_clear()
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
                "grade": "大三建筑学",
            },
        )
        project_id = project_response.json()["id"]

        submission_response = await client.post(
            "/api/submissions",
            json={
                "project_id": project_id,
                "title": "第二次方案提交",
                "design_stage": "方案阶段",
                "description": "补充总平面图并保存到后端。",
            },
        )
        submission_id = submission_response.json()["id"]

        upload_response = await client.post(
            f"/api/submissions/{submission_id}/files",
            data={"drawing_type": "site"},
            files={"file": ("site.png", b"fake-image-bytes", "image/png")},
        )
        pdf_upload_response = await client.post(
            f"/api/submissions/{submission_id}/files",
            data={"drawing_type": "plan"},
            files={"file": ("first-floor.pdf", b"%PDF-1.4\n1 0 obj\n<</Type /Page>>\nendobj", "application/pdf")},
        )
        multipage_pdf_response = await client.post(
            f"/api/submissions/{submission_id}/files",
            data={"drawing_type": "plan"},
            files={"file": ("multi-floor.pdf", b"%PDF-1.4\n1 0 obj\n<</Type /Page>>\nendobj\n2 0 obj\n<</Type /Page>>\nendobj", "application/pdf")},
        )
        list_response = await client.get(f"/api/submissions/{submission_id}/files")
        get_submission_response = await client.get(f"/api/submissions/{submission_id}")

    monkeypatch.delenv("UPLOAD_DIR", raising=False)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    get_settings.cache_clear()

    assert upload_response.status_code == 201
    uploaded_file = upload_response.json()
    assert uploaded_file["drawing_type"] == "site"
    assert uploaded_file["original_name"] == "site.png"
    assert uploaded_file["file_url"].startswith("/uploads/submissions/")
    assert pdf_upload_response.status_code == 201
    pdf_file = pdf_upload_response.json()
    assert pdf_file["mime_type"] == "image/png"
    assert pdf_file["original_name"] == "first-floor.pdf"
    assert pdf_file["file_url"].endswith(".png")
    assert multipage_pdf_response.status_code == 400
    assert "单页" in multipage_pdf_response.json()["detail"]

    assert list_response.status_code == 200
    assert len(list_response.json()) == 2

    assert get_submission_response.status_code == 200
    assert uploaded_file["file_url"] in get_submission_response.json()["image_urls"]
    assert pdf_file["file_url"] in get_submission_response.json()["image_urls"]


@pytest.mark.asyncio
async def test_delete_submission_removes_version():
    """确认删除单个提交版本后无法再次读取该版本。"""
    init_db()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        project_response = await client.post(
            "/api/projects",
            json={
                "name": "版本删除测试",
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
                "title": "待删除版本",
                "design_stage": "方案阶段",
                "description": "用于测试版本删除。",
            },
        )
        submission_id = submission_response.json()["id"]

        delete_response = await client.delete(f"/api/submissions/{submission_id}")
        get_response = await client.get(f"/api/submissions/{submission_id}")
        history_response = await client.get(f"/api/projects/{project_id}/history")

    assert delete_response.status_code == 200
    assert delete_response.json()["deleted"] == [submission_id]
    assert get_response.status_code == 404
    assert history_response.status_code == 200
    assert history_response.json() == []


@pytest.mark.asyncio
async def test_report_references_use_wiki_files(tmp_path, monkeypatch):
    """确认报告依据可以从 Wiki 测试知识库读取。"""
    wiki_file = (
        tmp_path
        / "评价维度"
        / "方案阶段"
        / "功能与流线"
        / "规范条文.md"
    )
    wiki_file.parent.mkdir(parents=True)
    wiki_file.write_text(
        "# 功能与流线 — 相关设计规范\n"
        "\n"
        "## 《民用建筑设计统一标准》GB 50352-2019\n"
        "- **评图应用**：评价时关注主要流线方向是否明确。\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("WIKI_DIR", str(tmp_path))
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    get_settings.cache_clear()
    init_db()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        project_response = await client.post(
            "/api/projects",
            json={
                "name": "Wiki 依据测试",
                "building_type": "小型公共建筑",
                "owner_name": "学生甲",
                "grade": "大三建筑学",
            },
        )
        project_id = project_response.json()["id"]
        submission_response = await client.post(
            "/api/submissions",
            json={
                "project_id": project_id,
                "title": "方案阶段提交",
                "design_stage": "方案阶段",
                "description": "测试知识库依据读取。",
            },
        )
        submission_id = submission_response.json()["id"]
        report_response = await client.post(
            f"/api/submissions/{submission_id}/evaluate-demo"
        )
        wiki_file.write_text(
            "# 已修改的新知识卡片\n"
            "\n"
            "- **评图应用**：这条内容不应影响已经生成的报告快照。\n",
            encoding="utf-8",
        )
        saved_report_response = await client.get(
            f"/api/submissions/{submission_id}/report"
        )
        references_response = await client.get(
            f"/api/submissions/{submission_id}/references"
        )

    monkeypatch.delenv("WIKI_DIR", raising=False)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    get_settings.cache_clear()

    assert report_response.status_code == 200
    assert report_response.json()["references"][0]["title"] == "功能与流线 — 相关设计规范"
    assert saved_report_response.status_code == 200
    assert (
        saved_report_response.json()["references"][0]["title"]
        == "功能与流线 — 相关设计规范"
    )
    assert references_response.status_code == 200
    assert references_response.json()[0]["source_type"] == "规范"


def test_wiki_loader_accepts_obsidian_dimension_folder(tmp_path):
    """确认后端可以读取新版 Obsidian 知识库的评价维度目录。"""
    wiki_file = tmp_path / "05评价维度" / "方案阶段" / "功能与流线.md"
    wiki_file.parent.mkdir(parents=True)
    wiki_file.write_text(
        "# 功能与流线\n"
        "\n"
        "- **可引用观点**：入口、门厅和展厅应形成清晰连续的进入过程。\n",
        encoding="utf-8",
    )

    from app.wiki import load_wiki_references

    references = load_wiki_references(str(tmp_path), "scheme")

    assert len(references) == 1
    assert references[0]["title"] == "功能与流线"
    assert references[0]["excerpt"] == "入口、门厅和展厅应形成清晰连续的进入过程。"


def test_feedback_items_only_link_current_report_references():
    """确认反馈只会关联本次报告真实存在的知识编号。"""
    feedback = build_feedback_items(
        {
            "must_fix": ["入口到达关系需要补充 [K2] [K9] [K2]。"],
            "should_improve": ["说明文字可继续精简。"],
        },
        [{"reference_id": "K2", "title": "入口组织"}],
    )

    assert feedback["must_fix"][0]["reference_ids"] == ["K2"]
    assert feedback["should_improve"][0]["reference_ids"] == []
