"""汇总正式论文实验数据，并生成可复核表格、文字报告和论文图表。"""

from __future__ import annotations

import csv
import json
import math
import shutil
import subprocess
import tempfile
from html import escape
from pathlib import Path

from PIL import Image


PROJECT_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_ROOT = PROJECT_ROOT.parent
DATA_ROOT = (
    WORKSPACE_ROOT
    / "标注基准集与实验数据与论文"
    / "正式论文实验_2026-07-27"
)
METRICS_ROOT = DATA_ROOT / "05_统计结果"
FIGURE_ROOT = (
    WORKSPACE_ROOT
    / "标注基准集与实验数据与论文"
    / "会议论文架构流程图_2026-07-27"
)
CONDITIONS = (
    "c0_direct",
    "c1_structured_single",
    "c2_multi_agent",
    "c3_multi_agent_knowledge",
)
SHORT_NAMES = {
    "c0_direct": "C0 直接评审",
    "c1_structured_single": "C1 结构化单模型",
    "c2_multi_agent": "C2 多 Agent",
    "c3_multi_agent_knowledge": "C3 知识增强",
}
FONT = (
    "'Source Han Sans SC','Noto Sans CJK SC','Microsoft YaHei',"
    "'Droid Sans Fallback',Arial,sans-serif"
)


def read_json(path: Path) -> dict:
    """读取 UTF-8 JSON。"""
    return json.loads(path.read_text(encoding="utf-8"))


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    """以 UTF-8 BOM 写出便于表格软件打开的 CSV。"""
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def load_metrics() -> dict[str, dict]:
    """读取四个条件的冻结指标。"""
    return {
        condition: read_json(METRICS_ROOT / f"{condition}.metrics.json")
        for condition in CONDITIONS
    }


def build_summary_rows(metrics: dict[str, dict]) -> list[dict]:
    """构造四条件总指标表。"""
    rows = []
    for condition in CONDITIONS:
        item = metrics[condition]
        rows.append(
            {
                "条件": condition,
                "条件名称": item["condition_name"],
                "样本数": item["case_count"],
                "MAE": item["score_mae"],
                "RMSE": item["score_rmse"],
                "平均偏差": item["score_mean_bias"],
                "Pearson_r": item["score_pearson_r"],
                "Spearman_rho": item["score_spearman_rho"],
                "必须问题严格命中": item["must_exact_hits"],
                "必须问题总数": item["must_total"],
                "模型意见总数": item["prediction_total"],
                "严格精确率": item["strict_issue_precision"],
                "必须问题召回率": item["must_issue_recall"],
                "严格F1": item["strict_issue_f1"],
                "扩展相关率": item["broader_relevance_precision"],
                "平均耗时秒": item["mean_duration_seconds"],
            }
        )
    return rows


def build_case_rows(metrics: dict[str, dict]) -> list[dict]:
    """构造九个案例的教师分与四条件模型分。"""
    case_maps = {
        condition: {item["case_id"]: item for item in metrics[condition]["cases"]}
        for condition in CONDITIONS
    }
    rows = []
    for case_id in sorted(case_maps[CONDITIONS[0]]):
        teacher_score = case_maps[CONDITIONS[0]][case_id]["teacher_score"]
        if teacher_score >= 90:
            band = "高分"
        elif teacher_score <= 75:
            band = "低分"
        else:
            band = "中分"
        row = {
            "案例": case_id,
            "教师分": teacher_score,
            "教师档位": band,
        }
        for condition in CONDITIONS:
            item = case_maps[condition][case_id]
            row[f"{condition}_模型分"] = item["model_score"]
            row[f"{condition}_绝对误差"] = round(item["absolute_error"], 2)
            row[f"{condition}_严格F1"] = round(item["strict_issue_f1"], 4)
        rows.append(row)
    return rows


def build_band_rows(case_rows: list[dict]) -> list[dict]:
    """按教师高、中、低档汇总模型分，观察评分压缩现象。"""
    rows = []
    for band in ("高分", "中分", "低分"):
        selected = [row for row in case_rows if row["教师档位"] == band]
        row = {
            "教师档位": band,
            "样本数": len(selected),
            "教师均分": round(
                sum(row["教师分"] for row in selected) / len(selected), 2
            ),
        }
        for condition in CONDITIONS:
            values = [row[f"{condition}_模型分"] for row in selected]
            row[f"{condition}_模型均分"] = round(sum(values) / len(values), 2)
        rows.append(row)
    return rows


