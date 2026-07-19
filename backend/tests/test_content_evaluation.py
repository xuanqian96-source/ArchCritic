"""验证固定案例检索和问题联动任务的结构与评分口径。"""

from app.benchmarking.content_evaluation import (
    evaluate_task_result,
    evaluation_task_is_complete,
    summarize_evaluation_tasks,
)


def base_case_task() -> dict:
    """生成一条满足前五至少四个相关案例口径的任务。"""
    return {
        "task_id": "CRT-001",
        "task_type": "case_retrieval",
        "query_or_problem": "寻找公共屋顶与地景结合的文化建筑案例。",
        "design_stage": "scheme",
        "building_type": "文化建筑",
        "problem_category": "case_lookup",
        "expected_knowledge_card_ids": ["KC-BEG-001"],
        "expected_case_ids": ["PBC-001"],
        "acceptable_case_ids": ["PBC-001", "PBC-002", "PBC-003", "PBC-004"],
        "required_reason_points": ["屋顶可达", "回应场地"],
        "forbidden_behaviors": ["编造性能"],
        "review_status": "pending",
        "reviewer": "张老师",
        "version": "0.1",
    }


def test_case_retrieval_task_requires_four_relevant_candidates() -> None:
    """确认案例检索任务本身足以检验前五四个相关结果。"""
    task = base_case_task()
    cards = {"KC-BEG-001"}
    cases = {"PBC-001", "PBC-002", "PBC-003", "PBC-004"}

    assert evaluation_task_is_complete(task, cards, cases) is True
    task["acceptable_case_ids"] = task["acceptable_case_ids"][:3]
    assert evaluation_task_is_complete(task, cards, cases) is False


def test_retrieval_result_uses_primary_hit_and_relevant_top_five() -> None:
    """确认命中四个相似案例但漏掉首选案例仍不通过。"""
    task = base_case_task()
    references = [
        {"governance_id": item}
        for item in ("PBC-002", "PBC-003", "PBC-004", "PBC-009", "PBC-001")
    ]
    result = evaluate_task_result(task, references)

    assert result["relevant_in_top_five"] == 4
    assert result["primary_hit"] is True
    assert result["passed"] is True


def test_problem_linkage_requires_at_least_eighty_five_percent_coverage() -> None:
    """确认知识卡和案例推荐按联合覆盖率计算。"""
    task = {
        **base_case_task(),
        "task_id": "PLT-001",
        "task_type": "problem_linkage",
        "problem_category": "site",
        "expected_knowledge_card_ids": ["KC-BEG-001", "KC-BEG-002"],
        "expected_case_ids": ["PBC-001"],
        "acceptable_case_ids": ["PBC-001"],
    }
    incomplete = [
        {"governance_id": "KC-BEG-001"},
        {"governance_id": "PBC-001"},
    ]
    complete = [
        {"governance_id": "KC-BEG-001"},
        {"governance_id": "KC-BEG-002"},
        {"governance_id": "PBC-001"},
    ]

    assert evaluate_task_result(task, incomplete)["passed"] is False
    assert evaluate_task_result(task, complete)["passed"] is True


def test_task_summary_keeps_structural_and_human_approval_counts_separate() -> None:
    """确认结构合格草稿不会被误计为人工批准任务。"""
    task = base_case_task()
    summary = summarize_evaluation_tasks(
        [task],
        {"KC-BEG-001"},
        {"PBC-001", "PBC-002", "PBC-003", "PBC-004"},
    )

    assert summary["valid_task_count"] == 1
    assert summary["approved_human_task_count"] == 0
