"""为 ArchCritic 公共建筑知识库初始化不覆盖的治理清单。"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.benchmarking.knowledge_governance import initialize_knowledge_governance


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    """初始化长程 Goal 内容治理工作区。"""
    parser = argparse.ArgumentParser(description="ArchCritic 知识库治理初始化")
    parser.add_argument(
        "--knowledge-root",
        type=Path,
        default=PROJECT_ROOT.parent / "知识库测试版",
    )
    args = parser.parse_args()
    result = initialize_knowledge_governance(args.knowledge_root.resolve())
    print(
        f"治理清单已初始化：来源 {result['source_slots']}，"
        f"媒体 {result['media_records']}，案例 {result['case_slots']}，"
        f"知识卡 {result['knowledge_card_slots']}，问答 {result['question_slots']}"
    )
    print(
        f"新建 {len(result['created_files'])} 份，"
        f"已存在并保留 {result['preserved_existing_files']} 份"
    )


if __name__ == "__main__":
    main()
