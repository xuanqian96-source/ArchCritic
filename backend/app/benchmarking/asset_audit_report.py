"""把长程 Goal 资产盘点转换为不泄漏答案的报告文件。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def render_markdown_report(audit: dict[str, Any]) -> str:
    """生成不暴露教师分和标注答案的中文盘点报告。"""
    dataset = audit["dataset"]
    knowledge = audit["knowledge_base"]
    gates = audit["gates"]
    core_source_gap = max(0, 3 - knowledge["core_source_record_count"])
    source_task = (
        f"补齐 {core_source_gap} 组核心资料来源与许可记录"
        if core_source_gap
        else "完成 60 张知识卡草稿和 30 道固定问答草稿的学科复核、修订与正式入库"
    )
    lines = [
        "# ArchCritic 长程 Goal 阶段 0—2 资产盘点",
        "",
        f"生成时间：{audit['generated_at']}",
        "",
        "> 本报告不包含教师具体分数和人工标注答案，可供开发侧查看。",
        "",
        "## 结论",
        "",
        f"- 资产门槛通过 {gates['passed']} 项，未通过 {gates['failed']} 项。",
        "- 当前不具备正式最终盲测和知识/案例专项验收条件。",
        "- 现有六份样本只用于开发回归，不计入新的最终盲测。",
        "",
        "## 基准数据",
        "",
        "| 项目 | 现状 | 验收线 |",
        "| --- | ---: | ---: |",
        f"| 匿名输入样本 | {dataset['prepared_input_count']} | ≥20 |",
        f"| 高分档 | {dataset['band_counts']['high']} | ≥6 |",
        f"| 中档 | {dataset['band_counts']['mid']} | ≥6 |",
        f"| 低分档 | {dataset['band_counts']['low']} | ≥6 |",
        f"| 双人复核可验证 | {dataset['double_reviewed_case_count']} | ≥10 |",
        f"| 授权可验证 | {dataset['authorization_verified_case_count']} | ≥20 |",
        f"| 匿名输入违规 | {dataset['model_input_violation_count']} | 0 |",
        f"| 原始目录名带分数 | {dataset['raw_names_with_score_count']} | 0 |",
        "",
        f"答案隔离状态：`{dataset['answer_isolation']}`。",
        "",
        "## 知识与案例",
        "",
        "| 项目 | 候选数 | 可计入验收 | 验收线 |",
        "| --- | ---: | ---: | ---: |",
        f"| 核心资料 | - | {knowledge['core_source_record_count']} | 3 |",
        f"| 知识卡 | {knowledge['knowledge_card_candidate_count']} | {knowledge['eligible_knowledge_card_count']} | 60 |",
        f"| 待学科复核的结构化知识卡草稿 | {knowledge['knowledge_card_structured_draft_count']} | {knowledge['knowledge_card_valid_draft_count']} 份结构合格草稿 | 不计入 60 张正式卡 |",
        f"| 公共建筑案例 | {knowledge['case_candidate_count']} | {knowledge['eligible_case_count']} | 20 |",
        f"| 已有官方事实来源的案例草稿 | {knowledge['case_candidate_count']} | {knowledge['case_candidate_with_approved_source_count']} | 20 |",
        f"| 待学科复核的结构化案例草稿 | {knowledge['case_structured_draft_count']} | {knowledge['case_valid_draft_count']} 份结构合格草稿 | 不计入 20 个正式案例 |",
        f"| 其中具备三类以上证据的案例草稿 | - | {knowledge['case_deep_ready_draft_count']} | 学科复核通过后才可计入深度案例 |",
        f"| 深度案例 | - | {knowledge['deep_case_count']} | 10 |",
        f"| 固定问答 | - | {knowledge['fixed_question_count']} | 30 |",
        f"| 待学科复核的固定问答草稿 | {knowledge['structured_question_draft_count']} | {knowledge['valid_question_draft_count']} 份结构合格草稿 | 不计入 30 道正式题 |",
        f"| 诱导/无答案问题 | - | {knowledge['adversarial_or_unanswerable_question_count']} | 10 |",
        f"| 媒体文件权限记录 | {knowledge['media_file_count']} | {knowledge['media_with_permission_record_count']} | 100% |",
        "",
        "## 确认缺口",
        "",
        "1. 需新增至少 14 份与现有样本独立的授权样本，并优先补齐中档。",
        "2. 需将最终测试答案与模型输入从目录、进程和权限三个层面分开。",
        "3. 需为每份样本补齐授权、匿名化、评分理由、时间、评分者类型和复核记录。",
        "4. 现有案例已开始形成逐条证据草稿，仍需补齐至 20 个、完成学科复核，并逐文件解决图片许可。",
        f"5. 需{source_task}。",
        "",
        "## 下一个已授权执行点",
        "",
        "组织知识卡、固定问答和案例草稿的学科复核，同时用新的盲跑—冻结—裁判流程导入授权新样本。",
        "",
    ]
    return "\n".join(lines)


def write_audit_files(output_root: Path, audit: dict[str, Any]) -> tuple[Path, Path]:
    """写入机器可读 JSON 和人类可读 Markdown 盘点。"""
    output_root.mkdir(parents=True, exist_ok=True)
    json_path = output_root / "阶段0-2资产盘点.json"
    markdown_path = output_root / "阶段0-2资产盘点.md"
    json_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(render_markdown_report(audit), encoding="utf-8")
    return json_path, markdown_path