def svg_header(title: str) -> list[str]:
    """生成统一论文图 SVG 头部。"""
    return [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1800" height="1100" '
        'viewBox="0 0 1800 1100">',
        "<defs>",
        f"<style>text{{font-family:{FONT};fill:#111}}"
        ".title{font-size:32px;font-weight:700;text-anchor:middle}"
        ".section{font-size:25px;font-weight:700;text-anchor:middle}"
        ".body{font-size:21px;text-anchor:middle}"
        ".small{font-size:18px;text-anchor:middle}"
        ".note{font-size:17px;text-anchor:middle;fill:#444}"
        ".box{fill:#fff;stroke:#111;stroke-width:2.5}"
        ".dash{fill:#fff;stroke:#111;stroke-width:2.5;stroke-dasharray:12 9}"
        ".grid{stroke:#bbb;stroke-width:1.3}"
        ".axis{stroke:#111;stroke-width:2.2}"
        ".line0{fill:none;stroke:#111;stroke-width:4}"
        ".line1{fill:none;stroke:#666;stroke-width:4;stroke-dasharray:12 7}"
        ".line2{fill:none;stroke:#111;stroke-width:6}"
        ".line3{fill:none;stroke:#999;stroke-width:4;stroke-dasharray:4 7}"
        "</style>",
        '<marker id="arrow" markerWidth="18" markerHeight="14" refX="15" '
        'refY="7" orient="auto" markerUnits="userSpaceOnUse">'
        '<path d="M0,0 L15,7 L0,14 z" fill="#111"/></marker>',
        "</defs>",
        '<rect width="1800" height="1100" fill="#fff"/>',
        '<rect width="1800" height="72" fill="#ededed"/>',
        f'<text class="title" x="900" y="47">{escape(title)}</text>',
    ]


def text_block(
    parts: list[str],
    x: float,
    y: float,
    lines: list[str],
    css_class: str = "body",
    gap: int = 30,
) -> None:
    """向 SVG 写入人工换行的文字块。"""
    start = y - (len(lines) - 1) * gap / 2
    content = "".join(
        f'<tspan x="{x}" y="{start + index * gap}">{escape(line)}</tspan>'
        for index, line in enumerate(lines)
    )
    parts.append(f'<text class="{css_class}">{content}</text>')


def build_experiment_figure(path: Path) -> None:
    """绘制九案例四条件控制变量实验流程图。"""
    parts = svg_header("九案例四条件控制变量实验流程")
    parts.append('<rect class="dash" x="55" y="105" width="1690" height="155"/>')
    text_block(parts, 900, 140, ["统一匿名输入包：9 份课程图纸，共 36 页"], "section")
    text_block(
        parts,
        900,
        205,
        ["相同任务书 · 相同 qwen3.6-plus · 同一冻结运行 · 教师分与人工问题清单隔离"],
        "body",
    )
    centers = [255, 685, 1115, 1545]
    labels = [
        ("C0", ["直接给图纸", "通用评审"]),
        ("C1", ["结构化提示词增强", "单模型评审"]),
        ("C2", ["专项多 Agent", "协同评审"]),
        ("C3", ["知识增强多 Agent", "探索性评审"]),
    ]
    for x, (code, lines) in zip(centers, labels):
        parts.append(
            f'<line x1="900" y1="260" x2="{x}" y2="335" '
            'stroke="#111" stroke-width="3.5" marker-end="url(#arrow)"/>'
        )
        parts.append(
            f'<rect class="box" x="{x - 180}" y="345" width="360" '
            'height="180" rx="14"/>'
        )
        text_block(parts, x, 390, [code], "section")
        text_block(parts, x, 465, lines, "body")
        parts.append(
            f'<line x1="{x}" y1="525" x2="{x}" y2="615" '
            'stroke="#111" stroke-width="3.5" marker-end="url(#arrow)"/>'
        )
    parts.append('<rect class="dash" x="55" y="625" width="1690" height="155"/>')
    text_block(
        parts,
        900,
        675,
        ["冻结 36 份模型原始报告", "作者依据预先标注清单逐条进行本地严格语义核对"],
        "section",
        38,
    )
    parts.append(
        '<line x1="900" y1="780" x2="900" y2="855" '
        'stroke="#111" stroke-width="4" marker-end="url(#arrow)"/>'
    )
    parts.append('<rect class="box" x="250" y="865" width="1300" height="160" rx="14"/>')
    text_block(
        parts,
        900,
        910,
        ["评分一致性：MAE、RMSE、偏差与相关性", "问题一致性：严格精确率、召回率与 F1"],
        "section",
        40,
    )
    text_block(
        parts,
        900,
        1000,
        ["C0—C2 为主要比较；C3 因知识库尚未完成教师审核，仅作探索性观察"],
        "note",
    )
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")


