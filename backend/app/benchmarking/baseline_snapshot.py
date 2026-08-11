"""冻结长程 Goal 开始时的代码、提示词、配置和历史聚合指标。"""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Any

from app.benchmarking.runner import calculate_prompt_fingerprint
from app.config import get_settings


METRIC_KEYS = (
    "case_count",
    "score_mae",
    "score_median_absolute_error",
    "score_rmse",
    "score_mean_bias",
    "score_pearson_r",
    "score_spearman_rho",
    "interval_hit_rate",
    "fact_accuracy",
    "must_issue_recall",
    "forbidden_violation_rate",
    "high_low_pair_accuracy",
    "model_score_range",
)


def build_baseline_snapshot(project_root: Path, dataset_root: Path, knowledge_root: Path) -> dict[str, Any]:
    """生成不含单份教师分或标注答案的阶段 0 基线快照。"""
    settings = get_settings()
    relevant_files = collect_relevant_files(project_root)
    git_status = run_git(project_root, ["status", "--short"])
    history = {
        round_name: read_aggregate_metrics(
            dataset_root / ".benchmark-results" / round_name / "metrics.json"
        )
        for round_name in ("formal-round1", "formal-round2")
    }
    evidence_summary = read_evidence_summary(
        dataset_root
        / "测试报告与论文数据"
        / "新版证据校准架构"
        / "02_校准与盲测结果.md"
    )
    retrieval_files = (
        [path for path in knowledge_root.rglob("*.md") if ".obsidian" not in path.parts]
        if knowledge_root.is_dir()
        else []
    )
    governance_root = knowledge_root / "99维护记录" / "长程Goal治理"
    governance_files = (
        [
            path
            for path in governance_root.rglob("*")
            if path.is_file() and path.suffix.lower() in {".json", ".html", ".md"}
        ]
        if governance_root.is_dir()
        else []
    )
    return {
        "snapshot_version": "archcritic-goal-baseline-v1",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "contains_individual_teacher_scores": False,
        "contains_annotation_answers": False,
        "git": {
            "head": run_git(project_root, ["rev-parse", "HEAD"]),
            "branch": run_git(project_root, ["branch", "--show-current"]),
            "working_tree_clean": not bool(git_status),
            "working_tree_change_count": len(git_status.splitlines()) if git_status else 0,
        },
        "code": {
            "relevant_file_count": len(relevant_files),
            "relevant_files_sha256": fingerprint_files(project_root, relevant_files),
            "legacy_prompt_fingerprint": calculate_prompt_fingerprint("legacy_v1"),
            "evidence_prompt_fingerprint": calculate_prompt_fingerprint("evidence_v2"),
        },
        "runtime": {
            "configured_scoring_architecture": settings.scoring_architecture,
            "code_default_scoring_architecture": "legacy_v1",
            "configured_llm_provider": settings.llm_provider,
            "configured_llm_model": settings.llm_model,
            "llm_timeout_seconds": settings.llm_timeout_seconds,
            "review_budget_seconds": settings.llm_review_timeout_seconds,
        },
        "knowledge_base": {
            "root_exists": knowledge_root.is_dir(),
            "sha256": fingerprint_files(knowledge_root, retrieval_files),
            "retrieval_markdown_file_count": len(retrieval_files),
            "retrieval_markdown_sha256": fingerprint_files(knowledge_root, retrieval_files),
            "governance_record_file_count": len(governance_files),
            "governance_record_sha256": fingerprint_files(knowledge_root, governance_files),
        },
        "historical_aggregate_metrics": history,
        "evidence_v2_historical_summary": evidence_summary,
        "product_decision": {
            "default_architecture": "legacy_v1",
            "evidence_v2_status": "research_only",
            "reason": "现有两份历史留出样本排序失败，不足以支持产品准入。",
        },
    }


