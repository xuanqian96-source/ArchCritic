"""集中删除一次提交的数据库记录和不再使用的本地文件。"""

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import (
    AgentEvaluation,
    Attachment,
    ChatMessage,
    DrawingFile,
    OverallReport,
    ReportReference,
    Submission,
)
from app.services.uploads import remove_upload_if_last_record


def delete_submission_tree(db: Session, submission_id: int) -> None:
    """删除提交全部关联数据，并保留仍被继承版本引用的共享文件。"""
    drawings = list(
        db.execute(
            select(DrawingFile).where(DrawingFile.submission_id == submission_id)
        ).scalars()
    )
    attachments = list(
        db.execute(
            select(Attachment).where(Attachment.submission_id == submission_id)
        ).scalars()
    )
    for drawing in drawings:
        remove_upload_if_last_record(db, DrawingFile, drawing.file_url)
    for attachment in attachments:
        remove_upload_if_last_record(db, Attachment, attachment.file_url)
    db.execute(delete(ReportReference).where(ReportReference.submission_id == submission_id))
    db.execute(delete(ChatMessage).where(ChatMessage.submission_id == submission_id))
    db.execute(delete(Attachment).where(Attachment.submission_id == submission_id))
    db.execute(delete(DrawingFile).where(DrawingFile.submission_id == submission_id))
    db.execute(delete(AgentEvaluation).where(AgentEvaluation.submission_id == submission_id))
    db.execute(delete(OverallReport).where(OverallReport.submission_id == submission_id))
    db.execute(delete(Submission).where(Submission.id == submission_id))
