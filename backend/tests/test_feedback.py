"""验证登录用户提交的问题反馈会进入后台数据库。"""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.database import get_session_factory, init_db
from app.main import app
from app.models import Feedback


@pytest.mark.asyncio
async def test_create_feedback():
    """提交反馈后返回回执，并保存原始问题内容。"""
    init_db()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/feedback", json={"content": "首页项目状态偶尔显示不正确。"})

    assert response.status_code == 201
    assert response.json()["status"] == "pending"
    with get_session_factory()() as db:
        saved = db.execute(select(Feedback)).scalar_one()
        assert saved.content == "首页项目状态偶尔显示不正确。"
