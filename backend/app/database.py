"""数据库连接与会话管理，供主应用、路由和模型模块共同使用。"""

from typing import AsyncGenerator

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
    Base.metadata.create_all(bind=get_engine(database_url))


async def get_db() -> AsyncGenerator[Session, None]:
    """为接口提供数据库会话。"""
    session_factory = get_session_factory()
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
