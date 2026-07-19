"""统计基准测试分数误差、区间命中和语义裁判结果。"""

from __future__ import annotations

from itertools import product
import json
import math
from pathlib import Path
import random
from statistics import mean, median


def calculate_round_metrics(results_root: Path, ground_truth_file: Path) -> dict:
    """汇总一轮已经完成的样本结果。"""
    truth_cases = {
        item["case_id"]: item
        for item in json.loads(ground_truth_file.read_text(encoding="utf-8"))["cases"]
    }
    cases = []
    for result_file in sorted(results_root.glob("CASE-*.json")):
        result = json.loads(result_file.read_text(encoding="utf-8"))
        truth = truth_cases[result["case_id"]]
        cases.append(calculate_case_metrics(result, truth))
    return aggregate_metrics(cases)


def calculate_case_metrics(result: dict, truth: dict) -> dict:
    """计算单份样本的评分和语义指标。"""
    report = result["report"]
    score_by_agent = {
        item["agent_type"]: float(item["score"])
        for item in report.get("agent_evaluations", [])
    }
    ranges = truth.get("score_ranges", {})
    interval_items = []
    for agent_type, expected in ranges.items():
        if agent_type not in score_by_agent:
            continue
        score = score_by_agent[agent_type]
        distance = max(expected["min"] - score, 0, score - expected["max"])
        interval_items.append(
            {
                "agent_type": agent_type,
                "score": score,
                "min": expected["min"],
                "max": expected["max"],
                "hit": distance == 0,
                "distance": round(distance, 1),
            }
        )
    judge = result.get("judge", {})
    return {
        "case_id": result["case_id"],
        "teacher_score": truth["teacher_score"],
        "overall_score": float(report["overall_score"]),
        "absolute_error": round(abs(float(report["overall_score"]) - truth["teacher_score"]), 1),
        "intervals": interval_items,
        "must_total": len(judge.get("must_issue_results", [])),
        "must_hits": sum(item.get("matched", False) for item in judge.get("must_issue_results", [])),
        "forbidden_total": len(judge.get("forbidden_results", [])),
        "forbidden_violations": sum(item.get("violated", False) for item in judge.get("forbidden_results", [])),
        "fact_total": len(judge.get("fact_results", [])),
        "fact_hits": sum(item.get("correct", False) for item in judge.get("fact_results", [])),
    }


def aggregate_metrics(cases: list[dict]) -> dict:
    """汇总全部样本并计算高低档排序。"""
    interval_items = [item for case in cases for item in case["intervals"]]
    high = [item for item in cases if item["teacher_score"] >= 90]
    low = [item for item in cases if item["teacher_score"] < 80]
    pairs = list(product(high, low))
    pair_hits = sum(left["overall_score"] > right["overall_score"] for left, right in pairs)
    must_total = sum(item["must_total"] for item in cases)
    forbidden_total = sum(item["forbidden_total"] for item in cases)
    fact_total = sum(item["fact_total"] for item in cases)
    teacher_scores = [item["teacher_score"] for item in cases]
    model_scores = [item["overall_score"] for item in cases]
    signed_errors = [model - teacher for model, teacher in zip(model_scores, teacher_scores)]
    absolute_errors = [abs(value) for value in signed_errors]
    return {
        "case_count": len(cases),
        "score_mae": round(mean(absolute_errors), 2) if cases else 0,
        "score_mae_ci95": bootstrap_mae_ci(signed_errors),
        "score_rmse": round(math.sqrt(mean(value * value for value in signed_errors)), 2) if cases else 0,
        "score_median_absolute_error": round(median(absolute_errors), 2) if cases else 0,
        "score_mean_bias": round(mean(signed_errors), 2) if cases else 0,
        "score_pearson_r": round(pearson_correlation(teacher_scores, model_scores), 4),
        "score_spearman_rho": round(spearman_correlation(teacher_scores, model_scores), 4),
        "model_score_range": round(max(model_scores) - min(model_scores), 1) if cases else 0,
        "interval_hit_rate": ratio(sum(item["hit"] for item in interval_items), len(interval_items)),
        "mean_interval_distance": round(sum(item["distance"] for item in interval_items) / len(interval_items), 2) if interval_items else 0,
        "must_issue_recall": ratio(sum(item["must_hits"] for item in cases), must_total),
        "forbidden_violation_rate": ratio(sum(item["forbidden_violations"] for item in cases), forbidden_total),
        "fact_accuracy": ratio(sum(item["fact_hits"] for item in cases), fact_total),
        "high_low_pair_accuracy": ratio(pair_hits, len(pairs)),
        "cases": cases,
    }


def ratio(value: int, total: int) -> float:
    """返回 0 到 1 之间的四位小数比例。"""
    return round(value / total, 4) if total else 0.0


def bootstrap_mae_ci(errors: list[float], iterations: int = 5000) -> list[float]:
    """以固定随机种子估计 MAE 的 95% 自助法区间，便于论文复核。"""
    if not errors:
        return [0.0, 0.0]
    generator = random.Random(20260717)
    values = []
    for _ in range(iterations):
        sample = [abs(generator.choice(errors)) for _ in errors]
        values.append(mean(sample))
    values.sort()
    return [
        round(values[int(iterations * 0.025)], 2),
        round(values[min(iterations - 1, int(iterations * 0.975))], 2),
    ]


def pearson_correlation(left: list[float], right: list[float]) -> float:
    """计算两组分数的 Pearson 相关系数。"""
    if len(left) < 2 or len(left) != len(right):
        return 0.0
    left_mean = mean(left)
    right_mean = mean(right)
    numerator = sum((x - left_mean) * (y - right_mean) for x, y in zip(left, right))
    denominator = math.sqrt(
        sum((x - left_mean) ** 2 for x in left)
        * sum((y - right_mean) ** 2 for y in right)
    )
    return numerator / denominator if denominator else 0.0


def spearman_correlation(left: list[float], right: list[float]) -> float:
    """按平均秩处理并列值后计算 Spearman 相关系数。"""
    return pearson_correlation(average_ranks(left), average_ranks(right))


def average_ranks(values: list[float]) -> list[float]:
    """返回带并列平均名次的秩序列。"""
    ordered = sorted(enumerate(values), key=lambda item: item[1])
    ranks = [0.0] * len(values)
    index = 0
    while index < len(ordered):
        end = index + 1
        while end < len(ordered) and ordered[end][1] == ordered[index][1]:
            end += 1
        rank = (index + 1 + end) / 2
        for position in range(index, end):
            ranks[ordered[position][0]] = rank
        index = end
    return ranks
