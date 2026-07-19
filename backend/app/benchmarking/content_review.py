"""导出和校验长程 Goal 内容复核表，并在明确确认后回写人工决定。"""

from __future__ import annotations

import csv
from datetime import datetime
import hashlib
import json
from pathlib import Path
from typing import Any


REVIEW_COLUMNS = (
    "content_type",
    "content_id",
    "title_or_question",
    "level_or_type",
    "source_ids",
    "evidence_summary",
    "current_status",
    "decision",
    "reviewer",
    "reviewed_at",
    "review_comment",
    "human_review_confirmed",
)
SHEET_FILES = {
    "knowledge_card": "知识卡复核表.csv",
    "question": "固定问答复核表.csv",
    "case": "公共建筑案例复核表.csv",
    "evaluation_task": "知识专项任务复核表.csv",
}
DECISION_TO_STATUS = {
    "approve": "approved",
    "revise": "pending",
    "reject": "rejected",
}
REVIEWER_PLACEHOLDERS = {
    "",
    "codex",
    "chatgpt",
    "ai",
    "建筑学学科专家待复核",
    "待复核",
}


def export_review_bundle(knowledge_root: Path, output_root: Path) -> dict[str, Any]:
    """按当前草稿快照生成三张人工复核表、说明和防错清单。"""
    governance_root = knowledge_root / "99维护记录" / "长程Goal治理"
    inputs = review_input_files(governance_root)
    output_root.mkdir(parents=True, exist_ok=True)

    rows = load_review_rows(inputs)
    sheets: dict[str, dict[str, Any]] = {}
    for content_type, filename in SHEET_FILES.items():
        selected = [item for item in rows if item["content_type"] == content_type]
        sheet_path = output_root / filename
        write_review_sheet(sheet_path, selected)
        sheets[content_type] = {
            "file": filename,
            "record_count": len(selected),
            "content_ids": [item["content_id"] for item in selected],
        }

    manifest = {
        "version": 1,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "knowledge_root": str(knowledge_root.resolve()),
        "input_snapshots": {
            str(path.relative_to(governance_root)).replace("\\", "/"): sha256_file(path)
            for path in inputs
        },
        "sheets": sheets,
        "rules": {
            "allowed_decisions": list(DECISION_TO_STATUS),
            "human_confirmation_required": True,
            "all_rows_required_before_apply": True,
            "input_hash_must_match": True,
        },
    }
    manifest_path = output_root / "复核包清单.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_review_guide(output_root / "人工复核说明.md", sheets)
    return {
        "output_root": str(output_root),
        "record_count": len(rows),
        "sheet_counts": {
            content_type: item["record_count"] for content_type, item in sheets.items()
        },
        "manifest": str(manifest_path),
    }


def validate_review_bundle(
    knowledge_root: Path, bundle_root: Path
) -> dict[str, Any]:
    """检查复核表是否完整、确为人工确认且仍对应同一批草稿。"""
    manifest = load_manifest(bundle_root / "复核包清单.json")
    governance_root = knowledge_root / "99维护记录" / "长程Goal治理"
    errors = validate_input_snapshots(governance_root, manifest)
    rows: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    for content_type, metadata in manifest["sheets"].items():
        sheet_path = bundle_root / metadata["file"]
        sheet_rows, sheet_errors = read_and_validate_sheet(
            sheet_path,
            content_type,
            set(metadata["content_ids"]),
        )
        errors.extend(sheet_errors)
        for row in sheet_rows:
            key = (row["content_type"], row["content_id"])
            if key in seen:
                errors.append(f"复核编号重复：{key[0]} / {key[1]}")
            seen.add(key)
        rows.extend(sheet_rows)

    expected = sum(item["record_count"] for item in manifest["sheets"].values())
    if len(rows) != expected:
        errors.append(f"复核行数应为 {expected}，实际为 {len(rows)}")
    return {
        "valid": not errors,
        "errors": errors,
        "record_count": len(rows),
        "approved_count": sum(row.get("decision") == "approve" for row in rows),
        "revise_count": sum(row.get("decision") == "revise" for row in rows),
        "rejected_count": sum(row.get("decision") == "reject" for row in rows),
        "rows": rows,
    }


