"""构造知识测试题型并执行逐题确定性判定，不影响知识库浏览与评图。"""

from __future__ import annotations

from collections import defaultdict
import hashlib
import math
import re
from time import monotonic
from typing import Any

from app.services.knowledge_library import _get_cached_library_items, build_knowledge_quiz


QUESTION_TYPE_ORDER = ("single_choice", "multiple_choice", "true_false", "image_choice", "short_answer")
QUESTION_TYPE_LABELS = {
    "single_choice": "单选题",
    "multiple_choice": "多选题",
    "true_false": "判断题",
    "image_choice": "识图题",
    "short_answer": "简答题",
}
GENERAL_DISTRACTORS = (
    "只关注外观效果，不核对真实使用条件与空间证据",
    "直接照搬案例形式，不分析当前场地与任务差异",
    "只在说明文字中表达意图，不落实到图纸和设计动作",
    "等方案完成后再补充判断依据，前期无需建立检查标准",
)
SHORT_PROMPT_REWRITES = {
    "KC-BEG-021": "自然光从开口进入地下空间时，应如何组织光线路径，并帮助使用者判断位置与方向？",
    "KC-BEG-026": "选择剖切线时，最有信息量的剖面应同时回答哪些设计问题？",
    "KC-ADV-025": "阅读现代公共建筑的剖面或立面时，应如何区分主要受力构件、非结构构件，以及兼具空间表达作用的受力构件？",
    "KC-ADV-030": "地下空间中的光井或天窗应如何同时支持自然照明与寻路？",
    "KC-ADV-035": "主入口的到达序列通常应如何分阶段组织，并形成怎样的空间节奏？",
    "KC-ADV-040": "控制中庭与开放阅览空间的声音传播时，应识别哪些传播路径，并采用哪些措施？",
    "KC-MAS-025": "用二十四小时运营视角检验文化建筑的公共性时，应关注哪些空间身份变化？",
}
QUIZ_CACHE_TTL_SECONDS = 300.0
_quiz_bank_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}


def build_knowledge_quiz_bank(wiki_dir: str) -> dict[str, Any]:
    """返回不包含正确答案的多题型测试题库。"""
    questions = _get_structured_quiz_bank(wiki_dir)
    counts = defaultdict(int)
    for question in questions:
        counts[question["difficulty"]] += 1
    difficulties = [
        {"value": value, "label": label, "count": counts[value]}
        for value, label in (("beginner", "入门"), ("advanced", "进阶"), ("master", "研习"))
        if counts[value]
    ]
    return {
        "questions": [_public_question(question) for question in questions],
        "difficulties": difficulties,
    }


def evaluate_quiz_answer(wiki_dir: str, question_id: str, answer: str | list[str]) -> dict[str, Any] | None:
    """按题号读取受保护答案并返回本题判定与解析。"""
    bank = _get_structured_quiz_bank(wiki_dir)
    question = next((item for item in bank if item["id"] == question_id), None)
    if question is None:
        return None
    return _evaluate_question(question, answer)


def _get_structured_quiz_bank(wiki_dir: str) -> list[dict[str, Any]]:
    """短时缓存完整题库，使逐题提交不必反复读取 100 份知识卡。"""
    now = monotonic()
    cached = _quiz_bank_cache.get(wiki_dir)
    if cached and now - cached[0] < QUIZ_CACHE_TTL_SECONDS:
        return cached[1]
    base_questions = build_knowledge_quiz(wiki_dir)["questions"]
    items = _get_cached_library_items(wiki_dir)
    questions = _build_structured_questions(
        base_questions,
        {item["id"]: item for item in items},
    )
    _quiz_bank_cache[wiki_dir] = (now, questions)
    return questions


def _evaluate_question(question: dict[str, Any], answer: str | list[str]) -> dict[str, Any]:
    """判定已经构造好的题目，供接口和专项测试复用。"""
    if question["question_type"] == "short_answer":
        result = _evaluate_short_answer(str(answer), question["answer_points"])
    else:
        selected = {str(value) for value in (answer if isinstance(answer, list) else [answer]) if str(value)}
        expected = set(question["correct_option_ids"])
        result = {
            "is_correct": selected == expected,
            "score": 1.0 if selected == expected else 0.0,
            "matched_points": [],
            "missed_points": [],
            "status_label": "回答正确" if selected == expected else "需要复习",
        }
    correct_answers = [
        option["label"] for option in question["options"]
        if option["id"] in question["correct_option_ids"]
    ] if question["options"] else question["answer_points"]
    return {
        "question_id": question["id"],
        **result,
        "correct_answers": correct_answers,
        "answer_points": question["answer_points"],
        "explanation": question["explanation"],
    }


