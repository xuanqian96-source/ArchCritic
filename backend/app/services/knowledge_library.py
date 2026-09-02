"""读取最终版 Markdown 知识库，统一支持学习浏览、自测和评图候选检索。"""

from __future__ import annotations

from functools import lru_cache
from io import BytesIO
from pathlib import Path
import posixpath
import re
from time import monotonic
from typing import Any
from urllib.parse import quote

from PIL import Image, ImageOps

from app.wiki import resolve_wiki_root, strip_frontmatter
from app.services.knowledge_taxonomy import (
    CATEGORY_AGENTS,
    DIFFICULTY_LABELS,
    KNOWLEDGE_CATEGORIES,
    build_quiz_item,
    classify_knowledge_card,
)


KNOWLEDGE_ROOT = "03_知识卡片"
CASE_ROOT = "02_建筑案例"
LEVEL_LABELS = {
    "beginner": "入门",
    "advanced": "进阶",
    "master": "研习",
}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
LIBRARY_CACHE_TTL_SECONDS = 300.0
_library_items_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
CASE_HIDDEN_DISPLAY_SECTIONS = {"案例概览", "基本信息", "图纸阅读重点"}
KNOWLEDGE_HIDDEN_DISPLAY_SECTIONS = {"学习层级", "学习目标", "原始 PDF", "原始PDF", "观察或自测任务", "自测任务", "答案要点", "参考答案"}
STANDALONE_ARROWS = {"→", "↓", "⇒", "➜", "->"}
THUMBNAIL_PHOTO_TERMS = {
    "exterior": 100,
    "外观": 100,
    "建筑外形": 100,
    "夜景": 100,
    "鸟瞰": 100,
    "航拍": 100,
    "aerial": 100,
    "facade": 90,
    "场地": 80,
    "城市环境": 80,
    "garden": 80,
    "公园": 80,
    "庭院": 80,
    "内院": 80,
    "entrance": 70,
    "入口": 70,
    "大厅": 70,
    "中庭": 70,
    "interior": 70,
    "室内": 70,
    "展陈": 70,
    "阅览": 70,
    "楼梯": 70,
    "stairs": 70,
    "official_": 40,
    "cc-by": 120,
    "cc_by": 120,
    "cc0": 120,
    "kogl": 120,
}
THUMBNAIL_DRAWING_TERMS = {
    "总平",
    "平面图",
    "剖面",
    "立面图",
    "分析图",
    "示意图",
    "草图",
    "轴测",
    "结构图",
    "节点",
    "大样",
}


def list_library_items(wiki_dir: str) -> list[dict[str, Any]]:
    """读取可见知识卡和案例卡的列表信息。"""
    wiki_root = resolve_wiki_root(wiki_dir)
    items: list[dict[str, Any]] = []
    items.extend(_read_items(wiki_root, wiki_root / KNOWLEDGE_ROOT, "knowledge"))
    items.extend(_read_items(wiki_root, wiki_root / CASE_ROOT, "case"))
    return sorted(items, key=lambda item: (0 if item["kind"] == "knowledge" else 1, item["id"]))


def get_library_item(wiki_dir: str, item_id: str) -> dict[str, Any] | None:
    """按知识卡或案例卡编号读取完整正文。"""
    normalized_id = item_id.strip().upper()
    for item in _get_cached_library_items(wiki_dir):
        if item["id"].upper() != normalized_id:
            continue
        file_path = Path(item.pop("_path"))
        content = file_path.read_text(encoding="utf-8")
        body = strip_frontmatter(content)
        item["content"] = _build_display_content(body, item["kind"])
        item["images"] = _extract_library_images(content, resolve_wiki_root(wiki_dir), file_path.parent)
        return item
    return None


def _build_display_content(body: str, kind: str) -> str:
    """保留原始 Markdown，只为详情页生成统一、连贯的阅读版正文。"""
    hidden_sections = CASE_HIDDEN_DISPLAY_SECTIONS if kind == "case" else KNOWLEDGE_HIDDEN_DISPLAY_SECTIONS
    visible_lines: list[str] = []
    skip_section = False
    for raw_line in body.splitlines():
        line = raw_line.rstrip()
        if kind == "case":
            line = _normalize_case_display_line(line)
            if line is None:
                continue
        line = _normalize_display_punctuation(line)
        heading = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if heading:
            level, title = heading.groups()
            legacy_subheading = level == "##" and _is_legacy_subheading(title)
            normalized_title = _strip_heading_number(title)
            if level == "#":
                continue
            if level == "##":
                skip_section = normalized_title in hidden_sections
                if skip_section:
                    continue
            if skip_section:
                continue
            if legacy_subheading:
                level = "###"
            line = f"{level} {normalized_title}"
        elif skip_section:
            continue
        visible_lines.append(line)
    return _collapse_standalone_arrows(visible_lines).strip()


