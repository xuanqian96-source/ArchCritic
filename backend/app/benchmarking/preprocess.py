"""生成不含成绩答案的逐页图纸输入，并把标准答案单独保存。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

from app.benchmarking.dataset import BenchmarkCase, load_benchmark_cases
from app.services.taskbooks import (
    build_task_book_summary,
    extract_requirement_lines,
    extract_task_book_text,
)
from app.services.taskbook_rules import build_structured_requirements


def prepare_benchmark(dataset_root: Path, output_root: Path, force: bool = False) -> dict:
    """准备全部样本并返回匿名输入索引。"""
    cases = load_benchmark_cases(dataset_root)
    taskbook = prepare_taskbook(dataset_root)
    inputs_root = output_root / "inputs"
    inputs_root.mkdir(parents=True, exist_ok=True)
    index_items = []
    ground_truth_items = []
    for case in cases:
        input_data = prepare_case(case, inputs_root / case.case_id, force)
        index_items.append(
            {
                "case_id": case.case_id,
                "input_file": f"inputs/{case.case_id}/input.json",
                "drawing_count": len(input_data["drawings"]),
            }
        )
        ground_truth_items.append(case.build_ground_truth())

    index = {
        "version": 2,
        "taskbook_file": "taskbook.json" if taskbook else "",
        "cases": index_items,
    }
    write_json(output_root / "index.json", index)
    write_json(output_root / "ground_truth.json", {"version": 1, "cases": ground_truth_items})
    if taskbook:
        write_json(output_root / "taskbook.json", taskbook)
    return index


def prepare_taskbook(dataset_root: Path) -> dict:
    """读取基准集根目录中的课程任务书，并记录可复核摘要。"""
    candidates = sorted(
        path
        for path in dataset_root.glob("*.pdf")
        if "任务书" in path.name or "教学大纲" in path.name
    )
    if not candidates:
        return {}
    text_parts = []
    hashes = []
    for path in candidates:
        content = path.read_bytes()
        text_parts.append(f"【{path.name}】\n{extract_task_book_text(content, path.suffix)}")
        hashes.append({"file": path.name, "sha256": hashlib.sha256(content).hexdigest()})
    full_text = "\n\n".join(text_parts)
    requirements = extract_requirement_lines(full_text)
    return {
        "source_files": [path.name for path in candidates],
        "source_hashes": hashes,
        "full_text": full_text,
        "summary": build_task_book_summary(full_text, "公共文化建筑"),
        "requirements": requirements,
        "structured_requirements": build_structured_requirements(requirements),
    }


def prepare_case(case: BenchmarkCase, case_root: Path, force: bool) -> dict:
    """拆分一份样本图纸并写入匿名输入配置。"""
    drawings_root = case_root / "drawings"
    drawings_root.mkdir(parents=True, exist_ok=True)
    prepared_paths = prepare_drawing_files(case, drawings_root, force)
    input_data = case.build_input()
    drawing_labels = case.drawings
    input_data["drawings"] = []
    for index, path in enumerate(prepared_paths):
        label = drawing_labels[min(index, len(drawing_labels) - 1)] if drawing_labels else {}
        input_data["drawings"].append(
            {
                "drawing_type": label.get("drawing_type", "analysis"),
                "original_name": path.name,
                "relative_path": f"drawings/{path.name}",
                "mime_type": "image/png" if path.suffix.lower() == ".png" else "image/jpeg",
                "description": label.get("description", "课程设计成果图"),
                "low_resolution": is_low_resolution_source(path),
            }
        )
    write_json(case_root / "input.json", input_data)
    return input_data


def prepare_drawing_files(case: BenchmarkCase, drawings_root: Path, force: bool) -> list[Path]:
    """把 PDF 转成高质量 PNG，并复制原始图片。"""
    sources = sorted((case.source_dir / "图纸").iterdir())
    prepared = []
    board_number = 1
    for source in sources:
        if source.suffix.lower() == ".pdf":
            prefix = drawings_root / "rendered"
            existing = sorted(drawings_root.glob("board_*.png"))
            if force or not existing:
                completed = render_pdf(source, prefix)
                if completed.returncode != 0:
                    raise RuntimeError(f"PDF 拆页失败：{source.name}：{completed.stderr[:200]}")
                for rendered in sorted(drawings_root.glob("rendered-*.png")):
                    target = drawings_root / f"board_{board_number:02d}.png"
                    rendered.replace(target)
                    prepared.append(target)
                    board_number += 1
            else:
                prepared.extend(existing)
                board_number = len(existing) + 1
        elif source.suffix.lower() in {".jpg", ".jpeg", ".png"}:
            suffix = source.suffix.lower()
            target = drawings_root / f"board_{board_number:02d}{suffix}"
            if force or not target.exists():
                shutil.copy2(source, target)
            prepared.append(target)
            board_number += 1
    return sorted(set(prepared))


def render_pdf(source: Path, prefix: Path) -> subprocess.CompletedProcess[str]:
    """按 180 DPI 拆页，并限制异常大画布的最长边，避免无效超大文件。"""
    command = ["pdftoppm", "-png"]
    if has_oversized_page_canvas(source):
        command.extend(["-scale-to", "6000"])
    else:
        command.extend(["-r", "180"])
    command.extend([str(source), str(prefix)])
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )


def has_oversized_page_canvas(source: Path) -> bool:
    """识别页面尺寸异常的 PDF，防止按常规 DPI 生成上亿像素图片。"""
    completed = subprocess.run(
        ["pdfinfo", str(source)],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    match = re.search(r"Page size:\s+([\d.]+)\s+x\s+([\d.]+)\s+pts", completed.stdout)
    return bool(match and max(float(match.group(1)), float(match.group(2))) > 3000)


def is_low_resolution_source(path: Path) -> bool:
    """用文件体积标记明显低清的原始图片，供报告提示风险。"""
    return path.suffix.lower() in {".jpg", ".jpeg"} and path.stat().st_size < 3 * 1024 * 1024


def write_json(path: Path, data: dict) -> None:
    """以 UTF-8 和稳定格式写入评测数据。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
