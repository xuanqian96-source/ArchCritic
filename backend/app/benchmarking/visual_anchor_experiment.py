"""建立视觉评分锚点，并以冻结的 C2 专项结果做三案例总分校准测试。"""

from __future__ import annotations

from io import BytesIO
from datetime import datetime
import json
from pathlib import Path
import re
import struct
import subprocess
from typing import Any
import xml.etree.ElementTree as ET
import zlib

from app.agents.scheme_review import (
    VisualScoreCalibrationAgent,
    build_scheme_overall_report,
)
from app.benchmarking.runner import (
    build_context,
    calculate_prompt_fingerprint,
    prepare_model_urls,
)
from app.llm.client import get_llm_client
from app.scoring.visual_anchors import (
    collect_visual_anchor_files,
    load_visual_anchor_manifest,
    sha256_file,
    visual_anchor_fingerprint,
)


IDENTITY_LABEL_PATTERN = re.compile(
    r"(?:学生|姓名|学号|指导老师|指导教师|教师|成绩)\s*[：:]?"
)


ANCHOR_SELECTIONS = (
    {
        "anchor_id": "A-L71",
        "band": "low",
        "teacher_score": 71,
        "display_title": "叠影生长——南头古城记忆档案馆",
        "source": "标注基准集与实验数据与论文/75-/71-2023100081王璞玉71.pdf",
    },
    {
        "anchor_id": "A-L73",
        "band": "low",
        "teacher_score": 73,
        "display_title": "圳巷茶盾——南头古城空间记忆建筑",
        "source": "标注基准集与实验数据与论文/75-/73-图纸.pdf",
    },
    {
        "anchor_id": "A-L74",
        "band": "low",
        "teacher_score": 74,
        "display_title": "巷·忆展览馆——古城记忆档案库",
        "source": "标注基准集与实验数据与论文/75-/74-2023100020聂山栗74.pdf",
        "manual_redactions": [(0.0, 0.94, 1.0, 1.0)],
    },
    {
        "anchor_id": "A-M79",
        "band": "middle",
        "teacher_score": 79,
        "display_title": "植萃博物馆",
        "source": "标注基准集与实验数据与论文/76-85/79-李尚兰-2023100015-植萃.pdf",
    },
    {
        "anchor_id": "A-M80",
        "band": "middle",
        "teacher_score": 80,
        "display_title": "味忆巷坊·早餐时光匣",
        "source": "标注基准集与实验数据与论文/76-85/80-图纸.pdf",
    },
    {
        "anchor_id": "A-M82",
        "band": "middle",
        "teacher_score": 82,
        "display_title": "拓扑方间——南头古城记忆档案库",
        "source": "标注基准集与实验数据与论文/76-85/82-2023100010彭政宇82.pdf",
    },
    {
        "anchor_id": "A-M84",
        "band": "middle",
        "teacher_score": 84,
        "display_title": "博弈档案馆——南头古城记忆档案馆",
        "source": "标注基准集与实验数据与论文/76-85/84-2023100042朱慧桥84.pdf",
    },
    {
        "anchor_id": "A-H86",
        "band": "high",
        "teacher_score": 86,
        "display_title": "转换·交织——南头古城记忆档案馆",
        "source": "标注基准集与实验数据与论文/86-94/86-2023100030-付容荣86.pdf",
    },
    {
        "anchor_id": "A-H88",
        "band": "high",
        "teacher_score": 88,
        "display_title": "浣·焕——南头古城记忆档案库",
        "source": "标注基准集与实验数据与论文/86-94/88-曾安淇2023100079《浣·焕》.pdf",
    },
    {
        "anchor_id": "A-H90",
        "band": "high",
        "teacher_score": 90,
        "display_title": "水廊——南头古城记忆档案库",
        "source": "标注基准集与实验数据与论文/86-94/90-2023105011-肖子熙-大二下图纸.pdf",
    },
    {
        "anchor_id": "A-H93",
        "band": "high",
        "teacher_score": 93,
        "display_title": "绿野逸境——南头古城记忆档案库",
        "source": "标注基准集与实验数据与论文/86-94/93-2023100016 胡润酥 终期图纸.pdf",
    },
)


