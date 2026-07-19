"""导出证据优先架构的校准、盲测、论文数据和可视化报告。"""

from __future__ import annotations

import csv
from datetime import datetime
from html import escape
import json
from pathlib import Path
from statistics import mean

from app.scoring.calibration import predict_calibrated_score


def export_evidence_v2_package(
    prepared_root: Path,
    results_root: Path,
    output_root: Path,
    calibration_round: str,
    blind_round: str,
    baseline_round: str,
) -> dict:
    """汇总四份校准和两份盲测，生成可复核的完整本地数据包。"""
    calibrator = read_json(prepared_root / "evidence_v2_calibration.json")
    split = calibrator["evaluation_split"]
    train_ids = split["train_case_ids"]
    heldout_ids = split["heldout_case_ids"]
    truth = {
        item["case_id"]: item
        for item in read_json(prepared_root / "ground_truth.json")["cases"]
    }
    baseline = {
        item["case_id"]: item
        for item in read_json(results_root / baseline_round / "metrics.json")["cases"]
    }
    calibration_results = load_required_results(
        results_root / calibration_round, train_ids, "校准"
    )
    blind_results = load_required_results(results_root / blind_round, heldout_ids, "盲测")
    rows = build_rows(
        train_ids,
        heldout_ids,
        calibration_results,
        blind_results,
        truth,
        baseline,
        calibrator,
    )
    output_root.mkdir(parents=True, exist_ok=True)
    write_csv(output_root / "03_逐样本科研数据.csv", rows)
    write_json(
        output_root / "实验配置.json",
        {
            "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "provider": "dashscope",
            "model": "qwen3.6-plus",
            "architecture": "evidence_v2",
            "calibration_round": calibration_round,
            "blind_round": blind_round,
            "baseline_round": baseline_round,
            "split": split,
            "calibrator": calibrator,
            "teacher_scores_sent_to_review_agents": False,
            "heldout_scores_used_for_fit": False,
        },
    )
    write_architecture_report(output_root / "01_新版评分架构说明.md")
    summary = summarize(rows, heldout_ids)
    write_result_report(output_root / "02_校准与盲测结果.md", rows, summary, calibrator)
    write_blind_error_chart(output_root / "04_盲测误差对比.svg", rows, heldout_ids)
    write_work_report(output_root / "05_工作总结报告.md", rows, summary)
    write_reproduction_notes(output_root / "06_复现与限制说明.md", calibrator)
    return summary


def load_required_results(root: Path, case_ids: list[str], label: str) -> dict[str, dict]:
    """读取指定结果；缺任一预注册样本时拒绝生成不完整结论。"""
    results = {}
    for case_id in case_ids:
        path = root / f"{case_id}.json"
        if not path.is_file():
            raise ValueError(f"{label}结果缺失：{case_id}")
        results[case_id] = read_json(path)
    return results


def build_rows(
    train_ids: list[str],
    heldout_ids: list[str],
    calibration_results: dict[str, dict],
    blind_results: dict[str, dict],
    truth: dict[str, dict],
    baseline: dict[str, dict],
    calibrator: dict,
) -> list[dict]:
    """整理训练与盲测的统一逐样本数据表。"""
    rows = []
    for case_id in train_ids + heldout_ids:
        split = "calibration" if case_id in train_ids else "heldout"
        result = calibration_results.get(case_id) or blind_results[case_id]
        report = result["report"]
        scoring = report["evaluation_context"]["scoring"]
        teacher_score = float(truth[case_id]["teacher_score"])
        raw_score = float(scoring["raw_score"])
        calibrated_score = (
            predict_calibrated_score(raw_score, calibrator)
            if split == "calibration"
            else float(report["overall_score"])
        )
        rows.append(
            {
                "case_id": case_id,
                "split": split,
                "design_stage": truth[case_id]["design_stage"],
                "teacher_score": teacher_score,
                "baseline_score": float(baseline[case_id]["overall_score"]),
                "baseline_absolute_error": float(baseline[case_id]["absolute_error"]),
                "quality_score": scoring.get("quality_score"),
                "compliance_score": scoring.get("compliance_score"),
                "raw_score": raw_score,
                "calibrated_score": calibrated_score,
                "calibrated_absolute_error": round(abs(calibrated_score - teacher_score), 1),
                "score_interval_low": scoring.get("score_interval", [None, None])[0],
                "score_interval_high": scoring.get("score_interval", [None, None])[1],
                "fact_accuracy": result_ratio(result, "fact_results", "correct", False),
                "must_issue_recall": result_ratio(
                    result, "must_issue_results", "matched", False
                ),
                "forbidden_violation_rate": result_ratio(
                    result, "forbidden_results", "violated", False
                ),
                "prompt_fingerprint": result.get("prompt_fingerprint", ""),
            }
        )
    return rows


