"""生成矢量评图 PDF，集中处理中文字体、分页、专项小分和报告排版。"""

from __future__ import annotations

from functools import lru_cache
from io import BytesIO
import re
import subprocess
from types import SimpleNamespace
from typing import Any

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont, TTFError
from reportlab.pdfgen.canvas import Canvas


PAGE_WIDTH, PAGE_HEIGHT = A4
MARGIN = 42
CONTENT_WIDTH = PAGE_WIDTH - MARGIN * 2
INK = HexColor("#171719")
MUTED = HexColor("#626772")
PURPLE = HexColor("#6C4DFF")
LINE = HexColor("#E6E8ED")
FEEDBACK_TONES = {
    "必须修改": HexColor("#D84F4F"),
    "重点优化": HexColor("#E58B2A"),
    "建议关注": HexColor("#4A73D9"),
    "当前优势": HexColor("#2F9B6A"),
}
FONT_CJK = "ArchCriticCJK"
FONT_LATIN = "ArchCriticLatin"
LATIN_SYMBOLS = set("“”‘’—–·…")


@lru_cache(maxsize=1)
def _system_font_paths() -> tuple[str, str]:
    """从系统字体配置分别选择中文和拉丁字体。"""
    try:
        chinese_result = subprocess.run(
            ["fc-list", "-f", "%{file}\n", ":lang=zh"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        latin_result = subprocess.run(
            ["fc-match", "-f", "%{file}", "sans-serif"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.SubprocessError) as exc:
        raise RuntimeError("服务器未找到可用字体，请安装 fontconfig 和中文字体。") from exc
    chinese_path = next((line.strip() for line in chinese_result.stdout.splitlines() if line.strip()), "")
    latin_path = latin_result.stdout.strip()
    if not chinese_path or not latin_path:
        raise RuntimeError("服务器未找到可用的中文与拉丁字体。")
    return chinese_path, latin_path


@lru_cache(maxsize=1)
def _register_fonts() -> tuple[str, str]:
    """优先嵌入系统字体，不兼容时回退到 PDF 标准中文字体。"""
    chinese_path, latin_path = _system_font_paths()
    try:
        pdfmetrics.registerFont(TTFont(FONT_CJK, chinese_path))
        chinese_font = FONT_CJK
    except (OSError, TTFError):
        # 部分 Linux 中文字体使用 CFF 轮廓，ReportLab 的 TTFont 无法读取。
        chinese_font = "STSong-Light"
        pdfmetrics.registerFont(UnicodeCIDFont(chinese_font))
    pdfmetrics.registerFont(TTFont(FONT_LATIN, latin_path))
    return chinese_font, FONT_LATIN


def _font_name(char: str) -> str:
    """为每个字符选择具备对应字形的字体。"""
    chinese_font, latin_font = _register_fonts()
    return latin_font if ord(char) <= 127 or char in LATIN_SYMBOLS else chinese_font


def _clean_text(value: Any) -> str:
    """清理 Markdown、不可见控制字符和替代字符。"""
    text = str(value or "").replace("\ufffd", "")
    text = re.sub(r"[\u0000-\u0008\u000b\u000c\u000e-\u001f]", "", text)
    text = text.replace("**", "").replace("__", "")
    return re.sub(r"\s+", " ", text).strip()


def _text_width(text: str, size: float) -> float:
    """计算中英文混排文字的矢量宽度。"""
    return sum(pdfmetrics.stringWidth(char, _font_name(char), size) for char in text)


def _wrap_text(text: Any, size: float, width: float) -> list[str]:
    """按 PDF 实际字宽换行，避免标点单独落在下一行。"""
    clean = _clean_text(text)
    if not clean:
        return []
    lines: list[str] = []
    current = ""
    for char in clean:
        candidate = current + char
        if current and _text_width(candidate, size) > width and char not in "，。！？；：、,.!?;:）)]}":
            lines.append(current.rstrip())
            current = char.lstrip()
        else:
            current = candidate
    if current:
        lines.append(current.rstrip())
    return lines


def _draw_mixed(
    pdf: Canvas,
    x: float,
    y: float,
    text: Any,
    size: float,
    color: Any,
    *,
    bold: bool = False,
) -> float:
    """用嵌入字体逐段绘制矢量文字，返回文字结束位置。"""
    clean = _clean_text(text)
    pdf.setFillColor(color)
    cursor = x
    run = ""
    run_font = ""
    for char in clean + "\0":
        char_font = _font_name(char) if char != "\0" else ""
        if run and char_font != run_font:
            pdf.setFont(run_font, size)
            pdf.drawString(cursor, y, run)
            if bold:
                pdf.drawString(cursor + 0.16, y, run)
            cursor += pdfmetrics.stringWidth(run, run_font, size)
            run = ""
        if char != "\0":
            run_font = char_font
            run += char
    return cursor


def _sub_scores(evaluation: Any) -> list[dict[str, Any]]:
    """从专项评价中提取页面使用的具体小分。"""
    raw_details = getattr(evaluation, "details", {})
    details = raw_details if isinstance(raw_details, dict) else {}
    values = details.get("sub_scores")
    if not isinstance(values, dict):
        return []
    result = []
    for name, raw in values.items():
        item = raw if isinstance(raw, dict) else {}
        score = raw if isinstance(raw, (int, float)) else item.get("score", 0)
        maximum = item.get("max_score", 25)
        reason = item.get("reason") or item.get("evidence") or evaluation.summary
        result.append({"name": str(name), "score": score, "maximum": maximum, "reason": str(reason)})
    return result[:4]


class ReportDocument:
    """维护 A4 页面、自动分页和报告组件。"""

    def __init__(self) -> None:
        _register_fonts()
        self.output = BytesIO()
        self.pdf = Canvas(self.output, pagesize=A4, pageCompression=1)
        self.page_number = 1
        self.y = PAGE_HEIGHT - MARGIN

    def _footer(self) -> None:
        """绘制统一页脚。"""
        _draw_mixed(self.pdf, MARGIN, 26, f"ArchCritic | AI 建筑评图报告    {self.page_number}", 7.5, HexColor("#9297A1"))

    def new_page(self) -> None:
        """结束当前页并开始下一页。"""
        self._footer()
        self.pdf.showPage()
        self.page_number += 1
        self.y = PAGE_HEIGHT - MARGIN

    def ensure(self, height: float) -> None:
        """剩余空间不足时自动分页。"""
        if self.y - height < 42:
            self.new_page()

    def section_title(self, title: str, count: int | None = None) -> None:
        """绘制二级章节标题。"""
        self.ensure(30)
        self.pdf.setFillColor(PURPLE)
        self.pdf.roundRect(MARGIN, self.y - 15, 2.5, 13, 1.25, stroke=0, fill=1)
        label = f"{title}  {count}" if count is not None else title
        _draw_mixed(self.pdf, MARGIN + 10, self.y - 15, label, 13, INK, bold=True)
        self.y -= 30

    def paragraph(self, text: Any, *, size: float = 10.5, color: Any = MUTED, gap: float = 12) -> None:
        """绘制可分页正文。"""
        line_height = size * 1.72
        for line in _wrap_text(text, size, CONTENT_WIDTH):
            self.ensure(line_height)
            _draw_mixed(self.pdf, MARGIN, self.y - size, line, size, color)
            self.y -= line_height
        self.y -= gap

    def dimension(self, evaluation: Any) -> None:
        """按前端报告结构绘制单层专项评分和横排具体小分。"""
        items = _sub_scores(evaluation)
        summary_lines = _wrap_text(evaluation.summary, 9, CONTENT_WIDTH - 4)
        column_width = CONTENT_WIDTH / max(1, len(items))
        reason_width = column_width - 18
        reason_lines = [_wrap_text(item["reason"], 7.5, reason_width) for item in items]
        detail_height = max((42 + len(lines) * 11.5 for lines in reason_lines), default=0)
        height = 30 + max(1, len(summary_lines)) * 14 + (18 + detail_height if items else 5)
        self.ensure(height + 18)

        top = self.y
        title = str(evaluation.dimension)
        score = f"{round(float(evaluation.score))} 分"
        _draw_mixed(self.pdf, MARGIN, top - 13, title, 12, INK, bold=True)
        _draw_mixed(self.pdf, PAGE_WIDTH - MARGIN - _text_width(score, 11), top - 13, score, 11, PURPLE, bold=True)
        line_y = top - 32
        for line in summary_lines or ["暂无专项说明"]:
            _draw_mixed(self.pdf, MARGIN, line_y, line, 9, MUTED)
            line_y -= 14

        if items:
            detail_top = line_y - 5
            self.pdf.setStrokeColor(LINE)
            self.pdf.setLineWidth(0.7)
            self.pdf.line(MARGIN, detail_top + 8, PAGE_WIDTH - MARGIN, detail_top + 8)
            for index, (item, lines) in enumerate(zip(items, reason_lines)):
                left = MARGIN + index * column_width
                if index:
                    self.pdf.line(left, detail_top + 1, left, detail_top - detail_height + 8)
                content_left = left + (9 if index else 0)
                _draw_mixed(self.pdf, content_left, detail_top - 10, item["name"], 8.5, INK, bold=True)
                sub_score = f"{round(float(item['score']))} / {round(float(item['maximum']))}"
                _draw_mixed(self.pdf, content_left, detail_top - 26, sub_score, 9.5, PURPLE, bold=True)
                reason_y = detail_top - 43
                for reason_line in lines or ["暂无说明"]:
                    _draw_mixed(self.pdf, content_left, reason_y, reason_line, 7.5, MUTED)
                    reason_y -= 11.5
            bottom = detail_top - detail_height + 1
        else:
            bottom = line_y
        self.pdf.setStrokeColor(LINE)
        self.pdf.line(MARGIN, bottom, PAGE_WIDTH - MARGIN, bottom)
        self.y = bottom - 18

    def feedback_group(self, title: str, values: list[Any]) -> None:
        """用颜色、留白和细分割线展示反馈，不绘制嵌套卡片。"""
        tone = FEEDBACK_TONES[title]
        self.ensure(34)
        self.pdf.setFillColor(tone)
        self.pdf.roundRect(MARGIN, self.y - 14, 2.5, 12, 1.25, stroke=0, fill=1)
        _draw_mixed(self.pdf, MARGIN + 10, self.y - 13, title, 12, INK, bold=True)
        count_text = str(len(values))
        _draw_mixed(self.pdf, PAGE_WIDTH - MARGIN - _text_width(count_text, 9), self.y - 13, count_text, 9, tone, bold=True)
        self.y -= 30
        if not values:
            self.paragraph("本次报告没有列出这一类内容。", size=9, gap=14)
            return
        for index, item in enumerate(values, start=1):
            lines = _wrap_text(item, 9.5, CONTENT_WIDTH - 34) or ["暂无内容"]
            height = max(31, len(lines) * 15 + 12)
            self.ensure(height)
            number = f"{index:02d}"
            _draw_mixed(self.pdf, MARGIN, self.y - 12, number, 8.5, tone, bold=True)
            text_y = self.y - 12
            for line in lines:
                _draw_mixed(self.pdf, MARGIN + 28, text_y, line, 9.5, INK)
                text_y -= 15
            bottom = self.y - height + 5
            self.pdf.setStrokeColor(LINE)
            self.pdf.setLineWidth(0.6)
            self.pdf.line(MARGIN + 28, bottom, PAGE_WIDTH - MARGIN, bottom)
            self.y = bottom - 8
        self.y -= 10

    def score_header(self, score: float, project_name: str, subtitle: str) -> None:
        """绘制首页封面与综合评分。"""
        top = PAGE_HEIGHT - MARGIN
        height = 190
        self.pdf.setFillColor(INK)
        self.pdf.roundRect(MARGIN, top - height, CONTENT_WIDTH, height, 14, stroke=0, fill=1)
        _draw_mixed(self.pdf, MARGIN + 24, top - 32, "ARCHCRITIC", 11, HexColor("#BFB2FF"), bold=True)
        _draw_mixed(self.pdf, MARGIN + 24, top - 67, "AI 建筑评图报告", 22, HexColor("#FFFFFF"), bold=True)
        for index, line in enumerate(_wrap_text(project_name, 14, 320)[:2]):
            _draw_mixed(self.pdf, MARGIN + 24, top - 98 - index * 20, line, 14, HexColor("#FFFFFF"))
        _draw_mixed(self.pdf, MARGIN + 24, top - 158, subtitle, 9, HexColor("#C8CBD2"))
        center_x = PAGE_WIDTH - MARGIN - 67
        center_y = top - 86
        self.pdf.setFillColor(HexColor("#2A2734"))
        self.pdf.setStrokeColor(HexColor("#8E79FF"))
        self.pdf.setLineWidth(5)
        self.pdf.circle(center_x, center_y, 48, stroke=1, fill=1)
        score_text = str(round(score))
        score_size = 38
        _draw_mixed(self.pdf, center_x - _text_width(score_text, score_size) / 2, center_y - 12, score_text, score_size, HexColor("#FFFFFF"), bold=True)
        self.y = top - height - 28

    def heading(self, title: str, eyebrow: str = "") -> None:
        """绘制新页主标题。"""
        if eyebrow:
            _draw_mixed(self.pdf, MARGIN, self.y - 10, eyebrow, 8.5, PURPLE)
            self.y -= 22
        _draw_mixed(self.pdf, MARGIN, self.y - 20, title, 19, INK, bold=True)
        self.y -= 42

    def finish(self) -> bytes:
        """写入末页并返回 PDF 字节。"""
        self._footer()
        self.pdf.save()
        return self.output.getvalue()


def build_report_pdf_snapshot(submission: Any) -> Any:
    """在线程外复制 PDF 所需字段，确保建筑类型和年级不会在导出时遗漏。"""
    project = submission.project
    return SimpleNamespace(
        project=SimpleNamespace(
            name=project.name,
            building_type=project.building_type,
            grade=project.grade,
        ),
        design_stage=submission.design_stage,
    )


def build_report_pdf(submission: Any, report: Any) -> bytes:
    """根据真实报告生成含具体小分的矢量 PDF，不附带知识卡正文。"""
    document = ReportDocument()
    project = submission.project
    subtitle_parts = [submission.design_stage, getattr(project, "building_type", ""), getattr(project, "grade", "")]
    document.score_header(
        float(report.overall_score),
        str(project.name or "未命名项目"),
        " / ".join(filter(None, subtitle_parts)),
    )
    document.section_title("综合评审")
    document.paragraph(report.summary, size=9, color=MUTED)
    evaluations = [item for item in report.agent_evaluations if item.agent_type != "review_agent"]
    document.section_title("评分维度")
    for evaluation in evaluations:
        document.dimension(evaluation)

    document.new_page()
    document.heading("反馈与修改建议", "REPORT DETAILS")
    for title, items in (
        ("必须修改", report.must_fix),
        ("重点优化", report.should_improve),
        ("建议关注", report.optional_improvements),
        ("当前优势", report.strengths),
    ):
        values = list(items or [])
        document.feedback_group(title, values)
    return document.finish()
