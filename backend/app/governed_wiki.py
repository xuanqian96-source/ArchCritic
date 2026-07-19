"""把人工批准的结构化知识卡和案例转换为 Wiki 检索条目。"""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any
from urllib.parse import quote

from .benchmarking.asset_content_validation import (
    approved_source_records,
    case_draft_record_is_complete,
    knowledge_card_record_is_complete,
    permitted_media_records,
)


STAGE_CODES = {
    "概念阶段": "concept",
    "方案阶段": "scheme",
    "图纸阶段": "drawing",
}


def collect_governed_references(wiki_root: Path, stage_name: str) -> list[dict[str, Any]]:
    """只读取人工确认、来源合格且媒体许可满足要求的结构化内容。"""
    governance_root = wiki_root / "99维护记录" / "长程Goal治理"
    try:
        source_records = read_records(governance_root / "source-records.json")
        media_records = read_records(governance_root / "media-manifest.json")
    except (OSError, ValueError, json.JSONDecodeError):
        return []
    approved_source_ids = {
        item["source_id"] for item in approved_source_records(source_records)
    }
    permitted_media = {
        item["media_id"]: item
        for item in permitted_media_records(media_records, approved_source_ids)
    }
    references = collect_knowledge_references(
        governance_root,
        stage_name,
        approved_source_ids,
    )
    references.extend(
        collect_case_references(
            governance_root,
            approved_source_ids,
            permitted_media,
            wiki_root,
        )
    )
    return references


def collect_knowledge_references(
    governance_root: Path,
    stage_name: str,
    approved_source_ids: set[str],
) -> list[dict[str, Any]]:
    """收集当前阶段可用的人工批准知识卡。"""
    references = []
    stage_code = STAGE_CODES.get(stage_name, "")
    for path in sorted(governance_root.glob("knowledge-card-drafts-*.json")):
        try:
            records = read_records(path)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        for record in records:
            if not is_human_approved(record):
                continue
            if not knowledge_card_record_is_complete(record, approved_source_ids):
                continue
            if stage_code and stage_code not in record.get("stages", []):
                continue
            references.append(build_knowledge_reference(record, path))
    return references


def collect_case_references(
    governance_root: Path,
    approved_source_ids: set[str],
    permitted_media: dict[str, dict[str, Any]],
    wiki_root: Path,
) -> list[dict[str, Any]]:
    """收集人工批准且每张关联图片均已授权的案例。"""
    path = governance_root / "public-building-case-drafts-v1.json"
    try:
        records = read_records(path)
    except (OSError, ValueError, json.JSONDecodeError):
        return []
    references = []
    for record in records:
        media_ids = [str(item) for item in record.get("media_record_ids", [])]
        if not is_human_approved(record):
            continue
        if not case_draft_record_is_complete(record, approved_source_ids):
            continue
        if record.get("media_permission_status") != "cleared":
            continue
        if not media_ids or not set(media_ids) <= permitted_media.keys():
            continue
        references.append(
            build_case_reference(
                record,
                path,
                [permitted_media[media_id] for media_id in media_ids],
                wiki_root,
            )
        )
    return references


def build_knowledge_reference(record: dict[str, Any], path: Path) -> dict[str, Any]:
    """把结构化知识卡转换为现有报告可显示的引用条目。"""
    source_text = ", ".join(record["source_record_ids"])
    content = (
        f"# {record['title']}\n\n"
        f"## 学习目标\n\n{record['learning_objective']}\n\n"
        f"## 学生版解释\n\n{record['student_explanation']}\n\n"
        f"## 适用边界\n\n适用阶段：{', '.join(record['stages'])}；"
        f"评价维度：{', '.join(record['dimensions'])}。\n\n"
        f"## 来源\n\n{source_text}"
    )
    return base_reference(
        governance_id=record["card_id"],
        title=record["title"],
        source_type="知识卡",
        excerpt=record["student_explanation"],
        dimension=str(record["dimensions"][0]),
        path=path,
        content=content,
        retrieval_extra=" ".join(
            [
                *record["building_types"],
                *record["stages"],
                *record["dimensions"],
                *record["key_terms"],
                *record["related_cases"],
                source_text,
            ]
        ),
        image_urls=[],
    )


