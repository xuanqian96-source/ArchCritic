"""验证知识测试题目抽取、多题型构造、答案保护和逐题判定。"""

from app.services.knowledge_quiz import (
    QUESTION_TYPE_ORDER,
    _build_structured_questions,
    _evaluate_question,
    _public_question,
)
from app.services.knowledge_taxonomy import build_quiz_item


def make_base_question(index: int) -> dict:
    """创建一条带明确答案要点的测试题。"""
    return {
        "id": f"Q-KC-BEG-{index:03d}",
        "card_id": f"KC-BEG-{index:03d}",
        "card_title": f"测试知识卡 {index}",
        "category": "空间",
        "difficulty": "beginner",
        "difficulty_label": "入门",
        "prompt": f"测试问题 {index}？",
        "reference_points": [f"答案要点 {index}-1", f"答案要点 {index}-2"],
    }


def test_quiz_item_requires_explicit_answer_and_reads_answer_points():
    """确认无答案题不会发布，有答案题优先读取明确答案要点。"""
    item = {
        "id": "KC-BEG-001",
        "title": "测试卡片",
        "category": "空间",
        "level": "beginner",
        "level_label": "入门",
        "excerpt": "不能替代答案的摘要。",
    }
    without_answer = "## 观察或自测任务\n\n- 如何判断空间关系？"
    assert build_quiz_item(item, without_answer) is None

    with_answer = without_answer + "\n\n## 答案要点\n\n- 入口清晰\n- 流线连续"
    question = build_quiz_item(item, with_answer)
    assert question is not None
    assert question["prompt"] == "如何判断空间关系？"
    assert question["reference_points"] == ["入口清晰", "流线连续"]


def test_structured_quiz_covers_five_types_and_protects_answers():
    """确认五种题型均可生成，公开题目不会提前泄露答案。"""
    base_questions = [make_base_question(index) for index in range(1, 6)]
    item_by_id = {
        question["card_id"]: {"related_ids": ["PBC-001"]}
        for question in base_questions
    }
    item_by_id["PBC-001"] = {
        "kind": "case",
        "title": "测试案例",
        "thumbnail": "/api/knowledge/thumbnail/test.jpg",
    }
    questions = _build_structured_questions(base_questions, item_by_id)
    assert tuple(question["question_type"] for question in questions) == QUESTION_TYPE_ORDER
    assert questions[0]["prompt"] == "关于“测试知识卡 1”，以下哪项最符合知识卡强调的设计要点？"
    assert [option["id"] for option in questions[2]["options"]] == ["A", "B"]
    assert questions[2]["prompt"].startswith("判断下列说法是否符合“测试知识卡 3”的设计原则")
    assert questions[3]["image_url"] == "/api/knowledge/thumbnail/test.jpg"
    public = _public_question(questions[0])
    assert "answer_points" not in public
    assert "correct_option_ids" not in public
    assert "explanation" not in public


def test_objective_and_short_answers_return_explainable_results():
    """确认客观题确定判分，简答题能返回命中和遗漏要点。"""
    base_questions = [make_base_question(index) for index in range(1, 6)]
    questions = _build_structured_questions(base_questions, {})
    single = questions[0]
    correct_option = single["correct_option_ids"][0]
    correct_result = _evaluate_question(single, correct_option)
    assert correct_result["is_correct"] is True
    assert correct_result["score"] == 1.0
    assert correct_result["correct_answers"]

    short = questions[4]
    short["answer_points"] = ["入口路径连续清晰", "设备接口与荷载明确"]
    short_result = _evaluate_question(short, "入口路径清晰，并补充其他说明。")
    assert short_result["is_correct"] is True
    assert short_result["matched_points"] == ["入口路径连续清晰"]
    assert short_result["missed_points"] == ["设备接口与荷载明确"]