def apply_review_bundle(
    knowledge_root: Path,
    bundle_root: Path,
    *,
    confirm_human_reviewed: bool,
) -> dict[str, Any]:
    """只在明确确认且复核表完整时，把人工决定写回结构化草稿。"""
    if not confirm_human_reviewed:
        raise ValueError("必须显式确认这些决定已经由人工复核，不能由 AI 自行通过。")
    validation = validate_review_bundle(knowledge_root, bundle_root)
    if not validation["valid"]:
        raise ValueError("复核包未通过校验：" + "；".join(validation["errors"]))

    decisions = {
        (row["content_type"], row["content_id"]): row
        for row in validation["rows"]
    }
    governance_root = knowledge_root / "99维护记录" / "长程Goal治理"
    changed_records = 0
    for path in review_input_files(governance_root):
        content_type = content_type_for_file(path)
        data = load_records(path)
        id_field = id_field_for_type(content_type)
        for record in data["records"]:
            row = decisions[(content_type, str(record[id_field]))]
            record["review_status"] = DECISION_TO_STATUS[row["decision"]]
            record["reviewer"] = row["reviewer"].strip()
            record["reviewed_at"] = row["reviewed_at"].strip()
            record["review_comment"] = row["review_comment"].strip()
            record["review_decision"] = row["decision"]
            record["human_review_confirmed"] = True
            changed_records += 1
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    receipt = {
        "version": 1,
        "applied_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "changed_record_count": changed_records,
        "approved_count": validation["approved_count"],
        "revise_count": validation["revise_count"],
        "rejected_count": validation["rejected_count"],
        "post_apply_snapshots": {
            str(path.relative_to(governance_root)).replace("\\", "/"): sha256_file(path)
            for path in review_input_files(governance_root)
        },
    }
    receipt_path = bundle_root / "复核回写凭据.json"
    receipt_path.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return receipt


def review_input_files(governance_root: Path) -> list[Path]:
    """返回需要人工复核的结构化草稿文件。"""
    paths = [
        *sorted(governance_root.glob("knowledge-card-drafts-*.json")),
        governance_root / "question-drafts-v1.json",
        governance_root / "public-building-case-drafts-v1.json",
        governance_root / "case-retrieval-task-drafts-v1.json",
        governance_root / "problem-linkage-task-drafts-v1.json",
    ]
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise ValueError("缺少复核输入文件：" + "；".join(missing))
    return paths


def load_review_rows(paths: list[Path]) -> list[dict[str, str]]:
    """把知识卡、问答和案例整理成统一的复核表行。"""
    rows: list[dict[str, str]] = []
    for path in paths:
        content_type = content_type_for_file(path)
        for record in load_records(path)["records"]:
            rows.append(review_row(content_type, record))
    return rows


def review_row(content_type: str, record: dict[str, Any]) -> dict[str, str]:
    """提取人工复核真正需要阅读和填写的字段。"""
    id_field = id_field_for_type(content_type)
    if content_type == "knowledge_card":
        title = str(record.get("title", ""))
        level = str(record.get("level", ""))
        sources = record.get("source_record_ids", [])
        evidence = "；".join(
            f"{item.get('source_id', '')}:{item.get('locator', '')}"
            for item in record.get("source_locators", [])
        )
    elif content_type == "question":
        title = str(record.get("question", ""))
        level = f"{record.get('level', '')}/{record.get('question_type', '')}"
        sources = record.get("expected_source_record_ids", [])
        evidence = "；".join(str(item) for item in record.get("expected_source_locators", []))
    elif content_type == "case":
        title = str(record.get("title", ""))
        level = "深度证据:" + ",".join(record.get("depth_evidence_categories", []))
        sources = record.get("reliable_source_record_ids", [])
        evidence = f"证据{len(record.get('evidence_register', []))}条；媒体:{record.get('media_permission_status', '')}"
    else:
        title = str(record.get("query_or_problem", ""))
        level = f"{record.get('task_type', '')}/{record.get('problem_category', '')}"
        sources = [
            *record.get("expected_knowledge_card_ids", []),
            *record.get("expected_case_ids", []),
        ]
        evidence = "；".join(str(item) for item in record.get("required_reason_points", []))
    return {
        "content_type": content_type,
        "content_id": str(record.get(id_field, "")),
        "title_or_question": title,
        "level_or_type": level,
        "source_ids": ",".join(str(item) for item in sources),
        "evidence_summary": evidence,
        "current_status": str(record.get("review_status", "")),
        "decision": "",
        "reviewer": "",
        "reviewed_at": "",
        "review_comment": "",
        "human_review_confirmed": "false",
    }


