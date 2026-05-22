"""验证数据库初始化后会创建核心数据表。"""

import pytest
from sqlalchemy import inspect

from app.database import get_engine, init_db


def test_init_db_creates_core_tables():
    """确认初始化数据库后可以看到核心表。"""
    init_db()
    engine = get_engine()
    with engine.begin() as connection:
        inspector = inspect(connection)
        table_names = set(inspector.get_table_names())
        agent_columns = {
            column["name"] for column in inspector.get_columns("agent_evaluations")
        }

    assert {
        "users",
        "projects",
        "submissions",
        "drawing_files",
        "agent_evaluations",
        "overall_reports",
    }.issubset(table_names)
    assert "details" in agent_columns
