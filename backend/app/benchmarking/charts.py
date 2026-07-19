"""生成 ArchCritic 两轮基准报告使用的轻量 SVG 图表。"""

from __future__ import annotations

from html import escape
from pathlib import Path


COLORS = {"teacher": "#111827", "first": "#64748B", "second": "#E56B3F"}


def write_score_bar_chart(path: Path, rows: list[dict]) -> None:
    """生成逐样本教师分与两轮模型分柱状图。"""
    width, height = 1080, 600
    left, top, plot_width, plot_height = 90, 100, 920, 390
    parts = svg_start(width, height, "逐样本教师分与两轮模型分")
    for value in range(50, 101, 10):
        y = top + plot_height - (value - 50) / 50 * plot_height
        parts.append(f'<line x1="{left}" y1="{y:.1f}" x2="{left+plot_width}" y2="{y:.1f}" stroke="#E5E7EB"/>')
        parts.append(svg_text(left - 14, y + 5, str(value), 14, "end", "#64748B"))
    group_width = plot_width / len(rows)
    bar_width = 28
    for index, row in enumerate(rows):
        center = left + group_width * (index + 0.5)
        for offset, key, color in (
            (-bar_width, "teacher_score", COLORS["teacher"]),
            (0, "round1_score", COLORS["first"]),
            (bar_width, "round2_score", COLORS["second"]),
        ):
            value = row[key]
            bar_height = (value - 50) / 50 * plot_height
            x = center + offset - bar_width / 2
            y = top + plot_height - bar_height
            parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_width-4}" height="{bar_height:.1f}" rx="4" fill="{color}"/>')
            parts.append(svg_text(x + (bar_width - 4) / 2, y - 7, f"{value:g}", 12, "middle", color))
        parts.append(svg_text(center, top + plot_height + 32, row["case_id"], 14, "middle", "#334155"))
    add_legend(parts, 690, 48)
    parts.append("</svg>")
    write_text(path, "\n".join(parts))


def write_scatter_chart(path: Path, rows: list[dict]) -> None:
    """生成两轮教师分与模型分散点图。"""
    width, height = 1080, 560
    parts = svg_start(width, height, "教师分与模型分数一致性")
    for panel, key, title, color in (
        (0, "round1_score", "第一轮", COLORS["first"]),
        (1, "round2_score", "第二轮", COLORS["second"]),
    ):
        left = 90 + panel * 510
        top, size = 100, 370
        parts.append(svg_text(left + size / 2, 65, title, 20, "middle", "#111827", 600))
        for value in range(60, 101, 10):
            position = (value - 55) / 45 * size
            x = left + position
            y = top + size - position
            parts.append(f'<line x1="{x:.1f}" y1="{top}" x2="{x:.1f}" y2="{top+size}" stroke="#F1F5F9"/>')
            parts.append(f'<line x1="{left}" y1="{y:.1f}" x2="{left+size}" y2="{y:.1f}" stroke="#F1F5F9"/>')
            parts.append(svg_text(x, top + size + 25, str(value), 12, "middle", "#64748B"))
            parts.append(svg_text(left - 12, y + 4, str(value), 12, "end", "#64748B"))
        parts.append(f'<line x1="{left}" y1="{top+size}" x2="{left+size}" y2="{top}" stroke="#94A3B8" stroke-dasharray="6 6"/>')
        for row in rows:
            x = left + (row["teacher_score"] - 55) / 45 * size
            y = top + size - (row[key] - 55) / 45 * size
            parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="7" fill="{color}" opacity="0.9"/>')
            parts.append(svg_text(x + 9, y - 9, row["case_id"].removeprefix("CASE-"), 11, "start", color))
        parts.append(svg_text(left + size / 2, height - 30, "教师分数", 14, "middle", "#475569"))
    parts.append(svg_text(25, 285, "模型分数", 14, "middle", "#475569"))
    parts.append("</svg>")
    write_text(path, "\n".join(parts))


def write_error_chart(path: Path, rows: list[dict]) -> None:
    """生成逐样本两轮绝对误差横向对比图。"""
    width, height = 1080, 570
    left, top, plot_width = 180, 105, 800
    parts = svg_start(width, height, "逐样本绝对误差（越低越好）")
    for value in range(0, 26, 5):
        x = left + value / 25 * plot_width
        parts.append(f'<line x1="{x:.1f}" y1="{top-20}" x2="{x:.1f}" y2="{top+390}" stroke="#E5E7EB"/>')
        parts.append(svg_text(x, top - 32, str(value), 13, "middle", "#64748B"))
    for index, row in enumerate(rows):
        y = top + index * 65
        parts.append(svg_text(left - 20, y + 9, row["case_id"], 14, "end", "#334155"))
        for offset, key, color in (
            (-9, "round1_absolute_error", COLORS["first"]),
            (12, "round2_absolute_error", COLORS["second"]),
        ):
            value = row[key]
            bar_width = value / 25 * plot_width
            parts.append(f'<rect x="{left}" y="{y+offset}" width="{bar_width:.1f}" height="16" rx="4" fill="{color}"/>')
            parts.append(svg_text(left + bar_width + 8, y + offset + 13, f"{value:g}", 12, "start", color))
    add_legend(parts, 700, 48, include_teacher=False)
    parts.append("</svg>")
    write_text(path, "\n".join(parts))


def svg_start(width: int, height: int, title: str) -> list[str]:
    """返回统一风格的 SVG 开头和标题。"""
    return [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#FFFFFF"/>',
        svg_text(48, 45, title, 24, "start", "#0F172A", 700),
    ]


def svg_text(x: float, y: float, value: str, size: int, anchor: str, color: str, weight: int = 400) -> str:
    """创建带中文字体回退的 SVG 文本。"""
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" fill="{color}" '
        f'font-size="{size}" font-weight="{weight}" font-family="Inter, Noto Sans CJK SC, Microsoft YaHei, sans-serif">'
        f"{escape(str(value))}</text>"
    )


def add_legend(parts: list[str], x: int, y: int, include_teacher: bool = True) -> None:
    """向图表加入统一图例。"""
    items = [("教师分", COLORS["teacher"])] if include_teacher else []
    items.extend((("第一轮", COLORS["first"]), ("第二轮", COLORS["second"])))
    for index, (label, color) in enumerate(items):
        item_x = x + index * 120
        parts.append(f'<rect x="{item_x}" y="{y-12}" width="18" height="12" rx="3" fill="{color}"/>')
        parts.append(svg_text(item_x + 26, y, label, 13, "start", "#475569"))


def write_text(path: Path, content: str) -> None:
    """写入 UTF-8 SVG。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")
