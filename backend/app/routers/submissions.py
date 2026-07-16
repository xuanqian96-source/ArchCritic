"""提交接口入口，组合草稿文件、报告追问和流式评图三个子路由。"""

from fastapi import APIRouter

from app.routers import submission_crud, submission_reports, submission_stream
from app.routers.submission_common import ALLOWED_DRAWING_TYPES
from app.routers.submission_report_data import build_feedback_items, build_model_error_message

router = APIRouter()
router.include_router(submission_crud.router)
router.include_router(submission_reports.router)
router.include_router(submission_stream.router)

__all__ = [
    "ALLOWED_DRAWING_TYPES",
    "build_feedback_items",
    "build_model_error_message",
    "router",
]
