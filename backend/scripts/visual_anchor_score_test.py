"""建立视觉评分锚点集，并运行高中低各一份的最终 Agent 校准测试。"""

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

from app.benchmarking.visual_anchor_experiment import (  # noqa: E402
    analyze_visual_anchor_pilot,
    build_visual_anchor_set,
    repair_visual_anchor_redactions,
    run_visual_anchor_pilot,
)


WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
DATASET_ROOT = WORKSPACE_ROOT / "标注基准集与实验数据与论文"
ANCHOR_ROOT = DATASET_ROOT / "图纸评分视觉锚点集_2026-07-27"
EXPERIMENT_ROOT = DATASET_ROOT / "正式论文实验_2026-07-27"
INPUT_ROOT = EXPERIMENT_ROOT / "01_匿名输入包"
PRIVATE_ANSWERS = EXPERIMENT_ROOT / "02_私有答案包" / "ground_truth.json"
C2_RESULTS = EXPERIMENT_ROOT / "03_模型原始结果" / "c2_multi_agent"
OUTPUT_ROOT = DATASET_ROOT / "图纸评分视觉锚点测试_2026-07-27_v2"
PILOT_CASE_IDS = ("CASE-004", "CASE-007", "CASE-001")


def main() -> None:
    """解析锚点构建、盲跑、解封分析和状态命令。"""
    parser = argparse.ArgumentParser(description="ArchCritic 视觉评分锚点测试")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("build-anchors", help="建立匿名视觉评分锚点集")
    subparsers.add_parser("repair-redactions", help="补做人工视觉定位的身份遮挡")

    run_parser = subparsers.add_parser("run", help="只运行最终 Agent，不读取测试教师分")
    run_parser.add_argument("--provider", default="dashscope")
    run_parser.add_argument("--model", default="qwen3.8-max")

    subparsers.add_parser("analyze", help="结果完成后解封三份教师分并比较")
    subparsers.add_parser("status", help="查看锚点和三份结果状态")
    args = parser.parse_args()

    if args.command == "build-anchors":
        manifest = build_visual_anchor_set(WORKSPACE_ROOT, ANCHOR_ROOT)
        print(f"视觉评分锚点集完成：{len(manifest['anchors'])}/11。")
        return

    if args.command == "repair-redactions":
        result = repair_visual_anchor_redactions(WORKSPACE_ROOT, ANCHOR_ROOT)
        print(
            f"视觉身份遮挡复核完成：修复 {result['repaired_count']}/"
            f"{result['anchor_count']}。"
        )
        return

    if args.command == "run":
        if args.provider != "dashscope" or not args.model.startswith("qwen"):
            raise ValueError("本次对照测试统一使用百炼千问模型。")
        manifest = run_visual_anchor_pilot(
            INPUT_ROOT,
            C2_RESULTS,
            ANCHOR_ROOT,
            OUTPUT_ROOT,
            args.provider,
            args.model,
            PILOT_CASE_IDS,
        )
        print(
            f"三案例最终 Agent 测试完成：{manifest['successful_count']}/3，"
            f"失败 {manifest['failure_count']}。"
        )
        return

    if args.command == "analyze":
        summary = analyze_visual_anchor_pilot(
            OUTPUT_ROOT,
            C2_RESULTS,
            PRIVATE_ANSWERS,
            PILOT_CASE_IDS,
        )
        print(
            f"三案例分析完成：{summary['case_count']}/3，"
            f"改善 {summary['improved_case_count']}/3。"
        )
        return

    print(
        json.dumps(
            {
                "anchor_manifest": (ANCHOR_ROOT / "manifest.json").is_file(),
                "result_count": len(list(OUTPUT_ROOT.glob("CASE-*.json"))),
                "analysis": (OUTPUT_ROOT / "analysis.json").is_file(),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
