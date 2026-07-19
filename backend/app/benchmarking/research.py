"""导出可用于论文整理的两轮基准数据、SVG 图表和中文报告。"""

from __future__ import annotations

import csv
from datetime import datetime
import json
from pathlib import Path
from typing import Any

from app.agents.prompts.course_scoring_v2 import (
    COURSE_SCORE_CALIBRATION,
    SPECIALIST_CALIBRATION,
)
from app.benchmarking.charts import (
    write_error_chart,
    write_scatter_chart,
    write_score_bar_chart,
)


def export_research_package(
    prepared_root: Path,
    results_root: Path,
    output_root: Path,
    first_round: str,
    second_round: str,
) -> dict:
    """汇总正式两轮结果并生成论文数据包。"""
    first_metrics = read_json(results_root / first_round / "metrics.json")
    second_metrics = read_json(results_root / second_round / "metrics.json")
    truth = read_json(prepared_root / "ground_truth.json")
    taskbook = read_json(prepared_root / "taskbook.json")
    first_results = load_results(results_root / first_round)
    second_results = load_results(results_root / second_round)
    truth_by_id = {item["case_id"]: item for item in truth["cases"]}

    data_root = output_root / "数据"
    charts_root = output_root / "图表"
    config_root = output_root / "实验配置"
    for path in (data_root, charts_root, config_root):
        path.mkdir(parents=True, exist_ok=True)

    case_rows = build_case_rows(first_metrics, second_metrics)
    agent_rows = build_agent_rows(first_results, second_results, truth_by_id)
    write_csv(data_root / "逐样本分数.csv", case_rows)
    write_csv(data_root / "逐Agent分数.csv", agent_rows)
    write_csv(data_root / "两轮总体指标.csv", build_metric_rows(first_metrics, second_metrics))
    write_json(
        data_root / "两轮完整统计.json",
        {
            "first_round": first_metrics,
            "second_round": second_metrics,
            "paired_summary": build_paired_summary(case_rows),
        },
    )
    write_json(data_root / "人工标准答案.json", truth)

    write_score_bar_chart(charts_root / "01_逐样本分数对比.svg", case_rows)
    write_scatter_chart(charts_root / "02_教师与模型分数散点.svg", case_rows)
    write_error_chart(charts_root / "03_逐样本绝对误差.svg", case_rows)

    prompt_fingerprints = {
        "first_round": sorted({item.get("prompt_fingerprint", "") for item in first_results.values()}),
        "second_round": sorted({item.get("prompt_fingerprint", "") for item in second_results.values()}),
    }
    config = build_experiment_config(
        first_round,
        second_round,
        prompt_fingerprints,
        taskbook,
    )
    write_json(config_root / "正式实验配置.json", config)
    write_prompt_snapshot(config_root / "第二轮评分锚点快照.md")

    write_research_report(
        output_root / "03_两轮测试论文数据报告.md",
        first_metrics,
        second_metrics,
        case_rows,
        config,
    )
    write_work_report(
        output_root / "04_工作总结报告.md",
        first_metrics,
        second_metrics,
        case_rows,
    )
    write_reproduction_guide(output_root / "05_数据与复现说明.md", config)
    return {
        "case_count": len(case_rows),
        "agent_row_count": len(agent_rows),
        "output_root": str(output_root),
    }


def build_case_rows(first_metrics: dict, second_metrics: dict) -> list[dict]:
    """整理逐样本教师分与两轮模型分。"""
    second_by_id = {item["case_id"]: item for item in second_metrics["cases"]}
    rows = []
    for first in first_metrics["cases"]:
        second = second_by_id[first["case_id"]]
        rows.append(
            {
                "case_id": first["case_id"],
                "teacher_score": first["teacher_score"],
                "round1_score": first["overall_score"],
                "round2_score": second["overall_score"],
                "round1_signed_error": round(first["overall_score"] - first["teacher_score"], 1),
                "round2_signed_error": round(second["overall_score"] - second["teacher_score"], 1),
                "round1_absolute_error": first["absolute_error"],
                "round2_absolute_error": second["absolute_error"],
                "absolute_error_change": round(second["absolute_error"] - first["absolute_error"], 1),
            }
        )
    return rows


