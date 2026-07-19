"""从指定校准样本结果拟合教师标尺，并记录不含答案的固定数据划分。"""

from __future__ import annotations

import json
from pathlib import Path

from app.scoring.calibration import fit_calibrator, save_calibrator


def fit_calibration_artifact(
    results_root: Path,
    ground_truth_file: Path,
    train_case_ids: list[str],
    heldout_case_ids: list[str],
    output_file: Path,
    split_file: Path,
) -> dict:
    """只读取训练编号的教师分，盲测编号仅写入无答案划分清单。"""
    if set(train_case_ids) & set(heldout_case_ids):
        raise ValueError("校准集与盲测集不能重叠。")
    truth_items = json.loads(ground_truth_file.read_text(encoding="utf-8"))["cases"]
    truth_by_id = {item["case_id"]: item for item in truth_items}
    records = []
    for case_id in train_case_ids:
        result_file = results_root / f"{case_id}.json"
        if not result_file.is_file():
            raise ValueError(f"缺少校准原始结果：{case_id}")
        result = json.loads(result_file.read_text(encoding="utf-8"))
        scoring = result["report"].get("evaluation_context", {}).get("scoring", {})
        if scoring.get("architecture") != "evidence_v2":
            raise ValueError(f"{case_id} 不是新版证据层结果。")
        records.append(
            {
                "case_id": case_id,
                "raw_score": float(scoring["raw_score"]),
                "teacher_score": float(truth_by_id[case_id]["teacher_score"]),
            }
        )
    artifact = fit_calibrator(records, train_case_ids)
    artifact["evaluation_split"] = {
        "train_case_ids": train_case_ids,
        "heldout_case_ids": heldout_case_ids,
        "heldout_scores_used_for_fit": False,
    }
    save_calibrator(output_file, artifact)
    split_file.parent.mkdir(parents=True, exist_ok=True)
    split_file.write_text(
        json.dumps(
            {
                "version": 1,
                "purpose": "evidence_v2_teacher_calibration_and_blind_test",
                "train_case_ids": train_case_ids,
                "heldout_case_ids": heldout_case_ids,
                "teacher_scores_in_split_file": False,
                "rule": "盲测教师分只在模型报告冻结后用于统计，不参与拟合。",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return artifact