def build_visual_anchor_set(workspace_root: Path, target_root: Path) -> dict[str, Any]:
    """从三个原始分档生成匿名代表性展板、公开清单和内部来源审计。"""
    ensure_resumable_build_target(target_root)
    manifest_items = []
    audit_items = []
    for selection in ANCHOR_SELECTIONS:
        source = (workspace_root / str(selection["source"])).resolve()
        if not source.is_file():
            raise FileNotFoundError(f"锚点源图纸不存在：{source}")
        band = str(selection["band"])
        image_dir = target_root / "images" / band
        image_dir.mkdir(parents=True, exist_ok=True)
        image_path = image_dir / f"{selection['anchor_id']}.png"
        page = extract_first_page_sensitive_boxes(source)
        if image_path.is_file():
            boxes = page["boxes"]
        else:
            render_first_board(source, image_path)
            boxes = redact_png_boxes(
                image_path,
                page["width"],
                page["height"],
                page["boxes"],
            )
            redact_png_relative_boxes(
                image_path,
                list(selection.get("manual_redactions") or []),
            )
        manifest_items.append(
            {
                "anchor_id": selection["anchor_id"],
                "band": band,
                "teacher_score": selection["teacher_score"],
                "display_title": selection["display_title"],
                "selection_note": "同类博物馆或记忆档案馆课程作品的代表性总览展板",
                "representative_page": 1,
                "image_path": str(image_path.relative_to(target_root)).replace("\\", "/"),
                "mime_type": "image/png",
                "image_sha256": sha256_file(image_path),
                "identity_redaction_count": len(boxes)
                + len(selection.get("manual_redactions") or []),
            }
        )
        audit_items.append(
            {
                "anchor_id": selection["anchor_id"],
                "source_path": str(source.relative_to(workspace_root)).replace("\\", "/"),
                "source_sha256": sha256_file(source),
                "source_page": 1,
            }
        )
    manifest = {
        "version": 1,
        "name": "ArchCritic 建筑设计课视觉评分锚点集",
        "created_at": now_text(),
        "purpose": "供最终综合评审 Agent 先判断档位、再在档内定位总分",
        "contains_test_cases": False,
        "representative_board_only": True,
        "anchors": manifest_items,
    }
    write_json(target_root / "manifest.json", manifest)
    write_json(
        target_root / "SOURCE_AUDIT.json",
        {
            "created_at": now_text(),
            "selection_count": len(audit_items),
            "sources": audit_items,
        },
    )
    (target_root / "README.md").write_text(
        build_anchor_readme(manifest_items),
        encoding="utf-8",
    )
    load_visual_anchor_manifest(target_root)
    return manifest


def repair_visual_anchor_redactions(
    workspace_root: Path,
    anchor_root: Path,
) -> dict[str, Any]:
    """补做清单中声明的人工遮挡，并刷新图片哈希和审计数量。"""
    manifest = load_visual_anchor_manifest(anchor_root)
    items_by_id = {
        str(item["anchor_id"]): item for item in manifest["anchors"]
    }
    repaired = 0
    for selection in ANCHOR_SELECTIONS:
        manual_boxes = list(selection.get("manual_redactions") or [])
        if not manual_boxes:
            continue
        item = items_by_id[str(selection["anchor_id"])]
        image_path = anchor_root / str(item["image_path"])
        redact_png_relative_boxes(image_path, manual_boxes)
        source = (workspace_root / str(selection["source"])).resolve()
        automatic_count = len(extract_first_page_sensitive_boxes(source)["boxes"])
        item["identity_redaction_count"] = automatic_count + len(manual_boxes)
        item["image_sha256"] = sha256_file(image_path)
        repaired += 1
    write_json(anchor_root / "manifest.json", manifest)
    load_visual_anchor_manifest(anchor_root)
    return {"repaired_count": repaired, "anchor_count": len(manifest["anchors"])}


