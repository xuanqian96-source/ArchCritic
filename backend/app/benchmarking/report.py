"""把一轮或两轮评测数据整理为便于人工阅读的 Markdown 报告。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path


def write_round_report(
    path: Path, round_name: str, metrics: dict, model: str, expected_count: int = 6
) -> None:
    """写入单轮评测报告。"""
    lines = [
        f"# ArchCritic {round_name}基准测试报告",
        "",
        f"生成时间：{datetime.now().astimezone().isoformat(timespec='seconds')}",
        f"模型：{model}",
        f"完成样本：{metrics['case_count']}/{expected_count}",
        "",
        "## 总体结果",
        "",
        f"- 教师分数平均绝对误差：{metrics['score_mae']}",
        f"- Agent 评分区间命中率：{percent(metrics['interval_hit_rate'])}",
        f"- 高低档排序准确率：{percent(metrics['high_low_pair_accuracy'])}",
        f"- 图纸事实准确率：{percent(metrics['fact_accuracy'])}",
        f"- 必须问题召回率：{percent(metrics['must_issue_recall'])}",
        f"- 禁止误报触发率：{percent(metrics['forbidden_violation_rate'])}",
        "",
        "## 分样本结果",
        "",
        "| 匿名样本 | 教师分 | 模型分 | 绝对误差 | 区间命中 | 必须问题 | 禁止误报 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for case in metrics["cases"]:
        interval_hits = sum(item["hit"] for item in case["intervals"])
        lines.append(
            f"| {case['case_id']} | {case['teacher_score']:g} | {case['overall_score']:g} | "
            f"{case['absolute_error']:g} | {interval_hits}/{len(case['intervals'])} | "
            f"{case['must_hits']}/{case['must_total']} | "
            f"{case['forbidden_violations']}/{case['forbidden_total']} |"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_comparison_report(path: Path, first: dict, second: dict) -> None:
    """写入两轮优化前后对比报告。"""
    metrics = (
        ("教师分数平均绝对误差", first["score_mae"], second["score_mae"], "越低越好"),
        ("Agent 评分区间命中率", first["interval_hit_rate"], second["interval_hit_rate"], "越高越好"),
        ("高低档排序准确率", first["high_low_pair_accuracy"], second["high_low_pair_accuracy"], "越高越好"),
        ("图纸事实准确率", first["fact_accuracy"], second["fact_accuracy"], "越高越好"),
        ("必须问题召回率", first["must_issue_recall"], second["must_issue_recall"], "越高越好"),
        ("禁止误报触发率", first["forbidden_violation_rate"], second["forbidden_violation_rate"], "越低越好"),
    )
    lines = [
        "# ArchCritic 两轮基准测试对比",
        "",
        "| 指标 | 第一轮 | 第二轮 | 方向 |",
        "| --- | ---: | ---: | --- |",
    ]
    for name, before, after, direction in metrics:
        lines.append(f"| {name} | {before} | {after} | {direction} |")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def percent(value: float) -> str:
    """把 0 到 1 的比例转换为百分数。"""
    return f"{value * 100:.1f}%"