def _build_structured_questions(base_questions: list[dict[str, Any]], item_by_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """按每个难度均匀安排五种题型，并为客观题构造稳定选项。"""
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for question in base_questions:
        grouped[question["difficulty"]].append(question)
    result: list[dict[str, Any]] = []
    for difficulty in ("beginner", "advanced", "master"):
        questions = grouped[difficulty]
        for index, base in enumerate(questions):
            question_type = QUESTION_TYPE_ORDER[index % len(QUESTION_TYPE_ORDER)]
            result.append(_build_question(base, question_type, index, questions, item_by_id))
    return result


def _build_question(
    base: dict[str, Any],
    question_type: str,
    index: int,
    peers: list[dict[str, Any]],
    item_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """把一道带答案要点的自测题转换成指定交互题型。"""
    answer_points = _expand_answer_points(base["reference_points"])
    if question_type == "multiple_choice" and len(answer_points) < 2:
        question_type = "single_choice"
    distractors = _collect_distractors(base["id"], answer_points, peers)
    title = base["card_title"]
    prompt = SHORT_PROMPT_REWRITES.get(base["card_id"], base["prompt"])
    options: list[dict[str, str]] = []
    correct_labels: list[str] = []
    image_url = ""
    image_alt = ""
    if question_type == "single_choice":
        prompt = f"关于“{title}”，以下哪项最符合知识卡强调的设计要点？"
        correct_labels = answer_points[:1]
        options = _make_options(base["id"], correct_labels + distractors[:3])
    elif question_type == "multiple_choice":
        prompt = f"关于“{title}”，以下哪些属于知识卡明确强调的设计要点？（多选）"
        correct_labels = answer_points[: min(3, len(answer_points))]
        options = _make_options(base["id"], correct_labels + distractors[: max(1, 5 - len(correct_labels))])
    elif question_type == "true_false":
        use_correct_statement = index % 2 == 0
        if use_correct_statement:
            statement = f"“{answer_points[0]}”是该知识卡要求核对的设计要点之一。"
        else:
            statement = f"“{distractors[0]}”符合该知识卡的设计原则。"
        prompt = f"判断下列说法是否符合“{title}”的设计原则：\n{statement}"
        options = [{"id": "A", "label": "正确"}, {"id": "B", "label": "错误"}]
        correct_labels = ["正确" if use_correct_statement else "错误"]
    elif question_type == "image_choice":
        related_case = _first_related_case(item_by_id.get(base["card_id"], {}), item_by_id)
        image_url = str(related_case.get("thumbnail", ""))
        image_alt = f"关联案例：{related_case.get('title', '建筑案例')}"
        prompt = f"观察下方与“{title}”关联的案例图片。以下哪项最值得结合图片重点检查？"
        correct_labels = answer_points[:1]
        options = _make_options(base["id"], correct_labels + distractors[:3])
    correct_option_ids = [option["id"] for option in options if option["label"] in correct_labels]
    return {
        **base,
        "question_type": question_type,
        "question_type_label": QUESTION_TYPE_LABELS[question_type],
        "prompt": prompt,
        "options": options,
        "correct_option_ids": correct_option_ids,
        "answer_points": answer_points,
        "image_url": image_url,
        "image_alt": image_alt,
        "explanation": f"答案依据来自 {base['card_id']}《{base['card_title']}》中已经整理的答案要点。",
    }


def _expand_answer_points(points: list[str]) -> list[str]:
    """把一条挤在一起的复合答案拆成可独立判断的清晰要点。"""
    expanded: list[str] = []
    for point in points:
        for clause in re.split(r"[；;。]", point):
            normalized = clause.strip(" \t\n，,：:")
            if len(normalized) >= 2 and normalized not in expanded:
                expanded.append(normalized)
    return expanded


def _collect_distractors(question_id: str, answers: list[str], peers: list[dict[str, Any]]) -> list[str]:
    """生成语义明确的错误做法，避免用其他知识卡的正确结论造成歧义。"""
    del peers
    offset = int(hashlib.sha256(question_id.encode()).hexdigest(), 16) % len(GENERAL_DISTRACTORS)
    ordered = GENERAL_DISTRACTORS[offset:] + GENERAL_DISTRACTORS[:offset]
    return [value for value in ordered if value not in answers]


def _make_options(question_id: str, labels: list[str]) -> list[dict[str, str]]:
    """使用题号生成稳定选项顺序，避免答案总出现在同一位置。"""
    unique_labels = list(dict.fromkeys(label for label in labels if label))
    ordered = sorted(unique_labels, key=lambda label: hashlib.sha256(f"{question_id}:{label}".encode()).hexdigest())
    return [{"id": chr(65 + index), "label": label} for index, label in enumerate(ordered[:5])]


def _first_related_case(card: dict[str, Any], item_by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """选择知识卡关联的第一张可显示案例图片。"""
    for related_id in card.get("related_ids", []):
        related = item_by_id.get(related_id, {})
        if related.get("kind") == "case" and related.get("thumbnail"):
            return related
    return {}


def _public_question(question: dict[str, Any]) -> dict[str, Any]:
    """移除正确答案和答案要点，防止用户作答前从接口直接读取。"""
    hidden = {"correct_option_ids", "answer_points", "reference_points", "explanation"}
    return {key: value for key, value in question.items() if key not in hidden}


def _evaluate_short_answer(answer: str, points: list[str]) -> dict[str, Any]:
    """按答案要点中的稳定中文片段给出可解释的参考匹配结果。"""
    normalized_answer = _normalize_text(answer)
    matched = [point for point in points if _point_matches(normalized_answer, point)]
    missed = [point for point in points if point not in matched]
    score = len(matched) / len(points) if points else 0.0
    threshold = max(1, math.ceil(len(points) / 2))
    return {
        "is_correct": len(matched) >= threshold,
        "score": round(score, 3),
        "matched_points": matched,
        "missed_points": missed,
        "status_label": f"已覆盖 {len(matched)}/{len(points)} 个要点",
    }


def _point_matches(normalized_answer: str, point: str) -> bool:
    """使用完整短句或关键双字片段判断简答题是否覆盖一个要点。"""
    normalized_point = _normalize_text(point)
    if not normalized_point:
        return False
    if normalized_point in normalized_answer:
        return True
    chunks = {
        normalized_point[index:index + 2]
        for index in range(max(0, len(normalized_point) - 1))
        if normalized_point[index:index + 2] not in {"可以", "需要", "通过", "进行", "空间", "设计", "建筑"}
    }
    if not chunks:
        return False
    hits = sum(chunk in normalized_answer for chunk in chunks)
    return hits >= max(1, math.ceil(len(chunks) * 0.35))


def _normalize_text(value: str) -> str:
    """移除标点与空白，统一简答题匹配口径。"""
    return re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]", "", value).lower()
