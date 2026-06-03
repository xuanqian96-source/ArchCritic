"""提供图纸修改和删除接口，供新版前端维护已上传资料。"""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import DrawingFile, Submission
from app.routers.submissions import ALLOWED_DRAWING_TYPES
from app.schemas import BatchDeleteFiles, DrawingFileRead, DrawingFileUpdate

router = APIRouter(prefix="/api/files", tags=["files"])


def remove_local_upload(file_url: str) -> None:
    """仅删除上传目录内的文件，避免路径越界。"""
    if not file_url.startswith("/uploads/"):
        return
    upload_root = Path(get_settings().upload_dir).resolve()
    file_path = (upload_root / file_url.removeprefix("/uploads/")).resolve()
    if upload_root in file_path.parents and file_path.is_file():
        file_path.unlink()


def delete_drawing_file(db: Session, drawing_file: DrawingFile) -> None:
    """删除图纸记录，并同步提交中的图片地址列表。"""
    submission = db.get(Submission, drawing_file.submission_id)
    if submission is not None:
        submission.image_urls = [
            url for url in (submission.image_urls or []) if url != drawing_file.file_url
        ]
    usage_count = db.scalar(
        select(func.count()).select_from(DrawingFile).where(
            DrawingFile.file_url == drawing_file.file_url
        )
    )
    if usage_count == 1:
        remove_local_upload(drawing_file.file_url)
    db.delete(drawing_file)


@router.patch("/{file_id}", response_model=DrawingFileRead)
async def update_file(
    file_id: int, payload: DrawingFileUpdate, db: Session = Depends(get_db)
) -> DrawingFile:
    """修改单张图纸类型、说明或排序。"""
    drawing_file = db.get(DrawingFile, file_id)
    if drawing_file is None:
        raise HTTPException(status_code=404, detail="未找到对应图纸。")
    updates = payload.model_dump(exclude_unset=True)
    drawing_type = updates.get("drawing_type")
    if drawing_type is not None and drawing_type not in ALLOWED_DRAWING_TYPES:
        raise HTTPException(status_code=400, detail="图纸类型不在支持范围内。")
    for field, value in updates.items():
        setattr(drawing_file, field, value)
    db.commit()
    db.refresh(drawing_file)
    return drawing_file


@router.delete("/{file_id}")
async def delete_file(file_id: int, db: Session = Depends(get_db)) -> dict:
    """删除单张图纸。"""
    drawing_file = db.get(DrawingFile, file_id)
    if drawing_file is None:
        raise HTTPException(status_code=404, detail="未找到对应图纸。")
    delete_drawing_file(db, drawing_file)
    db.commit()
    return {"deleted": [file_id]}


@router.post("/batch-delete")
async def batch_delete_files(
    payload: BatchDeleteFiles, db: Session = Depends(get_db)
) -> dict:
    """批量删除所选图纸。"""
    deleted_ids: list[int] = []
    for file_id in payload.file_ids:
        drawing_file = db.get(DrawingFile, file_id)
        if drawing_file is None:
            continue
        delete_drawing_file(db, drawing_file)
        deleted_ids.append(file_id)
    db.commit()
    return {"deleted": deleted_ids}