def collect_relevant_files(project_root: Path) -> list[Path]:
    """收集会影响评分、任务书、知识检索和基准评测的文件。"""
    roots = (
        project_root / "backend" / "app" / "agents",
        project_root / "backend" / "app" / "scoring",
        project_root / "backend" / "app" / "benchmarking",
    )
    files = [
        path
        for root in roots
        if root.is_dir()
        for path in root.rglob("*.py")
        if "__pycache__" not in path.parts
    ]
    files.extend(
        path
        for path in (
            project_root / "backend" / "app" / "config.py",
            project_root / "backend" / "app" / "services" / "taskbooks.py",
            project_root / "backend" / "app" / "services" / "taskbook_rules.py",
            project_root / "backend" / "app" / "wiki.py",
            project_root / "backend" / "app" / "governed_wiki.py",
            project_root / "backend" / "app" / "knowledge_selection.py",
            project_root / "backend" / "scripts" / "benchmark_review.py",
            project_root / "docs" / "plans" / "2026-07-19-archcritic-long-horizon-goal-taskbook.md",
        )
        if path.is_file()
    )
    return sorted(set(files))


def fingerprint_files(root: Path, paths: list[Path]) -> str:
    """按相对路径与内容生成稳定指纹。"""
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(str(path.relative_to(root)).replace("\\", "/").encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def read_aggregate_metrics(path: Path) -> dict[str, Any]:
    """只从历史指标文件中读取总体统计。"""
    if not path.is_file():
        return {"available": False}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {"available": True, **{key: raw.get(key) for key in METRIC_KEYS}}


def read_evidence_summary(path: Path) -> dict[str, Any]:
    """只提取新架构历史留出集的聚合结论。"""
    if not path.is_file():
        return {"available": False}
    text = path.read_text(encoding="utf-8")
    baseline = re.search(r"旧流程盲测 MAE：([\d.]+) 分", text)
    evidence = re.search(r"新架构盲测 MAE：([\d.]+) 分", text)
    ordering = re.search(r"高低分排序是否正确：([^。]+)", text)
    return {
        "available": bool(baseline and evidence),
        "baseline_mae": float(baseline.group(1)) if baseline else None,
        "evidence_v2_mae": float(evidence.group(1)) if evidence else None,
        "high_low_ordering_passed": ordering.group(1).strip() == "是" if ordering else None,
        "heldout_case_count": 2,
        "suitable_for_product_default": False,
    }


def run_git(project_root: Path, arguments: list[str]) -> str:
    """只读取 Git 版本信息，失败时返回空文本。"""
    completed = subprocess.run(
        ["git", *arguments],
        cwd=project_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    return completed.stdout.strip() if completed.returncode == 0 else ""


def write_baseline_snapshot(output_root: Path, snapshot: dict[str, Any]) -> tuple[Path, Path]:
    """写入机器快照和简明中文说明。"""
    output_root.mkdir(parents=True, exist_ok=True)
    json_path = output_root / "阶段0当前基线冻结.json"
    markdown_path = output_root / "阶段0当前基线冻结.md"
    json_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    history = snapshot["historical_aggregate_metrics"]
    evidence = snapshot["evidence_v2_historical_summary"]
    markdown = f"""# ArchCritic 长程 Goal 阶段 0 基线冻结

生成时间：{snapshot['generated_at']}

> 本快照只包含版本和总体指标，不包含单份教师分或人工标注答案。

## 版本

- Git 提交：`{snapshot['git']['head']}`
- 当前分支：`{snapshot['git']['branch']}`
- 相关代码指纹：`{snapshot['code']['relevant_files_sha256']}`
- `legacy_v1` 提示词指纹：`{snapshot['code']['legacy_prompt_fingerprint']}`
- `evidence_v2` 提示词指纹：`{snapshot['code']['evidence_prompt_fingerprint']}`
- 产品默认：`legacy_v1`；`evidence_v2` 仅研究模式。

## 历史聚合结果

- 正式第一轮 MAE：{history['formal-round1'].get('score_mae')}。
- 正式第二轮 MAE：{history['formal-round2'].get('score_mae')}。
- 新架构历史留出集 MAE：{evidence.get('evidence_v2_mae')}；高低排序通过：{evidence.get('high_low_ordering_passed')}。

## 冻结结论

当前基线不满足产品准入条件。后续只能在新增授权数据、严格分区和无答案盲跑流程上继续验证。
"""
    markdown_path.write_text(markdown, encoding="utf-8")
    return json_path, markdown_path