def run_visual_anchor_pilot(
    input_root: Path,
    c2_results_root: Path,
    anchor_root: Path,
    output_root: Path,
    provider: str,
    model: str,
    case_ids: tuple[str, ...],
) -> dict[str, Any]:
    """复用冻结 C2 专项结果，只替换最终总分步骤，避免混入其他变量。"""
    index = read_json(input_root / "index.json")
    selected = [
        item for item in index["cases"] if str(item["case_id"]) in set(case_ids)
    ]
    if {str(item["case_id"]) for item in selected} != set(case_ids):
        raise ValueError("视觉锚点测试案例不完整。")
    taskbook_name = str(index.get("taskbook_file") or "")
    taskbook = read_json(input_root / taskbook_name) if taskbook_name else {}
    extra_files = collect_visual_anchor_files(anchor_root)
    upload_cache = prepare_model_urls(
        input_root,
        selected,
        provider,
        model,
        extra_files=extra_files,
    )
    output_root.mkdir(parents=True, exist_ok=True)
    manifest_path = output_root / "run_manifest.json"
    expected_manifest = {
        "protocol": "visual-anchor-final-agent-pilot-v2",
        "provider": provider,
        "model": model,
        "case_ids": list(case_ids),
        "anchor_fingerprint": visual_anchor_fingerprint(anchor_root),
        "prompt_fingerprint": calculate_prompt_fingerprint("visual_anchor_v1"),
        "contains_test_teacher_scores": False,
        "reuses_frozen_c2_specialists": True,
        "separates_feedback_and_score_calibration": True,
    }
    if manifest_path.exists():
        current = read_json(manifest_path)
        if any(current.get(key) != value for key, value in expected_manifest.items()):
            raise ValueError("已有视觉锚点测试清单与本次配置不一致，不得混合续跑。")
    else:
        write_json(
            manifest_path,
            {**expected_manifest, "started_at": now_text(), "run_status": "running"},
        )

    completed = []
    failures = []
    by_case = {str(item["case_id"]): item for item in selected}
    for case_id in case_ids:
        output_path = output_root / f"{case_id}.json"
        if output_path.is_file():
            completed.append(case_id)
            continue
        try:
            result = run_visual_anchor_case(
                input_root,
                by_case[case_id],
                c2_results_root / f"{case_id}.json",
                taskbook,
                anchor_root,
                upload_cache,
                provider,
                model,
            )
            write_json(output_path, result)
            completed.append(case_id)
            print(
                f"{case_id} 视觉锚点校准完成：{result['report']['overall_score']}",
                flush=True,
            )
        except Exception as exc:  # noqa: BLE001 - 保留单案例技术失败
            failures.append(case_id)
            write_json(
                output_root / "errors" / f"{case_id}.json",
                {
                    "case_id": case_id,
                    "error_type": type(exc).__name__,
                    "message": str(exc)[:1000],
                    "failed_at": now_text(),
                },
            )
            print(f"{case_id} 视觉锚点校准失败：{type(exc).__name__}", flush=True)

    manifest = {
        **expected_manifest,
        "started_at": read_json(manifest_path).get("started_at"),
        "completed_at": now_text(),
        "successful_count": len(completed),
        "failure_count": len(failures),
        "run_status": "completed" if len(completed) == len(case_ids) else "failed",
    }
    write_json(manifest_path, manifest)
    return manifest


