"""验证知识库浏览接口可以读取最终版目录结构、正文和图片。"""

from pathlib import Path
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from PIL import Image

from app.config import get_settings
from app.database import init_db
from app.main import app
from app.services.knowledge_library import _specific_case_category
from app.services.knowledge_assistant import _normalize_area, extract_conditions


def write_note(path: Path, content: str) -> None:
    """创建测试用 UTF-8 Markdown 文件。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_specific_case_categories():
    """确认旧其他公共建筑会转换成明确的实际类型。"""
    assert _specific_case_category("乡村小学与社区教育设施", "甘多小学") == "学校"
    assert _specific_case_category("歌剧院与滨水公共文化设施", "挪威国家歌剧院") == "剧院"
    assert _specific_case_category("艺术展馆与社区教育设施", "Robert Olnick Pavilion") == "美术馆"
    assert _specific_case_category("其他公共建筑", "景德镇川上行景仰书院") == "酒店"
    assert _specific_case_category("其他公共建筑", "舟山海洋文化艺术中心二期") == "文化中心"


def test_knowledge_assistant_condition_and_area_normalization():
    """确认自然语言条件与不同面积口径可以稳定提取。"""
    conditions = extract_conditions("我要做一个约5000平米的城市校园博物馆，关注入口与流线")
    assert conditions["area_target_sqm"] == 5000
    assert conditions["building_types"] == ["博物馆", "学校"]
    assert conditions["site_contexts"] == ["城市", "校园"]
    assert conditions["dimensions"] == ["流线", "入口"]
    assert _normalize_area("建筑面积 5,700 m²") == (5700.0, 5700.0, "floor_area", "high")
    assert _normalize_area("展览面积 2000㎡；建筑面积 5000㎡") == (2000.0, 5000.0, "exhibition", "medium")


def test_knowledge_assistant_marks_unreviewed_recommendations(tmp_path, monkeypatch):
    """确认学习候选会保留人工复核状态，且空推荐不会伪造卡片。"""
    write_note(
        tmp_path / "02_建筑案例" / "博物馆" / "PBC-001_测试博物馆.md",
        """---
type: building_case
case_id: PBC-001
title: 测试城市博物馆
building_type: 博物馆
---
# 测试城市博物馆

## 案例概览

一座城市博物馆。
""",
    )
    monkeypatch.setenv("LLM_PROVIDER", "dashscope")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    get_settings.cache_clear()
    from app.services import knowledge_assistant

    monkeypatch.setattr(
        knowledge_assistant,
        "_call_model",
        lambda *args, **kwargs: {
            "answer": "可先把这张案例作为待复核的学习候选。",
            "clarification_required": False,
            "recommendations": [{"id": "PBC-001", "reason": "类型匹配"}],
        },
    )
    result = knowledge_assistant.generate_knowledge_answer(
        "case_recommendation", "推荐城市博物馆", {"current_card_id": None}, [], str(tmp_path)
    )
    assert result["recommendations"][0]["human_review_confirmed"] is False
    assert "内容待专业复核" in result["recommendations"][0]["limitations"]
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_browse_knowledge_library(tmp_path, monkeypatch):
    """确认列表分类、详情正文、图片与关联编号均能返回。"""
    image = tmp_path / "02_建筑案例" / "_图片" / "PBC-001" / "view.jpg"
    image.parent.mkdir(parents=True)
    Image.new("RGB", (1200, 800), "#d7d9d5").save(image, format="JPEG")
    write_note(
        tmp_path / "03_知识卡片" / "L1_入门" / "KC-BEG-001_入口.md",
        """---
type: knowledge_card
card_id: KC-BEG-001
title: 入口空间要形成清晰到达
level: beginner
related_cases:
- PBC-001
---
# 入口空间要形成清晰到达

## 学习目标

理解入口、门厅与城市到达之间的连续关系。
""",
    )
    write_note(
        tmp_path / "02_建筑案例" / "博物馆" / "PBC-001_测试博物馆.md",
        """---
type: building_case
case_id: PBC-001
title: 测试博物馆
building_type: 博物馆
related_knowledge_cards:
- KC-BEG-001
---
# 测试博物馆

## 案例概览

通过连续门厅组织公共到达。