def build_agent_rows(first: dict, second: dict, truth: dict) -> list[dict]:
    """整理每个专项 Agent 的两轮分数和人工区间。"""
    rows = []
    for case_id in sorted(first):
        expected = truth[case_id]
        first_scores = evaluation_scores(first[case_id])
        second_scores = evaluation_scores(second[case_id])
        for agent_type, interval in expected.get("score_ranges", {}).items():
            first_score = first_scores.get(agent_type)
            second_score = second_scores.get(agent_type)
            rows.append(
                {
                    "case_id": case_id,
                    "agent_type": agent_type,
                    "teacher_score": expected["teacher_score"],
                    "acceptable_min": interval["min"],
                    "acceptable_max": interval["max"],
                    "round1_score": first_score,
                    "round2_score": second_score,
                    "round1_hit": interval_hit(first_score, interval),
                    "round2_hit": interval_hit(second_score, interval),
                }
            )
    return rows


def build_metric_rows(first: dict, second: dict) -> list[dict]:
    """把论文常用总体指标整理为纵向表格。"""
    metrics = (
        ("score_mae", "平均绝对误差 MAE", "分", "越低越好"),
        ("score_rmse", "均方根误差 RMSE", "分", "越低越好"),
        ("score_mean_bias", "平均系统偏差", "分", "越接近0越好"),
        ("score_pearson_r", "Pearson 相关", "", "越高越好"),
        ("score_spearman_rho", "Spearman 相关", "", "越高越好"),
        ("high_low_pair_accuracy", "高低档配对排序准确率", "比例", "越高越好"),
        ("fact_accuracy", "图纸事实准确率", "比例", "越高越好"),
        ("must_issue_recall", "必须问题召回率", "比例", "越高越好"),
        ("forbidden_violation_rate", "禁止误报触发率", "比例", "越低越好"),
        ("interval_hit_rate", "Agent 人工区间命中率", "比例", "越高越好"),
    )
    return [
        {
            "metric": key,
            "label": label,
            "unit": unit,
            "direction": direction,
            "round1": first.get(key),
            "round2": second.get(key),
        }
        for key, label, unit, direction in metrics
    ]


def build_paired_summary(rows: list[dict]) -> dict:
    """计算逐样本配对改善数量和平均变化。"""
    changes = [item["absolute_error_change"] for item in rows]
    return {
        "improved_cases": sum(value < 0 for value in changes),
        "unchanged_cases": sum(value == 0 for value in changes),
        "worsened_cases": sum(value > 0 for value in changes),
        "mean_absolute_error_change": round(sum(changes) / len(changes), 2),
    }


def build_experiment_config(
    first_round: str,
    second_round: str,
    prompt_fingerprints: dict,
    taskbook: dict,
) -> dict:
    """生成正式实验条件与数据排除说明。"""
    return {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "model_provider": "dashscope",
        "model": "qwen3.6-plus",
        "sample_count": 6,
        "first_round": first_round,
        "second_round": second_round,
        "first_round_temperature": 0.2,
        "second_round_temperature": 0,
        "workers": 2,
        "prompt_fingerprints": prompt_fingerprints,
        "production_default_after_experiment": (
            "恢复第一轮评分标尺与 temperature=0.2；保留真实任务书接入和不确定性降级修复。"
        ),
        "taskbook_sources": taskbook.get("source_files", []),
        "taskbook_hashes": taskbook.get("source_hashes", []),
        "excluded_runs": [
            "round1：探索性千问测试，未接入任务书且 CASE-004 输入曾含标注结论，不纳入论文数据。",
            "gemini-round1：用户中断且无成功结果，不纳入论文数据。",
        ],
        "known_risks": [
            "CASE-003 的三张源图仅为 1280×1813，属于低清来源。",
            "六份样本来自同一学校、同一年级和同一课程，外部效度有限。",
            "第二轮提示词根据第一轮同一批样本设计，属于开发集内迭代，不是独立验证集。",
        ],
    }