def _normalize_case_display_line(line: str) -> str | None:
    """修复案例卡中误嵌在列表里的标题，并清理重复的迁移提示。"""
    list_heading = re.match(r"^\s*[-*]\s+(#{2,6})\s+(.+?)\s*$", line)
    if list_heading:
        return f"{list_heading.group(1)} {list_heading.group(2)}"
    if re.match(r"^\s*[-*]\s+\*\*最值得学习", line):
        return re.sub(r"^\s*[-*]\s+", "", line, count=1)
    if re.match(r"^\s*[-*]\s+迁移时同时核对场地、功能、流线、结构和运营条件。?\s*$", line):
        return None
    return line


def _strip_heading_number(title: str) -> str:
    """移除旧案例卡残留的 5.1、6.2 或 1. 等章节编号。"""
    return re.sub(r"^\d+(?:(?:\.\d+)+|[.、])\s*", "", title).strip()


def _is_legacy_subheading(title: str) -> bool:
    """识别旧卡中误用二级标题的编号小节和空间序列分段。"""
    return bool(re.match(r"^(?:\d+(?:(?:\.\d+)+|[.、])\s*|第[一二三四五六七八九十]+段[：:])", title))


def _normalize_display_punctuation(line: str) -> str:
    """清除图片说明等正文遗留的转义斜杠，并统一独立说明的括号。"""
    normalized = re.sub(r"\\([()[\]+&.\-])", r"\1", line)
    caption = re.match(r"^(\s*)[（(](.+)[）)](\s*)$", normalized)
    if caption:
        return f"{caption.group(1)}（{caption.group(2).strip()}）{caption.group(3)}"
    return normalized


def _collapse_standalone_arrows(lines: list[str]) -> str:
    """把被空行拆散的空间路径重新合并成一条可阅读的顺序。"""
    output: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.strip() not in STANDALONE_ARROWS:
            output.append(line)
            index += 1
            continue
        previous = next((position for position in range(len(output) - 1, -1, -1) if output[position].strip()), None)
        following = index + 1
        while following < len(lines) and not lines[following].strip():
            following += 1
        if (
            previous is not None
            and following < len(lines)
            and not _is_structural_markdown(output[previous])
            and not _is_structural_markdown(lines[following])
        ):
            output[previous] = f"{output[previous].rstrip()} → {lines[following].strip()}"
            index = following + 1
            continue
        index += 1
    return "\n".join(output)


def _is_structural_markdown(line: str) -> bool:
    """判断箭头两侧是否为标题、图片、表格等不可拼接的结构。"""
    return line.lstrip().startswith(("#", "!", "|", ">", "- ", "* "))


def build_library_payload(wiki_dir: str) -> dict[str, Any]:
    """汇总列表、数量和前端筛选项。"""
    items = _get_cached_library_items(wiki_dir)
    public_items = [
        {key: value for key, value in item.items() if key != "_path"}
        for item in items
    ]
    knowledge_count = sum(item["kind"] == "knowledge" for item in items)
    case_count = len(items) - knowledge_count
    category_counts: dict[str, int] = {}
    for item in items:
        if item["kind"] == "case":
            category_counts[item["category"]] = category_counts.get(item["category"], 0) + 1
    return {
        "items": public_items,
        "totals": {
            "all": len(items),
            "knowledge": knowledge_count,
            "case": case_count,
        },
        "levels": KNOWLEDGE_CATEGORIES,
        "knowledge_categories": KNOWLEDGE_CATEGORIES,
        "difficulties": list(DIFFICULTY_LABELS.values()),
        "building_types": sorted(category_counts, key=lambda category: (-category_counts[category], category)),
    }


def build_knowledge_quiz(wiki_dir: str) -> dict[str, Any]:
    """从现有知识卡自测章节生成按分类和难度筛选的题库。"""
    questions = []
    for item in _get_cached_library_items(wiki_dir):
        if item["kind"] != "knowledge":
            continue
        content = Path(item["_path"]).read_text(encoding="utf-8")
        question = build_quiz_item(item, strip_frontmatter(content))
        if question:
            questions.append(question)
    return {
        "questions": questions,
        "categories": KNOWLEDGE_CATEGORIES,
        "difficulties": list(DIFFICULTY_LABELS.values()),
    }