def run_visual_anchor_case(
    input_root: Path,
    index_item: dict,
    frozen_c2_path: Path,
    taskbook: dict,
    anchor_root: Path,
    upload_cache: dict[str, str],
    provider: str,
    model: str,
) -> dict[str, Any]:
    """对一份案例只重跑最终综合评审 Agent，不接触该案例教师分数。"""
    input_file = input_root / str(index_item["input_file"])
    case_input = read_json(input_file)
    frozen_c2 = read_json(frozen_c2_path)
    specialists = [
        item
        for item in frozen_c2["report"]["agent_evaluations"]
        if item.get("agent_type") != "review_agent"
    ]
    context = build_context(
        case_input,
        input_file.parent,
        upload_cache,
        provider,
        taskbook,
        "visual_anchor_v1",
        None,
        False,
        anchor_root,
    )
    llm_client = get_llm_client(provider, model)
    calibration = VisualScoreCalibrationAgent(llm_client).run(
        context,
        specialists,
        llm_client.agent_timeout_seconds,
    )
    baseline_report = frozen_c2["report"]
    synthesis = {
        "summary": baseline_report["summary"],
        "must_fix": baseline_report["must_fix"],
        "should_improve": baseline_report["should_improve"],
        "optional_improvements": baseline_report["optional_improvements"],
        "strengths": baseline_report["strengths"],
        "score_calibration": calibration,
    }
    report = build_scheme_overall_report(synthesis, specialists, context)
    return {
        "case_id": str(case_input["case_id"]),
        "provider": provider,
        "model": model,
        "completed_at": now_text(),
        "contains_test_teacher_score": False,
        "baseline_c2_report_sha256": sha256_file(frozen_c2_path),
        "anchor_fingerprint": visual_anchor_fingerprint(anchor_root),
        "report": report,
    }


def analyze_visual_anchor_pilot(
    output_root: Path,
    c2_results_root: Path,
    private_answers_file: Path,
    case_ids: tuple[str, ...],
) -> dict[str, Any]:
    """模型结果完成后再解封教师分数，比较旧 C2 与视觉校准总分。"""
    truth = {
        str(item["case_id"]): item
        for item in read_json(private_answers_file)["cases"]
    }
    rows = []
    for case_id in case_ids:
        result = read_json(output_root / f"{case_id}.json")
        baseline = read_json(c2_results_root / f"{case_id}.json")
        teacher_score = float(truth[case_id]["teacher_score"])
        before = float(baseline["report"]["overall_score"])
        after = float(result["report"]["overall_score"])
        scoring = result["report"]["evaluation_context"]["scoring"]
        rows.append(
            {
                "case_id": case_id,
                "teacher_score": teacher_score,
                "c2_before": before,
                "visual_anchor_after": after,
                "absolute_error_before": round(abs(before - teacher_score), 2),
                "absolute_error_after": round(abs(after - teacher_score), 2),
                "predicted_band": scoring.get("band", ""),
                "nearest_anchor_ids": scoring.get("nearest_anchor_ids", []),
                "confidence": scoring.get("confidence", ""),
            }
        )
    before_mae = sum(item["absolute_error_before"] for item in rows) / len(rows)
    after_mae = sum(item["absolute_error_after"] for item in rows) / len(rows)
    before_scores = [item["c2_before"] for item in rows]
    after_scores = [item["visual_anchor_after"] for item in rows]
    summary = {
        "version": 1,
        "created_at": now_text(),
        "case_count": len(rows),
        "rows": rows,
        "c2_before_mae": round(before_mae, 2),
        "visual_anchor_after_mae": round(after_mae, 2),
        "mae_improvement": round(before_mae - after_mae, 2),
        "c2_before_score_range": round(max(before_scores) - min(before_scores), 2),
        "visual_anchor_after_score_range": round(
            max(after_scores) - min(after_scores), 2
        ),
        "teacher_order_preserved": score_order_matches(rows),
        "improved_case_count": sum(
            item["absolute_error_after"] < item["absolute_error_before"]
            for item in rows
        ),
    }
    write_json(output_root / "analysis.json", summary)
    (output_root / "测试结果.md").write_text(
        build_analysis_markdown(summary),
        encoding="utf-8",
    )
    return summary


