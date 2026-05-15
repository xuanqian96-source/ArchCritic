"""读取本地 Wiki 知识库文件，供评图报告追溯依据使用。"""

from pathlib import Path


STAGE_ALIASES = {
    "concept": "概念阶段",
    "方案": "方案阶段",
    "scheme": "方案阶段",
    "drawing": "图纸阶段",
    "图纸": "图纸阶段",
}


def resolve_stage(design_stage: str) -> str:
    """把前端阶段名称统一成 Wiki 目录名称。"""
    normalized_stage = design_stage.strip()
    for keyword, stage_name in STAGE_ALIASES.items():
        if keyword in normalized_stage:
            return stage_name
    return normalized_stage or "方案阶段"


def load_wiki_references(wiki_dir: str, design_stage: str, limit: int = 5) -> list[dict]:
    """从 Wiki 中读取当前阶段相关的依据条目。"""
    wiki_root = resolve_wiki_root(wiki_dir)
    stage_name = resolve_stage(design_stage)
    stage_dir = wiki_root / "评价维度" / stage_name
    if not stage_dir.exists():
        return []

    references: list[dict] = []
    for file_path in sorted(stage_dir.rglob("*.md")):
        if len(references) >= limit:
            break
        relative_parts = file_path.relative_to(stage_dir).parts
        if any(part.startswith(".") for part in relative_parts):
            continue

        content = file_path.read_text(encoding="utf-8")
        reference = build_reference_item(file_path, stage_dir, content)
        if reference:
            references.append(reference)
    return references


def resolve_wiki_root(wiki_dir: str) -> Path:
    """解析 Wiki 目录，兼容从不同工作目录启动后端的情况。"""
    wiki_root = Path(wiki_dir).expanduser().resolve()
    if wiki_root.exists():
        return wiki_root
    project_parent = Path(__file__).resolve().parents[3]
    fallback_root = project_parent / "wiki-test" / "wiki"
    return fallback_root


def build_reference_item(file_path: Path, stage_dir: Path, content: str) -> dict | None:
    """把一个 Markdown 文件整理成前端可显示的知识依据。"""
    title = extract_title(content)
    excerpt = extract_excerpt(content)
    if not title or not excerpt:
        return None

    relative_path = file_path.relative_to(stage_dir)
    dimension = relative_path.parts[0] if relative_path.parts else "通用依据"
    return {
        "title": title,
        "source_type": infer_source_type(file_path),
        "excerpt": excerpt,
        "dimension": dimension,
        "path": str(file_path),
    }


def extract_title(content: str) -> str:
    """读取 Markdown 一级标题作为条目标题。"""
    for line in content.splitlines():
        stripped_line = line.strip()
        if stripped_line.startswith("# "):
            return stripped_line.removeprefix("# ").strip()
    return ""


def extract_excerpt(content: str) -> str:
    """优先提取可引用观点、评图应用或维度说明。"""
    lines = [line.strip() for line in content.splitlines()]
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
