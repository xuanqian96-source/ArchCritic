"""集中处理本地上传文件路径和安全删除，供图纸、附件及项目清理复用。"""

from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings


def resolve_local_upload(file_url: str) -> Path | None:
    """把上传地址转换为上传目录内的真实文件，拒绝路径越界。"""
    if not file_url.startswith("/uploads/"):
        return None
    upload_root = Path(get_settings().upload_dir).resolve()
    file_path = (upload_root / file_url.removeprefix("/uploads/")).resolve()
    if upload_root not in file_path.parents:
        return None
    return file_path


def remove_local_upload(file_url: str) -> None:
    """删除上传目录内的文件；文件不存在时保持幂等。"""
    file_path = resolve_local_upload(file_url)
    if file_path is not None and file_path.is_file():
        file_path.unlink()


def remove_upload_if_last_record(
    db: Session,
    model: Any,
    file_url: str,
) -> None:
    """只在当前记录是该文件最后一个引用时删除物理文件。"""
    usage_count = db.scalar(
        select(func.count()).select_from(model).where(model.file_url == file_url)
    )
    if usage_count == 1:
        remove_local_upload(file_url)