def write_research_report(
    path: Path,
    first: dict,
    second: dict,
    rows: list[dict],
    config: dict,
) -> None:
    """写出适合作为论文实验章节底稿的严谨报告。"""
    paired = build_paired_summary(rows)
    score_table = "\n".join(
        "| {case_id} | {teacher_score:g} | {round1_score:g} | {round1_absolute_error:g} | "
        "{round2_score:g} | {round2_absolute_error:g} | {absolute_error_change:+g} |".format(**item)
        for item in rows
    )
    content = f"""# ArchCritic 多 Agent 评图两轮基准测试：论文数据报告

生成时间：{config['generated_at']}  
正式模型：`qwen3.6-plus`  
有效样本：6 份（教师高分档 3 份、中低分档 3 份）

## 摘要

本实验考察 ArchCritic 多 Agent 评图结果与课程教师分数的一致性，并验证课程阶段评分锚点能否改善模型评分。两轮均使用相同的 6 份匿名图纸、同一课程任务书、相同模型与动态 Agent 权重。第一轮接入真实任务书但保留原评分提示；第二轮加入大二课程分档锚点、专项解释、零温度和不确定性降级流程。

结果显示：第二轮将高分样本的绝对误差全部降低，但同时显著抬高中低分样本。MAE 从 {first['score_mae']:.2f} 分上升到 {second['score_mae']:.2f} 分，整体点估计变差；RMSE 从 {first['score_rmse']:.2f} 降至 {second['score_rmse']:.2f}，高低档配对排序准确率从 {first['high_low_pair_accuracy']:.1%} 升至 {second['high_low_pair_accuracy']:.1%}。因此，第二轮提升了高分召回与部分排序能力，但产生明显过校准，不能据此宣称总体评分精度提高。

## 1. 研究问题

1. 多 Agent 能否准确识别图纸事实和教师认为必须指出的问题？
2. 模型综合分与教师分数之间的误差、系统偏差和排序一致性如何？
3. 加入低年级课程评分锚点后，评分误差是否下降？

## 2. 数据与实验控制

- 数据：6 份建筑学大二课程成果，共 23 页图纸；3 份教师分数为 93–94，3 份为 61–70。
- 任务书：真实读取《古城记忆档案库》任务书，包含规模、功能、结构和成果图纸要求；源文件 SHA-256 已记录在实验配置中。
- 匿名化：模型输入不含教师分数、样本高低档、人工事实答案和人工可接受分数区间。
- 正式轮次：只使用 `{config['first_round']}` 与 `{config['second_round']}`；早期无任务书探索数据与中断的 Gemini 数据均排除。
- 模型与输入：两轮均为千问 `qwen3.6-plus`、同一逐页图纸、同一任务书和同一动态权重。
- 干预差异：第二轮同时改变评分锚点、专项说明、temperature（0.2→0）和不确定性汇总流程，属于组合干预，无法把效果单独归因于某一项。

## 3. 指标定义

- MAE：模型分与教师分绝对差的平均值，越低越好。
- RMSE：对大误差更敏感的均方根误差，越低越好。
- 平均系统偏差：模型分减教师分的平均值；负数表示整体偏严，正数表示整体偏松。
- Pearson / Spearman：分别衡量线性一致性和排序一致性。
- 高低档配对准确率：3 份高分样本与 3 份中低分样本组成 9 对，模型是否把高分排在低分之前。
- 事实准确率、必须问题召回率、禁止误报率：由独立文本裁判在评图完成后对照人工标注计算。

## 4. 总体结果

| 指标 | 第一轮 | 第二轮 | 变化判断 |
| --- | ---: | ---: | --- |
| MAE | {first['score_mae']:.2f} | {second['score_mae']:.2f} | 变差 {second['score_mae']-first['score_mae']:+.2f} 分 |
| MAE 95% bootstrap CI | {first['score_mae_ci95'][0]:.2f}–{first['score_mae_ci95'][1]:.2f} | {second['score_mae_ci95'][0]:.2f}–{second['score_mae_ci95'][1]:.2f} | 样本少，区间较宽 |
| RMSE | {first['score_rmse']:.2f} | {second['score_rmse']:.2f} | 改善 {second['score_rmse']-first['score_rmse']:+.2f} 分 |
| 平均系统偏差 | {first['score_mean_bias']:+.2f} | {second['score_mean_bias']:+.2f} | 从偏严转为偏松 |
| Pearson r | {first['score_pearson_r']:.3f} | {second['score_pearson_r']:.3f} | 仅作探索性描述 |
| Spearman ρ | {first['score_spearman_rho']:.3f} | {second['score_spearman_rho']:.3f} | 仅作探索性描述 |
| 高低档配对准确率 | {first['high_low_pair_accuracy']:.1%} | {second['high_low_pair_accuracy']:.1%} | 改善 |
| 图纸事实准确率 | {first['fact_accuracy']:.1%} | {second['fact_accuracy']:.1%} | 略降 |
| 必须问题召回率 | {first['must_issue_recall']:.1%} | {second['must_issue_recall']:.1%} | 持平 |
| 禁止误报触发率 | {first['forbidden_violation_rate']:.1%} | {second['forbidden_violation_rate']:.1%} | 均为 0 |

![六份样本的教师分与两轮模型分](图表/01_逐样本分数对比.svg)

## 5. 逐样本结果

| 样本 | 教师分 | 第一轮 | 第一轮误差 | 第二轮 | 第二轮误差 | 误差变化 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
{score_table}

配对结果为：{paired['improved_cases']} 份改善、{paired['worsened_cases']} 份变差、{paired['unchanged_cases']} 份不变。三份教师高分样本全部改善，三份中低分样本全部变差，说明第二轮不是普遍提准，而是把评分尺度整体上移。

![教师分与模型分散点](图表/02_教师与模型分数散点.svg)

![逐样本绝对误差](图表/03_逐样本绝对误差.svg)

## 6. 结果解释

第一轮表现出明显偏严，平均系统偏差为 {first['score_mean_bias']:+.2f} 分；第二轮转为偏松，平均系统偏差为 {second['score_mean_bias']:+.2f} 分。第二轮对高分作品更愿意进入优秀档，但把“概念存在、局部表达较好”误当成“跨页证据闭环”，导致 L001、L002、L003 被抬高。其根本问题不是事实识别能力不足：两轮事实准确率均接近或超过 88%，必须问题召回率均为 97.4%；问题主要发生在把事实和问题映射到教师分数档位的校准阶段。

## 7. 科研边界与局限

1. 样本仅 6 份，置信区间宽，不适合做显著性或普遍性结论。
2. 样本来自同一学校、同一年级、同一课程，不能直接外推至其他课程或高年级。
3. 教师只提供综合分，没有原始逐 Agent 分；当前 Agent 区间是人工复核后按教师总分校准的辅助标签，存在循环校准风险。
4. 第二轮依据第一轮同一批样本设计，属于开发集内优化，不能作为独立测试集性能。
5. CASE-003 源图分辨率较低，细小文字与功能标注判断存在额外不确定性。
6. 两轮是组合干预，且大模型即使 temperature=0 仍可能存在服务端非确定性。

## 8. 结论

ArchCritic 当前已具备较强的图纸事实识别和问题发现能力，但教师分数校准仍未完成。第二轮改善了高分召回和高低档配对排序，却使总体 MAE 从 {first['score_mae']:.2f} 增至 {second['score_mae']:.2f}；因此第二轮评分锚点不应直接作为生产默认方案。后续研究应把任务书核心成果覆盖率、跨页证据完整度和概念—空间闭环转成显式中间变量，并使用新增的独立教师评分样本进行盲测。
"""
    write_text(path, content)