![[02_建筑案例/_图片/PBC-001/view.jpg]]
""",
    )
    monkeypatch.setenv("WIKI_DIR", str(tmp_path))
    get_settings.cache_clear()
    init_db()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        listing = await client.get("/api/knowledge")
        detail = await client.get("/api/knowledge/PBC-001")
        thumbnail = await client.get("/api/knowledge/thumbnail/02_建筑案例/_图片/PBC-001/view.jpg")
        missing = await client.get("/api/knowledge/PBC-999")

    assert listing.status_code == 200
    payload = listing.json()
    assert payload["totals"] == {"all": 2, "knowledge": 1, "case": 1}
    assert payload["items"][0]["level_label"] == "入门"
    assert payload["items"][1]["thumbnail"].endswith("view.jpg")
    assert detail.status_code == 200
    assert detail.json()["related_ids"] == ["KC-BEG-001"]
    assert detail.json()["images"][0]["url"].endswith("view.jpg")
    assert thumbnail.status_code == 200
    assert thumbnail.headers["content-type"] == "image/webp"
    assert len(thumbnail.content) < image.stat().st_size
    assert missing.status_code == 404
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_knowledge_assistant_validates_ids_and_saves_conversation(tmp_path, monkeypatch):
    """确认助手只返回真实候选编号，并按账户保存对话。"""
    write_note(
        tmp_path / "03_知识卡片" / "L1_入门" / "KC-BEG-001_入口.md",
        """---
type: knowledge_card
card_id: KC-BEG-001
title: 入口空间要形成清晰到达
level: beginner
related_cases:
- PBC-001
---
# 入口空间要形成清晰到达

## 学习目标

理解入口、门厅与城市到达之间的连续关系。
""",
    )
    write_note(
        tmp_path / "02_建筑案例" / "博物馆" / "PBC-001_测试博物馆.md",
        """---
type: building_case
case_id: PBC-001
title: 测试城市博物馆
building_type: 博物馆
related_knowledge_cards:
- KC-BEG-001
---
# 测试城市博物馆

## 案例概览

一座通过连续门厅组织公共到达的城市博物馆。
""",
    )
    monkeypatch.setenv("WIKI_DIR", str(tmp_path))
    monkeypatch.setenv("LLM_PROVIDER", "dashscope")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    get_settings.cache_clear()
    from app.services import knowledge_assistant

    monkeypatch.setattr(
        knowledge_assistant,
        "_call_model",
        lambda *args, **kwargs: {
            "answer": "建议先学习测试城市博物馆及入口知识卡。",
            "clarification_required": False,
            "recommendations": [
                {"id": "PBC-999", "reason": "不存在的编号"},
                {"id": "PBC-001", "reason": "类型与城市场景匹配"},
                {"id": "KC-BEG-001", "reason": "补充入口组织原理"},
            ],
        },
    )
    init_db()
    conversation_id = str(uuid4())
    request = {
        "conversation_id": conversation_id,
        "tool": "case_recommendation",
        "message": "推荐城市博物馆入口案例",
        "context": {"view": "overview", "main_tab": "all", "category": "全部"},
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/knowledge/assistant/chat", json=request)
        saved = await client.get(f"/api/knowledge/assistant/conversations/{conversation_id}/messages")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["recommendations"]] == ["PBC-001", "KC-BEG-001"]
    assert response.json()["ui_action"] == "show_assistant_results"
    assert saved.status_code == 200
    assert [item["role"] for item in saved.json()] == ["user", "assistant"]
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_knowledge_assistant_rejects_mock_model(tmp_path, monkeypatch):
    """确认演示模型不会伪造知识助手成功回答。"""
    monkeypatch.setenv("WIKI_DIR", str(tmp_path))
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    get_settings.cache_clear()
    init_db()
    conversation_id = str(uuid4())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/knowledge/assistant/chat", json={
            "conversation_id": conversation_id,
            "tool": "knowledge_query",
            "message": "入口应该怎么设计？",
            "context": {"view": "overview", "main_tab": "all", "category": "全部"},
        })
        saved = await client.get(f"/api/knowledge/assistant/conversations/{conversation_id}/messages")
    assert response.status_code == 503
    assert "演示模型" in response.json()["detail"]
    assert [(item["role"], item["content"]) for item in saved.json()] == [("user", "入口应该怎么设计？")]
    get_settings.cache_clear()
