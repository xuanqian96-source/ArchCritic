"""提供本地密码哈希、会话创建和接口身份校验。"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import User, UserSession


PASSWORD_ITERATIONS = 310_000


def normalize_username(username: str) -> str:
    """统一账户名格式，登录时忽略大小写。"""
    return username.strip().lower()


def hash_password(password: str) -> str:
    """使用 PBKDF2 为密码生成带随机盐的不可逆哈希。"""
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS
    )
    return "$".join(
        (
            "pbkdf2_sha256",
            str(PASSWORD_ITERATIONS),
            base64.urlsafe_b64encode(salt).decode("ascii"),
            base64.urlsafe_b64encode(digest).decode("ascii"),
        )
    )


def verify_password(password: str, encoded: str | None) -> bool:
    """校验输入密码，不暴露哈希比较耗时差异。"""
    if not encoded:
        return False
    try:
        algorithm, iterations, salt_text, digest_text = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        salt = base64.urlsafe_b64decode(salt_text.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_text.encode("ascii"))
        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, int(iterations)
        )
        return hmac.compare_digest(actual, expected)
    except (TypeError, ValueError):
        return False


def hash_session_token(token: str) -> str:
    """数据库只保存会话令牌哈希。"""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def clear_expired_sessions(db: Session) -> None:
    """清理过期会话，避免本地数据库持续累积。"""
    db.execute(delete(UserSession).where(UserSession.expires_at <= datetime.now(timezone.utc)))


def create_user_session(db: Session, user: User) -> tuple[str, UserSession]:
    """创建一个可持久化的本地登录会话。"""
    settings = get_settings()
    clear_expired_sessions(db)
    token = secrets.token_urlsafe(32)
    session = UserSession(
        user_id=user.id,
        token_hash=hash_session_token(token),
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.auth_session_days),
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return token, session


async def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    """从 HttpOnly Cookie 读取当前用户，未登录时返回 401。"""
    cookie_name = get_settings().auth_cookie_name
    token = request.cookies.get(cookie_name, "")
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先登录。")
    session = db.execute(
        select(UserSession).where(UserSession.token_hash == hash_session_token(token))
    ).scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录状态已失效，请重新登录。")
    expires_at = session.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= datetime.now(timezone.utc):
        db.delete(session)
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录状态已过期，请重新登录。")
    user = db.get(User, session.user_id)
    if user is None or not user.username:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="账户不存在。")
    return user


def require_owned_project(db: Session, project_id: int, user: User):
    """读取当前用户拥有的项目。"""
    from app.models import Project

    project = db.get(Project, project_id)
    if project is None or project.user_id != user.id:
        raise HTTPException(status_code=404, detail="项目不存在。")
    return project


def require_owned_submission(db: Session, submission_id: int, user: User):
    """读取当前用户拥有的提交版本。"""
    from app.models import Project, Submission

    submission = db.execute(
        select(Submission)
        .join(Project, Project.id == Submission.project_id)
        .where(Submission.id == submission_id, Project.user_id == user.id)
    ).scalar_one_or_none()
    if submission is None:
        raise HTTPException(status_code=404, detail="未找到对应的方案提交。")
    return submission