def write_work_report(path: Path, first: dict, second: dict, rows: list[dict]) -> None:
    """写出面向项目负责人的通俗工作总结。"""
    content = f"""# ArchCritic 评分系统本轮工作总结

## 本轮完成的工作

1. 逐页复核 6 份学生图纸，修正样本编号、总平面、入口和档案功能等明确标注问题。
2. 重新校准人工专项区间，使任务书动态权重下的加权中点与教师分数误差均不超过 0.5 分。
3. 将 2 页真实课程任务书完整接入测试，Agent 能读取规模、功能、结构与成果要求并动态调整权重。
4. 生成 23 页匿名测试图，教师分数、档位和标注答案与模型输入物理分离；异常超大图压到最长边 6000 像素。
5. 建立可重复执行的真实多 Agent 测试程序，记录提示词指纹、单样本错误、事实识别、问题召回和评分误差。
6. 使用同一千问模型完成正式两轮测试，并导出 CSV、JSON、SVG 图表和论文数据报告。
7. 修复“不确定观察被当作确定问题展示”的流程错误。

## 两轮结果

| 项目 | 第一轮 | 第二轮 |
| --- | ---: | ---: |
| 教师分数平均绝对误差 | {first['score_mae']:.2f} 分 | {second['score_mae']:.2f} 分 |
| 高低档排序准确率 | {first['high_low_pair_accuracy']:.1%} | {second['high_low_pair_accuracy']:.1%} |
| 图纸事实准确率 | {first['fact_accuracy']:.1%} | {second['fact_accuracy']:.1%} |
| 必须问题召回率 | {first['must_issue_recall']:.1%} | {second['must_issue_recall']:.1%} |
| 禁止误报 | {first['forbidden_violation_rate']:.1%} | {second['forbidden_violation_rate']:.1%} |

第二轮把 3 份高分作业都评得更接近教师，但也把 3 份中低分作业全部抬高。因此它改善了高分识别，却没有提高整体精度，MAE 反而增加 1.12 分。这个结果已如实保留，没有筛选或改写。

## 当前结论

系统现在“看图和找问题”已经比较可靠，主要困难是“把看到的质量映射到教师分数”。第二轮评分锚点存在过校准，不适合直接作为默认生产标尺；第一轮是当前两轮中整体误差更小的版本。代码中的生产评分标尺已恢复为第一轮版本，同时保留真实任务书接入和不确定性降级修复。

## 后续建议

下一步应新增一批不参与提示词修改的教师盲评分样本，并把“任务书核心成果覆盖率、跨页证据完整度、概念到空间的转译闭环”做成独立可计算指标，再进行校准。只有在独立测试集上 MAE 和排序同时改善，才适合正式替换生产评分标尺。

详细方法、限制与图表见 [03_两轮测试论文数据报告.md](03_两轮测试论文数据报告.md)。
"""
    write_text(path, content)


