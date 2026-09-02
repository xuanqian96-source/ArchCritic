"""生成限量的模型辅助裁切图，供评图输入读取且不改动用户原图。"""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import logging
from pathlib import Path
from tempfile import gettempdir

from PIL import Image, ImageOps

from app.agents.image_payload import build_model_image_data_url
from app.config import get_settings
from app.llm.dashscope_files import DashScopeFileClient
from app.services.uploads import resolve_local_upload


LOGGER = logging.getLogger(__name__)
MAX_MODEL_IMAGES_AFTER_SPLIT = 8
MAX_DERIVED_IMAGES = 4
SPLIT_TYPE_PRIORITY = {"plan": 0, "site": 1, "section": 2, "elevation": 3, "analysis": 4}
REGION_CACHE_ROOT = Path(gettempdir()) / "archcritic-model-regions"
_MODEL_URL_CACHE: dict[tuple[str, int, str], tuple[str, datetime]] = {}


def add_preprocessed_model_drawings(
    context: dict,
    provider: str,
    model: str,
) -> int:
    """识别合成图中的完整分区并补充模型辅助图，返回新增数量。"""
    drawings = context.get("drawings") or []
    available_slots = min(
        MAX_DERIVED_IMAGES,
        max(0, MAX_MODEL_IMAGES_AFTER_SPLIT - len(drawings)),
    )
    if available_slots <= 0:
        return 0

    derived: list[dict] = []
    candidates = sorted(drawings, key=drawing_split_priority)
    for drawing in candidates:
        if len(derived) >= available_slots:
            break
        if drawing_split_priority(drawing) >= 99:
            continue
        file_path = resolve_local_upload(str(drawing.get("file_url", "")))
        if file_path is None or not file_path.is_file():
            continue
        try:
            with Image.open(file_path) as source:
                image = ImageOps.exif_transpose(source).convert("RGB")
                boxes = detect_panel_boxes(image)
                remaining_slots = available_slots - len(derived)
                if len(boxes) > remaining_slots:
                    continue
                prepared_regions = []
                for index, box in enumerate(boxes, start=1):
                    crop_path = save_region_image(image, file_path, box, index)
                    model_url = build_region_model_url(crop_path, provider, model)
                    if not model_url:
                        prepared_regions = []
                        break
                    prepared_regions.append({
                        **drawing,
                        "original_name": f"{drawing.get('original_name', '图纸')} · 自动拆分 {index}/{len(boxes)}",
                        "description": "系统从合成图中识别出的完整图纸分区；评分时同时保留原图作为上下文。",
                        "file_url": "",
                        "model_file_url": model_url,
                        "mime_type": "image/png",
                        "derived_from": drawing.get("original_name", ""),
                    })
                derived.extend(prepared_regions)
        except Exception as exc:
            LOGGER.warning("图纸自动拆分失败，继续使用原图：%s", exc)
    drawings.extend(derived)
    context["drawing_preprocess"] = {
        "original_count": len(drawings) - len(derived),
        "derived_count": len(derived),
        "total_model_images": len(drawings),
    }
    return len(derived)


def drawing_split_priority(drawing: dict) -> int:
    """优先处理平面和技术图纸，避免辅助效果图占用拆分预算。"""
    drawing_type = str(drawing.get("drawing_type", ""))
    base_type = "plan" if drawing_type.startswith("plan-") else drawing_type
    if base_type == "render":
        return 99
    filename = str(drawing.get("original_name", "")).lower()
    if any(keyword in filename for keyword in ("效果", "场景", "render", "pano")):
        return 99
    filename_priority = (
        ("平面", "plan", "1f", "2f", "3f", "4f", "5f", "6f", "7f"),
        ("总平", "场地", "site"),
        ("剖面", "section"),
        ("立面", "facade", "elevation"),
        ("分析", "analysis", "diagram"),
    )
    for priority, keywords in enumerate(filename_priority):
        if any(keyword in filename for keyword in keywords):
            return priority
    fallback = SPLIT_TYPE_PRIORITY.get(base_type, 99)
    return fallback + 10 if fallback < 99 else 99


def detect_panel_boxes(image: Image.Image) -> list[tuple[int, int, int, int]]:
    """沿贯穿图面的留白带识别二至四个独立图纸分区。"""
    width, height = image.size
    if min(width, height) < 700:
        return []
    boxes = [(0, 0, width, height)]
    while len(boxes) < MAX_DERIVED_IMAGES:
        candidates = []
        for index, box in enumerate(boxes):
            split = find_whitespace_split(image, box)
            if split is not None:
                first, second, score = split
                candidates.append((score, index, first, second))
        if not candidates:
            break
        _, index, first, second = max(candidates, key=lambda item: item[0])
        boxes[index:index + 1] = [first, second]
    if len(boxes) < 2:
        return []
    return sorted(boxes, key=lambda box: (box[1], box[0]))


