"""验证数据库初始化后会创建核心数据表。"""

import pytest
from sqlalchemy import inspect

from app.database import get_engine, init_db


def test_init_db_creates_core_tables():
    """确认初始化数据库后可以看到核心表。"""
    init_db()
    engine = get_engine()
    with engine.begin() as connection:
        table_names = set(inspect(connection).get_table_names())

    assert {
        "users",
        "projects",
        "submissions",
        "agent_evaluations",
        "overall_reports",
    }.issubset(table_names)
