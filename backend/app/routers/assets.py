"""受登录保护地返回用户图纸和任务书文件。"""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import Attachment, DrawingFile, Project, Submission, User
from app.services.auth import get_current_user


router = APIRouter(tags=["assets"])


@router.get("/uploads/{relative_path:path}")
async def get_user_upload(
    relative_path: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FileResponse:
    """只允许文件所属用户读取本地上传内容。"""
    file_url = f"/uploads/{relative_path}"
    drawing_exists = db.execute(
        select(DrawingFile.id)
        .join(Submission, Submission.id == DrawingFile.submission_id)
        .join(Project, Project.id == Submission.project_id)
        .where(DrawingFile.file_url == file_url, Project.user_id == user.id)
        .limit(1)
    ).scalar_one_or_none()
    attachment_exists = db.execute(
        select(Attachment.id)
        .join(Submission, Submission.id == Attachment.submission_id)
        .join(Project, Project.id == Submission.project_id)
        .where(Attachment.file_url == file_url, Project.user_id == user.id)
        .limit(1)
    ).scalar_one_or_none()
    if drawing_exists is None and attachment_exists is None:
        raise HTTPException(status_code=404, detail="文件不存在。")
    upload_root = Path(get_settings().upload_dir).resolve()
    file_path = (upload_root / relative_path).resolve()
    if upload_root not in file_path.parents or not file_path.is_file():
        raise HTTPException(status_code=404, detail="文件不存在。")
    return FileResponse(file_path)