def load_library_references(wiki_dir: str, query_context: dict[str, Any], limit: int = 40) -> list[dict[str, Any]]:
    """把当前浏览知识库转换为评图可引用依据，替代旧目录检索。"""
    query = " ".join(str(value) for value in query_context.values()).lower()
    query_tokens = set(re.findall(r"[a-z][a-z0-9_-]{2,}", query))
    for segment in re.findall(r"[\u4e00-\u9fff]{2,}", query):
        query_tokens.add(segment)
        query_tokens.update(segment[index:index + size] for size in (2, 3, 4) for index in range(max(0, len(segment) - size + 1)))
    candidates = []
    for item in _get_cached_library_items(wiki_dir):
        if item["kind"] != "knowledge":
            continue
        searchable = f"{item['title']} {item['excerpt']} {item['category']}".lower()
        keyword_score = sum(token in searchable for token in query_tokens)
        candidates.append((keyword_score, item))
    candidates.sort(key=lambda value: (-value[0], value[1]["id"]))
    # 每个 Agent 对应主题至少保留少量候选，再按项目相关度补足，避免只取编号靠前的卡片。
    selected_candidates = []
    selected_ids: set[str] = set()
    for category in KNOWLEDGE_CATEGORIES:
        for candidate in (value for value in candidates if value[1]["category"] == category):
            if sum(item[1]["category"] == category for item in selected_candidates) >= 3:
                break
            selected_candidates.append(candidate)
            selected_ids.add(candidate[1]["id"])
    selected_candidates.extend(candidate for candidate in candidates if candidate[1]["id"] not in selected_ids)
    references = []
    for _, item in selected_candidates[:limit]:
        detail = get_library_item(wiki_dir, item["id"])
        if detail is None:
            continue
        # 评图仍读取完整原文；详情页隐藏的资料表和自测内容不会丢失。
        raw_content = strip_frontmatter(Path(item["_path"]).read_text(encoding="utf-8"))
        searchable = f"{item['title']} {item['excerpt']} {item['category']}".lower()
        references.append({
            "reference_id": "",
            "library_item_id": item["id"],
            "title": item["title"],
            "source_type": "知识卡",
            "excerpt": item["excerpt"],
            "dimension": item["category"],
            "path": item["_path"],
            "content": raw_content,
            "display_content": item["excerpt"],
            "image_urls": detail.get("images", []),
            "retrieval_text": searchable,
            "applicable_agents": CATEGORY_AGENTS.get(item["category"], []),
        })
    return references


def get_library_items(wiki_dir: str) -> list[dict[str, Any]]:
    """返回知识助手可使用的目录副本，同时保留内部文件位置。"""
    return _get_cached_library_items(wiki_dir)


def _get_cached_library_items(wiki_dir: str) -> list[dict[str, Any]]:
    """短期缓存目录解析结果，避免每次进入页面重复读取全部 Markdown。"""
    cache_key = str(resolve_wiki_root(wiki_dir).resolve())
    now = monotonic()
    cached = _library_items_cache.get(cache_key)
    if cached and now - cached[0] < LIBRARY_CACHE_TTL_SECONDS:
        return [dict(item) for item in cached[1]]
    items = list_library_items(wiki_dir)
    _library_items_cache[cache_key] = (now, items)
    return [dict(item) for item in items]


def _read_items(
    wiki_root: Path,
    root: Path,
    kind: str,
) -> list[dict[str, Any]]:
    """读取一个栏目下的 Markdown，并忽略图片和隐藏维护目录。"""
    if not root.is_dir():
        return []
    items: list[dict[str, Any]] = []
    for file_path in sorted(root.rglob("*.md")):
        relative_parts = file_path.relative_to(root).parts
        if any(part.startswith(".") or part == "_图片" for part in relative_parts):
            continue
        content = file_path.read_text(encoding="utf-8")
        fields = _parse_frontmatter(content)
        item_id = fields.get("card_id") if kind == "knowledge" else fields.get("case_id")
        if not item_id:
            continue
        title = fields.get("title") or _first_heading(content) or file_path.stem
        excerpt = _extract_excerpt(content)
        category = _item_category(kind, file_path, root, fields, title, excerpt)
        related = _list_field(fields, "related_cards")
        related.extend(_list_field(fields, "related_cases"))
        related.extend(_list_field(fields, "related_knowledge_cards"))
        image_count = _image_ref_count(content)
        items.append(
            {
                "id": item_id,
                "title": title,
                "kind": kind,
                "kind_label": "知识卡" if kind == "knowledge" else "建筑案例",
                "category": category,
                "level": fields.get("level", "") if kind == "knowledge" else "",
                "level_label": _level_label(fields, file_path) if kind == "knowledge" else "",
                "excerpt": excerpt,
                "related_ids": list(dict.fromkeys(related)),
                "thumbnail": _first_thumbnail_url(content, wiki_root, file_path.parent),
                "image_count": image_count,
                "_path": str(file_path),
            }
        )
    return items