def write_reproduction_guide(path: Path, config: dict) -> None:
    """说明数据文件用途与正式轮次复现边界。"""
    content = f"""# 测试数据与复现说明

## 目录用途

- `数据/逐样本分数.csv`：教师分、两轮模型分和逐样本误差。
- `数据/逐Agent分数.csv`：各专项 Agent 分数、人工区间与命中情况。
- `数据/两轮总体指标.csv`：论文表格可直接引用的总体指标。
- `数据/两轮完整统计.json`：两轮完整统计和逐样本明细。
- `数据/人工标准答案.json`：测试完成后使用的教师分数、事实与问题标注，禁止作为模型输入。
- `图表/`：可直接嵌入 Markdown 或转为论文图片的 SVG 图。
- `实验配置/正式实验配置.json`：模型、提示词指纹、任务书哈希和排除数据说明。

## 正式实验范围

- 第一轮：`{config['first_round']}`
- 第二轮：`{config['second_round']}`
- 模型：`{config['model']}`
- 样本：{config['sample_count']} 份

`.benchmark-results/` 中的 `round1` 和 `gemini-round1` 是探索或中断数据，不进入论文统计。正式报告只引用上述两个轮次。

## 复现命令

在 `ArchCritic/backend` 下使用项目虚拟环境：

```bash
.venv/bin/python scripts/benchmark_review.py prepare
.venv/bin/python scripts/benchmark_review.py run --round formal-round1 --provider dashscope --model qwen3.6-plus --workers 2
.venv/bin/python scripts/benchmark_review.py report --round formal-round1 --model qwen3.6-plus
```

第二轮需要使用实验配置中记录的评分锚点快照。大模型服务存在非确定性，复现结果应报告均值与波动，不应期待逐字逐分完全一致。
"""
    write_text(path, content)


def write_prompt_snapshot(path: Path) -> None:
    """保存第二轮课程评分锚点，确保论文方法可追溯。"""
    specialist_text = "\n".join(
        f"- `{agent}`：{text}" for agent, text in SPECIALIST_CALIBRATION.items()
    )
    write_text(
        path,
        f"# 第二轮评分锚点快照\n\n```text\n{COURSE_SCORE_CALIBRATION}\n```\n\n## 专项说明\n\n{specialist_text}\n",
    )


def load_results(path: Path) -> dict[str, dict]:
    """读取某轮全部成功样本结果。"""
    return {item.stem: read_json(item) for item in sorted(path.glob("CASE-*.json"))}


def evaluation_scores(result: dict) -> dict[str, float]:
    """提取专项 Agent 分数。"""
    return {
        item["agent_type"]: float(item["score"])
        for item in result["report"].get("agent_evaluations", [])
    }


def interval_hit(score: float | None, interval: dict) -> bool:
    """判断一个专项分数是否落在人工区间内。"""
    return score is not None and interval["min"] <= score <= interval["max"]


def write_csv(path: Path, rows: list[dict]) -> None:
    """以 UTF-8 BOM 写 CSV，方便中文 Excel 直接打开。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8-sig")
        return
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def read_json(path: Path) -> dict:
    """读取 UTF-8 JSON。"""
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    """写入可读 UTF-8 JSON。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    """写入 UTF-8 文本并保留末尾换行。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")
