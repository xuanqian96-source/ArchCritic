"""ArchCritic 本地基准集准备、真实评图和报告生成入口。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.benchmarking.metrics import calculate_round_metrics
from app.benchmarking.calibration import fit_calibration_artifact
from app.benchmarking.preprocess import prepare_benchmark
from app.benchmarking.report import write_comparison_report, write_round_report
from app.benchmarking.research import export_research_package
from app.benchmarking.runner import run_benchmark_round
from app.benchmarking.evidence_report import export_evidence_v2_package
from app.benchmarking.blind_protocol import (
    create_blind_input_bundle,
    judge_frozen_round,
    run_blind_round,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATASET_ROOT = PROJECT_ROOT / "标注基准集"
PREPARED_ROOT = DATASET_ROOT / ".prepared"
RESULTS_ROOT = DATASET_ROOT / ".benchmark-results"
REPORTS_ROOT = DATASET_ROOT / "测试报告与论文数据"


def main() -> None:
    """解析命令并执行对应基准任务。"""
    parser = argparse.ArgumentParser(description="ArchCritic 真实评图基准工具")
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare_parser = subparsers.add_parser("prepare", help="生成匿名逐页评测材料")
    prepare_parser.add_argument("--force", action="store_true")

    run_parser = subparsers.add_parser("run", help="运行一轮真实多 Agent 评图")
    run_parser.add_argument("--round", required=True)
    run_parser.add_argument("--provider", default="dashscope")
    run_parser.add_argument("--model", default="qwen3.8-max")
    run_parser.add_argument("--workers", type=int, default=2)
    run_parser.add_argument("--cases", nargs="*")
    run_parser.add_argument(
        "--architecture", choices=["legacy_v1", "evidence_v2"], default="legacy_v1"
    )
    run_parser.add_argument("--calibration-file", type=Path)

    calibrate_parser = subparsers.add_parser("calibrate", help="用固定训练样本拟合教师校准层")
    calibrate_parser.add_argument("--round", required=True)
    calibrate_parser.add_argument("--train", nargs="+", required=True)
    calibrate_parser.add_argument("--heldout", nargs="+", required=True)
    calibrate_parser.add_argument(
        "--output", type=Path, default=PREPARED_ROOT / "evidence_v2_calibration.json"
    )

    report_parser = subparsers.add_parser("report", help="统计一轮结果")
    report_parser.add_argument("--round", required=True)
    report_parser.add_argument("--model", default="qwen3.8-max")
    report_parser.add_argument("--expected", type=int, default=6)

    compare_parser = subparsers.add_parser("compare", help="比较两轮指标")
    compare_parser.add_argument("--first", required=True)
    compare_parser.add_argument("--second", required=True)

    export_parser = subparsers.add_parser("export", help="导出论文数据、图表与工作报告")
    export_parser.add_argument("--first", required=True)
    export_parser.add_argument("--second", required=True)

    subparsers.add_parser("evidence-export", help="导出新版证据校准架构科研数据包")

    blind_prepare_parser = subparsers.add_parser(
        "blind-prepare", help="生成不含教师答案的独立盲测输入包"
    )
    blind_prepare_parser.add_argument("--source-root", type=Path, default=PREPARED_ROOT)
    blind_prepare_parser.add_argument(
        "--output-root",
        type=Path,
        default=DATASET_ROOT / ".blind-workspace" / "model-inputs",
    )

    blind_run_parser = subparsers.add_parser(
        "blind-run", help="不读取教师答案地运行并冻结评图结果"
    )
    blind_run_parser.add_argument("--test-id", required=True)
    blind_run_parser.add_argument(
        "--input-root",
        type=Path,
        default=DATASET_ROOT / ".blind-workspace" / "model-inputs",
    )
    blind_run_parser.add_argument("--results-root", type=Path)
    blind_run_parser.add_argument("--provider", default="dashscope")
    blind_run_parser.add_argument("--model", default="qwen3.8-max")
    blind_run_parser.add_argument("--workers", type=int, default=1)
    blind_run_parser.add_argument("--cases", nargs="*")
    blind_run_parser.add_argument(
        "--architecture", choices=["legacy_v1", "evidence_v2"], default="legacy_v1"
    )
    blind_run_parser.add_argument("--calibration-file", type=Path)
    blind_run_parser.add_argument("--resume-technical-failures", action="store_true")

    blind_judge_parser = subparsers.add_parser(
        "blind-judge", help="在结果冻结后用独立进程解封答案并裁判"
    )
    blind_judge_parser.add_argument("--results-root", type=Path, required=True)
    blind_judge_parser.add_argument("--private-answers", type=Path, required=True)
    blind_judge_parser.add_argument("--judgments-root", type=Path, required=True)
    blind_judge_parser.add_argument("--provider", default="dashscope")
    blind_judge_parser.add_argument("--model", default="qwen3.8-max")

    args = parser.parse_args()
    if args.command == "prepare":
        index = prepare_benchmark(DATASET_ROOT, PREPARED_ROOT, args.force)
        print(f"匿名样本准备完成：{len(index['cases'])}/6")
    elif args.command == "run":
        paths = run_benchmark_round(
            PREPARED_ROOT,
            RESULTS_ROOT / args.round,
            args.provider,
            args.model,
            args.workers,
            set(args.cases or []),
            args.architecture,
            args.calibration_file,
        )
        expected = len(args.cases) if args.cases else 6
        print(f"真实评图完成：{len(paths)}/{expected}")
    elif args.command == "calibrate":
        artifact = fit_calibration_artifact(
            RESULTS_ROOT / args.round,
            PREPARED_ROOT / "ground_truth.json",
            args.train,
            args.heldout,
            args.output,
            PREPARED_ROOT / "evidence_v2_split.json",
        )
        print(
            f"教师校准层已生成：{artifact['sample_count']} 份训练样本，"
            f"盲测答案参与拟合：否"
        )
    elif args.command == "report":
        metrics = calculate_round_metrics(
            RESULTS_ROOT / args.round,
            PREPARED_ROOT / "ground_truth.json",
        )
        metrics_file = RESULTS_ROOT / args.round / "metrics.json"
        metrics_file.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
        report_names = {
            "formal-round1": "01_第一轮测试报告.md",
            "formal-round2": "02_第二轮测试报告.md",
        }
        report_file = REPORTS_ROOT / report_names.get(
            args.round, f"探索性_{args.round}_测试报告.md"
        )
        write_round_report(report_file, args.round, metrics, args.model, args.expected)
        print(f"报告已生成：{report_file}")
    elif args.command == "compare":
        first = json.loads((RESULTS_ROOT / args.first / "metrics.json").read_text(encoding="utf-8"))
        second = json.loads((RESULTS_ROOT / args.second / "metrics.json").read_text(encoding="utf-8"))
        report_file = REPORTS_ROOT / "两轮简要对比.md"
        write_comparison_report(report_file, first, second)
        print(f"对比报告已生成：{report_file}")
    elif args.command == "export":
        summary = export_research_package(
            PREPARED_ROOT,
            RESULTS_ROOT,
            REPORTS_ROOT,
            args.first,
            args.second,
        )
        print(
            f"论文数据包已生成：{summary['case_count']} 个样本，"
            f"{summary['agent_row_count']} 条 Agent 数据"
        )
    elif args.command == "evidence-export":
        summary = export_evidence_v2_package(
            PREPARED_ROOT,
            RESULTS_ROOT,
            REPORTS_ROOT / "新版证据校准架构",
            "evidence-v2-calibration-raw",
            "evidence-v2-blind-test",
            "formal-round1",
        )
        print(
            f"新版科研数据包已生成：盲测 {summary['heldout_case_count']}/2，"
            f"MAE={summary['evidence_v2_mae']}"
        )
    elif args.command == "blind-prepare":
        bundle = create_blind_input_bundle(
            args.source_root.resolve(),
            args.output_root.resolve(),
        )
        print(f"盲测输入包已生成：{bundle['case_count']} 份，答案 0 份")
    elif args.command == "blind-run":
        results_root = args.results_root or (
            DATASET_ROOT / ".blind-workspace" / "run-results" / args.test_id
        )
        manifest = run_blind_round(
            args.input_root.resolve(),
            results_root.resolve(),
            args.provider,
            args.model,
            args.architecture,
            args.test_id,
            args.workers,
            set(args.cases or []),
            args.calibration_file.resolve() if args.calibration_file else None,
            args.resume_technical_failures,
        )
        print(
            f"盲测评图完成：{manifest['successful_count']}/"
            f"{len(manifest['case_ids'])}，状态 {manifest['run_status']}"
        )
    else:
        manifest = judge_frozen_round(
            args.results_root.resolve(),
            args.private_answers.resolve(),
            args.judgments_root.resolve(),
            args.provider,
            args.model,
        )
        print(f"冻结结果裁判完成：{len(manifest['judgment_hashes'])} 份")


if __name__ == "__main__":
    main()
