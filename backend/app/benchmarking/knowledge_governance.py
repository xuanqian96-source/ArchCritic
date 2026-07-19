"""为公共建筑知识库建立来源、媒体、案例、知识卡和问答工作清单。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".svg", ".tif", ".tiff"}


def initialize_knowledge_governance(knowledge_root: Path) -> dict[str, Any]:
    """只新建不覆盖的治理清单，未核验内容默认不计入验收。"""
    if not knowledge_root.is_dir():
        raise ValueError(f"知识库目录不存在：{knowledge_root}")
    maintenance_root = knowledge_root / "99维护记录" / "长程Goal治理"
    maintenance_root.mkdir(parents=True, exist_ok=True)

    source_records = build_core_source_slots()
    media_records = build_media_records(knowledge_root)
    case_records = build_case_worklist(knowledge_root, media_records)
    knowledge_records = build_knowledge_card_worklist()
    question_records = build_question_worklist()

    outputs = {
        "source_records": write_new_json(
            maintenance_root / "source-records.json",
            {"version": 1, "records": source_records},
        ),
        "media_manifest": write_new_json(
            maintenance_root / "media-manifest.json",
            {"version": 1, "records": media_records},
        ),
        "case_worklist": write_new_json(
            maintenance_root / "case-source-worklist.json",
            {"version": 1, "records": case_records},
        ),
        "knowledge_worklist": write_new_json(
            maintenance_root / "knowledge-card-worklist.json",
            {"version": 1, "records": knowledge_records},
        ),
        "question_worklist": write_new_json(
            maintenance_root / "question-worklist.json",
            {"version": 1, "records": question_records},
        ),
    }
    return {
        "maintenance_root": str(maintenance_root),
        "source_slots": len(source_records),
        "media_records": len(media_records),
        "case_slots": len(case_records),
        "knowledge_card_slots": len(knowledge_records),
        "question_slots": len(question_records),
        "created_files": [str(path) for path in outputs.values() if path],
        "preserved_existing_files": sum(path is None for path in outputs.values()),
    }


def build_core_source_slots() -> list[dict[str, Any]]:
    """建立三份核心资料待核验槽位。"""
    return [
        {
            "source_id": f"SRC-CORE-{index:03d}",
            "source_title": "",
            "source_author_or_organization": "",
            "source_url_or_file": "",
            "publication_or_project_date": "",
            "accessed_at": "",
            "source_type": "book",
            "license_or_permission": "unverified",
            "allowed_use": "not_cleared",
            "attribution_text": "",
            "original_file_hash_or_snapshot_hash": "",
            "counts_as_core_source": True,
            "review_status": "draft",
            "reviewer": "",
            "notes": "未核验，不得计入 Goal 验收。",
        }
        for index in range(1, 4)
    ]


def build_media_records(knowledge_root: Path) -> list[dict[str, Any]]:
    """为现有案例图片建立稳定哈希和待授权记录。"""
    media_root = knowledge_root / "00原始资料" / "优秀案例"
    paths = sorted(
        path
        for path in media_root.rglob("*")
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    ) if media_root.is_dir() else []
    return [
        {
            "media_id": build_media_id(path, knowledge_root),
            "relative_path": str(path.relative_to(knowledge_root)).replace("\\", "/"),
            "sha256": sha256_file(path),
            "source_record_id": "",
            "creator_or_rights_holder": "",
            "license_or_permission": "unverified",
            "allowed_use": "not_cleared",
            "attribution_text": "",
            "review_status": "pending",
            "reviewer": "",
            "notes": "来源与权限未核验，只能留在待整理区。",
        }
        for path in paths
    ]


def build_case_worklist(
    knowledge_root: Path, media_records: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """为现有案例笔记分配固定编号并关联媒体。"""
    note_root = knowledge_root / "03优秀案例笔记"
    notes = sorted(note_root.glob("*.md")) if note_root.is_dir() else []
    records = []
    for index, note in enumerate(notes, start=1):
        title = read_title(note)
        matched_media = [
            item["media_id"]
            for item in media_records
            if f"/{title.split(' ')[0]}" in f"/{item['relative_path']}"
            or title.split(" ")[-1].replace(".md", "") in item["relative_path"]
        ]
        records.append(
            {
                "case_id": f"PBC-{index:03d}",
                "title": title,
                "note_file": str(note.relative_to(knowledge_root)).replace("\\", "/"),
                "reliable_source_record_ids": [],
                "media_record_ids": matched_media,
                "review_status": "draft",
                "missing_fields": [
                    "architect",
                    "location",
                    "year",
                    "scale",
                    "reliable_source",
                    "media_license",
                    "disciplinary_analysis",
                    "reviewer",
                ],
            }
        )
    return records


def build_knowledge_card_worklist() -> list[dict[str, Any]]:
    """按三个教学层级各建立二十张知识卡槽位。"""
    level_codes = (("beginner", "BEG"), ("advanced", "ADV"), ("master", "MAS"))
    return [
        {
            "card_id": f"KC-{code}-{index:03d}",
            "level": level,
            "title": "",
            "source_record_ids": [],
            "related_case_ids": [],
            "review_status": "planned",
        }
        for level, code in level_codes
        for index in range(1, 21)
    ]


def build_question_worklist() -> list[dict[str, Any]]:
    """建立三层各十题，其中固定十题为诱导或无依据题。"""
    records = []
    adversarial_ids = {3, 6, 9}
    for level_index, level in enumerate(("beginner", "advanced", "master"), start=1):
        for index in range(1, 11):
            is_adversarial = index in adversarial_ids or (level_index == 3 and index == 10)
            records.append(
                {
                    "question_id": f"Q-{level_index}-{index:02d}",
                    "level": level,
                    "question_type": "unanswerable" if is_adversarial else "evidence_based",
                    "question": "",
                    "expected_source_record_ids": [],
                    "review_status": "planned",
                }
            )
    return records


def read_title(path: Path) -> str:
    """从 Markdown 第一个一级标题读取案例名。"""
    text = path.read_text(encoding="utf-8")
    match = re.search(r"(?m)^#\s+(.+?)\s*$", text)
    return match.group(1).strip() if match else path.stem


def write_new_json(path: Path, data: dict[str, Any]) -> Path | None:
    """只在文件不存在时写入，避免覆盖人工审核记录。"""
    if path.exists():
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def sha256_file(path: Path) -> str:
    """计算媒体文件的稳定哈希。"""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_media_id(path: Path, knowledge_root: Path) -> str:
    """结合内容与相对路径生成逐文件唯一的媒体编号。"""
    content_hash = sha256_file(path)
    relative = str(path.relative_to(knowledge_root)).replace("\\", "/")
    path_hash = hashlib.sha256(relative.encode("utf-8")).hexdigest()
    return f"MEDIA-{content_hash[:12].upper()}-{path_hash[:4].upper()}"
