"""验证本地账户登录、会话保持和不同用户的数据隔离。"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.database import init_db
from app.main import app
from app.services.auth import get_current_user


@pytest.mark.asyncio
async def test_local_auth_keeps_each_users_projects_separate():
    """确认注册登录使用安全 Cookie，且账户之间看不到彼此项目。"""
    app.dependency_overrides.pop(get_current_user, None)
    init_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as first:
        register = await first.post(
            "/api/auth/register",
            json={"username": "student_a", "password": "password-a", "display_name": "学生甲"},
        )
        create = await first.post(
            "/api/projects",
            json={"name": "甲的项目", "building_type": "公共建筑", "owner_name": "学生甲"},
        )
        own_projects = await first.get("/api/projects")
        logout = await first.post("/api/auth/logout")
        unauthorized = await first.get("/api/projects")
        wrong_login = await first.post(
            "/api/auth/login",
            json={"username": "student_a", "password": "wrong-password"},
        )
        login = await first.post(
            "/api/auth/login",
            json={"username": "STUDENT_A", "password": "password-a"},
        )
        restored_projects = await first.get("/api/projects")

    async with AsyncClient(transport=transport, base_url="http://test") as second:
        second_register = await second.post(
            "/api/auth/register",
            json={"username": "student_b", "password": "password-b", "display_name": "学生乙"},
        )
        isolated_projects = await second.get("/api/projects")

    assert register.status_code == 201
    assert "httponly" in register.headers["set-cookie"].lower()
    assert create.status_code == 201
    assert len(own_projects.json()) == 1
    assert logout.status_code == 200
    assert unauthorized.status_code == 401
    assert wrong_login.status_code == 401
    assert login.status_code == 200
    assert len(restored_projects.json()) == 1
    assert second_register.status_code == 201
    assert isolated_projects.json() == []