def result_ratio(result: dict, group: str, flag: str, default: bool) -> float | None:
    """计算一份报告的裁判布尔命中比例。"""
    items = result.get("judge", {}).get(group, [])
    if not items:
        return None
    return round(sum(bool(item.get(flag, default)) for item in items) / len(items), 4)


def summarize(rows: list[dict], heldout_ids: list[str]) -> dict:
    """计算只面向两份独立盲测的核心误差结论。"""
    heldout = [item for item in rows if item["case_id"] in heldout_ids]
    baseline_mae = mean(item["baseline_absolute_error"] for item in heldout)
    new_mae = mean(item["calibrated_absolute_error"] for item in heldout)
    by_id = {item["case_id"]: item for item in heldout}
    return {
        "heldout_case_count": len(heldout),
        "baseline_mae": round(baseline_mae, 2),
        "evidence_v2_mae": round(new_mae, 2),
        "mae_change": round(new_mae - baseline_mae, 2),
        "mae_improvement_rate": round((baseline_mae - new_mae) / baseline_mae, 4),
        "blind_rank_correct": by_id[heldout_ids[0]]["calibrated_score"]
        > by_id[heldout_ids[1]]["calibrated_score"],
        "improved_cases": sum(
            item["calibrated_absolute_error"] < item["baseline_absolute_error"]
            for item in heldout
        ),
    }


def write_architecture_report(path: Path) -> None:
    """写出新版四层评分流程和建筑学规则。"""
    content = """# ArchCritic 新版评图评分架构

## 核心变化

新版把过去一次模型调用同时“识图并打分”的方式拆成四层：

1. **任务书规则层**：把要求标为强制、弹性、选配、参考或一般说明，并分配给对应专项。选配与参考项不扣分。
2. **结构化证据层**：各 Agent 只输出可见事实、来源、置信度、任务书符合状态和 0—4 级专项判断，不接触教师分，也不直接输出 0—100 分。
3. **确定性评分层**：后端按固定映射把等级换算为专项分，再按任务书动态权重合成。低置信观察不进入“必须修改”。
4. **教师评分校准层**：使用预先固定的四份校准样本拟合单调映射，只调整最终总分标尺，不修改证据、问题和专项原始判断。

## 建筑学等级规则

- 4 级：专项逻辑鲜明，跨图纸形成闭环，达到当前年级优秀水平；允许存在下一阶段才处理的细节。
- 3 级：主线清楚，大部分有证据，局部问题不破坏总体成立。
- 2 级：基本框架成立，但证据闭环、空间转译或成果完整度一般。
- 1 级：关键关系薄弱、矛盾或明显不完整。
- 0 级：缺少当前专项关键成果，或确认存在使其难以成立的核心问题。

## 兼容方式

数据库和前端继续读取原有综合分、专项分和报告字段；新版证据记录、校准版本、原始分与区间保存在 `evaluation_context.scoring` 和专项 `details` 中。旧流程仍可通过 `legacy_v1` 显式回退。
"""
    write_text(path, content)


