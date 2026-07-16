"""提供本地注册、登录、退出和当前用户接口。"""

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import Project, User, UserSession
from app.schemas import AuthLogin, AuthPasswordUpdate, AuthProfileUpdate, AuthRegister, AuthUserRead
from app.services.auth import (
    create_user_session,
    get_current_user,
    hash_password,
    hash_session_token,
    normalize_username,
    verify_password,
)


router = APIRouter(prefix="/api/auth", tags=["auth"])


def user_response(user: User) -> AuthUserRead:
    """把数据库用户转换为前端公开结构。"""
    return AuthUserRead(
        id=user.id,
        username=user.username or "",
        display_name=user.name,
        role=user.role,
    )


def set_session_cookie(response: Response, token: str) -> None:
    """写入只允许后端读取的登录 Cookie。"""
    settings = get_settings()
    response.set_cookie(
        key=settings.auth_cookie_name,
        value=token,
        max_age=settings.auth_session_days * 24 * 60 * 60,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        path="/",
    )


@router.post("/register", response_model=AuthUserRead, status_code=status.HTTP_201_CREATED)
async def register(
    payload: AuthRegister,
    response: Response,
    db: Session = Depends(get_db),
) -> AuthUserRead:
    """创建本地账户；首个账户接管升级前的历史项目。"""
    username = normalize_username(payload.username)
    existing = db.execute(select(User).where(func.lower(User.username) == username)).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=409, detail="该用户名已被使用。")
    has_registered_user = db.execute(
        select(User.id).where(User.username.is_not(None)).limit(1)
    ).scalar_one_or_none()
    user = User(
        name=payload.display_name.strip(),
        username=username,
        password_hash=hash_password(payload.password),
        role="student",
    )
    db.add(user)
    db.flush()
    if has_registered_user is None:
        db.execute(update(Project).values(user_id=user.id))
    db.commit()
    db.refresh(user)
    token, _ = create_user_session(db, user)
    set_session_cookie(response, token)
    return user_response(user)


@router.post("/login", response_model=AuthUserRead)
async def login(
    payload: AuthLogin,
    response: Response,
    db: Session = Depends(get_db),
) -> AuthUserRead:
    """校验本地账户并创建新会话。"""
    username = normalize_username(payload.username)
    user = db.execute(select(User).where(func.lower(User.username) == username)).scalar_one_or_none()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码不正确。")
    token, _ = create_user_session(db, user)
    set_session_cookie(response, token)
    return user_response(user)


@router.get("/me", response_model=AuthUserRead)
async def current_user(user: User = Depends(get_current_user)) -> AuthUserRead:
    """返回当前登录账户。"""
    return user_response(user)


@router.patch("/profile", response_model=AuthUserRead)
async def update_profile(
    payload: AuthProfileUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AuthUserRead:
    """更新当前账户显示名称。"""
    user.name = payload.display_name.strip()
    db.commit()
    db.refresh(user)
    return user_response(user)


@router.post("/password")
async def update_password(
    payload: AuthPasswordUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """校验原密码后保存新的密码哈希。"""
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="当前密码不正确。")
    user.password_hash = hash_password(payload.new_password)
    db.commit()
    return {"ok": True}


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> dict:
    """删除当前本地会话并清除 Cookie。"""
    settings = get_settings()
    token = request.cookies.get(settings.auth_cookie_name, "")
    if token:
        session = db.execute(
            select(UserSession).where(UserSession.token_hash == hash_session_token(token))
        ).scalar_one_or_none()
        if session is not None:
            db.delete(session)
            db.commit()
    response.delete_cookie(settings.auth_cookie_name, path="/")
    return {"ok": True}
