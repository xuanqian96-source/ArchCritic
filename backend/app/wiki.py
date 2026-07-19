"""读取和检索本地 Wiki 知识库，供评图报告追溯依据使用。"""

from pathlib import Path
import re
from urllib.parse import quote

from .governed_wiki import collect_governed_references


STAGE_ALIASES = {
    "concept": "概念阶段",
    "方案": "方案阶段",
    "scheme": "方案阶段",
    "drawing": "图纸阶段",
    "图纸": "图纸阶段",
}
APPROVED_CONTENT_STATUSES = {"approved", "已审核", "审核通过", "已通过", "正式"}


def resolve_stage(design_stage: str) -> str:
    """把前端阶段名称统一成 Wiki 目录名称。"""
    normalized_stage = design_stage.strip()
    for keyword, stage_name in STAGE_ALIASES.items():
        if keyword in normalized_stage:
            return stage_name
    return normalized_stage or "方案阶段"


def load_wiki_references(
    wiki_dir: str,
    design_stage: str,
    limit: int = 6,
    query_context: dict | None = None,
) -> list[dict]:
    """从完整 Wiki 中检索当前提交最相关的依据条目。"""
    wiki_root = resolve_wiki_root(wiki_dir)
    stage_name = resolve_stage(design_stage)
    candidates = collect_wiki_candidates(wiki_root, stage_name)
    scored = [
        score_reference(reference, stage_name, query_context or {})
        for reference in candidates
    ]
    ranked = [
        reference
        for score, reference in sorted(
            scored, key=lambda item: (item[0], item[1]["title"]), reverse=True
        )
        if score > 0
    ]
    if not ranked:
        ranked = candidates

    for index, reference in enumerate(ranked[:limit], start=1):
        reference["reference_id"] = f"K{index}"
    return ranked[:limit]


def collect_wiki_candidates(wiki_root: Path, stage_name: str) -> list[dict]:
    """收集 Wiki 中可用于检索的 Markdown 条目。"""
    search_roots = [
        resolve_stage_dir(wiki_root, stage_name),
        wiki_root / "02设计规范笔记",
        wiki_root / "03优秀案例笔记",
        wiki_root / "04常见问题",
    ]
    candidates: list[dict] = []
    seen_paths: set[Path] = set()
    for search_root in search_roots:
        if not search_root.exists():
            continue
        for file_path in sorted(search_root.rglob("*.md")):
            if file_path in seen_paths or should_skip_wiki_file(file_path, wiki_root):
                continue
            content = file_path.read_text(encoding="utf-8")
            if content_is_pending_review(content):
                continue
            references = build_reference_items(file_path, wiki_root, content)
            if references:
                candidates.extend(references)
                seen_paths.add(file_path)
    existing_titles = {item["title"] for item in candidates}
    candidates.extend(
        item
        for item in collect_governed_references(wiki_root, stage_name)
        if item["title"] not in existing_titles
    )
    return candidates


def should_skip_wiki_file(file_path: Path, wiki_root: Path) -> bool:
    """跳过隐藏目录、索引和维护记录，避免干扰模型依据。"""
    relative_parts = file_path.relative_to(wiki_root).parts
    if any(part.startswith(".") for part in relative_parts):
        return True
    ignored_roots = {"01索引", "99维护记录"}
    return bool(relative_parts and relative_parts[0] in ignored_roots)


def content_is_pending_review(content: str) -> bool:
    """有审核字段时仅接收明确通过的内容，未设字段的旧稳定内容保持兼容。"""
    if not content.startswith("---\n"):
        return False
    end = content.find("\n---", 4)
    if end < 0:
        return True
    frontmatter = content[4:end]
    match = re.search(r"(?m)^(?:review_status|status)\s*:\s*['\"]?(.+?)['\"]?\s*$", frontmatter)
    if not match:
        return False
    status = match.group(1).strip().strip("\"'").strip().lower()
    return status not in APPROVED_CONTENT_STATUSES


