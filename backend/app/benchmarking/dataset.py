"""读取本地 Markdown 标注，转换成匿名化评测样本和标准答案。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


AGENT_NAMES = {
    "功能与流线": "function_agent",
    "场地": "site_agent",
    "几何形式": "form_agent",
    "结构": "structure_agent",
    "图面表达": "drawing_agent",
    "综合评审": "review_agent",
}


@dataclass
class BenchmarkCase:
    """保存一份原始标注中可公开输入和不可泄漏答案。"""

    case_id: str
    sample_id: str
    annotation_path: Path
    source_dir: Path
    teacher_score: float
    project_name: str
    building_type: str
    design_stage: str
    description: str
    facts: list[dict]
    must_issues: list[dict]
    optional_issues: list[dict]
    forbidden_issues: list[dict]
    score_ranges: dict[str, dict]
    drawings: list[dict]

    def build_input(self) -> dict:
        """生成不含成绩、学生身份和基准答案的模型输入。"""
        return {
            "case_id": self.case_id,
            "project_name": self.project_name,
            "building_type": self.building_type,
            "grade": "大二",
            "design_stage": self.design_stage,
            "description": self.description,
            "drawings": self.drawings,
        }

    def build_ground_truth(self) -> dict:
        """生成只供评测器读取的标准答案。"""
        return {
            "case_id": self.case_id,
            "sample_id": self.sample_id,
            "teacher_score": self.teacher_score,
            "design_stage": self.design_stage,
            "facts": self.facts,
            "must_issues": self.must_issues,
            "optional_issues": self.optional_issues,
            "forbidden_issues": self.forbidden_issues,
            "score_ranges": self.score_ranges,
        }


def load_benchmark_cases(dataset_root: Path) -> list[BenchmarkCase]:
    """发现并解析基准集目录中的全部样本。"""
    parsed = []
    for source_dir in sorted(path for path in dataset_root.iterdir() if path.is_dir()):
        if not re.search(r"（\d+(?:\.\d+)?分）", source_dir.name):
            continue
        annotation_files = sorted(source_dir.glob("*.md"))
        if not annotation_files:
            continue
        annotation_path = annotation_files[0]
        text = annotation_path.read_text(encoding="utf-8")
        metadata = parse_metadata(text)
        parsed.append((metadata.get("样本编号", source_dir.name), source_dir, annotation_path, text, metadata))

    cases = []
    for index, (_, source_dir, annotation_path, text, metadata) in enumerate(
        sorted(parsed, key=lambda item: item[0]), start=1
    ):
        case_id = f"CASE-{index:03d}"
        cases.append(
            BenchmarkCase(
                case_id=case_id,
                sample_id=metadata.get("样本编号", ""),
                annotation_path=annotation_path,
                source_dir=source_dir,
                teacher_score=parse_teacher_score(source_dir.name),
                project_name=metadata.get("样本名称", "公共文化建筑课程设计"),
                building_type=metadata.get("建筑类型", "公共文化建筑"),
                design_stage=metadata.get("设计阶段", "方案阶段"),
                description=extract_clean_description(text),
                facts=parse_fact_rows(text),
                must_issues=parse_issue_rows(text, "必须识别的问题", "可以识别的问题"),
                optional_issues=parse_issue_rows(text, "可以识别的问题", "不应误报的问题"),
                forbidden_issues=parse_forbidden_rows(text),
                score_ranges=parse_score_ranges(text),
                drawings=parse_drawing_rows(text),
            )
        )
    return cases


def parse_metadata(text: str) -> dict[str, str]:
    """读取样本基本信息表。"""
    rows = parse_markdown_table(extract_section(text, "样本基本信息", "图纸内容清单"))
    return {row[0]: row[1] for row in rows if len(row) >= 2}


def parse_teacher_score(directory_name: str) -> float:
    """从仅供评测器使用的原始目录名中读取教师分数。"""
    match = re.search(r"（(\d+(?:\.\d+)?)分）", directory_name)
    if not match:
        raise ValueError(f"样本目录缺少教师成绩：{directory_name}")
    return float(match.group(1))


def extract_clean_description(text: str) -> str:
    """提取设计说明，去掉标注者对高低分和完成度的判断。"""
    section = extract_section(text, "设计说明概括", "图纸事实标注")
    kept = []
    blocked_words = (
        "适合作为",
        "高分样本",
        "低分样本",
        "中等分样本",
        "基准样本",
        "但从图纸",
        "与第一份相比",
        "主要短板",
        "尚未形成完整",
    )
    for raw_line in section.splitlines():
        line = raw_line.strip().lstrip("- ")
        line = re.sub(r"[*_`]", "", line)
        if not line or line == "---" or any(word in line for word in blocked_words):
            continue
        kept.append(line)
    return "\n".join(kept)[:3000]


def parse_fact_rows(text: str) -> list[dict]:
    """读取图纸事实及其状态和证据。"""
    rows = parse_markdown_table(extract_section(text, "图纸事实标注", "必须识别的问题"))
    return [
        {"item": row[0], "status": row[1], "evidence": row[2]}
        for row in rows
        if len(row) >= 3 and row[0] not in {"事实项", "项目"}
    ]


def parse_issue_rows(text: str, start: str, end: str) -> list[dict]:
    """读取必须问题或可选问题。"""
    rows = parse_markdown_table(extract_section(text, start, end))
    return [
        {"id": row[0], "description": row[1], "agent": row[2], "evidence": row[3]}
        for row in rows
        if len(row) >= 4 and re.fullmatch(r"[MO]-\d+", row[0])
    ]


def parse_forbidden_rows(text: str) -> list[dict]:
    """读取不应误报的判断边界。"""
    section = extract_section(text, "不应误报的问题", "专项评分参考")
    return [
        {"id": row[0], "description": row[1], "reason": row[2]}
        for row in parse_markdown_table(section)
        if len(row) >= 3 and re.fullmatch(r"N-\d+", row[0])
    ]


def parse_score_ranges(text: str) -> dict[str, dict]:
    """读取各 Agent 的人工可接受区间。"""
    result = {}
    section = extract_section(text, "专项评分参考", "缺失信息")
    for row in parse_markdown_table(section):
        if len(row) < 3:
            continue
        match = re.fullmatch(r"(.+?) Agent", row[0])
        range_match = re.search(r"(\d+(?:\.\d+)?)[—-](\d+(?:\.\d+)?)", row[1])
        if not match or not range_match:
            continue
        agent_type = AGENT_NAMES.get(match.group(1))
        if agent_type:
            result[agent_type] = {
                "min": float(range_match.group(1)),
                "max": float(range_match.group(2)),
                "reason": row[2],
            }
    return result


def parse_drawing_rows(text: str) -> list[dict]:
    """读取图纸页清单，并为模型排序选择主类型。"""
    rows = parse_markdown_table(extract_section(text, "图纸内容清单", "设计说明概括"))
    drawings = []
    for row in rows:
        if len(row) < 3 or row[0] in {"页码", "图纸"}:
            continue
        combined = " ".join(row[1:])
        drawings.append(
            {
                "source_label": row[0],
                "drawing_type": infer_drawing_type(combined),
                "description": row[1],
            }
        )
    return drawings


def infer_drawing_type(description: str) -> str:
    """按一页中的主要内容选择系统图纸类型。"""
    for keyword, drawing_type in (
        ("平面", "plan"),
        ("总平", "site"),
        ("场地", "site"),
        ("剖面", "section"),
        ("立面", "elevation"),
        ("效果", "render"),
    ):
        if keyword in description:
            return drawing_type
    return "analysis"


def extract_section(text: str, start_title: str, end_title: str) -> str:
    """按二级标题名称截取 Markdown 正文。"""
    start_match = re.search(rf"(?m)^##\s+(?:\d+\.\s*)?{re.escape(start_title)}\s*$", text)
    if not start_match:
        return ""
    end_match = re.search(
        rf"(?m)^##\s+(?:\d+\.\s*)?{re.escape(end_title)}(?:\s.*)?$",
        text[start_match.end() :],
    )
    end = start_match.end() + end_match.start() if end_match else len(text)
    return text[start_match.end() : end]


def parse_markdown_table(section: str) -> list[list[str]]:
    """把简单 Markdown 表格转换为二维文本数组。"""
    rows = []
    for line in section.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
            continue
        rows.append(cells)
    return rows
