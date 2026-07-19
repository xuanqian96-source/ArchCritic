"""导出、校验和回写 ArchCritic 知识与案例人工复核结果。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.benchmarking.content_review import (
    apply_review_bundle,
    export_review_bundle,
    validate_review_bundle,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def build_parser() -> argparse.ArgumentParser:
    """建立复核工作流命令行参数。"""
    parser = argparse.ArgumentParser(description="ArchCritic 内容人工复核工作流")
    parser.add_argument(
        "--knowledge-root",
        type=Path,
        default=PROJECT_ROOT.parent / "知识库测试版",
    )
    parser.add_argument(
        "--bundle-root",
        type=Path,
        default=PROJECT_ROOT / "标注基准集" / "治理与验收" / "人工复核包",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("export", help="生成三张待填写复核表")
    commands.add_parser("validate", help="校验已填写复核表，不修改草稿")
    apply_parser = commands.add_parser("apply", help="确认后把完整人工决定写回草稿")
    apply_parser.add_argument(
        "--confirm-human-reviewed",
        action="store_true",
        help="确认所有决定均由真实人工逐条完成",
    )
    return parser


def main() -> None:
    """执行选定的复核工作流。"""
    args = build_parser().parse_args()
    knowledge_root = args.knowledge_root.resolve()
    bundle_root = args.bundle_root.resolve()
    if args.command == "export":
        result = export_review_bundle(knowledge_root, bundle_root)
        print(
            f"复核包已生成：共 {result['record_count']} 条，"
            f"知识卡 {result['sheet_counts']['knowledge_card']}，"
            f"问答 {result['sheet_counts']['question']}，"
            f"案例 {result['sheet_counts']['case']}，"
            f"固定任务 {result['sheet_counts']['evaluation_task']}"
        )
        print(result["output_root"])
        return
    if args.command == "validate":
        result = validate_review_bundle(knowledge_root, bundle_root)
        print(json.dumps({key: value for key, value in result.items() if key != "rows"}, ensure_ascii=False, indent=2))
        if not result["valid"]:
            raise SystemExit(1)
        return
    result = apply_review_bundle(
        knowledge_root,
        bundle_root,
        confirm_human_reviewed=args.confirm_human_reviewed,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