def find_whitespace_split(
    image: Image.Image,
    box: tuple[int, int, int, int],
) -> tuple[tuple[int, int, int, int], tuple[int, int, int, int], float] | None:
    """寻找贯穿当前区域的最佳横向或纵向留白分隔带。"""
    left, top, right, bottom = box
    width, height = right - left, bottom - top
    if min(width, height) < 500:
        return None
    preview = image.crop(box)
    preview.thumbnail((420, 420), Image.Resampling.BILINEAR)
    gray = ImageOps.grayscale(preview)
    sample_width, sample_height = gray.size
    pixels = gray.tobytes()
    column_ink = [0] * sample_width
    row_ink = [0] * sample_height
    for y in range(sample_height):
        offset = y * sample_width
        for x in range(sample_width):
            if pixels[offset + x] < 242:
                column_ink[x] += 1
                row_ink[y] += 1

    vertical = best_gap(column_ink, sample_height)
    horizontal = best_gap(row_ink, sample_width)
    options = []
    if vertical is not None:
        start, end, gap_score = vertical
        split_x = left + round(((start + end) / 2) / sample_width * width)
        if split_x - left >= width * 0.24 and right - split_x >= width * 0.24:
            options.append((gap_score, (left, top, split_x, bottom), (split_x, top, right, bottom)))
    if horizontal is not None:
        start, end, gap_score = horizontal
        split_y = top + round(((start + end) / 2) / sample_height * height)
        if split_y - top >= height * 0.24 and bottom - split_y >= height * 0.24:
            options.append((gap_score, (left, top, right, split_y), (left, split_y, right, bottom)))
    if not options:
        return None
    score, first, second = max(options, key=lambda item: item[0])
    return first, second, score


def best_gap(ink_counts: list[int], cross_length: int) -> tuple[int, int, float] | None:
    """从投影中选择位于内部且几乎无内容的连续留白带。"""
    axis_length = len(ink_counts)
    margin = max(2, round(axis_length * 0.1))
    minimum_run = max(3, round(axis_length * 0.012))
    maximum_ink = max(1, round(cross_length * 0.008))
    runs = []
    start = None
    for index in range(margin, axis_length - margin):
        if ink_counts[index] <= maximum_ink:
            start = index if start is None else start
            continue
        if start is not None and index - start >= minimum_run:
            runs.append((start, index))
        start = None
    if start is not None and axis_length - margin - start >= minimum_run:
        runs.append((start, axis_length - margin))
    if not runs:
        return None
    start, end = max(
        runs,
        key=lambda run: (run[1] - run[0]) * (1 - abs(((run[0] + run[1]) / 2) / axis_length - 0.5)),
    )
    center = ((start + end) / 2) / axis_length
    balance = 1 - abs(center - 0.5)
    return start, end, (end - start) / axis_length + balance * 0.05


def save_region_image(
    image: Image.Image,
    source_path: Path,
    box: tuple[int, int, int, int],
    index: int,
) -> Path:
    """把识别区域保存为清晰 PNG，并用源文件指纹复用结果。"""
    signature = sha256(
        f"{source_path.resolve()}:{source_path.stat().st_mtime_ns}:{box}".encode("utf-8")
    ).hexdigest()[:16]
    REGION_CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    target = REGION_CACHE_ROOT / f"{signature}-{index}.png"
    if target.is_file():
        return target
    crop = image.crop(box)
    if max(crop.size) > 4096:
        crop.thumbnail((4096, 4096), Image.Resampling.LANCZOS)
    crop.save(target, format="PNG", optimize=True)
    return target


def build_region_model_url(file_path: Path, provider: str, model: str) -> str:
    """按模型来源生成局部图 URL；上传失败时只跳过局部图。"""
    if provider != "dashscope":
        return build_model_image_data_url(
            file_path,
            "image/png",
            get_settings().llm_image_max_side,
        )
    key = (str(file_path), file_path.stat().st_mtime_ns, model)
    cached = _MODEL_URL_CACHE.get(key)
    if cached and cached[1] > datetime.now(timezone.utc):
        return cached[0]
    settings = get_settings()
    try:
        result = DashScopeFileClient(
            settings.dashscope_api_key,
            model,
            settings.llm_timeout_seconds,
            settings.llm_trust_env,
        ).upload_file(file_path, "image/png")
    except Exception as exc:
        LOGGER.warning("自动拆分图上传失败，继续使用原图：%s", exc)
        return ""
    _MODEL_URL_CACHE[key] = (result.url, result.expires_at)
    return result.url
