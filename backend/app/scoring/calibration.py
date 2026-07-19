"""拟合和读取小样本单调教师评分校准器，保持校准集与盲测集隔离。"""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from statistics import mean
from typing import Any


CALIBRATION_METHOD = "regularized_monotonic_piecewise_linear_v1"


def fit_calibrator(records: list[dict], train_case_ids: list[str]) -> dict:
    """仅使用明确列出的训练样本拟合单调映射。"""
    allowed = set(train_case_ids)
    selected = [item for item in records if item.get("case_id") in allowed]
    if {item.get("case_id") for item in selected} != allowed:
        missing = sorted(allowed - {item.get("case_id") for item in selected})
        raise ValueError(f"校准样本缺失：{', '.join(missing)}")
    points = sorted(
        [
            {
                "case_id": str(item["case_id"]),
                "raw_score": float(item["raw_score"]),
                "teacher_score": float(item["teacher_score"]),
            }
            for item in selected
        ],
        key=lambda item: item["raw_score"],
    )
    blocks = fit_isotonic_blocks(points)
    residuals = [
        abs(predict_from_blocks(item["raw_score"], blocks) - item["teacher_score"])
        for item in points
    ]
    return {
        "version": "evidence-v2-calibration-1",
        "method": CALIBRATION_METHOD,
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "train_case_ids": train_case_ids,
        "sample_count": len(points),
        "regularization": {"identity_weight": 0.15, "calibrated_weight": 0.85},
        "points": points,
        "blocks": blocks,
        "training_mae": round(mean(residuals), 3) if residuals else 0.0,
        "heldout_case_ids": [],
    }


def fit_isotonic_blocks(points: list[dict]) -> list[dict]:
    """使用 PAVA 合并逆序教师分，保证原始分越高校准分不下降。"""
    blocks = []
    for item in points:
        blocks.append(
            {
                "x_sum": item["raw_score"],
                "y_sum": item["teacher_score"],
                "weight": 1,
            }
        )
        while len(blocks) >= 2 and block_y(blocks[-2]) > block_y(blocks[-1]):
            right = blocks.pop()
            left = blocks.pop()
            blocks.append(
                {
                    "x_sum": left["x_sum"] + right["x_sum"],
                    "y_sum": left["y_sum"] + right["y_sum"],
                    "weight": left["weight"] + right["weight"],
                }
            )
    return [
        {
            "raw_score": round(block["x_sum"] / block["weight"], 3),
            "teacher_score": round(block["y_sum"] / block["weight"], 3),
            "weight": block["weight"],
        }
        for block in blocks
    ]


def block_y(block: dict) -> float:
    """返回 PAVA 临时块的教师均值。"""
    return block["y_sum"] / block["weight"]


def predict_calibrated_score(raw_score: float, calibrator: dict | None) -> float:
    """应用带恒等映射收缩的教师校准，缺少校准器时返回原始分。"""
    raw = float(raw_score)
    if not calibrator or not calibrator.get("blocks"):
        return round(max(0.0, min(100.0, raw)), 1)
    calibrated = predict_from_blocks(raw, calibrator["blocks"])
    regularization = calibrator.get("regularization") or {}
    identity_weight = float(regularization.get("identity_weight", 0.15))
    result = raw * identity_weight + calibrated * (1 - identity_weight)
    return round(max(0.0, min(100.0, result)), 1)


def predict_from_blocks(raw_score: float, blocks: list[dict]) -> float:
    """在单调锚点间线性插值，范围外以端点偏差平移。"""
    if not blocks:
        return float(raw_score)
    if len(blocks) == 1:
        return float(raw_score) + blocks[0]["teacher_score"] - blocks[0]["raw_score"]
    x = float(raw_score)
    if x <= blocks[0]["raw_score"]:
        return x + blocks[0]["teacher_score"] - blocks[0]["raw_score"]
    if x >= blocks[-1]["raw_score"]:
        return x + blocks[-1]["teacher_score"] - blocks[-1]["raw_score"]
    for left, right in zip(blocks, blocks[1:]):
        if left["raw_score"] <= x <= right["raw_score"]:
            width = right["raw_score"] - left["raw_score"]
            if width <= 0:
                return (left["teacher_score"] + right["teacher_score"]) / 2
            ratio = (x - left["raw_score"]) / width
            return left["teacher_score"] + ratio * (
                right["teacher_score"] - left["teacher_score"]
            )
    return x


def load_calibrator(source: str | Path | dict | None) -> dict | None:
    """从字典或 UTF-8 JSON 文件读取校准器，文件不存在时保持未校准。"""
    if isinstance(source, dict):
        return source
    if not source:
        return None
    path = Path(source)
    if not path.is_file():
        return None
    data: Any = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else None


def save_calibrator(path: Path, calibrator: dict) -> None:
    """把校准器写为可复核的 UTF-8 JSON 文件。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(calibrator, ensure_ascii=False, indent=2), encoding="utf-8")