def render_first_board(source: Path, target: Path) -> None:
    """把 PDF 第一张总览展板渲染为高分辨率 PNG。"""
    target.parent.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        [
            "pdftoppm",
            "-f",
            "1",
            "-l",
            "1",
            "-singlefile",
            "-png",
            "-scale-to",
            "4000",
            str(source),
            str(target.with_suffix("")),
        ],
        capture_output=True,
        check=False,
        timeout=300,
    )
    if completed.returncode != 0 or not target.is_file():
        raise RuntimeError(f"锚点展板渲染失败：{source.name}")


def extract_first_page_sensitive_boxes(source: Path) -> dict[str, Any]:
    """用 PDF 文字坐标定位第一张展板的身份和成绩栏。"""
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
    page = root.find(".//x:page", namespace)
    if page is None:
        raise ValueError(f"PDF 没有可解析页面：{source.name}")
    boxes = []
    for line in page.findall(".//x:line", namespace):
        text = "".join(
            (word.text or "").strip()
            for word in line.findall("./x:word", namespace)
        )
        compact = re.sub(r"\s+", "", text)
        if not IDENTITY_LABEL_PATTERN.search(compact):
            continue
        boxes.append(
            {
                "x_min": float(line.attrib["xMin"]),
                "y_min": float(line.attrib["yMin"]),
                "x_max": float(line.attrib["xMax"]),
                "y_max": float(line.attrib["yMax"]),
                "text": "身份或成绩栏",
            }
        )
    return {
        "width": float(page.attrib["width"]),
        "height": float(page.attrib["height"]),
        "boxes": boxes,
    }


