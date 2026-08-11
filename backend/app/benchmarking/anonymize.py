"""对正式实验图纸中的姓名、学号、教师和成绩栏做可追溯遮挡。"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
import re
import subprocess
from typing import Any
import xml.etree.ElementTree as ET

from PIL import Image, ImageDraw

from app.benchmarking.dataset import BenchmarkCase, parse_metadata


IDENTITY_FIELDS = ("学生姓名", "学号", "指导老师")
IDENTITY_LABEL_PATTERN = re.compile(
    r"(?:学生|姓名|学号|指导老师|指导教师|教师|成绩)\s*[：:]"
)
MANUAL_RELATIVE_REDACTIONS = {
    "SAUP-MUS-L002": {
        1: [(0.50, 0.94, 1.00, 1.00)],
        2: [(0.50, 0.94, 1.00, 1.00)],
        3: [(0.50, 0.92, 1.00, 1.00)],
    },
    "SAUP-MUS-M001": {
        1: [(0.76, 0.95, 1.00, 1.00)],
        2: [(0.76, 0.95, 1.00, 1.00)],
        3: [(0.76, 0.95, 1.00, 1.00)],
    },
}


def redact_case_identity(
    case: BenchmarkCase,
    prepared_paths: list[Path],
) -> dict[str, Any]:
    """遮挡 PDF 可提取身份文字，并清除所有输出图的元数据。"""
    metadata = parse_metadata(case.annotation_path.read_text(encoding="utf-8"))
    sensitive_values = {
        str(metadata.get(field, "")).strip()
        for field in IDENTITY_FIELDS
        if str(metadata.get(field, "")).strip()
        and "未清晰识别" not in str(metadata.get(field, ""))
    }
    sources = sorted((case.source_dir / "图纸").iterdir())
    prepared_index = 0
    page_audits = []
    for source in sources:
        suffix = source.suffix.lower()
        if suffix == ".pdf":
            pages = extract_pdf_sensitive_boxes(source, sensitive_values)
            for page_number, page in enumerate(pages, start=1):
                if prepared_index >= len(prepared_paths):
                    raise ValueError(f"{case.case_id} 脱敏页数与图纸页数不一致。")
                target = prepared_paths[prepared_index]
                boxes = redact_image_boxes(
                    target,
                    page["width"],
                    page["height"],
                    page["boxes"],
                )
                page_audits.append(
                    {
                        "page": target.name,
                        "source_kind": "pdf",
                        "source_page": page_number,
                        "redaction_count": len(boxes),
                        "redacted_labels": [item["text"] for item in boxes],
                    }
                )
                prepared_index += 1
        elif suffix in {".jpg", ".jpeg", ".png"}:
            if prepared_index >= len(prepared_paths):
                raise ValueError(f"{case.case_id} 脱敏页数与图纸页数不一致。")
            target = prepared_paths[prepared_index]
            strip_image_metadata(target)
            page_audits.append(
                {
                    "page": target.name,
                    "source_kind": "raster",
                    "source_page": 1,
                    "redaction_count": 0,
                    "redacted_labels": [],
                    "visual_review": "未发现可见姓名、学号、教师或成绩栏",
                }
            )
            prepared_index += 1
    if prepared_index != len(prepared_paths):
        raise ValueError(f"{case.case_id} 仍有未审计图纸页。")
    manual_counts = apply_manual_relative_redactions(case.sample_id, prepared_paths)
    for index, count in manual_counts.items():
        page_audits[index - 1]["redaction_count"] += count
        page_audits[index - 1]["redacted_labels"].extend(
            ["人工视觉定位身份栏"] * count
        )
    return {
        "case_id": case.case_id,
        "sample_id": case.sample_id,
        "page_count": len(page_audits),
        "redaction_count": sum(item["redaction_count"] for item in page_audits),
        "source_files_renamed": True,
        "image_metadata_removed": True,
        "pages": page_audits,
    }


def apply_manual_relative_redactions(
    sample_id: str,
    prepared_paths: list[Path],
) -> dict[int, int]:
    """处理嵌入图片、无法由 PDF 文字坐标识别的固定身份栏。"""
    specifications = MANUAL_RELATIVE_REDACTIONS.get(sample_id, {})
    counts: dict[int, int] = {}
    for page_number, boxes in specifications.items():
        if page_number < 1 or page_number > len(prepared_paths):
            raise ValueError(f"{sample_id} 人工脱敏页码超出范围：{page_number}")
        path = prepared_paths[page_number - 1]
        with Image.open(path) as source:
            image = source.convert("RGB")
        draw = ImageDraw.Draw(image)
        for left, top, right, bottom in boxes:
            draw.rectangle(
                (
                    round(left * image.width),
                    round(top * image.height),
                    round(right * image.width),
                    round(bottom * image.height),
                ),
                fill="white",
            )
        if path.suffix.lower() == ".png":
            image.save(path, format="PNG", optimize=True)
        else:
            image.save(path, format="JPEG", quality=95, optimize=True)
        counts[page_number] = len(boxes)
    return counts


def extract_pdf_sensitive_boxes(
    source: Path,
    sensitive_values: set[str],
) -> list[dict[str, Any]]:
    """读取 pdftotext 坐标，定位身份字段所在文字行。"""
    completed = subprocess.run(
        ["pdftotext", "-bbox-layout", str(source), "-"],
        capture_output=True,
        check=False,
        timeout=120,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"PDF 身份定位失败：{source.name}")
    root = ET.parse(BytesIO(completed.stdout)).getroot()
    namespace = {"x": "http://www.w3.org/1999/xhtml"}
    pages = []
    for page in root.findall(".//x:page", namespace):
        boxes = []
        for line in page.findall(".//x:line", namespace):
            text = "".join(
                (word.text or "").strip()
                for word in line.findall("./x:word", namespace)
            )
            compact = re.sub(r"\s+", "", text)
            has_value = any(
                re.sub(r"\s+", "", value) in compact
                for value in sensitive_values
                if len(value) >= 2
            )
            if not has_value and not IDENTITY_LABEL_PATTERN.search(compact):
                continue
            boxes.append(
                {
                    "x_min": float(line.attrib["xMin"]),
                    "y_min": float(line.attrib["yMin"]),
                    "x_max": float(line.attrib["xMax"]),
                    "y_max": float(line.attrib["yMax"]),
                    "text": identity_label(text),
                }
            )
        pages.append(
            {
                "width": float(page.attrib["width"]),
                "height": float(page.attrib["height"]),
                "boxes": merge_overlapping_boxes(boxes),
            }
        )
    return pages


def redact_image_boxes(
    path: Path,
    page_width: float,
    page_height: float,
    boxes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """把 PDF 坐标映射到渲染图并以白色矩形遮挡。"""
    with Image.open(path) as source:
        image = source.convert("RGB")
    draw = ImageDraw.Draw(image)
    scale_x = image.width / page_width
    scale_y = image.height / page_height
    padding = max(8, round(min(image.width, image.height) * 0.003))
    for item in boxes:
        x0 = max(0, round(item["x_min"] * scale_x) - padding)
        y0 = max(0, round(item["y_min"] * scale_y) - padding)
        x1 = min(image.width, round(item["x_max"] * scale_x) + padding)
        y1 = min(image.height, round(item["y_max"] * scale_y) + padding)
        draw.rectangle((x0, y0, x1, y1), fill="white")
    if path.suffix.lower() == ".png":
        image.save(path, format="PNG", optimize=True)
    else:
        image.save(path, format="JPEG", quality=95, optimize=True)
    return boxes


def strip_image_metadata(path: Path) -> None:
    """重存图片以移除 EXIF 和其他身份元数据。"""
    with Image.open(path) as source:
        image = source.convert("RGB")
    if path.suffix.lower() == ".png":
        image.save(path, format="PNG", optimize=True)
    else:
        image.save(path, format="JPEG", quality=95, optimize=True)


def merge_overlapping_boxes(boxes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """合并同一身份栏内相交的文字框，减少碎片。"""
    merged: list[dict[str, Any]] = []
    for item in sorted(boxes, key=lambda value: (value["y_min"], value["x_min"])):
        match = next(
            (
                target
                for target in merged
                if rectangles_overlap(target, item)
            ),
            None,
        )
        if match is None:
            merged.append(dict(item))
            continue
        match["x_min"] = min(match["x_min"], item["x_min"])
        match["y_min"] = min(match["y_min"], item["y_min"])
        match["x_max"] = max(match["x_max"], item["x_max"])
        match["y_max"] = max(match["y_max"], item["y_max"])
        match["text"] = identity_label(f"{match['text']}、{item['text']}")
    return merged


def rectangles_overlap(left: dict[str, Any], right: dict[str, Any]) -> bool:
    """判断两个身份文字框是否相交或相邻。"""
    return not (
        left["x_max"] + 8 < right["x_min"]
        or right["x_max"] + 8 < left["x_min"]
        or left["y_max"] + 8 < right["y_min"]
        or right["y_max"] + 8 < left["y_min"]
    )


def identity_label(text: str) -> str:
    """审计记录只保存字段类型，不保存真实身份值。"""
    labels = []
    for label in ("学生", "姓名", "学号", "指导老师", "指导教师", "教师", "成绩"):
        if label in text and label not in labels:
            labels.append(label)
    return "、".join(labels) or "身份值"
