"""验证评图报告 PDF 生成，不访问数据库或外部模型。"""

import subprocess
from types import SimpleNamespace

from app.services.report_pdf import build_report_pdf, build_report_pdf_snapshot


def test_build_report_pdf_snapshot_keeps_project_grade():
    """导出线程快照必须保留封面所需的真实年级。"""
    project = SimpleNamespace(name="社区活动中心", building_type="公共建筑", grade="三年级")
    submission = SimpleNamespace(project=project, title="方案阶段提交", design_stage="方案阶段")

    snapshot = build_report_pdf_snapshot(submission)

    assert snapshot.project.grade == "三年级"
    assert snapshot.design_stage == "方案阶段"


def test_build_report_pdf_contains_real_report_sections(tmp_path):
    """真实评分、反馈和知识依据应生成有效的多页 PDF。"""
    project = SimpleNamespace(name="墟中有隙——社区活动中心", building_type="文化建筑", grade="大二")
    submission = SimpleNamespace(project=project, title="方案阶段 V1", design_stage="方案阶段")
    evaluation = SimpleNamespace(
        agent_type="function_agent",
        dimension="功能与流线",
        score=82,
        summary="参观流线整体清晰，但入口集散空间仍需补充容量说明。",
        details={
            "sub_scores": {
                "入口集散": {"score": 20, "max_score": 25, "reason": "入口识别清晰，集散面积仍需复核。"},
                "无障碍流线": {"score": 18, "max_score": 25, "reason": "连续无障碍路径尚未闭环。"},
            },
        },
    )
    reference = SimpleNamespace(
        library_item_id="KC-FUN-001",
        reference_id="K1",
        title="公共建筑入口与集散空间",
        excerpt="入口空间应兼顾识别性、集散能力与无障碍到达。",
        display_content="",
        content="",
    )
    report = SimpleNamespace(
        overall_score=83,
        grade="优秀",
        summary="方案在“墟中有隙”概念下建立了清晰的空间主线，后续应优先完善入口与消防疏散。",
        agent_evaluations=[evaluation],
        must_fix=["补充主要入口集散空间的尺度依据。[K1]"],
        should_improve=["优化后勤流线与公众流线的交叉位置。"],
        optional_improvements=["增加公共空间停留节点。"],
        strengths=["空间叙事与场地记忆联系明确。"],
        references=[reference],
    )

    pdf = build_report_pdf(submission, report)
    pdf_path = tmp_path / "report.pdf"
    pdf_path.write_bytes(pdf)
    extracted = subprocess.run(
        ["pdftotext", str(pdf_path), "-"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout

    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 20_000
    assert "入口集散" in extracted
    assert "20 / 25" in extracted
    assert "无障碍流线" in extracted
    assert "18 / 25" in extracted
    assert "墟中有隙——社区活动中心" in extracted
    assert "“墟中有隙”" in extracted
    assert "反馈与修改建议" in extracted
    assert "方案阶段 / 文化建筑 / 大二" in extracted
    assert "方案阶段 V1" not in extracted
    assert "优秀" not in extracted
    assert "评分维度 1" not in extracted
    assert "关联知识依据" not in extracted
