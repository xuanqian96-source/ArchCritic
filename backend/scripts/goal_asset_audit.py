"""ArchCritic 长程 Goal 样本、知识和案例资产盘点入口。"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.benchmarking.asset_audit import audit_goal_assets
from app.benchmarking.asset_audit_report import write_audit_files
from app.benchmarking.baseline_snapshot import build_baseline_snapshot, write_baseline_snapshot


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    """执行只读盘点，并可选按正式门槛返回失败状态。"""
    parser = argparse.ArgumentParser(description="ArchCritic 长程 Goal 资产盘点")
    parser.add_argument("--dataset-root", type=Path, default=PROJECT_ROOT / "标注基准集")
    parser.add_argument("--knowledge-root", type=Path, default=PROJECT_ROOT.parent / "知识库测试版")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=PROJECT_ROOT / "标注基准集" / "治理与验收",
    )
    parser.add_argument("--strict", action="store_true", help="任一资产门槛未通过时返回失败")
    args = parser.parse_args()

    audit = audit_goal_assets(args.dataset_root.resolve(), args.knowledge_root.resolve())
    json_path, markdown_path = write_audit_files(args.output_root.resolve(), audit)
    snapshot = build_baseline_snapshot(
        PROJECT_ROOT,
        args.dataset_root.resolve(),
        args.knowledge_root.resolve(),
    )
    snapshot_json, snapshot_markdown = write_baseline_snapshot(
        args.output_root.resolve(), snapshot
    )
    gates = audit["gates"]
    print(f"资产盘点完成：通过 {gates['passed']}，未通过 {gates['failed']}")
    print(f"JSON：{json_path}")
    print(f"报告：{markdown_path}")
    print(f"基线 JSON：{snapshot_json}")
    print(f"基线报告：{snapshot_markdown}")
    if args.strict and not gates["all_asset_gates_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
