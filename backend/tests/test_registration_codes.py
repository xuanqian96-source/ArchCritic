"""验证内测码限额、失败回滚、并发争用及原账户登录兼容。"""

from concurrent.futures import ThreadPoolExecutor
import hashlib

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.config import get_settings
from app.database import Base, get_engine, get_session_factory, init_db
from app.main import app
from app.models import RegistrationCodeUsage
from app.services.auth import get_current_user
from app.services.registration_codes import reserve_registration_code

CODE = "test-invitation-only"
DIGEST = hashlib.sha256(CODE.encode()).hexdigest()


@pytest.fixture
def code_settings(monkeypatch):
    """为测试配置一个最多注册两人的内测码。"""
    monkeypatch.setattr(get_settings(), "registration_code_required", True)
    monkeypatch.setattr(get_settings(), "registration_code_limits", {DIGEST: 2})


@pytest.mark.asyncio
async def test_registration_capacity_and_existing_login(code_settings, monkeypatch):
    """检查缺码、错码、重复账户、名额耗尽和关闭新注册后的原用户登录。"""
    app.dependency_overrides.pop(get_current_user, None)
    init_db()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        payload = {"username": "invite1", "password": "password-test", "display_name": "内测用户"}
        assert (await client.post("/api/auth/register", json=payload)).status_code == 403
        assert (await client.post("/api/auth/register", json={**payload, "invitation_code": "bad"})).status_code == 403
        payload["invitation_code"] = CODE
        assert (await client.post("/api/auth/register", json=payload)).status_code == 201
        assert (await client.post("/api/auth/register", json=payload)).status_code == 409
        assert (await client.post("/api/auth/register", json={**payload, "username": "invite2"})).status_code == 201
        assert (await client.post("/api/auth/register", json={**payload, "username": "invite3"})).status_code == 403
        monkeypatch.setattr(get_settings(), "registration_code_limits", {})
        assert (await client.post("/api/auth/login", json={"username": "invite1", "password": "password-test"})).status_code == 200
        public = (await client.get("/api/site/config")).json()
        assert DIGEST not in str(public) and CODE not in str(public)
    with get_session_factory()() as db:
        assert db.get(RegistrationCodeUsage, DIGEST).used_count == 2


def test_code_reservation_rolls_back_with_failed_registration(code_settings):
    """注册事务失败时不会消耗名额。"""
    init_db()
    with get_session_factory()() as db:
        reserve_registration_code(db, CODE)
        db.rollback()
        assert db.scalar(select(RegistrationCodeUsage.used_count)) is None
        reserve_registration_code(db, CODE)
        db.commit()
        assert db.get(RegistrationCodeUsage, DIGEST).used_count == 1


def test_parallel_registration_never_exceeds_capacity(code_settings, tmp_path):
    """不同连接同时争用两席时，只有两个事务能成功。"""
    url = f"sqlite:///{tmp_path / 'capacity.db'}"
    engine = get_engine(url)
    Base.metadata.create_all(engine)
    factory = get_session_factory(url)

    def attempt():
        """用独立数据库连接模拟一个注册事务。"""
        with factory() as db:
            try:
                reserve_registration_code(db, CODE)
                db.commit()
                return True
            except HTTPException:
                db.rollback()
                return False

    with ThreadPoolExecutor(max_workers=6) as pool:
        outcomes = list(pool.map(lambda _: attempt(), range(6)))
    assert sum(outcomes) == 2
    with factory() as db:
        assert db.get(RegistrationCodeUsage, DIGEST).used_count == 2
    engine.dispose()
