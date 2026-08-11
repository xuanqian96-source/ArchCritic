"""验证基准集匿名化、人工区间校准与指标统计。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.benchmarking.dataset import load_benchmark_cases
from app.benchmarking.metrics import calculate_case_metrics
from app.services.taskbooks import STAGE_BASE_WEIGHTS


DATASET_ROOT = Path(__file__).resolve().parents[2] / "标注基准集"
PRIVATE_CASES = load_benchmark_cases(DATASET_ROOT) if DATASET_ROOT.is_dir() else []


@pytest.mark.skipif(not PRIVATE_CASES, reason="本地私有基准样本未提供")
def test_private_dataset_is_anonymous_and_complete() -> None:
    """确认六份私有样本输入不含教师答案和原样本编号。"""
    assert len(PRIVATE_CASES) == 6
    for case in PRIVATE_CASES:
        model_input = case.build_input()
        encoded = json.dumps(model_input, ensure_ascii=False)
        assert case.sample_id not in encoded
        assert str(int(case.teacher_score)) not in encoded
        assert "teacher_score" not in model_input
        assert "facts" not in model_input
        assert "score_ranges" not in model_input


@pytest.mark.skipif(not PRIVATE_CASES, reason="本地私有基准样本未提供")
def test_human_intervals_are_calibrated_to_teacher_scores() -> None:
    """确认校准后的人工区间加权中点与教师分数接近。"""
    for case in PRIVATE_CASES:
        weights = STAGE_BASE_WEIGHTS[case.design_stage]
        midpoint = sum(
            ((case.score_ranges[key]["min"] + case.score_ranges[key]["max"]) / 2)
            * weight
            / 100
            for key, weight in weights.items()
        )
        assert abs(midpoint - case.teacher_score) <= 0.5


def test_case_metrics_count_score_and_semantic_results() -> None:
    """确认单样本指标能统计分数误差、命中和误报。"""
    result = {
        "case_id": "CASE-001",
        "report": {
            "overall_score": 90,
            "agent_evaluations": [{"agent_type": "site_agent", "score": 88}],
        },
        "judge": {
            "fact_results": [{"correct": True}, {"correct": False}],
            "must_issue_results": [{"matched": True}],
            "forbidden_results": [{"violated": False}],
        },
    }
    truth = {
        "teacher_score": 94,
        "score_ranges": {"site_agent": {"min": 90, "max": 94}},
    }
    metrics = calculate_case_metrics(result, truth)
    assert metrics["absolute_error"] == 4
    assert metrics["intervals"][0]["distance"] == 2
    assert metrics["fact_hits"] == 1
    assert metrics["must_hits"] == 1
    assert metrics["forbidden_violations"] == 0
