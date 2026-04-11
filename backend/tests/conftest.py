"""测试环境初始化，统一设置数据库和演示模型配置。"""

import os
from pathlib import Path

import pytest

TEST_DB_PATH = Path(__file__).resolve().parent.parent / "test_archcritic.db"

os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH.as_posix()}"
os.environ["LLM_PROVIDER"] = "mock"
os.environ["CORS_ORIGINS"] = "http://localhost:5173,http://127.0.0.1:5173"


@pytest.fixture(autouse=True)
def clean_test_database():
    """每个测试前后清理测试数据库文件。"""
    if TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink()
    yield
    if TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink()
