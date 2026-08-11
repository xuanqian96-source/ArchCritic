"""验证正式盲测输入、冻结和答案解封边界。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.benchmarking.blind_protocol import (
    assert_manifest_matches,
    create_blind_input_bundle,
    freeze_blind_results,
    validate_blind_input_root,
    verify_frozen_results,
)


def write_json(path: Path, value: object) -> None:
    """为测试写入 UTF-8 JSON。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def build_safe_source(root: Path) -> Path:
    """生成一份不含人工答案的最小匿名输入。"""
    input_file = root / "inputs" / "CASE-A01" / "input.json"
    drawing_file = input_file.parent / "drawings" / "board_01.png"
    drawing_file.parent.mkdir(parents=True)
    drawing_file.write_bytes(b"safe-image-placeholder")
    write_json(
        input_file,
        {
            "case_id": "CASE-A01",
            "project_name": "匿名文化建筑",
            "building_type": "博物馆",
            "design_stage": "scheme",
            "description": "公共建筑课程作业",
            "drawings": [
                {
                    "drawing_type": "plan",
                    "relative_path": "drawings/board_01.png",
                    "mime_type": "image/png",
                    "description": "平面图"
                }
            ]
        },
    )
    write_json(
        root / "index.json",
        {
            "version": 3,
            "taskbook_file": "taskbook.json",
            "cases": [{"case_id": "CASE-A01", "input_file": "inputs/CASE-A01/input.json"}],
        },
    )
    write_json(root / "taskbook.json", {"full_text": "公共建筑设计任务书"})
    return root


def test_bundle_copies_only_model_inputs(tmp_path: Path) -> None:
    """确认模型输入包不会复制私有答案。"""
    source = build_safe_source(tmp_path / "prepared")
    write_json(source / "ground_truth.json", {"cases": [{"teacher_score": 94}]})
    target = tmp_path / "blind-inputs"

    bundle = create_blind_input_bundle(source, target)

    assert bundle["case_count"] == 1
    assert (target / "inputs" / "CASE-A01" / "input.json").is_file()
    assert not (target / "ground_truth.json").exists()
    assert validate_blind_input_root(target)["input_violation_count"] == 0


def test_validation_rejects_answer_file_or_hint(tmp_path: Path) -> None:
    """确认盲测根目录中不能放答案文件或高低分暗示。"""
    root = build_safe_source(tmp_path / "blind-inputs")
    write_json(root / "private-answers.json", {"teacher_score": 94})
    with pytest.raises(ValueError, match="答案文件"):
        validate_blind_input_root(root)

    (root / "private-answers.json").unlink()
    input_file = root / "inputs" / "CASE-A01" / "input.json"
    payload = json.loads(input_file.read_text(encoding="utf-8"))
    payload["description"] = "这是高分样本"
    write_json(input_file, payload)
    with pytest.raises(ValueError, match="禁止字段或暗示"):
        validate_blind_input_root(root)


def test_frozen_results_detect_changes(tmp_path: Path) -> None:
    """确认裁判前会检查冻结结果是否被改动。"""
    results = tmp_path / "results"
    write_json(results / "CASE-A01.json", {"case_id": "CASE-A01", "report": {"overall_score": 80}})
    write_json(results / "run_manifest.json", {"test_id": "final-001"})
    freeze_blind_results(results, {"test_id": "final-001"})
    assert verify_frozen_results(results)["results_may_be_rerun"] is False

    write_json(results / "CASE-A01.json", {"case_id": "CASE-A01", "report": {"overall_score": 81}})
    with pytest.raises(ValueError, match="被修改"):
        verify_frozen_results(results)


def test_resume_rejects_changed_code_or_calibration() -> None:
    """确认技术失败续跑不能更换代码或校准文件。"""
    manifest = {
        "provider": "qianwen",
        "model": "qwen-vl-max",
        "architecture": "evidence_v2",
        "test_id": "blind-001",
        "input_index_sha256": "input-hash",
        "taskbook_sha256": "taskbook-hash",
        "calibration_sha256": "old-calibration",
        "prompt_fingerprint": "prompt-hash",
        "review_code_fingerprint": "old-code",
        "knowledge_fingerprint": "old-knowledge",
        "case_ids": ["CASE-A01"],
    }
    with pytest.raises(ValueError, match="calibration_sha256.*review_code_fingerprint"):
        assert_manifest_matches(
            manifest,
            "qianwen",
            "qwen-vl-max",
            "evidence_v2",
            "blind-001",
            {"index_sha256": "input-hash"},
            ["CASE-A01"],
            "taskbook-hash",
            "new-calibration",
            "new-code",
            "new-knowledge",
        )
