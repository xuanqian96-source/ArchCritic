"""测试环境初始化，统一设置数据库和演示模型配置。"""

import os
from pathlib import Path

TEST_DB_PATH = Path(__file__).resolve().parent.parent / "test_archcritic.db"

os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH.as_posix()}"
os.environ["LLM_PROVIDER"] = "mock"
os.environ["CORS_ORIGINS"] = "http://localhost:5173,http://127.0.0.1:5173"

import pytest
from fastapi import Depends
from sqlalchemy import select

from app.database import get_db
from app.main import app
from app.models import User
from app.services.auth import get_current_user, hash_password

TEST_PASSWORD_HASH = hash_password("test-password")


@pytest.fixture(autouse=True)
def clean_test_database():
    """每个测试前后清理测试数据库文件。"""
    async def override_current_user(db=Depends(get_db)):
        user = db.execute(select(User).where(User.username == "test-user")).scalar_one_or_none()
        if user is None:
            user = User(
                name="测试用户",
                username="test-user",
                password_hash=TEST_PASSWORD_HASH,
                role="student",
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        return user

    app.dependency_overrides[get_current_user] = override_current_user
    if TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink()
    yield
    app.dependency_overrides.pop(get_current_user, None)
    if TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink()
