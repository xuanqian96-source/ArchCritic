"""提供基础健康检查接口，供前端和部署环境确认服务状态。"""

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health_check():
    """返回基础服务状态。"""
    return {"status": "ok", "service": "archcritic"}