def resolve_stage_dir(wiki_root: Path, stage_name: str) -> Path:
    """兼容旧测试 Wiki 和新版 Obsidian 知识库目录。"""
    candidates = [
        wiki_root / "评价维度" / stage_name,
        wiki_root / "05评价维度" / stage_name,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def resolve_wiki_root(wiki_dir: str) -> Path:
    """解析 Wiki 目录，兼容从不同工作目录启动后端的情况。"""
    wiki_root = Path(wiki_dir).expanduser().resolve()
    if wiki_root.exists():
        return wiki_root
    project_parent = Path(__file__).resolve().parents[3]
    fallback_root = project_parent / "wiki-test" / "wiki"
    return fallback_root


def build_reference_items(file_path: Path, wiki_root: Path, content: str) -> list[dict]:
    """把一个 Markdown 文件整理成一个或多个知识卡片。"""
    if "04常见问题" in str(file_path):
        problem_items = build_common_problem_items(file_path, wiki_root, content)
        if problem_items:
            return problem_items
    item = build_reference_item(file_path, wiki_root, content)
    return [item] if item else []


def build_common_problem_items(file_path: Path, wiki_root: Path, content: str) -> list[dict]:
    """把常见问题文件按二级标题拆成用户更容易理解的问题卡片。"""
    title = extract_title(content)
    body = strip_frontmatter(content)
    sections = re.split(r"(?m)^##\s+", body)
    items: list[dict] = []
    for section in sections[1:]:
        lines = section.splitlines()
        if not lines:
            continue
        section_title = lines[0].strip()
        section_content = "\n".join(lines[1:]).strip()
        if not section_title or not section_content:
            continue
        card_content = f"## {section_title}\n\n{section_content}"
        excerpt = extract_excerpt(card_content) or next_non_empty_line(
            [line.strip().lstrip("- ") for line in section_content.splitlines()]
        )
        if not excerpt:
            continue
        relative_path = file_path.relative_to(wiki_root)
        items.append(
            {
                "reference_id": "",
                "title": f"{title}｜{section_title}",
                "source_type": "常见问题",
                "excerpt": excerpt,
                "dimension": infer_dimension(relative_path, content),
                "path": str(file_path),
                "content": card_content,
                "display_content": build_display_content("常见问题", card_content),
                "image_urls": extract_image_urls(card_content, wiki_root, file_path.parent),
                "retrieval_text": build_retrieval_text(relative_path, section_title, card_content),
            }
        )
    return items


def build_reference_item(file_path: Path, wiki_root: Path, content: str) -> dict | None:
    """把一个 Markdown 文件整理成前端可显示的知识依据。"""
    title = extract_title(content)
    excerpt = extract_excerpt(content)
    if not title or not excerpt:
        return None

    relative_path = file_path.relative_to(wiki_root)
    return {
        "reference_id": "",
        "title": title,
        "source_type": infer_source_type(file_path),
        "excerpt": excerpt,
        "dimension": infer_dimension(relative_path, content),
        "path": str(file_path),
        "content": strip_frontmatter(content),
        "display_content": build_display_content(infer_source_type(file_path), strip_frontmatter(content)),
        "image_urls": extract_image_urls(content, wiki_root, file_path.parent),
        "retrieval_text": build_retrieval_text(relative_path, title, content),
    }


def build_display_content(source_type: str, content: str) -> str:
    """生成面向用户阅读的精简卡片内容。"""
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    if source_type == "常见问题":
        keep_prefixes = ("## ", "- **典型表现**：", "- **修改策略**：", "- **可引用观点**：")
        return "\n".join(line for line in lines if line.startswith(keep_prefixes))
    if source_type == "案例":
        keep_prefixes = ("# ", "## 基本信息", "## 可借鉴点", "## 评图应用", "- **")
        selected = [line for line in lines if line.startswith(keep_prefixes)]
        return "\n".join(selected[:18]) or "\n".join(lines[:12])
    if source_type == "规范":
        keep_prefixes = ("# ", "## 关键条文", "## 评图应用", "- **", "- ")
        selected = [line for line in lines if line.startswith(keep_prefixes)]
        return "\n".join(selected[:16]) or "\n".join(lines[:10])
    keep_prefixes = ("# ", "## 维度说明", "## 评价重点", "- ")
    selected = [line for line in lines if line.startswith(keep_prefixes)]
    return "\n".join(selected[:18]) or "\n".join(lines[:10])


def extract_image_urls(content: str, wiki_root: Path, current_dir: Path) -> list[dict]:
    """提取 Obsidian 和 Markdown 图片链接，返回前端可访问地址。"""
    image_refs = re.findall(r"!\[\[([^\]]+)\]\]", content)
    image_refs.extend(match[1] for match in re.findall(r"!\[([^\]]*)\]\(([^)]+)\)", content))
    images = []
    for raw_ref in image_refs:
        ref = raw_ref.split("|", 1)[0].strip()
        if not is_image_ref(ref):
            continue
        path = resolve_wiki_asset_path(ref, wiki_root, current_dir)
        if path is None:
            continue
        relative_path = path.relative_to(wiki_root).as_posix()
        images.append(
            {
                "name": path.name,
                "url": f"/wiki-assets/{quote(relative_path)}",
            }
        )
    return images[:8]


def is_image_ref(ref: str) -> bool:
    """判断链接是否为前端可展示的图片。"""
    return Path(ref).suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".gif"}


def resolve_wiki_asset_path(ref: str, wiki_root: Path, current_dir: Path) -> Path | None:
    """把知识库中的相对图片引用解析为实际文件路径。"""
    candidates = [
        (wiki_root / ref).resolve(),
        (current_dir / ref).resolve(),
    ]
    filename = Path(ref).name
    if filename != ref:
        candidates.append((wiki_root / filename).resolve())
    for candidate in candidates:
        if candidate.is_file() and wiki_root.resolve() in candidate.parents:
            return candidate
    matches = list(wiki_root.rglob(filename))
    for match in matches:
        if match.is_file():
            return match.resolve()
    return None