def write_result_report(path: Path, rows: list[dict], summary: dict, calibrator: dict) -> None:
    """写出校准集和独立盲测的科研结果报告。"""
    table = "\n".join(
        f"| {item['case_id']} | {item['split']} | {item['teacher_score']:g} | "
        f"{item['baseline_score']:g} | {item['raw_score']:g} | {item['calibrated_score']:g} | "
        f"{item['calibrated_absolute_error']:g} |"
        for item in rows
    )
    direction = "下降" if summary["mae_change"] < 0 else "上升"
    content = f"""# 证据优先架构：校准与盲测结果

生成时间：{datetime.now().astimezone().isoformat(timespec='seconds')}  
模型：`qwen3.6-plus`  
校准样本：4 份；独立盲测：2 份

## 数据隔离

校准集固定为 CASE-001、CASE-003、CASE-004、CASE-005；盲测集固定为 CASE-002、CASE-006。盲测教师分未参与提示词、证据判断或校准拟合，只在两份模型报告写入后用于统计。

## 逐样本结果

| 样本 | 划分 | 教师分 | 旧流程分 | 新架构原始分 | 校准后分 | 校准后绝对误差 |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
{table}

## 独立盲测结论

- 旧流程盲测 MAE：{summary['baseline_mae']:.2f} 分。
- 新架构盲测 MAE：{summary['evidence_v2_mae']:.2f} 分，较旧流程{direction} {abs(summary['mae_change']):.2f} 分。
- 两份盲测中改善 {summary['improved_cases']}/2；高低分排序是否正确：{'是' if summary['blind_rank_correct'] else '否'}。
- 四份校准样本的单调拟合训练残差 MAE 为 {calibrator['training_mae']:.3f} 分，说明当前小样本中仍存在模型原始等级与教师判断冲突，不能把校准器视为稳定通用标尺。

## 解释边界

这次结果只证明当前模型、当前六份同课程样本上的表现。两份盲测足以检查流程是否泄漏和方向是否改善，但不足以证明泛化能力或统计显著性。后续论文应把中档样本和更多课程教师评分作为新的外部测试集，冻结本版代码后再评估。
"""
    write_text(path, content)


def write_work_report(path: Path, rows: list[dict], summary: dict) -> None:
    """用通俗语言汇报已完成的系统工作。"""
    content = f"""# ArchCritic 新版评分系统工作总结

## 已完成

- 任务书已经从普通文本摘要升级为可核对规则，能区分强制、弹性、选配和参考内容。
- 各专项 Agent 不再直接决定 0—100 分，而是先交付图纸事实、来源、置信度和建筑学等级。
- 后端按统一规则换算专项分、合成任务书符合度，并保存原始分、校准分和不确定区间。
- 教师校准使用两份高分、两份低分；另外一高一低严格作为盲测，不参与拟合。
- 历史报告、前端评分卡和数据库字段保持兼容，旧流程仍可回退。
- 已补齐百炼代理连接、瞬时连接重试和长 JSON 截断处理。

## 测试结果

两份独立盲测的旧流程 MAE 为 {summary['baseline_mae']:.2f} 分，新架构为 {summary['evidence_v2_mae']:.2f} 分；两份中改善 {summary['improved_cases']}/2。详细逐样本数据见 `03_逐样本科研数据.csv`，可视化见 `04_盲测误差对比.svg`。

## 需要谨慎理解的地方

只有四份校准和两份盲测，且来自同一课程。校准层现在适合作为本地研究原型和分数风险提示，不能替代教师成绩，也不应宣称已经达到稳定教学测评精度。

## 上线决定

由于两份盲测的高低排序失败，且低分样本被抬高到 85.4 分，本地产品默认继续使用 `legacy_v1`。新版完整链路保留为 `evidence_v2` 研究模式，避免把尚未验证稳定的校准分直接展示给学生形成错误预期。
"""
    write_text(path, content)


