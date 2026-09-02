"""解析用户上传的任务书，并生成可供 Agent 与总分共同使用的评分配置。"""

from __future__ import annotations

import re
import subprocess
import zipfile
from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree

from app.models import Attachment, Submission
from app.services.taskbook_rules import build_structured_requirements


MAX_TASK_BOOK_CHARS = 16_000
DIMENSION_LABELS = {
    "function_agent": "功能与流线",
    "site_agent": "场地与回应",
    "form_agent": "几何形式",
    "structure_agent": "结构与构造",
    "concept_agent": "设计概念",
    "drawing_agent": "图面表达",
}
DIMENSION_KEYWORDS = {
    "function_agent": ("功能", "面积", "房间", "流线", "分区", "使用", "交通空间"),
    "site_agent": ("场地", "基地", "总图", "环境", "道路", "入口", "景观", "城市"),
    "form_agent": ("形体", "形式", "体量", "构图", "立面", "几何", "空间序列"),
    "structure_agent": ("结构", "柱网", "跨度", "构造", "梁", "承重", "材料体系"),
    "concept_agent": ("概念", "创意", "立意", "主题", "叙事", "构思", "空间体验"),
    "drawing_agent": ("图面", "制图", "表达", "排版", "标注", "线型", "图纸完整"),
}
SUBSTANTIVE_STRUCTURE_KEYWORDS = (
    "柱网", "跨度", "构造图", "节点", "梁柱", "承重", "支撑体系",
    "结构计算", "结构分析", "结构设计", "结构逻辑",
)
STAGE_BASE_WEIGHTS = {
    "概念阶段": {
        "site_agent": 25.0,
        "form_agent": 25.0,
        "concept_agent": 50.0,
    },
    "方案阶段": {
        "function_agent": 30.0,
        "site_agent": 20.0,
        "form_agent": 25.0,
        "structure_agent": 25.0,
    },
    "图纸阶段": {
        "drawing_agent": 30.0,
        "function_agent": 25.0,
        "site_agent": 15.0,
        "form_agent": 15.0,
        "structure_agent": 15.0,
    },
}


class TaskBookExtractionError(ValueError):
    """表示任务书无法可靠抽取文字。"""


def refresh_attachment_extraction(attachment: Attachment, upload_dir: str) -> bool:
    """为升级前已上传的任务书补做文字抽取，返回记录是否改变。"""
    if attachment.extraction_status == "ready" and (attachment.extracted_text or "").strip():
        return False
    if not attachment.file_url.startswith("/uploads/"):
        attachment.extraction_status = "failed"
        return True
    upload_root = Path(upload_dir).resolve()
    file_path = (upload_root / attachment.file_url.removeprefix("/uploads/")).resolve()
    if upload_root not in file_path.parents or not file_path.is_file():
        attachment.extraction_status = "failed"
        return True
    try:
        attachment.extracted_text = extract_task_book_text(file_path.read_bytes(), file_path.suffix)
        attachment.extraction_status = "ready"
    except (OSError, TaskBookExtractionError):
        attachment.extracted_text = ""
        attachment.extraction_status = "failed"
    return True


def extract_task_book_text(content: bytes, extension: str) -> str:
    """按文件类型抽取任务书文字，无法确认内容时明确失败。"""
    normalized_extension = extension.lower()
    if normalized_extension == ".txt":
        text = decode_text(content)
    elif normalized_extension == ".docx":
        text = extract_docx_text(content)
    elif normalized_extension == ".pdf":
        text = extract_pdf_text(content)
    elif normalized_extension == ".doc":
        raise TaskBookExtractionError(
            "当前环境不能可靠读取旧版 DOC，请另存为 DOCX、PDF 或 TXT 后重新上传。"
        )
    else:
        raise TaskBookExtractionError("当前任务书格式不支持文字解析。")
    cleaned = clean_extracted_text(text)
    if len(cleaned) < 20:
        raise TaskBookExtractionError(
            "任务书没有提取到足够文字；如果是扫描版 PDF，请先进行文字识别或上传可复制文字的版本。"
        )
    return cleaned[:MAX_TASK_BOOK_CHARS]


def decode_text(content: bytes) -> str:
    """兼容常见中文文本编码。"""
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise TaskBookExtractionError("TXT 文件编码无法识别，请保存为 UTF-8 后重新上传。")


def extract_docx_text(content: bytes) -> str:
    """从 DOCX 的 XML 正文中读取段落文本。"""
    try:
        with zipfile.ZipFile(BytesIO(content)) as archive:
            document = archive.read("word/document.xml")
        root = ElementTree.fromstring(document)
    except (KeyError, zipfile.BadZipFile, ElementTree.ParseError) as exc:
        raise TaskBookExtractionError("DOCX 文件结构损坏，无法读取正文。") from exc
    namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    paragraphs = []
    for paragraph in root.iter(f"{namespace}p"):
        text = "".join(node.text or "" for node in paragraph.iter(f"{namespace}t"))
        if text.strip():
            paragraphs.append(text.strip())
    return "\n".join(paragraphs)