def polyline_points(values: list[float], left: int, top: int, width: int, height: int) -> str:
    """把 0—100 分数转换为折线坐标。"""
    points = []
    for index, value in enumerate(values):
        x = left + index * width / (len(values) - 1)
        y = top + (100 - value) / 45 * height
        points.append(f"{x:.1f},{y:.1f}")
    return " ".join(points)


def build_result_figure(path: Path, metrics: dict[str, dict]) -> None:
    """绘制评分轨迹和关键指标对比图。"""
    parts = svg_header("四条件正式实验结果")
    left, top, width, height = 110, 145, 1580, 390
    for score in (60, 70, 80, 90, 100):
        y = top + (100 - score) / 45 * height
        parts.append(f'<line class="grid" x1="{left}" y1="{y}" x2="1690" y2="{y}"/>')
        parts.append(f'<text class="small" x="75" y="{y + 6}">{score}</text>')
    teacher = [item["teacher_score"] for item in metrics[CONDITIONS[0]]["cases"]]
    values = {"teacher": teacher}
    for condition in CONDITIONS:
        values[condition] = [
            item["model_score"] for item in metrics[condition]["cases"]
        ]
    styles = {
        "teacher": "line2",
        "c0_direct": "line1",
        "c1_structured_single": "line0",
        "c2_multi_agent": "line3",
        "c3_multi_agent_knowledge": "line1",
    }
    for key, series in values.items():
        points = polyline_points(series, left, top, width, height)
        parts.append(f'<polyline class="{styles[key]}" points="{points}"/>')
    for index in range(9):
        x = left + index * width / 8
        parts.append(f'<text class="small" x="{x}" y="570">案例 {index + 1}</text>')
    legend = [
        ("教师分", "#111", "6", ""),
        ("C0", "#666", "4", "12 7"),
        ("C1", "#111", "4", ""),
        ("C2", "#999", "4", "4 7"),
        ("C3", "#777", "4", "12 7"),
    ]
    for index, (label, color, stroke_width, dash) in enumerate(legend):
        x = 510 + index * 185
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        parts.append(
            f'<line x1="{x}" y1="105" x2="{x + 62}" y2="105" '
            f'stroke="{color}" stroke-width="{stroke_width}"{dash_attr}/>'
        )
        parts.append(f'<text class="small" x="{x + 105}" y="112">{label}</text>')
    parts.append('<rect class="dash" x="70" y="625" width="800" height="395"/>')
    parts.append('<rect class="dash" x="930" y="625" width="800" height="395"/>')
    text_block(parts, 470, 670, ["教师分拟合误差 MAE（越低越好）"], "section")
    text_block(parts, 1330, 670, ["问题识别严格 F1（越高越好）"], "section")
    mae_values = [metrics[key]["score_mae"] for key in CONDITIONS]
    f1_values = [metrics[key]["strict_issue_f1"] for key in CONDITIONS]
    for index, condition in enumerate(CONDITIONS):
        x = 155 + index * 180
        bar_height = mae_values[index] / 14 * 230
        y = 950 - bar_height
        parts.append(
            f'<rect x="{x}" y="{y}" width="105" height="{bar_height}" '
            'fill="#ddd" stroke="#111" stroke-width="2"/>'
        )
        parts.append(f'<text class="body" x="{x + 52}" y="{y - 14}">{mae_values[index]:.2f}</text>')
        parts.append(f'<text class="small" x="{x + 52}" y="988">C{index}</text>')
        x2 = 1015 + index * 180
        f1_height = f1_values[index] / 0.5 * 230
        y2 = 950 - f1_height
        fill = "#111" if condition == "c2_multi_agent" else "#ddd"
        parts.append(
            f'<rect x="{x2}" y="{y2}" width="105" height="{f1_height}" '
            f'fill="{fill}" stroke="#111" stroke-width="2"/>'
        )
        text_color = "#fff" if condition == "c2_multi_agent" else "#111"
        parts.append(
            f'<text class="body" x="{x2 + 52}" y="{y2 + 30}" '
            f'fill="{text_color}" style="fill:{text_color}">{f1_values[index]:.3f}</text>'
        )
        parts.append(f'<text class="small" x="{x2 + 52}" y="988">C{index}</text>')
    text_block(
        parts,
        900,
        1065,
        ["C1、C2 提升了问题清单一致性，但四组均未形成可靠的教师分数拟合"],
        "note",
    )
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")


