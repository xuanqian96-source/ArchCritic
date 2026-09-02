"""提供登录用户问题反馈接口，并把内容保存到本地数据库。"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Feedback, User
from app.schemas import FeedbackCreate, FeedbackRead
from app.services.auth import get_current_user


router = APIRouter(prefix="/api/feedback", tags=["feedback"])


@router.post("", response_model=FeedbackRead, status_code=status.HTTP_201_CREATED)
async def create_feedback(
    payload: FeedbackCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Feedback:
    """保存当前登录用户提交的一条反馈。"""
    feedback = Feedback(user_id=user.id, content=payload.content.strip())
    db.add(feedback)
    db.commit()
    db.refresh(feedback)
    return feedback