def build_retrieval_text(relative_path: Path, title: str, content: str) -> str:
    """生成用于简单关键词检索的文本。"""
    return normalize_text(f"{relative_path} {title} {strip_frontmatter(content)}")


def score_reference(reference: dict, stage_name: str, query_context: dict) -> tuple[int, dict]:
    """按阶段、建筑类型、评价维度和说明文字给知识卡片打分。"""
    text = reference.get("retrieval_text", "")
    score = 0
    if normalize_text(stage_name) in text:
        score += 8

    building_type = normalize_text(str(query_context.get("building_type", "")))
    if building_type and building_type in text:
        score += 8
    if "公共建筑" in text and ("公共" in building_type or "博物馆" in building_type):
        score += 4

    for keyword in build_query_keywords(query_context):
        normalized_keyword = normalize_text(keyword)
        if normalized_keyword and normalized_keyword in text:
            score += 5 if len(normalized_keyword) >= 3 else 2

    source_type = reference.get("source_type", "")
    if source_type == "评价维度":
        score += 3
    elif source_type in {"规范", "常见问题"}:
        score += 2
    return score, reference


def build_query_keywords(query_context: dict) -> list[str]:
    """从项目上下文中提取用于检索知识库的关键词。"""
    raw_text = " ".join(
        str(query_context.get(key, ""))
        for key in ("project_name", "building_type", "design_stage", "description")
    )
    drawing_types = " ".join(str(item) for item in query_context.get("drawing_types", []))
    base_keywords = [
        "功能与流线",
        "功能分区",
        "流线",
        "入口",
        "门厅",
        "卫生间",
        "车库",
        "地下车库",
        "人车分流",
        "后勤",
        "展厅",
        "博物馆",
        "公共服务",
        "一层平面",
    ]
    extracted = re.findall(r"[\u4e00-\u9fffA-Za-z0-9]{2,}", f"{raw_text} {drawing_types}")
    return [*base_keywords, *extracted]


def normalize_text(value: str) -> str:
    """统一检索文本格式。"""
    return re.sub(r"\s+", "", value.lower())


def infer_dimension(relative_path: Path, content: str) -> str:
    """根据路径和正文判断知识条目所属维度。"""
    parts = relative_path.parts
    if "05评价维度" in parts:
        index = parts.index("05评价维度")
        if len(parts) > index + 2:
            return parts[index + 2].removesuffix(".md")
        if len(parts) > index + 1:
            return parts[index + 1]
    if "评价维度" in parts:
        index = parts.index("评价维度")
        if len(parts) > index + 2:
            return parts[index + 2].removesuffix(".md")
    for dimension in ("功能与流线", "场地与回应", "形式与构图", "结构与可行性", "图面表达"):
        if dimension in content or dimension in str(relative_path):
            return dimension
    return parts[0] if parts else "通用依据"


def strip_frontmatter(content: str) -> str:
    """去掉 Markdown 顶部元数据，保留适合前端卡片展示的正文。"""
    lines = content.splitlines()
    if lines and lines[0].strip() == "---":
        for index, line in enumerate(lines[1:], start=1):
            if line.strip() == "---":
                return "\n".join(lines[index + 1 :]).strip()
    return content.strip()


def extract_title(content: str) -> str:
    """读取 Markdown 一级标题作为条目标题。"""
    for line in content.splitlines():
        stripped_line = line.strip()
        if stripped_line.startswith("# "):
            return stripped_line.removeprefix("# ").strip()
    return ""


def extract_excerpt(content: str) -> str:
    """优先提取可引用观点、评图应用或维度说明。"""
    lines = [line.strip() for line in strip_frontmatter(content).splitlines()]
    for prefix in ("- **可引用观点**：", "- **评图应用**："):
        for line in lines:
            if line.startswith(prefix):
                return line.removeprefix(prefix).strip()

    for index, line in enumerate(lines):
        if line == "## 维度说明":
            return next_non_empty_line(lines[index + 1 :])

    for line in lines:
        if line and not line.startswith("#") and not line.startswith(">"):
            return line.lstrip("- ").strip()
    return ""


def next_non_empty_line(lines: list[str]) -> str:
    """返回列表中的第一行有效文字。"""
    for line in lines:
        if line:
            return line
    return ""


def infer_source_type(file_path: Path) -> str:
    """根据文件路径判断知识来源类型。"""
    path_text = str(file_path)
    if "规范" in path_text:
        return "规范"
    if "案例" in path_text:
        return "案例"
    if "常见问题" in path_text:
        return "常见问题"
    return "评价维度"
