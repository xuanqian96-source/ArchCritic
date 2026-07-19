"""盘点固定知识问答、案例检索和问题联动任务的准备状态。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.benchmarking.content_evaluation import (
    load_evaluation_tasks,
    run_retrieval_evaluation,
    summarize_evaluation_tasks,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_ids(governance_root: Path) -> tuple[set[str], set[str]]:
    """读取当前知识卡和案例稳定编号。"""
    card_ids = set()
    for path in governance_root.glob("knowledge-card-drafts-*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        card_ids.update(str(item["card_id"]) for item in data["records"])
    case_data = json.loads(
        (governance_root / "case-source-worklist.json").read_text(encoding="utf-8")
    )
    case_ids = {str(item["case_id"]) for item in case_data["records"]}
    return card_ids, case_ids


def main() -> None:
    """输出结构盘点，或在全部人工批准后运行本地检索验收。"""
    parser = argparse.ArgumentParser(description="ArchCritic 内容专项固定任务")
    parser.add_argument("command", choices=("status", "run"))
    parser.add_argument(
        "--knowledge-root",
        type=Path,
        default=PROJECT_ROOT.parent / "知识库测试版",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "标注基准集" / "治理与验收" / "知识专项固定任务盘点.json",
    )
    args = parser.parse_args()
    knowledge_root = args.knowledge_root.resolve()
    governance_root = knowledge_root / "99维护记录" / "长程Goal治理"
    tasks = load_evaluation_tasks(governance_root)
    if args.command == "status":
        card_ids, case_ids = load_ids(governance_root)
        result = summarize_evaluation_tasks(tasks, card_ids, case_ids)
    else:
        result = run_retrieval_evaluation(knowledge_root, tasks)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
