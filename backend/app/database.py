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

        if "users" in inspector.get_table_names():
            user_columns = {
                column["name"] for column in inspector.get_columns("users")
            }
            if "username" not in user_columns:
                connection.execute(
                    text("ALTER TABLE users ADD COLUMN username VARCHAR(100)")
                )
            if "password_hash" not in user_columns:
                connection.execute(
                    text("ALTER TABLE users ADD COLUMN password_hash VARCHAR(300)")
                )
            connection.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_username_unique "
                    "ON users(username) WHERE username IS NOT NULL"
                )
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

        if "report_references" in table_names:
            reference_columns = {
                column["name"] for column in inspector.get_columns("report_references")
            }
            if "library_item_id" not in reference_columns:
                connection.execute(
                    text("ALTER TABLE report_references ADD COLUMN library_item_id VARCHAR(30) DEFAULT ''")
                )

        if "attachments" in table_names:
            attachment_columns = {
                column["name"] for column in inspector.get_columns("attachments")
            }
            if "extracted_text" not in attachment_columns:
                connection.execute(
                    text("ALTER TABLE attachments ADD COLUMN extracted_text TEXT DEFAULT ''")
                )
            if "extraction_status" not in attachment_columns:
                connection.execute(
                    text("ALTER TABLE attachments ADD COLUMN extraction_status VARCHAR(30) DEFAULT 'pending'")
                )

        if "agent_evaluations" in table_names:
            agent_columns = {
                column["name"] for column in inspector.get_columns("agent_evaluations")
            }
            if "details" not in agent_columns:
                connection.execute(
                    text("ALTER TABLE agent_evaluations ADD COLUMN details JSON DEFAULT '{}'")
                )


        if "overall_reports" in table_names:
            report_columns = {
                column["name"] for column in inspector.get_columns("overall_reports")
            }
            if "evaluation_context" not in report_columns:
                connection.execute(
                    text("ALTER TABLE overall_reports ADD COLUMN evaluation_context JSON DEFAULT '{}'")
                )

        if "chat_messages" in table_names:
            chat_columns = {
                column["name"] for column in inspector.get_columns("chat_messages")
            }
            if "tool" not in chat_columns:
                connection.execute(
                    text("ALTER TABLE chat_messages ADD COLUMN tool VARCHAR(50) DEFAULT 'none'")
                )
            if "citations" not in chat_columns:
                connection.execute(
                    text("ALTER TABLE chat_messages ADD COLUMN citations JSON DEFAULT '[]'")
                )
            if "report_updated" not in chat_columns:
                connection.execute(
                    text("ALTER TABLE chat_messages ADD COLUMN report_updated BOOLEAN DEFAULT 0")
                )


async def get_db() -> AsyncGenerator[Session, None]:
    """为接口提供数据库会话。"""
    session_factory = get_session_factory()
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
