"""会议论文九样本、四条件盲测实验的命令行入口。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from dotenv import load_dotenv


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
load_dotenv(BACKEND_ROOT / ".env", override=False)

from app.benchmarking.paper_experiment import (  # noqa: E402
    PAPER_CONDITIONS,
    prepare_paper_experiment,
    run_paper_condition,
)
from app.benchmarking.paper_experiment_analysis import (  # noqa: E402
    calculate_paper_metrics,
    evaluate_pause_gate,
    judge_paper_condition,
    judge_paper_condition_local,
)


WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
DATASET_ROOT = WORKSPACE_ROOT / "标注基准集与实验数据与论文"
EXPERIMENT_ROOT = DATASET_ROOT / "正式论文实验_2026-07-27"
INPUT_ROOT = EXPERIMENT_ROOT / "01_匿名输入包"
PRIVATE_ROOT = EXPERIMENT_ROOT / "02_私有答案包"
RESULTS_ROOT = EXPERIMENT_ROOT / "03_模型原始结果"
JUDGMENTS_ROOT = EXPERIMENT_ROOT / "04_严格语义核对"
METRICS_ROOT = EXPERIMENT_ROOT / "05_统计结果"


def main() -> None:
    """解析命令并执行准备、评图、裁判或统计。"""
    parser = argparse.ArgumentParser(description="ArchCritic 会议论文正式实验")
    parser.add_argument("--experiment-root", type=Path, default=EXPERIMENT_ROOT)
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare_parser = subparsers.add_parser("prepare", help="生成九份匿名输入和私有答案")
    prepare_parser.add_argument("--dataset-root", type=Path, default=DATASET_ROOT)

    run_parser = subparsers.add_parser("run", help="运行并冻结一个实验条件")
    run_parser.add_argument("--condition", choices=PAPER_CONDITIONS, required=True)
    run_parser.add_argument("--provider", default="dashscope")
    run_parser.add_argument("--model", default="qwen3.8-max")
    run_parser.add_argument("--workers", type=int, default=1)

    judge_parser = subparsers.add_parser("judge", help="对冻结结果做严格语义核对")
    judge_parser.add_argument("--condition", choices=PAPER_CONDITIONS, required=True)
    judge_parser.add_argument("--provider", default="dashscope")
    judge_parser.add_argument("--model", default="qwen3.8-max")

    local_judge_parser = subparsers.add_parser(
        "judge-local", help="不向外部发送私有答案，按逐条决定核对冻结结果"
    )
    local_judge_parser.add_argument("--condition", choices=PAPER_CONDITIONS, required=True)
    local_judge_parser.add_argument("--decisions", type=Path, required=True)

    metrics_parser = subparsers.add_parser("metrics", help="计算一个条件的实验指标")
    metrics_parser.add_argument("--condition", choices=PAPER_CONDITIONS, required=True)

    subparsers.add_parser("gate", help="按预注册规则判断是否暂停")
    subparsers.add_parser("status", help="查看四个条件的完成状态")

    args = parser.parse_args()
    root = args.experiment_root.resolve()
    input_root = root / INPUT_ROOT.name
    private_root = root / PRIVATE_ROOT.name
    results_root = root / RESULTS_ROOT.name
    judgments_root = root / JUDGMENTS_ROOT.name
    metrics_root = root / METRICS_ROOT.name

    if args.command == "prepare":
        manifest = prepare_paper_experiment(
            args.dataset_root.resolve(),
            input_root,
            private_root,
        )
        print(
            f"匿名实验材料完成：{manifest['case_count']}/9，"
            "模型输入不含教师分数和问题清单。"
        )
        return

    if args.command == "run":
        require_qwen(args.provider, args.model)
        manifest = run_paper_condition(
            input_root,
            results_root / args.condition,
            args.condition,
            args.provider,
            args.model,
            args.workers,
        )
        print(
            f"{args.condition} 评图完成：{manifest['successful_count']}/"
            f"{len(manifest['case_ids'])}，状态 {manifest['run_status']}。"
        )
        return

    if args.command == "judge":
        require_qwen(args.provider, args.model)
        manifest = judge_paper_condition(
            results_root / args.condition,
            private_root / "ground_truth.json",
            judgments_root / args.condition,
            args.provider,
            args.model,
        )
        print(f"{args.condition} 严格语义核对完成：{len(manifest['judgment_hashes'])}/9。")
        return

    if args.command == "judge-local":
        manifest = judge_paper_condition_local(
            results_root / args.condition,
            private_root / "ground_truth.json",
            args.decisions.resolve(),
            judgments_root / args.condition,
        )
        print(
            f"{args.condition} 本地严格核对完成："
            f"{len(manifest['judgment_hashes'])}/9，私有答案外发：否。"
        )
        return

    if args.command == "metrics":
        metrics = calculate_paper_metrics(
            results_root / args.condition,
            judgments_root / args.condition,
            private_root / "ground_truth.json",
        )
        metrics_root.mkdir(parents=True, exist_ok=True)
        output = metrics_root / f"{args.condition}.metrics.json"
        write_json(output, metrics)
        print(
            f"{args.condition} 统计完成：9/9，"
            f"MAE={metrics['score_mae']}，严格问题F1={metrics['strict_issue_f1']}。"
        )
        return

    if args.command == "gate":
        available = load_available_metrics(metrics_root)
        gate = evaluate_pause_gate(available)
        metrics_root.mkdir(parents=True, exist_ok=True)
        write_json(metrics_root / "pause_gate.json", gate)
        print(
            "需要暂停。" if gate["pause_required"] else "未触发暂停条件，可继续后续实验。"
        )
        for reason in gate["reasons"]:
            print(f"- {reason}")
        return

    print(json.dumps(build_status(root), ensure_ascii=False, indent=2))


def require_qwen(provider: str, model: str) -> None:
    """正式实验只接受百炼千问模型。"""
    if provider != "dashscope" or not model.lower().startswith("qwen"):
        raise ValueError("正式四条件实验统一要求 provider=dashscope 且模型为 qwen。")


def load_available_metrics(metrics_root: Path) -> dict[str, dict]:
    """读取已经完成的条件指标。"""
    result = {}
    for condition in PAPER_CONDITIONS:
        path = metrics_root / f"{condition}.metrics.json"
        if path.is_file():
            result[condition] = json.loads(path.read_text(encoding="utf-8"))
    return result


def build_status(root: Path) -> dict:
    """汇总匿名输入、结果冻结、核对和统计状态。"""
    status = {
        "experiment_root": str(root),
        "prepared": (root / INPUT_ROOT.name / "BLIND_INPUT_BUNDLE.json").is_file(),
        "conditions": {},
    }
    for condition in PAPER_CONDITIONS:
        result_dir = root / RESULTS_ROOT.name / condition
        judgment_dir = root / JUDGMENTS_ROOT.name / condition
        status["conditions"][condition] = {
            "result_count": len(list(result_dir.glob("CASE-*.json"))),
            "frozen": (result_dir / "FROZEN.json").is_file(),
            "judgment_count": len(list(judgment_dir.glob("CASE-*.judge.json"))),
            "metrics": (
                root / METRICS_ROOT.name / f"{condition}.metrics.json"
            ).is_file(),
        }
    return status


def write_json(path: Path, value: dict) -> None:
    """以 UTF-8 写入 JSON。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