def redact_png_boxes(
    path: Path,
    page_width: float,
    page_height: float,
    boxes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """仅用标准库解码 PNG 扫描线，并把身份文字框覆盖为白色。"""
    width, height, color_type, rows = read_png_rows(path)
    channels = 3 if color_type == 2 else 4
    padding = max(8, round(min(width, height) * 0.003))
    for item in boxes:
        x0 = max(0, round(item["x_min"] * width / page_width) - padding)
        y0 = max(0, round(item["y_min"] * height / page_height) - padding)
        x1 = min(width, round(item["x_max"] * width / page_width) + padding)
        y1 = min(height, round(item["y_max"] * height / page_height) + padding)
        for row_index in range(y0, y1):
            row = rows[row_index]
            for column in range(x0, x1):
                offset = column * channels
                row[offset : offset + 3] = b"\xff\xff\xff"
                if channels == 4:
                    row[offset + 3] = 255
    write_png_rows(path, width, height, color_type, rows)
    return boxes


def redact_png_relative_boxes(
    path: Path,
    boxes: list[tuple[float, float, float, float]],
) -> None:
    """按图片宽高比例遮挡无法从 PDF 文字层识别的身份栏。"""
    if not boxes:
        return
    width, height, color_type, rows = read_png_rows(path)
    channels = 3 if color_type == 2 else 4
    for left, top, right, bottom in boxes:
        x0 = max(0, round(left * width))
        y0 = max(0, round(top * height))
        x1 = min(width, round(right * width))
        y1 = min(height, round(bottom * height))
        for row_index in range(y0, y1):
            row = rows[row_index]
            for column in range(x0, x1):
                offset = column * channels
                row[offset : offset + 3] = b"\xff\xff\xff"
                if channels == 4:
                    row[offset + 3] = 255
    write_png_rows(path, width, height, color_type, rows)


def read_png_rows(path: Path) -> tuple[int, int, int, list[bytearray]]:
    """读取 8 位 RGB/RGBA PNG，并还原每行过滤器。"""
    data = path.read_bytes()
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError(f"不是有效 PNG：{path.name}")
    chunks = parse_png_chunks(data)
    ihdr = next(payload for kind, payload in chunks if kind == b"IHDR")
    width, height, bit_depth, color_type, _, _, interlace = struct.unpack(
        ">IIBBBBB", ihdr
    )
    if bit_depth != 8 or color_type not in {2, 6} or interlace != 0:
        raise ValueError("锚点 PNG 必须是非交错 8 位 RGB 或 RGBA。")
    channels = 3 if color_type == 2 else 4
    raw = zlib.decompress(
        b"".join(payload for kind, payload in chunks if kind == b"IDAT")
    )
    stride = width * channels
    rows = []
    previous = bytearray(stride)
    offset = 0
    for _ in range(height):
        filter_type = raw[offset]
        encoded = bytearray(raw[offset + 1 : offset + 1 + stride])
        row = unfilter_png_row(encoded, previous, channels, filter_type)
        rows.append(row)
        previous = row
        offset += stride + 1
    return width, height, color_type, rows


def unfilter_png_row(
    encoded: bytearray,
    previous: bytearray,
    channels: int,
    filter_type: int,
) -> bytearray:
    """还原 PNG 的 None/Sub/Up/Average/Paeth 行过滤。"""
    row = bytearray(len(encoded))
    for index, value in enumerate(encoded):
        left = row[index - channels] if index >= channels else 0
        up = previous[index]
        upper_left = previous[index - channels] if index >= channels else 0
        if filter_type == 0:
            predictor = 0
        elif filter_type == 1:
            predictor = left
        elif filter_type == 2:
            predictor = up
        elif filter_type == 3:
            predictor = (left + up) // 2
        elif filter_type == 4:
            predictor = paeth_predictor(left, up, upper_left)
        else:
            raise ValueError(f"不支持的 PNG 过滤器：{filter_type}")
        row[index] = (value + predictor) & 0xFF
    return row


def paeth_predictor(left: int, up: int, upper_left: int) -> int:
    """实现 PNG Paeth 预测器。"""
    estimate = left + up - upper_left
    distances = (
        abs(estimate - left),
        abs(estimate - up),
        abs(estimate - upper_left),
    )
    if distances[0] <= distances[1] and distances[0] <= distances[2]:
        return left
    if distances[1] <= distances[2]:
        return up
    return upper_left


def write_png_rows(
    path: Path,
    width: int,
    height: int,
    color_type: int,
    rows: list[bytearray],
) -> None:
    """以无行过滤方式重新编码 PNG，保留完整分辨率。"""
    raw = b"".join(b"\x00" + bytes(row) for row in rows)
    ihdr = struct.pack(">IIBBBBB", width, height, 8, color_type, 0, 0, 0)
    output = b"\x89PNG\r\n\x1a\n"
    output += make_png_chunk(b"IHDR", ihdr)
    output += make_png_chunk(b"IDAT", zlib.compress(raw, level=6))
    output += make_png_chunk(b"IEND", b"")
    path.write_bytes(output)


def parse_png_chunks(data: bytes) -> list[tuple[bytes, bytes]]:
    """解析 PNG 数据块。"""
    chunks = []
    offset = 8
    while offset < len(data):
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        kind = data[offset + 4 : offset + 8]
        payload = data[offset + 8 : offset + 8 + length]
        chunks.append((kind, payload))
        offset += 12 + length
        if kind == b"IEND":
            break
    return chunks


def make_png_chunk(kind: bytes, payload: bytes) -> bytes:
    """构造带 CRC 的 PNG 数据块。"""
    checksum = zlib.crc32(kind)
    checksum = zlib.crc32(payload, checksum) & 0xFFFFFFFF
    return (
        struct.pack(">I", len(payload))
        + kind
        + payload
        + struct.pack(">I", checksum)
    )


def build_anchor_readme(items: list[dict[str, Any]]) -> str:
    """生成供研究者复核的锚点集说明。"""
    rows = "\n".join(
        f"| {item['anchor_id']} | {item['band']} | "
        f"{item['teacher_score']} | {item['display_title']} |"
        for item in items
    )
    return f"""# ArchCritic 建筑设计课视觉评分锚点集

本锚点集用于最终综合评审 Agent 的课程尺度校准：先比较当前作品与低、中、高档匿名代表作品，再在档内确定总分。它不是模型训练集，也不替代教师评分。

## 选取规则

- 仅选博物馆、记忆档案馆或任务要求高度接近的课程作品。
- 与九份正式测试样本按源文件哈希隔离，不包含测试样本。
- 低档 3 份、中档 4 份、高档 4 份，覆盖各档内部不同分数位置。
- 每份只保留第一张代表性总览展板，以控制多模态上下文；姓名、学号、教师和图面成绩栏已遮挡。
- 教师原始成绩通过清单明确提供给最终 Agent，不依赖文件名猜测。

## 锚点目录

| 锚点编号 | 分档 | 教师原始成绩 | 匿名题名 |
|---|---|---:|---|
{rows}

## 使用边界

锚点只用于总分尺度定位，不向专项 Agent 提供，也不能作为当前作品问题清单的答案。正式评价应记录最近锚点、比较依据、档位、置信度和校准后的总分。
"""


def build_analysis_markdown(summary: dict[str, Any]) -> str:
    """生成三案例校准前后对照表。"""
    rows = "\n".join(
        f"| {item['case_id']} | {item['teacher_score']:.1f} | "
        f"{item['c2_before']:.1f} | {item['visual_anchor_after']:.1f} | "
        f"{item['absolute_error_before']:.1f} | "
        f"{item['absolute_error_after']:.1f} | {item['predicted_band']} |"
        for item in summary["rows"]
    )
    return f"""# 视觉评分锚点三案例测试结果

本测试复用已冻结 C2 的五个专项 Agent 结果，只替换最终综合评审的总分生成步骤，因此主要变量是视觉锚点校准。

| 案例 | 教师分 | 原 C2 | 锚点校准后 | 原绝对误差 | 新绝对误差 | 预测档位 |
|---|---:|---:|---:|---:|---:|---|
{rows}

- 原 C2 三案例 MAE：{summary['c2_before_mae']:.2f}
- 锚点校准后三案例 MAE：{summary['visual_anchor_after_mae']:.2f}
- MAE 改善：{summary['mae_improvement']:.2f}
- 原 C2 评分跨度：{summary['c2_before_score_range']:.2f}
- 锚点校准后评分跨度：{summary['visual_anchor_after_score_range']:.2f}
- 改善案例数：{summary['improved_case_count']}/{summary['case_count']}
- 是否保持教师高中低排序：{'是' if summary['teacher_order_preserved'] else '否'}

该结果只用于验证评分架构方向，样本量为 3，不能替代完整独立测试。
"""


def score_order_matches(rows: list[dict[str, Any]]) -> bool:
    """判断模型分数是否保持三份教师成绩的严格顺序。"""
    ordered = sorted(rows, key=lambda item: item["teacher_score"])
    model_scores = [item["visual_anchor_after"] for item in ordered]
    return all(left < right for left, right in zip(model_scores, model_scores[1:]))


def ensure_resumable_build_target(path: Path) -> None:
    """允许续建未完成目录，但已有正式清单时禁止覆盖。"""
    if (path / "manifest.json").exists():
        raise ValueError(f"视觉锚点集已经完成，不得覆盖：{path}")
    path.mkdir(parents=True, exist_ok=True)


def read_json(path: Path) -> dict[str, Any]:
    """读取 UTF-8 JSON。"""
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: dict[str, Any]) -> None:
    """写入 UTF-8 JSON。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def now_text() -> str:
    """返回带时区的审计时间。"""
    return datetime.now().astimezone().isoformat(timespec="seconds")
