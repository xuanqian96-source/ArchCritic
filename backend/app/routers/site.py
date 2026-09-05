"""向网页提供可公开的站点配置，不返回密钥或内测码。"""

from fastapi import APIRouter
from app.config import get_settings

router = APIRouter(prefix="/api/site", tags=["site"])


@router.get("/config")
async def site_config() -> dict:
    """提供访客统计标识和注册要求，配置为空时统计关闭。"""
    settings = get_settings()
    return {
        "baidu_tongji_site_id": settings.baidu_tongji_site_id,
        "registration_code_required": settings.registration_code_required,
    }