def _image_ref_count(content: str) -> int:
    """只统计正文图片引用，不在目录阶段访问图片文件。"""
    return sum(
        Path(ref.split("|", 1)[0].strip()).suffix.lower() in IMAGE_SUFFIXES
        for ref in _image_refs(content)
    )


def _image_refs(content: str) -> list[str]:
    """按正文出现顺序读取 Obsidian 和标准 Markdown 图片引用。"""
    pattern = re.compile(r"!\[\[([^\]]+)\]\]|!\[[^\]]*\]\(([^)]+)\)")
    return [match.group(1) or match.group(2) for match in pattern.finditer(content)]


def _safe_relative_image_path(raw_ref: str, wiki_root: Path, current_dir: Path) -> str | None:
    """把图片引用转换为知识库内安全相对路径，不读取图片文件。"""
    ref = raw_ref.split("|", 1)[0].strip().replace("\\", "/")
    if "://" in ref or ref.startswith("/") or Path(ref).suffix.lower() not in IMAGE_SUFFIXES:
        return None
    base = "" if ref.startswith((f"{KNOWLEDGE_ROOT}/", f"{CASE_ROOT}/")) else current_dir.relative_to(wiki_root).as_posix()
    normalized = posixpath.normpath(posixpath.join(base, ref))
    if normalized == ".." or normalized.startswith("../"):
        return None
    return normalized


def _first_thumbnail_url(content: str, wiki_root: Path, current_dir: Path) -> str:
    """为目录优先返回建筑实景，无法识别时再使用首张正文图片。"""
    candidates: list[tuple[int, int, str]] = []
    for index, raw_ref in enumerate(_image_refs(content)):
        relative_path = _safe_relative_image_path(raw_ref, wiki_root, current_dir)
        if relative_path:
            candidates.append((_thumbnail_priority(raw_ref), -index, relative_path))
    if candidates:
        relative_path = max(candidates)[2]
        return f"/api/knowledge/thumbnail/{quote(relative_path)}"
    return ""


def _thumbnail_priority(raw_ref: str) -> int:
    """根据文件名区分实景照片和技术图纸，避免案例封面优先显示平剖面。"""
    name = Path(raw_ref.split("|", 1)[0].strip()).stem.lower()
    if any(term in name for term in THUMBNAIL_DRAWING_TERMS):
        return -100
    return max((score for term, score in THUMBNAIL_PHOTO_TERMS.items() if term in name), default=0)


def render_library_thumbnail(wiki_dir: str, asset_path: str) -> bytes | None:
    """读取知识库内单张图片并生成适合总览卡片的 WebP 缩略图。"""
    wiki_root = resolve_wiki_root(wiki_dir).resolve()
    image_path = (wiki_root / asset_path).resolve()
    if not image_path.is_file() or wiki_root not in image_path.parents or image_path.suffix.lower() not in IMAGE_SUFFIXES:
        return None
    try:
        return _render_thumbnail_cached(str(image_path), image_path.stat().st_mtime_ns)
    except (OSError, ValueError):
        return None


@lru_cache(maxsize=160)
def _render_thumbnail_cached(image_path: str, modified_ns: int) -> bytes:
    """按文件修改时间缓存缩略图，避免列表滚动时重复处理原图。"""
    del modified_ns
    with Image.open(image_path) as source:
        image = ImageOps.exif_transpose(source)
        image.thumbnail((720, 420), Image.Resampling.LANCZOS)
        if image.mode not in {"RGB", "RGBA"}:
            image = image.convert("RGB")
        output = BytesIO()
        image.save(output, format="WEBP", quality=78, method=4)
        return output.getvalue()


