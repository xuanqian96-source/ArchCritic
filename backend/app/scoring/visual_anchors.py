"""读取和校验建筑设计课视觉评分锚点，供综合评审 Agent 做尺度校准。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from app.agents.image_payload import build_model_image_data_url
from app.config import get_settings


BAND_ORDER = {"low": 0, "middle": 1, "high": 2}
BAND_SCORE_RANGES = {
    "low": (0, 75),
    "middle": (76, 85),
    "high": (86, 100),
}


def load_visual_anchor_manifest(anchor_root: Path) -> dict[str, Any]:
    """读取锚点清单并核对数量、分档、分数和图片哈希。"""
    root = anchor_root.resolve()
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"视觉评分锚点清单不存在：{manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    anchors = list(manifest.get("anchors") or [])
    if not 9 <= len(anchors) <= 15:
        raise ValueError("视觉评分锚点总数必须为 9—15 份。")

    seen_ids: set[str] = set()
    band_counts = {band: 0 for band in BAND_ORDER}
    for item in anchors:
        anchor_id = str(item.get("anchor_id") or "").strip()
        if not anchor_id or anchor_id in seen_ids:
            raise ValueError(f"视觉评分锚点编号缺失或重复：{anchor_id}")
        seen_ids.add(anchor_id)
        band = str(item.get("band") or "").strip()
        if band not in BAND_SCORE_RANGES:
            raise ValueError(f"{anchor_id} 使用了未知分档：{band}")
        score = float(item.get("teacher_score"))
        lower, upper = BAND_SCORE_RANGES[band]
        if not lower <= score <= upper:
            raise ValueError(f"{anchor_id} 的分数 {score:g} 不属于 {band} 分档。")
        image_path = resolve_anchor_image(root, str(item.get("image_path") or ""))
        expected_hash = str(item.get("image_sha256") or "")
        if expected_hash and sha256_file(image_path) != expected_hash:
            raise ValueError(f"{anchor_id} 的锚点图片哈希不一致。")
        band_counts[band] += 1
    if any(count < 3 for count in band_counts.values()):
        raise ValueError(f"每个分档至少需要 3 份视觉锚点：{band_counts}")
    return manifest


def collect_visual_anchor_files(anchor_root: Path) -> list[dict[str, Any]]:
    """返回需要上传给真实多模态模型的锚点图片。"""
    root = anchor_root.resolve()
    manifest = load_visual_anchor_manifest(root)
    return [
        {
            "label": str(item["anchor_id"]),
            "path": resolve_anchor_image(root, str(item["image_path"])),
            "mime_type": str(item.get("mime_type") or "image/jpeg"),
        }
        for item in manifest["anchors"]
    ]


def build_visual_anchor_context(
    anchor_root: Path,
    upload_cache: dict[str, str],
    provider: str,
) -> list[dict[str, Any]]:
    """把锚点清单转换成综合评审 Agent 可直接读取的图文结构。"""
    root = anchor_root.resolve()
    manifest = load_visual_anchor_manifest(root)
    anchors = []
    for item in sorted(
        manifest["anchors"],
        key=lambda value: (
            BAND_ORDER[str(value["band"])],
            float(value["teacher_score"]),
        ),
    ):
        image_path = resolve_anchor_image(root, str(item["image_path"]))
        model_file_url = upload_cache.get(str(image_path), "")
        mime_type = str(item.get("mime_type") or "image/jpeg")
        if not model_file_url and provider in {"openai", "gemini"}:
            model_file_url = build_model_image_data_url(
                image_path,
                mime_type,
                get_settings().llm_image_max_side,
            )
        anchors.append(
            {
                "anchor_id": str(item["anchor_id"]),
                "band": str(item["band"]),
                "teacher_score": float(item["teacher_score"]),
                "display_title": str(item.get("display_title") or "匿名课程作品"),
                "selection_note": str(item.get("selection_note") or ""),
                "drawings": [
                    {
                        "drawing_type": "board",
                        "original_name": str(item["anchor_id"]),
                        "mime_type": mime_type,
                        "description": "视觉评分锚点代表性总览展板",
                        "analysis_purpose": "比较课程作品的整体设计与表达水平",
                        "file_url": "",
                        "model_file_url": model_file_url,
                        "usable_for_model": bool(model_file_url),
                    }
                ],
            }
        )
    return anchors


def visual_anchor_fingerprint(anchor_root: Path) -> str:
    """计算锚点清单及全部图片的联合指纹。"""
    root = anchor_root.resolve()
    manifest = load_visual_anchor_manifest(root)
    digest = hashlib.sha256()
    manifest_path = root / "manifest.json"
    digest.update(manifest_path.read_bytes())
    for item in manifest["anchors"]:
        image_path = resolve_anchor_image(root, str(item["image_path"]))
        digest.update(str(item["image_path"]).encode("utf-8"))
        digest.update(image_path.read_bytes())
    return digest.hexdigest()


def resolve_anchor_image(anchor_root: Path, relative_path: str) -> Path:
    """解析锚点图片并阻止目录越界。"""
    root = anchor_root.resolve()
    path = (root / relative_path).resolve()
    if path != root and root not in path.parents:
        raise ValueError(f"锚点图片路径越界：{relative_path}")
    if not path.is_file():
        raise FileNotFoundError(f"锚点图片不存在：{relative_path}")
    return path


def sha256_file(path: Path) -> str:
    """计算文件 SHA-256。"""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