def build_case_reference(
    record: dict[str, Any],
    path: Path,
    media_records: list[dict[str, Any]],
    wiki_root: Path,
) -> dict[str, Any]:
    """把结构化案例转换为带授权图片的检索条目。"""
    lessons = "\n".join(f"- {item}" for item in record["transferable_lessons"])
    content = (
        f"# {record['title']}\n\n"
        f"## 基本信息\n\n- 建筑师：{record['architect']}\n- 地点：{record['location']}\n"
        f"- 年份：{record['year']}\n- 规模：{record['scale']}\n- 类型：{record['building_type']}\n\n"
        f"## 场地与空间\n\n{record['site_strategy']}\n\n{record['spatial_sequence']}\n\n"
        f"## 功能与流线\n\n{record['functional_organization']}\n\n{record['circulation']}\n\n"
        f"## 形态、结构与环境\n\n{record['form_strategy']}\n\n"
        f"{record['structure_strategy']}\n\n{record['environmental_response']}\n\n"
        f"## 可借鉴点\n\n{lessons}\n\n"
        f"## 适用边界\n\n{record['application_limits']}"
    )
    images = [media_image_item(item, wiki_root) for item in media_records]
    return base_reference(
        governance_id=record["case_id"],
        title=record["title"],
        source_type="案例",
        excerpt=str(record["transferable_lessons"][0]),
        dimension="案例",
        path=path,
        content=content,
        retrieval_extra=" ".join(
            [
                record["architect"],
                record["location"],
                record["building_type"],
                *record["related_knowledge_cards"],
                *record["similar_cases"],
                *record["depth_evidence_categories"],
            ]
        ),
        image_urls=images,
    )


def base_reference(
    *,
    governance_id: str,
    title: str,
    source_type: str,
    excerpt: str,
    dimension: str,
    path: Path,
    content: str,
    retrieval_extra: str,
    image_urls: list[dict[str, str]],
) -> dict[str, Any]:
    """建立与旧 Markdown 检索结果兼容的统一字段。"""
    return {
        "reference_id": "",
        "governance_id": governance_id,
        "title": title,
        "source_type": source_type,
        "excerpt": excerpt,
        "dimension": dimension,
        "path": str(path),
        "content": content,
        "display_content": content,
        "image_urls": image_urls,
        "retrieval_text": normalize_text(f"{title} {content} {retrieval_extra}"),
    }


def media_image_item(record: dict[str, Any], wiki_root: Path) -> dict[str, str]:
    """把已授权媒体记录转换为前端静态资源地址并保留署名。"""
    relative_path = str(record["relative_path"]).replace("\\", "/")
    path = wiki_root / relative_path
    return {
        "name": path.name,
        "url": f"/wiki-assets/{quote(relative_path)}",
        "attribution": str(record.get("attribution_text", "")),
        "license": str(record.get("license_or_permission", "")),
    }


def is_human_approved(record: dict[str, Any]) -> bool:
    """要求审核通过标记和明确的人工确认同时存在。"""
    return record.get("review_status") == "approved" and record.get("human_review_confirmed") is True


def read_records(path: Path) -> list[dict[str, Any]]:
    """读取固定 records 数组。"""
    data = json.loads(path.read_text(encoding="utf-8"))
    records = data.get("records") if isinstance(data, dict) else None
    if not isinstance(records, list):
        raise ValueError(f"治理文件格式错误：{path}")
    return records


def normalize_text(value: str) -> str:
    """使用与旧 Wiki 相同的无空白小写检索文本。"""
    return re.sub(r"\s+", "", value.lower())