def extract_pdf_text(content: bytes) -> str:
    """调用本机 pdftotext 读取带文字层的 PDF。"""
    try:
        completed = subprocess.run(
            ["pdftotext", "-layout", "-", "-"],
            input=content,
            capture_output=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise TaskBookExtractionError("服务器暂时无法读取 PDF 任务书。") from exc
    if completed.returncode != 0:
        raise TaskBookExtractionError("PDF 任务书文字解析失败，请检查文件是否损坏。")
    return completed.stdout.decode("utf-8", errors="ignore")


def clean_extracted_text(text: str) -> str:
    """清理重复空白，同时保留任务条目之间的换行。"""
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def build_task_book_profile(submission: Submission, attachments: list[Attachment]) -> dict:
    """把任务书正文整理为摘要、要求和动态 Agent 权重。"""
    text_parts = [
        f"【{item.original_name}】\n{item.extracted_text.strip()}"
        for item in attachments
        if item.extraction_status == "ready" and item.extracted_text.strip()
    ]
    full_text = "\n\n".join(text_parts)[:MAX_TASK_BOOK_CHARS]
    requirements = extract_requirement_lines(full_text)
    structured_requirements = build_structured_requirements(requirements)
    design_stage = getattr(submission, "design_stage", "方案阶段")
    enabled_agents = getattr(submission, "enabled_agents", [])
    project = submission.project
    active_agents = normalize_active_agents(design_stage, enabled_agents)
    weights = calculate_dimension_weights(
        design_stage,
        getattr(project, "grade", "") or "",
        full_text,
        active_agents,
    )
    return {
        "has_task_book": bool(full_text),
        "source_files": [item.original_name for item in attachments if item.extraction_status == "ready"],
        "full_text": full_text,
        "summary": build_task_book_summary(full_text, getattr(project, "building_type", "")),
        "requirements": requirements,
        "structured_requirements": structured_requirements,
        "dimension_weights": weights,
        "weight_reasons": build_weight_reasons(
            getattr(project, "grade", "") or "", full_text, active_agents, weights
        ),
    }


def normalize_active_agents(design_stage: str, enabled_agents: list[str] | None) -> list[str]:
    """只保留会参与专项评分的 Agent。"""
    base = STAGE_BASE_WEIGHTS.get(resolve_stage(design_stage), STAGE_BASE_WEIGHTS["方案阶段"])
    enabled = enabled_agents or list(base)
    return [agent for agent in enabled if agent in base]


def resolve_stage(design_stage: str) -> str:
    """统一三种设计阶段名称。"""
    for stage in STAGE_BASE_WEIGHTS:
        if stage in str(design_stage):
            return stage
    return "方案阶段"


def extract_requirement_lines(text: str) -> list[str]:
    """提取包含任务、成果、要求和评分重点的代表性条目。"""
    if not text:
        return []
    candidates = []
    requirement_pattern = re.compile(
        r"规模|面积|高度|基地|结构|设备|设施|功能|展览|服务|公共区|附加空间|"
        r"总平面|平面图|立面图|剖面图|构造图|透视图|模型|成果|图面|比例|"
        r"要求|应当|需要|须|不得|不应|不少于|至少|必须|评分|设计内容"
    )
    for line in text.splitlines():
        cleaned = line.strip(" -•\t")
        if not 6 <= len(cleaned) <= 220:
            continue
        if requirement_pattern.search(cleaned):
            candidates.append(cleaned)
    if not candidates:
        candidates = [line.strip() for line in text.splitlines() if 12 <= len(line.strip()) <= 160]
    return list(dict.fromkeys(candidates))[:20]


def build_task_book_summary(text: str, building_type: str) -> str:
    """生成可直接进入提示词的短摘要。"""
    if not text:
        return f"未读取到任务书正文，只能按{building_type or '当前建筑类型'}和设计说明进行低置信度评价。"
    requirements = extract_requirement_lines(text)
    if requirements:
        return "；".join(requirements[:6])[:1200]
    return text[:1200]


def calculate_dimension_weights(
    design_stage: str,
    grade: str,
    text: str,
    active_agents: list[str],
) -> dict[str, float]:
    """根据阶段、年级与任务书关注点计算最终总分占比。"""
    stage = resolve_stage(design_stage)
    base = STAGE_BASE_WEIGHTS[stage]
    weights = {agent: base[agent] for agent in active_agents if agent in base}
    if not weights:
        weights = dict(base)
    normalized_text = text.lower()
    for agent in list(weights):
        hits = sum(normalized_text.count(keyword.lower()) for keyword in DIMENSION_KEYWORDS[agent])
        weights[agent] *= 1 + min(hits, 8) * 0.06
    deemphasized_agents = get_deemphasized_agents(normalized_text, list(weights))
    for agent in deemphasized_agents:
        weights[agent] *= 0.2
    early_grade = any(label in grade for label in ("大一", "大二", "一年级", "二年级"))
    structure_required = has_substantive_structure_requirement(normalized_text)
    if early_grade and "structure_agent" in weights and "structure_agent" not in deemphasized_agents and not structure_required:
        weights["structure_agent"] *= 0.35
    if early_grade and "concept_agent" in weights:
        weights["concept_agent"] *= 1.2
    total = sum(weights.values()) or 1
    rounded = {agent: round(value / total * 100, 1) for agent, value in weights.items()}
    difference = round(100 - sum(rounded.values()), 1)
    if rounded and difference:
        largest = max(rounded, key=rounded.get)
        rounded[largest] = round(rounded[largest] + difference, 1)
    return rounded


def build_weight_reasons(
    grade: str,
    text: str,
    active_agents: list[str],
    weights: dict[str, float],
) -> list[str]:
    """说明任务书为何改变评分占比，供报告追溯。"""
    reasons = []
    early_grade = any(label in grade for label in ("大一", "大二", "一年级", "二年级"))
    structure_required = has_substantive_structure_requirement(text)
    deemphasized_agents = get_deemphasized_agents(text, active_agents)
    for agent in deemphasized_agents:
        reasons.append(
            f"任务书明确弱化或不考查{DIMENSION_LABELS[agent]}，因此显著降低{DIMENSION_LABELS[agent]}专项占比。"
        )
    if early_grade and "structure_agent" in active_agents and "structure_agent" not in deemphasized_agents and not structure_required:
        reasons.append("当前为低年级任务，任务书未突出结构要求，因此降低结构专项占比。")
    for agent in active_agents:
        if agent in deemphasized_agents:
            continue
        hits = [keyword for keyword in DIMENSION_KEYWORDS[agent] if keyword in text]
        if hits:
            reasons.append(
                f"任务书多次涉及{'、'.join(hits[:3])}，{DIMENSION_LABELS[agent]}占比调整为 {weights.get(agent, 0):g}%。"
            )
    return reasons[:6]


def has_substantive_structure_requirement(text: str) -> bool:
    """判断任务书是否真正要求结构设计深度，而非仅列出可选结构材料。"""
    normalized = str(text or "").lower()
    return any(keyword.lower() in normalized for keyword in SUBSTANTIVE_STRUCTURE_KEYWORDS)


def has_deemphasized_requirement(text: str, dimension_keyword: str) -> bool:
    """识别“结构不作要求”等明确弱化表述，避免只按关键词误加权。"""
    patterns = (
        rf"{dimension_keyword}.{{0,12}}(?:不作要求|不做要求|不要求|要求不高|不考[察核]|不计分|无需|暂不涉及)",
        rf"(?:不作要求|不做要求|不要求|不考[察核]|不计分|无需).{{0,12}}{dimension_keyword}",
    )
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def get_deemphasized_agents(text: str, active_agents: list[str]) -> list[str]:
    """返回任务书中被明确写为不要求或不计分的专项。"""
    return [
        agent
        for agent in active_agents
        if any(
            has_deemphasized_requirement(text, keyword)
            for keyword in DIMENSION_KEYWORDS.get(agent, ())
        )
    ]


def build_task_book_snapshot(profile: dict) -> dict:
    """生成适合随历史报告保存的任务书评分快照。"""
    return {
        "has_task_book": profile.get("has_task_book", False),
        "source_files": profile.get("source_files", []),
        "summary": profile.get("summary", ""),
        "requirements": profile.get("requirements", []),
        "structured_requirements": profile.get("structured_requirements", []),
        "dimension_weights": profile.get("dimension_weights", {}),
        "weight_reasons": profile.get("weight_reasons", []),
    }


def calculate_weighted_score(evaluations: list[dict], weights: dict[str, float]) -> float:
    """按任务书权重合成总分，未参与评分的综合 Agent 不重复计分。"""
    scored = [item for item in evaluations if item.get("agent_type") in weights]
    if not scored:
        scored = [item for item in evaluations if item.get("agent_type") != "review_agent"]
        if not scored:
            return 0.0
        return round(sum(float(item.get("score", 0)) for item in scored) / len(scored), 1)
    used_weight = sum(weights[item["agent_type"]] for item in scored) or 1
    return round(
        sum(float(item.get("score", 0)) * weights[item["agent_type"]] for item in scored)
        / used_weight,
        1,
    )