def _extract_library_images(
    content: str,
    wiki_root: Path,
    current_dir: Path,
) -> list[dict[str, str]]:
    """按正文顺序匹配图片，并保留其在知识库中的准确路径。"""
    images: list[dict[str, str]] = []
    for raw_ref in _image_refs(content):
        ref = raw_ref.split("|", 1)[0].strip().replace("\\", "/")
        if Path(ref).suffix.lower() not in IMAGE_SUFFIXES:
            continue
        candidates = ((wiki_root / ref).resolve(), (current_dir / ref).resolve())
        path = next(
            (candidate for candidate in candidates if candidate.is_file() and wiki_root.resolve() in candidate.parents),
            None,
        )
        if path is None:
            continue
        relative_path = path.relative_to(wiki_root.resolve()).as_posix()
        images.append({"name": path.name, "url": f"/wiki-assets/{quote(relative_path)}"})
        if len(images) >= 40:
            break
    return images


def _parse_frontmatter(content: str) -> dict[str, str]:
    """读取当前知识库所用的简单 YAML 顶层字段。"""
    if not content.startswith("---\n"):
        return {}
    end = content.find("\n---", 4)
    if end < 0:
        return {}
    fields: dict[str, list[str]] = {}
    current = ""
    for line in content[4:end].splitlines():
        match = re.match(r"^([A-Za-z][A-Za-z0-9_]*)\s*:\s*(.*)$", line)
        if match:
            current = match.group(1)
            fields[current] = [match.group(2)]
        elif current and line.lstrip().startswith("-"):
            fields[current].append(line)
    return {key: "\n".join(value).strip().strip("\"'") for key, value in fields.items()}


def _list_field(fields: dict[str, str], name: str) -> list[str]:
    """读取前置区中的多行列表。"""
    raw = fields.get(name, "")
    return [line.lstrip()[1:].strip().strip("\"'") for line in raw.splitlines() if line.lstrip().startswith("-")]


def _item_category(kind: str, file_path: Path, root: Path, fields: dict[str, str], title: str, excerpt: str) -> str:
    """生成页面用于筛选的中文分类。"""
    if kind == "case":
        folder = file_path.relative_to(root).parts[0]
        if folder != "其他公共建筑":
            return folder
        return _specific_case_category(fields.get("building_type", ""), title)
    return classify_knowledge_card(fields, title, excerpt)


def _specific_case_category(building_type: str, title: str) -> str:
    """把旧“其他公共建筑”目录细分为用户可理解的真实建筑类型。"""
    text = f"{building_type} {title}"
    category_keywords = (
        ("美术馆", ("艺术展馆", "美术馆")),
        ("酒店", ("景德镇川上行", "景仰书院", "酒店")),
        ("学校", ("小学", "学校")),
        ("剧院", ("歌剧", "芭蕾", "剧院")),
        ("文化中心", ("文化艺术中心", "艺术中心")),
        ("改造建筑", ("烟筒插建院",)),
        ("文化空间", ("清堂",)),
    )
    for category, keywords in category_keywords:
        if any(keyword in text for keyword in keywords):
            return category
    return "文化空间"


def _level_label(fields: dict[str, str], file_path: Path) -> str:
    """把机器分级转换为面向学生的栏目名称。"""
    del file_path
    return LEVEL_LABELS.get(fields.get("level", ""), fields.get("level", "") or "未分级")


def _first_heading(content: str) -> str:
    """读取 Markdown 一级标题。"""
    match = re.search(r"(?m)^#\s+(.+)$", strip_frontmatter(content))
    return match.group(1).strip() if match else ""


def _extract_excerpt(content: str) -> str:
    """优先从学习目标、核心原理或案例概览中提取卡片摘要。"""
    body = strip_frontmatter(content)
    for heading in ("学习目标", "核心原理", "案例概览", "核心设计命题"):
        match = re.search(rf"(?ms)^##\s+{re.escape(heading)}\s*\n+(.+?)(?=\n##\s+|\Z)", body)
        if match:
            excerpt = _plain_text(match.group(1))
            if excerpt:
                return excerpt[:150]
    for paragraph in re.split(r"\n\s*\n", body):
        excerpt = _plain_text(paragraph)
        if excerpt and not paragraph.lstrip().startswith("#"):
            return excerpt[:150]
    return ""


def _plain_text(value: str) -> str:
    """去除摘要中的常见 Markdown 标记。"""
    text = re.sub(r"!\[\[[^\]]+\]\]", "", value)
    text = re.sub(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]", lambda match: match.group(2) or match.group(1), text)
    text = re.sub(r"[*_`>#]", "", text)
    text = re.sub(r"(?m)^\s*[-+]\s+", "", text)
    return re.sub(r"\s+", " ", text).strip()
