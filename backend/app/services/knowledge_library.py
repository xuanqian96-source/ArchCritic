"""读取最终版 Markdown 知识库，供学习浏览页面展示，不参与正式 AI 评图检索。"""

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
        item["content"] = body
        item["images"] = _extract_library_images(content, resolve_wiki_root(wiki_dir), file_path.parent)
        return item
    return None


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
        "levels": ["入门", "进阶", "研习", "规范应用"],
        "building_types": sorted(category_counts, key=lambda category: (-category_counts[category], category)),
    }


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
        category = _item_category(kind, file_path, root, fields, title)
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
                "excerpt": _extract_excerpt(content),
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
    """为目录返回首张正文图片的缩略图接口地址。"""
    for raw_ref in _image_refs(content):
        relative_path = _safe_relative_image_path(raw_ref, wiki_root, current_dir)
        if relative_path:
            return f"/api/knowledge/thumbnail/{quote(relative_path)}"
    return ""


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


def _item_category(kind: str, file_path: Path, root: Path, fields: dict[str, str], title: str) -> str:
    """生成页面用于筛选的中文分类。"""
    if kind == "case":
        folder = file_path.relative_to(root).parts[0]
        if folder != "其他公共建筑":
            return folder
        return _specific_case_category(fields.get("building_type", ""), title)
    if fields.get("category") == "规范应用" or "规范应用" in file_path.parts:
        return "规范应用"
    return _level_label(fields, file_path)


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
    if fields.get("category") == "规范应用" or "规范应用" in file_path.parts:
        return "规范应用"
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
