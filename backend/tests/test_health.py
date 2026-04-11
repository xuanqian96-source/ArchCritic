"""验证基础健康检查接口可用。"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.database import init_db
from app.main import app


@pytest.mark.asyncio
async def test_health_returns_ok():
    """确认服务健康接口返回正常状态。"""
    init_db()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "archcritic"
