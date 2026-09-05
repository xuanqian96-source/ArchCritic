"""由注册路由调用，在同一数据库事务中检查并占用内测名额。"""

import hashlib

from fastapi import HTTPException
from sqlalchemy import update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import RegistrationCodeUsage


def reserve_registration_code(db: Session, code: str) -> None:
    """原子增加用量，注册失败时由调用方回滚，避免并发超额。"""
    settings = get_settings()
    if not settings.registration_code_required:
        return
    digest = hashlib.sha256(code.strip().encode("utf-8")).hexdigest()
    limit = settings.registration_code_limits.get(digest)
    if not code.strip() or limit is None:
        raise HTTPException(status_code=403, detail="请输入有效的内测码。")
    dialect = db.get_bind().dialect.name
    if dialect not in {"sqlite", "postgresql"}:
        raise HTTPException(status_code=503, detail="注册服务暂不可用，请联系管理员。")
    insert = sqlite_insert if dialect == "sqlite" else postgres_insert
    db.execute(insert(RegistrationCodeUsage).values(code_hash=digest, used_count=0)
               .on_conflict_do_nothing(index_elements=["code_hash"]))
    result = db.execute(
        update(RegistrationCodeUsage)
        .where(RegistrationCodeUsage.code_hash == digest, RegistrationCodeUsage.used_count < limit)
        .values(used_count=RegistrationCodeUsage.used_count + 1)
    )
    if result.rowcount != 1:
        raise HTTPException(status_code=403, detail="该内测码的注册名额已用完，请联系邀请人。")
