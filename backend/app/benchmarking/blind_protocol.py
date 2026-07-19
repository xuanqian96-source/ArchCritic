"""把基准评图、结果冻结和答案裁判分成三个独立阶段。"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import hashlib
import json
from pathlib import Path
import shutil
import time
import traceback
from typing import Any

from app.benchmarking.asset_audit import find_input_violations
from app.benchmarking.baseline_snapshot import collect_relevant_files, fingerprint_files
from app.benchmarking.runner import (
    build_context,
    calculate_prompt_fingerprint,
    judge_report,
    prepare_model_urls,
)
from app.llm.client import get_llm_client
from app.scoring.calibration import load_calibrator


FORBIDDEN_ANSWER_FILE_WORDS = (
    "ground_truth",
    "ground-truth",
    "private_answer",
    "private-answer",
    "teacher_score",
    "teacher-score",
    "标准答案",
    "教师分",
    "教师成绩",
)


def create_blind_input_bundle(source_root: Path, target_root: Path) -> dict[str, Any]:
    """从已准备数据中只复制匿名输入、任务书和公开索引。"""
    if target_root.exists() and any(target_root.iterdir()):
        raise ValueError("盲测输入目录不为空，不得覆盖。")
    index = read_json(source_root / "index.json")
    selected_files = [source_root / "index.json"]
    taskbook_name = str(index.get("taskbook_file", "")).strip()
    if taskbook_name:
        selected_files.append(source_root / taskbook_name)
    for item in index.get("cases", []):
        input_file = source_root / str(item["input_file"])
        selected_files.append(input_file)
        payload = read_json(input_file)
        for drawing in payload.get("drawings", []):
            selected_files.append(input_file.parent / str(drawing["relative_path"]))

    for source in selected_files:
        if not source.is_file():
            raise ValueError(f"盲测输入源文件缺失：{source}")
        relative = source.relative_to(source_root)
        target = target_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)

    validation = validate_blind_input_root(target_root)
    bundle = {
        "version": 1,
        "created_at": now_text(),
        "source_index_sha256": sha256_file(source_root / "index.json"),
        "case_count": validation["case_count"],
        "contains_answer_files": False,
        "contains_input_violations": False,
    }
    write_json(target_root / "BLIND_INPUT_BUNDLE.json", bundle)
    return bundle


def validate_blind_input_root(input_root: Path) -> dict[str, Any]:
    """确认盲测输入目录不含答案文件或答案暗示。"""
    if not input_root.is_dir():
        raise ValueError(f"盲测输入目录不存在：{input_root}")
    forbidden_files = [
        str(path.relative_to(input_root))
        for path in input_root.rglob("*")
        if path.is_file()
        and any(word in path.name.lower() for word in FORBIDDEN_ANSWER_FILE_WORDS)
    ]
    if forbidden_files:
        raise ValueError(f"盲测输入目录发现答案文件：{forbidden_files[:3]}")

    index_file = input_root / "index.json"
    if not index_file.is_file():
        raise ValueError("盲测输入目录缺少 index.json。")
    index = read_json(index_file)
    violations = []
    seen_case_ids: set[str] = set()
    for item in index.get("cases", []):
        case_id = str(item.get("case_id", "")).strip()
        if not case_id or case_id in seen_case_ids:
            raise ValueError(f"盲测编号缺失或重复：{case_id or 'empty'}")
        seen_case_ids.add(case_id)
        input_file = input_root / str(item.get("input_file", ""))
        payload = read_json(input_file)
        case_violations = find_input_violations(payload, set())
        if case_violations:
            violations.append({"case_id": case_id, "violations": case_violations})
        for drawing in payload.get("drawings", []):
            drawing_path = input_file.parent / str(drawing.get("relative_path", ""))
            if not drawing_path.is_file():
                raise ValueError(f"盲测图纸缺失：{case_id}/{drawing_path.name}")
    if violations:
        raise ValueError(f"盲测模型输入包含禁止字段或暗示：{violations[:2]}")
    return {
        "case_count": len(seen_case_ids),
        "case_ids": sorted(seen_case_ids),
        "index_sha256": sha256_file(index_file),
        "answer_file_count": 0,
        "input_violation_count": 0,
    }


def run_blind_round(
    input_root: Path,
    results_root: Path,
    provider: str,
    model: str,
    architecture: str,
    test_id: str,
    workers: int = 1,
    case_ids: set[str] | None = None,
    calibration_file: Path | None = None,
    resume_technical_failures: bool = False,
) -> dict[str, Any]:
    """在完全不读取教师答案的进程中运行评图并冻结结果。"""
    validation = validate_blind_input_root(input_root)
    frozen_file = results_root / "FROZEN.json"
    if frozen_file.exists():
        raise ValueError("该盲测结果已冻结，禁止再次运行。")
    manifest_file = results_root / "run_manifest.json"
    if manifest_file.exists() and not resume_technical_failures:
        raise ValueError("该盲测已启动过，只允许显式恢复技术失败项。")

    index = read_json(input_root / "index.json")
    taskbook_name = str(index.get("taskbook_file", "")).strip()
    taskbook = read_json(input_root / taskbook_name) if taskbook_name else {}
    selected = [
        item
        for item in index.get("cases", [])
        if not case_ids or item.get("case_id") in case_ids
    ]
    if not selected:
        raise ValueError("没有可运行的盲测样本。")
    requested_case_ids = sorted(str(item["case_id"]) for item in selected)
    taskbook_sha256 = sha256_file(input_root / taskbook_name) if taskbook_name else ""
    if calibration_file and not calibration_file.is_file():
        raise ValueError(f"校准文件不存在：{calibration_file}")
    calibration_sha256 = sha256_file(calibration_file) if calibration_file else ""
    project_root = Path(__file__).resolve().parents[3]
    review_code_fingerprint = fingerprint_files(
        project_root,
        collect_relevant_files(project_root),
    )

    existing = {
        path.stem for path in results_root.glob("CASE-*.json") if path.is_file()
    }
    selected = [item for item in selected if item.get("case_id") not in existing]
    if not selected:
        raise ValueError("所有盲测样本已有结果，禁止重复运行。")

    results_root.mkdir(parents=True, exist_ok=True)
    manifest = read_json(manifest_file) if manifest_file.exists() else {
        "protocol": "blind-run-freeze-judge-v1",
        "test_id": test_id,
        "provider": provider,
        "model": model,
        "architecture": architecture,
        "prompt_fingerprint": calculate_prompt_fingerprint(architecture),
        "review_code_fingerprint": review_code_fingerprint,
        "input_index_sha256": validation["index_sha256"],
        "taskbook_sha256": taskbook_sha256,
        "calibration_sha256": calibration_sha256,
        "case_ids": requested_case_ids,
        "started_at": now_text(),
        "contains_teacher_scores": False,
        "contains_annotation_answers": False,
        "attempts": [],
    }
    assert_manifest_matches(
        manifest,
        provider,
        model,
        architecture,
        test_id,
        validation,
        requested_case_ids,
        taskbook_sha256,
        calibration_sha256,
        review_code_fingerprint,
    )
    write_json(manifest_file, manifest)
    calibrator = load_calibrator(calibration_file)
    upload_cache = prepare_model_urls(input_root, selected, provider, model)

    output_paths: list[Path] = []
    failed_case_ids: list[str] = []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        futures = {}
        for item in selected:
            input_file = input_root / str(item["input_file"])
            future = executor.submit(
                run_blind_case,
                input_file,
                taskbook,
                upload_cache,
                provider,
                model,
                architecture,
                calibrator,
            )
            futures[future] = str(item["case_id"])
        for future in as_completed(futures):
            case_id = futures[future]
            try:
                result = future.result()
            except Exception as exc:  # noqa: BLE001 - 技术失败必须保留且不得中断全轮
                failed_case_ids.append(case_id)
                write_blind_error(results_root, case_id, exc)
                continue
            output_path = results_root / f"{case_id}.json"
            write_json(output_path, result)
            output_paths.append(output_path)

    manifest["attempts"].append(
        {
            "completed_at": now_text(),
            "attempted_case_ids": sorted(str(item["case_id"]) for item in selected),
            "successful_case_ids": sorted(path.stem for path in output_paths),
            "technical_failure_case_ids": sorted(failed_case_ids),
        }
    )
    all_expected = set(manifest["case_ids"])
    completed = {
        path.stem for path in results_root.glob("CASE-*.json") if path.is_file()
    }
    manifest["successful_count"] = len(completed & all_expected)
    manifest["technical_failure_count"] = len(all_expected - completed)
    manifest["run_status"] = "complete" if all_expected <= completed else "technical_failures"
    write_json(manifest_file, manifest)
    if manifest["run_status"] == "complete":
        freeze_blind_results(results_root, manifest)
    return manifest


def run_blind_case(
    input_file: Path,
    taskbook: dict[str, Any],
    upload_cache: dict[str, str],
    provider: str,
    model: str,
    architecture: str,
    calibrator: dict[str, Any] | None,
) -> dict[str, Any]:
    """运行单份不带答案的评图，并记录真实耗时。"""
    case_input = read_json(input_file)
    violations = find_input_violations(case_input, set())
    if violations:
        raise ValueError(f"模型输入安全检查失败：{violations}")
    llm_client = get_llm_client(provider, model)
    context = build_context(
        case_input,
        input_file.parent,
        upload_cache,
        provider,
        taskbook,
        architecture,
        calibrator,
    )
    started = time.monotonic()
    report = llm_client.generate_evaluation(context)
    duration = round(time.monotonic() - started, 3)
    return {
        "case_id": case_input["case_id"],
        "provider": provider,
        "model": model,
        "architecture": architecture,
        "calibrator_version": (calibrator or {}).get("version", "not_configured"),
        "prompt_fingerprint": calculate_prompt_fingerprint(architecture),
        "completed_at": now_text(),
        "duration_seconds": duration,
        "contains_judge": False,
        "contains_teacher_score": False,
        "report": report,
    }


def freeze_blind_results(results_root: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    """为每份盲测结果记录哈希，供解封裁判前核对。"""
    result_hashes = {
        path.name: sha256_file(path)
        for path in sorted(results_root.glob("CASE-*.json"))
        if path.is_file()
    }
    frozen = {
        "protocol": "blind-run-freeze-judge-v1",
        "test_id": manifest["test_id"],
        "frozen_at": now_text(),
        "result_hashes": result_hashes,
        "run_manifest_sha256": sha256_file(results_root / "run_manifest.json"),
        "results_may_be_rerun": False,
    }
    write_json(results_root / "FROZEN.json", frozen)
    return frozen


def judge_frozen_round(
    results_root: Path,
    private_answers_file: Path,
    judgments_root: Path,
    provider: str,
    model: str,
) -> dict[str, Any]:
    """在分数结果冻结后，用独立进程读取私有答案完成语义裁判。"""
    frozen = verify_frozen_results(results_root)
    if judgments_root.exists() and any(judgments_root.iterdir()):
        raise ValueError("裁判结果目录不为空，不得覆盖或挑选结果。")
    answers = read_json(private_answers_file)
    truth_by_id = {
        item["case_id"]: item
        for item in answers.get("cases", [])
        if isinstance(item, dict) and item.get("case_id")
    }
    result_files = sorted(results_root.glob("CASE-*.json"))
    missing_answers = [path.stem for path in result_files if path.stem not in truth_by_id]
    if missing_answers:
        raise ValueError(f"私有答案缺少样本：{missing_answers}")

    judgments_root.mkdir(parents=True, exist_ok=True)
    llm_client = get_llm_client(provider, model)
    output_hashes = {}
    for result_file in result_files:
        result = read_json(result_file)
        case_id = str(result["case_id"])
        judgment = judge_report(llm_client, result["report"], truth_by_id[case_id])
        output = {
            "case_id": case_id,
            "source_result_sha256": sha256_file(result_file),
            "judged_at": now_text(),
            "judge_provider": provider,
            "judge_model": model,
            "judge": judgment,
        }
        output_file = judgments_root / f"{case_id}.judge.json"
        write_json(output_file, output)
        output_hashes[output_file.name] = sha256_file(output_file)

    manifest = {
        "protocol": frozen["protocol"],
        "test_id": frozen["test_id"],
        "judged_at": now_text(),
        "source_frozen_sha256": sha256_file(results_root / "FROZEN.json"),
        "private_answers_sha256": sha256_file(private_answers_file),
        "judgment_hashes": output_hashes,
        "teacher_answers_sent_to_scoring_agent": False,
    }
    write_json(judgments_root / "judgment_manifest.json", manifest)
    return manifest


def verify_frozen_results(results_root: Path) -> dict[str, Any]:
    """在裁判前确认所有冻结评图结果未被修改。"""
    frozen_file = results_root / "FROZEN.json"
    if not frozen_file.is_file():
        raise ValueError("盲测结果尚未冻结，禁止读取私有答案。")
    frozen = read_json(frozen_file)
    for name, expected_hash in frozen.get("result_hashes", {}).items():
        path = results_root / name
        if not path.is_file() or sha256_file(path) != expected_hash:
            raise ValueError(f"冻结结果已缺失或被修改：{name}")
    return frozen


def assert_manifest_matches(
    manifest: dict[str, Any],
    provider: str,
    model: str,
    architecture: str,
    test_id: str,
    validation: dict[str, Any],
    requested_case_ids: list[str],
    taskbook_sha256: str,
    calibration_sha256: str,
    review_code_fingerprint: str,
) -> None:
    """技术失败恢复时禁止更换模型、代码、校准器或输入。"""
    expected = {
        "provider": provider,
        "model": model,
        "architecture": architecture,
        "test_id": test_id,
        "input_index_sha256": validation["index_sha256"],
        "taskbook_sha256": taskbook_sha256,
        "calibration_sha256": calibration_sha256,
        "prompt_fingerprint": calculate_prompt_fingerprint(architecture),
        "review_code_fingerprint": review_code_fingerprint,
        "case_ids": requested_case_ids,
    }
    changed = [key for key, value in expected.items() if manifest.get(key) != value]
    if changed:
        raise ValueError(f"盲测技术恢复条件已变更，禁止继续：{changed}")


def write_blind_error(results_root: Path, case_id: str, exc: Exception) -> Path:
    """以递增文件保留每次技术失败，不覆盖旧记录。"""
    error_root = results_root / "errors" / case_id
    error_root.mkdir(parents=True, exist_ok=True)
    attempt = len(list(error_root.glob("attempt-*.json"))) + 1
    output = error_root / f"attempt-{attempt:02d}.json"
    write_json(
        output,
        {
            "case_id": case_id,
            "failed_at": now_text(),
            "error_type": type(exc).__name__,
            "message": str(exc)[:1000],
            "traceback": traceback.format_exc()[-4000:],
        },
    )
    return output


def sha256_file(path: Path) -> str:
    """计算文件 SHA-256 用于冻结和篡改检查。"""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def now_text() -> str:
    """返回带时区的秒级时间。"""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def read_json(path: Path) -> dict[str, Any]:
    """读取 UTF-8 JSON。"""
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    """以稳定格式写入 UTF-8 JSON。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
