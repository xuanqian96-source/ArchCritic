"""数据库连接与会话管理，供主应用、路由和模型模块共同使用。"""

from typing import AsyncGenerator

from sqlalchemy import inspect, text
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    """定义所有 ORM 模型共享的基类。"""


def get_engine(database_url: str | None = None) -> Engine:
    """根据配置创建数据库引擎。"""
    resolved_database_url = database_url or get_settings().database_url
    connect_args = (
        {"check_same_thread": False}
        if resolved_database_url.startswith("sqlite")
        else {}
    )
    return create_engine(resolved_database_url, future=True, connect_args=connect_args)


def get_session_factory(database_url: str | None = None) -> sessionmaker[Session]:
    """创建数据库会话工厂。"""
    return sessionmaker(get_engine(database_url), expire_on_commit=False)


def init_db(database_url: str | None = None) -> None:
    """初始化数据库表结构。"""
    from app import models

    del models
    engine = get_engine(database_url)
    Base.metadata.create_all(bind=engine)
    ensure_sqlite_columns(engine)


def ensure_sqlite_columns(engine: Engine) -> None:
    """为旧版 SQLite 数据库补齐新增字段。"""
    if engine.dialect.name != "sqlite":
        return

    with engine.begin() as connection:
        inspector = inspect(connection)
        if "projects" not in inspector.get_table_names():
            return

        project_columns = {
            column["name"] for column in inspector.get_columns("projects")
        }
        if "grade" not in project_columns:
            connection.execute(
                text("ALTER TABLE projects ADD COLUMN grade VARCHAR(100) DEFAULT ''")
            )
        if "site_location" not in project_columns:
            connection.execute(
                text("ALTER TABLE projects ADD COLUMN site_location VARCHAR(200) DEFAULT ''")
            )
        if "course_name" not in project_columns:
            connection.execute(
                text("ALTER TABLE projects ADD COLUMN course_name VARCHAR(200) DEFAULT ''")
            )

        table_names = set(inspector.get_table_names())
        if "submissions" in table_names:
            submission_columns = {
                column["name"] for column in inspector.get_columns("submissions")
            }
            if "status" not in submission_columns:
                connection.execute(
                    text("ALTER TABLE submissions ADD COLUMN status VARCHAR(30) DEFAULT 'draft'")
                )
            if "enabled_agents" not in submission_columns:
                connection.execute(
                    text("ALTER TABLE submissions ADD COLUMN enabled_agents JSON DEFAULT '[]'")
                )
            if "selected_model_provider" not in submission_columns:
                connection.execute(
                    text("ALTER TABLE submissions ADD COLUMN selected_model_provider VARCHAR(50) DEFAULT 'mock'")
                )
            if "selected_model_name" not in submission_columns:
                connection.execute(
                    text("ALTER TABLE submissions ADD COLUMN selected_model_name VARCHAR(100) DEFAULT 'demo'")
                )
            if "updated_at" not in submission_columns:
                connection.execute(
                    text("ALTER TABLE submissions ADD COLUMN updated_at DATETIME")
                )

        if "drawing_files" in table_names:
            drawing_columns = {
                column["name"] for column in inspector.get_columns("drawing_files")
            }
            if "model_file_url" not in drawing_columns:
                connection.execute(
                    text("ALTER TABLE drawing_files ADD COLUMN model_file_url VARCHAR(500) DEFAULT ''")
                )
            if "model_file_expires_at" not in drawing_columns:
                connection.execute(
                    text("ALTER TABLE drawing_files ADD COLUMN model_file_expires_at DATETIME")
                )
            if "description" not in drawing_columns:
                connection.execute(
                    text("ALTER TABLE drawing_files ADD COLUMN description TEXT DEFAULT ''")
                )
            if "sort_order" not in drawing_columns:
                connection.execute(
                    text("ALTER TABLE drawing_files ADD COLUMN sort_order INTEGER DEFAULT 0")
                )

        if "agent_evaluations" in table_names:
            agent_columns = {
                column["name"] for column in inspector.get_columns("agent_evaluations")
            }
            if "details" not in agent_columns:
                connection.execute(
                    text("ALTER TABLE agent_evaluations ADD COLUMN details JSON DEFAULT '{}'")
                )


async def get_db() -> AsyncGenerator[Session, None]:
    """为接口提供数据库会话。"""
    session_factory = get_session_factory()
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