def write_reproduction_notes(path: Path, calibrator: dict) -> None:
    """记录论文复现命令、版本和已知限制。"""
    content = f"""# 新版证据校准实验复现说明

## 固定划分

- 校准：CASE-001、CASE-003、CASE-004、CASE-005
- 盲测：CASE-002、CASE-006
- 校准方法：`{calibrator['method']}`
- 校准版本：`{calibrator['version']}`
- 盲测分数参与拟合：否

## 命令

```bash
cd /mnt/e/claude/论文/ArchCritic/backend
./.venv/bin/python scripts/benchmark_review.py prepare
./.venv/bin/python scripts/benchmark_review.py run --round evidence-v2-calibration-raw --provider dashscope --model qwen3.6-plus --workers 1 --architecture evidence_v2 --cases CASE-001 CASE-003 CASE-004 CASE-005
./.venv/bin/python scripts/benchmark_review.py calibrate --round evidence-v2-calibration-raw --train CASE-001 CASE-003 CASE-004 CASE-005 --heldout CASE-002 CASE-006
./.venv/bin/python scripts/benchmark_review.py run --round evidence-v2-blind-test --provider dashscope --model qwen3.6-plus --workers 1 --architecture evidence_v2 --calibration-file ../标注基准集/.prepared/evidence_v2_calibration.json --cases CASE-002 CASE-006
./.venv/bin/python scripts/benchmark_review.py evidence-export
```

## 限制

样本量极小、同源性高；CASE-003 为低清来源；多模态模型存在随机性；教师分是课程总评，而系统读取的成果图与课堂过程信息并不完全等价。因此报告同时保留原始分、校准分和区间，不把单点分数包装成绝对结论。
"""
    write_text(path, content)


def write_blind_error_chart(path: Path, rows: list[dict], heldout_ids: list[str]) -> None:
    """生成两份盲测旧流程与新版绝对误差的横向对比图。"""
    heldout = [item for item in rows if item["case_id"] in heldout_ids]
    width, height = 980, 390
    left, top, plot_width = 190, 120, 680
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#FFFFFF"/>',
        svg_text(48, 48, "两份独立盲测绝对误差（越低越好）", 24, "start", "#111827", 700),
    ]
    maximum = max(20.0, *(item["baseline_absolute_error"] for item in heldout))
    for index, item in enumerate(heldout):
        y = top + index * 105
        parts.append(svg_text(left - 18, y + 25, item["case_id"], 15, "end", "#334155", 600))
        for offset, key, color, label in (
            (0, "baseline_absolute_error", "#64748B", "旧流程"),
            (34, "calibrated_absolute_error", "#7C3AED", "证据+校准"),
        ):
            value = float(item[key])
            bar_width = value / maximum * plot_width
            parts.append(
                f'<rect x="{left}" y="{y+offset}" width="{bar_width:.1f}" height="22" rx="5" fill="{color}"/>'
            )
            parts.append(svg_text(left + bar_width + 8, y + offset + 17, f"{value:g}", 13, "start", color))
            if index == 0:
                parts.append(svg_text(left + index * 120 + (0 if offset == 0 else 100), 88, label, 13, "start", color, 600))
    parts.append("</svg>")
    write_text(path, "\n".join(parts))


def svg_text(
    x: float, y: float, value: str, size: int, anchor: str, color: str, weight: int = 400
) -> str:
    """生成带中文字体回退的 SVG 文本。"""
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" fill="{color}" '
        f'font-size="{size}" font-weight="{weight}" '
        'font-family="Inter, Noto Sans CJK SC, Microsoft YaHei, sans-serif">'
        f"{escape(str(value))}</text>"
    )


def write_csv(path: Path, rows: list[dict]) -> None:
    """写入带 UTF-8 BOM 的 CSV，便于 Excel 直接打开中文。"""
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def read_json(path: Path) -> dict:
    """读取 UTF-8 JSON。"""
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict) -> None:
    """写入可复核的 UTF-8 JSON。"""
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    """以 UTF-8 保存 Markdown 或 SVG 文本。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")