def write_review_sheet(path: Path, rows: list[dict[str, str]]) -> None:
    """以标准 UTF-8 CSV 保存复核表。"""
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEW_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def read_and_validate_sheet(
    path: Path,
    content_type: str,
    expected_ids: set[str],
) -> tuple[list[dict[str, str]], list[str]]:
    """读取单张复核表，并拒绝缺行、占位审核人或不完整决定。"""
    if not path.is_file():
        return [], [f"缺少复核表：{path.name}"]
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = [dict(row) for row in reader]
        fieldnames = set(reader.fieldnames or [])
    errors = []
    if not set(REVIEW_COLUMNS) <= fieldnames:
        errors.append(f"{path.name} 缺少必填列")
        return rows, errors
    actual_ids = {row.get("content_id", "") for row in rows}
    if actual_ids != expected_ids:
        errors.append(f"{path.name} 的编号集合与导出清单不一致")
    for row in rows:
        item_id = row.get("content_id", "")
        if row.get("content_type") != content_type:
            errors.append(f"{item_id} 的内容类型被改动")
        decision = row.get("decision", "").strip().lower()
        reviewer = row.get("reviewer", "").strip()
        confirmed = row.get("human_review_confirmed", "").strip().lower()
        if decision not in DECISION_TO_STATUS:
            errors.append(f"{item_id} 缺少有效决定")
        if not reviewer or reviewer.lower() in REVIEWER_PLACEHOLDERS:
            errors.append(f"{item_id} 缺少真实人工复核人")
        if not row.get("reviewed_at", "").strip():
            errors.append(f"{item_id} 缺少复核时间")
        if decision in {"revise", "reject"} and not row.get("review_comment", "").strip():
            errors.append(f"{item_id} 退回或拒绝时必须填写原因")
        if confirmed not in {"true", "yes", "1", "是"}:
            errors.append(f"{item_id} 未确认由人工完成复核")
        row["decision"] = decision
    return rows, errors


def validate_input_snapshots(governance_root: Path, manifest: dict[str, Any]) -> list[str]:
    """确保复核期间草稿没有改变，防止旧复核表回写新内容。"""
    errors = []
    for relative, expected_hash in manifest.get("input_snapshots", {}).items():
        path = governance_root / relative
        if not path.is_file():
            errors.append(f"复核输入已丢失：{relative}")
        elif sha256_file(path) != expected_hash:
            errors.append(f"复核输入已变化，必须重新导出：{relative}")
    return errors


def content_type_for_file(path: Path) -> str:
    """根据固定文件名识别内容类型。"""
    if path.name.startswith("knowledge-card-drafts-"):
        return "knowledge_card"
    if path.name == "question-drafts-v1.json":
        return "question"
    if path.name == "public-building-case-drafts-v1.json":
        return "case"
    if path.name in {
        "case-retrieval-task-drafts-v1.json",
        "problem-linkage-task-drafts-v1.json",
    }:
        return "evaluation_task"
    raise ValueError(f"未知复核输入：{path}")


def id_field_for_type(content_type: str) -> str:
    """返回各类内容的稳定编号字段。"""
    return {
        "knowledge_card": "card_id",
        "question": "question_id",
        "case": "case_id",
        "evaluation_task": "task_id",
    }[content_type]


def load_records(path: Path) -> dict[str, Any]:
    """读取具有 records 数组的 UTF-8 JSON。"""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("records"), list):
        raise ValueError(f"复核输入格式错误：{path}")
    return data


def load_manifest(path: Path) -> dict[str, Any]:
    """读取并检查复核包清单。"""
    if not path.is_file():
        raise ValueError(f"复核包清单不存在：{path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("version") != 1 or not isinstance(data.get("sheets"), dict):
        raise ValueError("复核包清单格式错误")
    return data


def write_review_guide(path: Path, sheets: dict[str, dict[str, Any]]) -> None:
    """生成人工复核人可直接阅读的简短说明。"""
    text = f"""# ArchCritic 内容人工复核说明

本复核包锁定了当前草稿文件哈希。草稿发生任何变化后，旧复核表会被拒绝回写，必须重新导出。

## 本批数量

- 知识卡：{sheets['knowledge_card']['record_count']} 条
- 固定问答：{sheets['question']['record_count']} 条
- 公共建筑案例：{sheets['case']['record_count']} 条
- 知识专项固定任务：{sheets['evaluation_task']['record_count']} 条

## 填写规则

1. `decision` 只能填写 `approve`、`revise` 或 `reject`。
2. `reviewer` 填写真实人工复核人姓名；AI、Codex 或“待复核”不能作为复核人。
3. `reviewed_at` 使用带日期的时间；退回或拒绝必须在 `review_comment` 写明原因。
4. 逐条核对事实、来源位置、建筑学推断、适用边界和版权后，把 `human_review_confirmed` 改为 `true`。
5. 不得修改内容编号、类型或删除行。完整校验通过后，才允许使用带明确确认参数的回写命令。

## 判断重点

- 知识卡：来源是否真的支持结论，是否区分规范、教材观点、案例启发和经验。
- 固定问答：预期答案是否可由指定来源得到，无依据题是否明确要求拒答。
- 案例：基本事实、四类分析证据、推断边界、可迁移启发和图片许可是否准确。
- 固定任务：检索问题是否自然、首选与相关编号是否合理、通过条件是否足以区分有效和无效推荐。

复核通过只表示内容可进入后续检索验收，不代表 AI 评分可替代教师成绩。
"""
    path.write_text(text, encoding="utf-8")


def sha256_file(path: Path) -> str:
    """分块计算文件哈希。"""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