def find_chrome() -> Path:
    """定位无界面浏览器。"""
    for command in ("chromium", "chromium-browser", "google-chrome", "chrome"):
        resolved = shutil.which(command)
        if resolved:
            return Path(resolved)
    candidates = sorted(
        Path("/root/.cache/ms-playwright").glob(
            "chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell"
        ),
        reverse=True,
    )
    if not candidates:
        raise FileNotFoundError("未找到无界面浏览器，无法导出论文图。")
    return candidates[0]


def export_figure(svg_path: Path) -> None:
    """把 SVG 导出为 300 dpi PNG 和固定版面矢量 PDF。"""
    chrome = find_chrome()
    with tempfile.TemporaryDirectory(
        prefix="archcritic-paper-figure-",
        dir="/tmp",
    ) as temp_name:
        temp_dir = Path(temp_name)
        profile = temp_dir / "profile"
        png_path = svg_path.with_suffix(".png")
        pdf_path = svg_path.with_suffix(".pdf")
        common = [
            str(chrome),
            "--headless",
            "--no-sandbox",
            "--disable-gpu",
            f"--user-data-dir={profile}",
        ]
        subprocess.run(
            [
                *common,
                "--hide-scrollbars",
                "--force-device-scale-factor=2",
                "--window-size=1800,1100",
                f"--screenshot={png_path}",
                svg_path.as_uri(),
            ],
            check=True,
            capture_output=True,
        )
        with Image.open(png_path) as image:
            image.save(png_path, dpi=(300, 300), optimize=True)
        html_path = temp_dir / "figure.html"
        html_path.write_text(
            "<!doctype html><meta charset='utf-8'><style>"
            "@page{size:180mm 110mm;margin:0}html,body{margin:0;width:180mm;height:110mm}"
            "img{display:block;width:180mm;height:110mm}</style>"
            f"<img src='{svg_path.as_uri()}'>",
            encoding="utf-8",
        )
        subprocess.run(
            [
                *common,
                "--no-pdf-header-footer",
                f"--print-to-pdf={pdf_path}",
                html_path.as_uri(),
            ],
            check=True,
            capture_output=True,
        )


