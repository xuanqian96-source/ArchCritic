"""验证知识库浏览接口可以读取最终版目录结构、正文和图片。"""

from pathlib import Path
from urllib.parse import unquote
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from PIL import Image

from app.config import get_settings
from app.database import init_db
from app.main import app
from app.services.knowledge_library import _build_display_content, _first_thumbnail_url, _specific_case_category
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


def test_case_thumbnail_prefers_building_photo(tmp_path):
    """确认技术图先出现时，案例封面仍优先采用后面的建筑实景。"""
    current_dir = tmp_path / "02_建筑案例" / "博物馆"
    content = "\n".join([
        "![[02_建筑案例/_图片/PBC-001/总平面图.jpg]]",
        "![[02_建筑案例/_图片/PBC-001/建筑外形.jpg]]",
    ])
    thumbnail = _first_thumbnail_url(content, tmp_path, current_dir)
    assert unquote(thumbnail).endswith("PBC-001/建筑外形.jpg")


def test_library_detail_builds_consistent_reading_content():
    """确认详情页隐藏后台资料与测试内容，并修复旧编号和断开的箭头。"""
    case_body = r"""# 测试案例

## 案例概览

与详情页导语重复。

## 基本信息

|项目|内容|
|---|---|
|建筑师|测试团队|

## 5.1 场地关系

城市广场

↓

入口雨棚

→

共享大厅

## 6. 功能组织

正文保留。

## 图纸阅读重点

- MEDIA-PBC-001-001

## 可迁移的设计方法

- **最值得学习的不是建筑外形，而是空间组织。**
- ## 1\. 先建立共享核心

问题 → 策略 → 结果。

- 迁移时同时核对场地、功能、流线、结构和运营条件。
"""
    display_case = _build_display_content(case_body, "case")
    assert "案例概览" not in display_case
    assert "基本信息" not in display_case
    assert "|建筑师|" not in display_case
    assert "### 场地关系" in display_case
    assert "### 功能组织" in display_case
    assert "城市广场 → 入口雨棚 → 共享大厅" in display_case
    assert "图纸阅读重点" not in display_case
    assert "MEDIA-PBC-001-001" not in display_case
    assert "- **最值得学习" not in display_case
    assert "**最值得学习的不是建筑外形，而是空间组织。**" in display_case
    assert "### 先建立共享核心" in display_case
    assert "迁移时同时核对" not in display_case

    knowledge_body = """# 测试知识卡

## 核心原理

正文保留。

## 原始 PDF

![[01_原始资料/设计规范/测试规范.pdf]]

## 观察或自测任务

测试题不在详情重复显示。

## 答案要点

答案只供知识测试读取。

## 适用边界

边界保留。
"""
    display_knowledge = _build_display_content(knowledge_body, "knowledge")
    assert "原始 PDF" not in display_knowledge
    assert "测试规范.pdf" not in display_knowledge
    assert "观察或自测任务" not in display_knowledge
    assert "答案只供知识测试读取" not in display_knowledge
    assert "## 适用边界" in display_knowledge

    repeated_level = """# 测试知识卡

## 学习层级

L2 进阶

## 核心原理

正文保留。
"""
    display_level = _build_display_content(repeated_level, "knowledge")
    assert "学习层级" not in display_level
    assert "L2 进阶" not in display_level
    assert "## 核心原理" in display_level

    caption = _build_display_content("![[image.png]]\n\n\\(室内木结构实景\\)", "case")
    assert "\\(" not in caption
    assert "\\)" not in caption
    assert "（室内木结构实景）" in caption


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
