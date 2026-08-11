"""验证会议论文正式实验的留一法、条件命名和暂停规则。"""

from pathlib import Path

from PIL import Image

from app.benchmarking.anonymize import apply_manual_relative_redactions
from app.benchmarking.dataset import BenchmarkCase
from app.benchmarking.paper_experiment import build_loo_guidance
from app.benchmarking.paper_experiment_analysis import (
    enforce_one_to_one_exact_matches,
    evaluate_pause_gate,
)
from app.benchmarking.paper_experiment_prompts import (
    CONDITION_NAMES,
    build_single_model_user_prompt,
)


def make_case(case_id: str, score: float) -> BenchmarkCase:
    """构造不需要真实图纸的最小测试样本。"""
    return BenchmarkCase(
        case_id=case_id,
        sample_id=f"S-{case_id}",
        annotation_path=Path("annotation.md"),
        source_dir=Path("."),
        teacher_score=score,
        project_name="测试项目",
        building_type="公共文化建筑",
        design_stage="图纸阶段",
        description=f"不得进入锚点的说明 {case_id}",
        facts=[{"item": f"不得进入锚点的事实 {case_id}"}],
        must_issues=[{"id": "M-01", "description": f"不得进入锚点的问题 {case_id}"}],
        optional_issues=[],
        forbidden_issues=[],
        score_ranges={
            "function_agent": {"min": score - 1, "max": score + 1},
            "review_agent": {"min": score - 2, "max": score + 2},
        },
        drawings=[],
    )


def test_loo_guidance_excludes_heldout_sample_content() -> None:
    """留一法锚点不得包含当前样本的分数、编号或标注内容。"""
    heldout = make_case("HELDOUT", 42.3)
    others = [
        make_case("LOW", 68),
        make_case("MID", 81),
        make_case("HIGH", 94),
    ]
    guidance = build_loo_guidance([heldout, *others], heldout)

    assert "42.3" not in guidance
    assert "HELDOUT" not in guidance
    assert "不得进入锚点" not in guidance
    assert "68.0" in guidance
    assert "81.0" in guidance
    assert "94.0" in guidance


def test_c1_name_and_prompt_difference_are_frozen() -> None:
    """C1 名称准确，C0 不读锚点而 C1 明确读取锚点。"""
    context = {
        "building_type": "博物馆",
        "grade": "大二",
        "design_stage": "图纸阶段",
        "task_book_text": "任务书正文",
        "drawings": [{"original_name": "D01"}],
        "score_band_guidance": "仅供测试的课程尺度",
    }

    direct = build_single_model_user_prompt(context, False)
    structured = build_single_model_user_prompt(context, True)

    assert CONDITION_NAMES["c1_structured_single"] == "结构化提示词增强的单模型评审"
    assert "仅供测试的课程尺度" not in direct
    assert "仅供测试的课程尺度" in structured


def test_pause_gate_flags_suspicious_direct_baseline() -> None:
    """直接评审异常偏高时必须暂停。"""
    gate = evaluate_pause_gate(
        {
            "c0_direct": {"strict_issue_f1": 0.86, "score_mae": 4.0},
            "c1_structured_single": {"strict_issue_f1": 0.87, "score_mae": 3.5},
        }
    )

    assert gate["pause_required"] is True
    assert gate["reasons"]


def test_pause_gate_allows_broadly_expected_order() -> None:
    """前三组无异常高值且没有明显双重退化时继续。"""
    gate = evaluate_pause_gate(
        {
            "c0_direct": {"strict_issue_f1": 0.30, "score_mae": 14.0},
            "c1_structured_single": {"strict_issue_f1": 0.43, "score_mae": 10.0},
            "c2_multi_agent": {"strict_issue_f1": 0.51, "score_mae": 8.0},
        }
    )

    assert gate["pause_required"] is False


def test_same_prediction_cannot_exactly_match_two_must_issues() -> None:
    """同一条模型意见只能贡献一次严格命中。"""
    judgment = {
        "must_reference_results": [
            {"id": "M-01", "match": "exact", "prediction_id": "PM-01", "reason": ""},
            {"id": "M-02", "match": "exact", "prediction_id": "PM-01", "reason": ""},
        ]
    }

    enforce_one_to_one_exact_matches(judgment)

    assert [item["match"] for item in judgment["must_reference_results"]] == [
        "exact",
        "partial",
    ]


def test_manual_identity_redaction_masks_raster_title_block(tmp_path: Path) -> None:
    """嵌入图像的身份栏也会按视觉审计坐标遮挡。"""
    paths = []
    for index in range(1, 4):
        path = tmp_path / f"board_{index:02d}.jpg"
        Image.new("RGB", (100, 100), "black").save(path)
        paths.append(path)

    counts = apply_manual_relative_redactions("SAUP-MUS-M001", paths)

    assert counts == {1: 1, 2: 1, 3: 1}
    with Image.open(paths[0]) as image:
        assert image.convert("RGB").getpixel((90, 98))[0] > 240
