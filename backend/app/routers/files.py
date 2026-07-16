"""提供图纸修改和删除接口，供新版前端维护已上传资料。"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import DrawingFile, Project, Submission, User
from app.routers.submissions import ALLOWED_DRAWING_TYPES
from app.schemas import BatchDeleteFiles, DrawingFileRead, DrawingFileUpdate
from app.services.auth import get_current_user
from app.services.uploads import remove_upload_if_last_record

router = APIRouter(prefix="/api/files", tags=["files"])


def get_owned_drawing_file(db: Session, file_id: int, user: User) -> DrawingFile | None:
    """读取当前用户拥有的图纸记录。"""
    return db.execute(
        select(DrawingFile)
        .join(Submission, Submission.id == DrawingFile.submission_id)
        .join(Project, Project.id == Submission.project_id)
        .where(DrawingFile.id == file_id, Project.user_id == user.id)
    ).scalar_one_or_none()


def delete_drawing_file(db: Session, drawing_file: DrawingFile) -> None:
    """删除图纸记录，并同步提交中的图片地址列表。"""
    submission = db.get(Submission, drawing_file.submission_id)
    if submission is not None:
        submission.image_urls = [
            url for url in (submission.image_urls or []) if url != drawing_file.file_url
        ]
    remove_upload_if_last_record(db, DrawingFile, drawing_file.file_url)
    db.delete(drawing_file)


@router.patch("/{file_id}", response_model=DrawingFileRead)
async def update_file(
    file_id: int,
    payload: DrawingFileUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DrawingFile:
    """修改单张图纸类型、说明或排序。"""
    drawing_file = get_owned_drawing_file(db, file_id, user)
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
async def delete_file(
    file_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """删除单张图纸。"""
    drawing_file = get_owned_drawing_file(db, file_id, user)
    if drawing_file is None:
        raise HTTPException(status_code=404, detail="未找到对应图纸。")
    delete_drawing_file(db, drawing_file)
    db.commit()
    return {"deleted": [file_id]}


@router.post("/batch-delete")
async def batch_delete_files(
    payload: BatchDeleteFiles,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """批量删除所选图纸。"""
    deleted_ids: list[int] = []
    for file_id in payload.file_ids:
        drawing_file = get_owned_drawing_file(db, file_id, user)
        if drawing_file is None:
            continue
        delete_drawing_file(db, drawing_file)
        deleted_ids.append(file_id)
    db.commit()
    return {"deleted": deleted_ids}