def build_markdown_report(
    metrics: dict[str, dict],
    summary_rows: list[dict],
    case_rows: list[dict],
    band_rows: list[dict],
) -> str:
    """生成可直接进入论文写作的实验结果报告。"""
    summary_lines = []
    for row in summary_rows:
        summary_lines.append(
            f"| {SHORT_NAMES[row['条件']]} | {row['MAE']:.2f} | "
            f"{row['RMSE']:.2f} | {row['平均偏差']:+.2f} | "
            f"{row['必须问题严格命中']}/{row['必须问题总数']} | "
            f"{row['严格精确率']:.3f} | {row['必须问题召回率']:.3f} | "
            f"{row['严格F1']:.3f} | {row['平均耗时秒']:.2f} |"
        )
    score_lines = []
    for row in case_rows:
        score_lines.append(
            f"| {row['案例']} | {row['教师档位']} | {row['教师分']:.0f} | "
            + " | ".join(
                f"{row[f'{condition}_模型分']:.1f}" for condition in CONDITIONS
            )
            + " |"
        )
    band_lines = []
    for row in band_rows:
        band_lines.append(
            f"| {row['教师档位']} | {row['样本数']} | {row['教师均分']:.2f} | "
            + " | ".join(
                f"{row[f'{condition}_模型均分']:.2f}" for condition in CONDITIONS
            )
            + " |"
        )
    c0 = metrics["c0_direct"]
    c1 = metrics["c1_structured_single"]
    c2 = metrics["c2_multi_agent"]
    c3 = metrics["c3_multi_agent_knowledge"]
    return f"""# ArchCritic 九案例四条件正式实验结果报告

生成日期：2026 年 7 月 27 日

实验模型：qwen3.6-plus

有效样本：9 份；模型报告：36 份；图纸页面：36 页

核对口径：教师原始成绩作为分数基准，团队既有人工标注清单作为问题基准；未进行新增教师复核。

## 1. 四条件总结果

| 条件 | MAE | RMSE | 平均偏差 | 严格命中 | 严格精确率 | 召回率 | 严格 F1 | 平均耗时/s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
{chr(10).join(summary_lines)}

## 2. 九案例评分

| 案例 | 教师档位 | 教师分 | C0 | C1 | C2 | C3 |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
{chr(10).join(score_lines)}

## 3. 按教师档位汇总

| 教师档位 | n | 教师均分 | C0 均分 | C1 均分 | C2 均分 | C3 均分 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
{chr(10).join(band_lines)}

## 4. 结果解释

1. C0、C1、C2 的严格问题 F1 依次为 {c0['strict_issue_f1']:.4f}、{c1['strict_issue_f1']:.4f} 和 {c2['strict_issue_f1']:.4f}。相对 C0，C1 提高 {((c1['strict_issue_f1'] / c0['strict_issue_f1']) - 1) * 100:.1f}%；C2 提高 {((c2['strict_issue_f1'] / c0['strict_issue_f1']) - 1) * 100:.1f}%。这支持“结构化约束和多 Agent 专项分工有助于问题发现”的形成性结论。
2. C2 的严格召回率为 {c2['must_issue_recall']:.4f}，高于 C0 的 {c0['must_issue_recall']:.4f} 和 C1 的 {c1['must_issue_recall']:.4f}；但严格精确率为 {c2['strict_issue_precision']:.4f}，略低于 C1 的 {c1['strict_issue_precision']:.4f}。即多 Agent 找到更多人工必须问题，也产生了更多未被严格计为命中的意见。
3. 四组 MAE 为 {c0['score_mae']:.2f}—{c3['score_mae']:.2f} 分，C1 和 C2 均未优于 C0。C0、C1 的输出集中在 82 分附近，C2 虽扩大了分布范围，但仍低估高分作品并高估低分作品。由此不能把系统分数作为课程成绩。
4. C3 的严格问题 F1 为 {c3['strict_issue_f1']:.4f}，低于 C2；MAE 为 {c3['score_mae']:.2f}，也是四组中最高。由于当前知识库尚未完成教师逐条审核和针对性优化，C3 仅能视为探索性结果。
5. 本次严格语义核对只评价问题清单的一致性，没有重新计算图纸事实状态准确率；不得沿用开发期 97.4% 等结果描述本次实验。
6. 样本量仅为 9，来源单一，且问题标注由团队既有材料提供、未取得独立教师复核。本报告只作描述性比较，不进行显著性推断，也不声称达到教师水平。

## 5. 论文可采用的结论

在相同模型和匿名图纸输入下，结构化提示词使严格问题 F1 从 {c0['strict_issue_f1']:.3f} 提升至 {c1['strict_issue_f1']:.3f}，多 Agent 专项协同进一步提升至 {c2['strict_issue_f1']:.3f}；但三者的教师分数 MAE 分别为 {c0['score_mae']:.2f}、{c1['score_mae']:.2f} 和 {c2['score_mae']:.2f}，并未同步改善。结果表明，当前 ArchCritic 的相对优势在于辅助发现和组织图纸问题，而不是拟合教师综合成绩。

## 6. 数据与图表文件

- `condition_summary.csv`：四条件总指标。
- `case_level_scores.csv`：九案例逐条件分数、误差和问题 F1。
- `score_band_summary.csv`：教师高、中、低档的均值对照。
- 图 8：九案例四条件实验流程。
- 图 9：教师分轨迹、MAE 与严格问题 F1 对比。
"""


def main() -> None:
    """生成全部统计交付物并进行基本一致性检查。"""
    metrics = load_metrics()
    summary_rows = build_summary_rows(metrics)
    case_rows = build_case_rows(metrics)
    band_rows = build_band_rows(case_rows)
    write_csv(
        METRICS_ROOT / "condition_summary.csv",
        summary_rows,
        list(summary_rows[0]),
    )
    write_csv(
        METRICS_ROOT / "case_level_scores.csv",
        case_rows,
        list(case_rows[0]),
    )
    write_csv(
        METRICS_ROOT / "score_band_summary.csv",
        band_rows,
        list(band_rows[0]),
    )
    report = build_markdown_report(metrics, summary_rows, case_rows, band_rows)
    (METRICS_ROOT / "正式实验结果报告.md").write_text(report, encoding="utf-8")
    experiment_figure = FIGURE_ROOT / "图8_九案例四条件控制变量实验流程.svg"
    result_figure = FIGURE_ROOT / "图9_四条件正式实验结果.svg"
    build_experiment_figure(experiment_figure)
    build_result_figure(result_figure, metrics)
    export_figure(experiment_figure)
    export_figure(result_figure)
    assert all(item["case_count"] == 9 for item in metrics.values())
    assert sum(item["case_count"] for item in metrics.values()) == 36
    assert math.isclose(
        metrics["c2_multi_agent"]["strict_issue_f1"], 0.4234, abs_tol=0.0001
    )
    print("实验报告、3 份数据表和 2 张论文图已生成；一致性检查通过。")


if __name__ == "__main__":
    main()
