"""验证长程 Goal 基线冻结只保留聚合结果和稳定指纹。"""

from __future__ import annotations

import json
from pathlib import Path

from app.benchmarking.baseline_snapshot import fingerprint_files, read_aggregate_metrics


def test_file_fingerprint_changes_with_content(tmp_path: Path) -> None:
    """确认基线指纹能发现文件内容变更。"""
    path = tmp_path / "prompt.py"
    path.write_text("VERSION = 1\n", encoding="utf-8")
    first = fingerprint_files(tmp_path, [path])
    path.write_text("VERSION = 2\n", encoding="utf-8")
    second = fingerprint_files(tmp_path, [path])
    assert first != second


def test_aggregate_reader_drops_per_case_answers(tmp_path: Path) -> None:
    """确认基线快照不会复制逐样本教师分。"""
    metrics_file = tmp_path / "metrics.json"
    metrics_file.write_text(
        json.dumps(
            {
                "case_count": 2,
                "score_mae": 7.5,
                "cases": [{"case_id": "CASE-A01", "teacher_score": 94}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    output = read_aggregate_metrics(metrics_file)
    assert output["case_count"] == 2
    assert output["score_mae"] == 7.5
    assert "cases" not in output
    assert "teacher_score" not in json.dumps(output)
