"""提交与文件接口，负责草稿、图纸和任务书的增删改查。"""

import re
import subprocess
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import Attachment, DrawingFile, Project, Submission, User
from app.schemas import AttachmentRead, DrawingFileRead, SubmissionCreate, SubmissionRead, SubmissionUpdate
from app.services.auth import get_current_user, require_owned_project, require_owned_submission
from app.services.submission_cleanup import delete_submission_tree
from app.services.taskbooks import TaskBookExtractionError, extract_task_book_text, refresh_attachment_extraction
from app.services.uploads import remove_upload_if_last_record
from app.routers.submission_common import ALLOWED_ATTACHMENT_TYPES, ALLOWED_DRAWING_FILE_TYPES, ALLOWED_DRAWING_TYPES, CANCELLED_SUBMISSIONS, MAX_ATTACHMENT_BYTES, MAX_UPLOAD_BYTES

router = APIRouter(prefix="/api/submissions", tags=["submissions"])

@router.post("", response_model=SubmissionRead, status_code=status.HTTP_201_CREATED)
async def create_submission(
    payload: SubmissionCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Submission:
    """创建一次新的方案提交记录。"""
    require_owned_project(db, payload.project_id, user)

    submission = Submission(
        project_id=payload.project_id,
        title=payload.title,
        design_stage=payload.design_stage,
        description=payload.description,
        image_urls=payload.image_urls,
        status=payload.status,
        enabled_agents=payload.enabled_agents,
        selected_model_provider=payload.selected_model_provider,
        selected_model_name=payload.selected_model_name,
    )
    db.add(submission)
    db.commit()
    db.refresh(submission)
    return submission


@router.patch("/{submission_id}", response_model=SubmissionRead)
async def update_submission(
    submission_id: int,
    payload: SubmissionUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Submission:
    """修改草稿提交、阶段、模型和 Agent 选择。"""
    submission = require_owned_submission(db, submission_id, user)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(submission, field, value)
    db.commit()
    db.refresh(submission)
    return submission


@router.delete("/{submission_id}")
async def delete_submission(
    submission_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """删除一个版本提交及其报告、图纸记录和追问记录。"""
    require_owned_submission(db, submission_id, user)
    delete_submission_tree(db, submission_id)
    db.commit()
    CANCELLED_SUBMISSIONS.discard(submission_id)
    return {"deleted": [submission_id]}


@router.get("/{submission_id}", response_model=SubmissionRead)
async def get_submission(
    submission_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Submission:
    """返回一次提交记录。"""
    return require_owned_submission(db, submission_id, user)


@router.post(
    "/{submission_id}/files",
    response_model=DrawingFileRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_submission_file(
    submission_id: int,
    drawing_type: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DrawingFile:
    """上传并保存某次提交下的一张图纸。"""
    submission = require_owned_submission(db, submission_id, user)

    if drawing_type not in ALLOWED_DRAWING_TYPES:
        raise HTTPException(status_code=400, detail="图纸类型不在支持范围内。")

    mime_type = file.content_type or ""
    extension = ALLOWED_DRAWING_FILE_TYPES.get(mime_type)
    if extension is None:
        raise HTTPException(status_code=400, detail="当前只支持图片或 PDF 图纸。")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="上传文件不能为空。")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="单个图纸文件不能超过 30MB。")
    if mime_type == "application/pdf" and count_pdf_pages(content) != 1:
        raise HTTPException(status_code=400, detail="PDF 图纸仅支持上传单页文件，请拆分后重新上传。")

    settings = get_settings()
    stored_mime_type = mime_type
    stored_extension = extension
    if mime_type == "application/pdf":
        stored_mime_type = "image/png"
        stored_extension = ".png"
    relative_path = Path("submissions") / str(submission_id) / f"{uuid4().hex}{stored_extension}"
    target_path = Path(settings.upload_dir) / relative_path
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if mime_type == "application/pdf":
        convert_pdf_to_png(content, target_path)
    else:
        target_path.write_bytes(content)

    file_url = f"/uploads/{relative_path.as_posix()}"
    drawing_file = DrawingFile(
        submission_id=submission_id,
        drawing_type=drawing_type,
        original_name=file.filename or "未命名图纸",
        file_url=file_url,
        mime_type=stored_mime_type,
    )

    submission.image_urls = [*(submission.image_urls or []), file_url]
    db.add(drawing_file)
    db.commit()
    db.refresh(drawing_file)
    return drawing_file


def count_pdf_pages(content: bytes) -> int:
    """读取 PDF 页数；当前图纸上传只接受单页 PDF。"""
    if not content.startswith(b"%PDF"):
        return 0
    page_markers = re.findall(rb"/Type\s*/Page\b", content)
    if page_markers:
        return len(page_markers)
    count_match = re.search(rb"/Count\s+(\d+)", content)
    if count_match:
        return int(count_match.group(1))
    return 0


def convert_pdf_to_png(content: bytes, target_path: Path) -> None:
    """把单页 PDF 转为 PNG，避免前端使用浏览器 PDF 查看器。"""
    source_path = target_path.with_suffix(".source.pdf")
    output_prefix = target_path.with_suffix("")
    try:
        source_path.write_bytes(content)
        completed = subprocess.run(
            ["pdftoppm", "-singlefile", "-png", "-r", "180", str(source_path), str(output_prefix)],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0 or not target_path.is_file():
            raise HTTPException(status_code=400, detail="PDF 图纸转换失败，请导出为 PNG 后重新上传。")
    except OSError as exc:
        raise HTTPException(status_code=500, detail="服务器缺少 PDF 转图片工具。") from exc
    finally:
        source_path.unlink(missing_ok=True)


@router.get("/{submission_id}/files", response_model=list[DrawingFileRead])
async def list_submission_files(
    submission_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[DrawingFile]:
    """返回某次提交下已上传的图纸列表。"""
    require_owned_submission(db, submission_id, user)

    result = db.execute(
        select(DrawingFile)
        .where(DrawingFile.submission_id == submission_id)
        .order_by(DrawingFile.id.asc())
    )
    return list(result.scalars().all())


@router.post(
    "/{submission_id}/attachments",
    response_model=AttachmentRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_submission_attachment(
    submission_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Attachment:
    """上传任务书等补充资料。"""
    require_owned_submission(db, submission_id, user)
    mime_type = file.content_type or ""
    extension = ALLOWED_ATTACHMENT_TYPES.get(mime_type)
    if extension is None:
        raise HTTPException(status_code=400, detail="任务书仅支持 PDF、Word 或文本文件。")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="上传文件不能为空。")
    if len(content) > MAX_ATTACHMENT_BYTES:
        raise HTTPException(status_code=400, detail="单个任务书不能超过 20MB。")
    try:
        extracted_text = extract_task_book_text(content, extension)
    except TaskBookExtractionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    relative_path = Path("attachments") / str(submission_id) / f"{uuid4().hex}{extension}"
    target_path = Path(get_settings().upload_dir) / relative_path
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_bytes(content)
    attachment = Attachment(
        submission_id=submission_id,
        original_name=file.filename or "未命名任务书",
        file_url=f"/uploads/{relative_path.as_posix()}",
        mime_type=mime_type,
        extracted_text=extracted_text,
        extraction_status="ready",
    )
    db.add(attachment)
    db.commit()
    db.refresh(attachment)
    return attachment


@router.get("/{submission_id}/attachments", response_model=list[AttachmentRead])
async def list_submission_attachments(
    submission_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[Attachment]:
    """返回某次提交下的补充资料。"""
    require_owned_submission(db, submission_id, user)
    result = db.execute(
        select(Attachment)
        .where(Attachment.submission_id == submission_id)
        .order_by(Attachment.id.asc())
    )
    attachments = list(result.scalars().all())
    refresh_submission_attachments(db, attachments)
    return attachments


def refresh_submission_attachments(db: Session, attachments: list[Attachment]) -> None:
    """自动升级旧任务书记录，使历史项目也能参与真实评图。"""
    settings = get_settings()
    changed = False
    for attachment in attachments:
        changed = refresh_attachment_extraction(attachment, settings.upload_dir) or changed
    if changed:
        db.commit()


@router.delete("/attachments/{attachment_id}")
async def delete_submission_attachment(
    attachment_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """删除一个任务书或补充资料附件。"""
    attachment = db.execute(
        select(Attachment)
        .join(Submission, Submission.id == Attachment.submission_id)
        .join(Project, Project.id == Submission.project_id)
        .where(Attachment.id == attachment_id, Project.user_id == user.id)
    ).scalar_one_or_none()
    if attachment is None:
        raise HTTPException(status_code=404, detail="未找到对应附件。")
    remove_upload_if_last_record(db, Attachment, attachment.file_url)
    db.delete(attachment)
    db.commit()
    return {"deleted": [attachment_id]}
