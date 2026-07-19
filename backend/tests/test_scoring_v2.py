"""验证证据优先评分、任务书规则和教师校准层的关键边界。"""

from __future__ import annotations

import json
from types import SimpleNamespace

from app.agents.scheme_review import generate_scheme_review
from app.agents.prompts.evidence_agents_v2 import FUNCTION_EVIDENCE_SPEC
from app.benchmarking.calibration import fit_calibration_artifact
from app.scoring.calibration import fit_calibrator, predict_calibrated_score
from app.scoring.evidence import normalize_evidence_output
from app.scoring.overall import build_evidence_score
from app.services.taskbook_rules import build_structured_requirements


def test_taskbook_rules_distinguish_optional_and_required_items() -> None:
    """确认选配货梯不会与强制结构和图纸要求混为一谈。"""
    rules = build_structured_requirements(
        [
            "可选配一部货运电梯。",
            "结构形式应采用框架结构。",
            "各层平面图比例为1:100。",
        ]
    )

    assert rules[0]["level"] == "optional"
    assert "function_agent" in rules[0]["agent_types"]
    assert rules[1]["level"] == "required"
    assert rules[1]["dimension"] == "structure_agent"
    assert rules[2]["verification_mode"] == "quantitative"


def test_evidence_levels_are_mapped_by_backend_not_model_scores() -> None:
    """确认模型只返回等级，后端按固定表生成兼容专项分。"""
    requirements = build_structured_requirements(["可选配一部货运电梯。"])
    report = normalize_evidence_output(
        FUNCTION_EVIDENCE_SPEC,
        build_evidence_payload(requirements[0]["id"]),
        requirements,
    )

    assert report["overall_score"] == 78
    assert report["sub_scores"]["功能满足"]["score"] == 23.4
    assert report["criterion_assessments"]["功能满足"]["level"] == 3
    assert report["must_fix"] == []
    assert report["requirement_checks"][0]["level"] == "optional"


def test_evidence_layer_accepts_named_assessment_list_from_json_mode() -> None:
    """确认百炼 JSON-object 模式偶发返回数组时仍能按名称安全转换。"""
    payload = build_evidence_payload("R-001")
    payload["criterion_assessments"] = [
        {"criterion": name, **item}
        for name, item in payload["criterion_assessments"].items()
    ]
    report = normalize_evidence_output(
        FUNCTION_EVIDENCE_SPEC,
        payload,
        build_structured_requirements(["可选配一部货运电梯。"]),
    )

    assert report["overall_score"] == 78


def test_optional_and_uncertain_requirements_do_not_reduce_total() -> None:
    """确认选配项与不确定项不会进入任务书符合度扣分。"""
    rules = build_structured_requirements(
        ["可选配一部货运电梯。", "建筑高度不应高于13米。"]
    )
    evaluations = [
        build_evaluation(
            80,
            [
                requirement_check(rules[0], "not_met", "high"),
                requirement_check(rules[1], "uncertain", "medium"),
            ],
        )
    ]
    scoring = build_evidence_score(
        evaluations, {"function_agent": 100}, rules, calibrator=None
    )

    assert scoring["compliance_score"] is None
    assert scoring["raw_score"] == 80
    assert scoring["calibrated_score"] == 80


def test_monotonic_calibrator_keeps_scores_ordered() -> None:
    """确认小样本教师校准不会造成原始分越高、最终分反而越低。"""
    records = [
        {"case_id": "A", "raw_score": 60, "teacher_score": 61},
        {"case_id": "B", "raw_score": 70, "teacher_score": 67},
        {"case_id": "C", "raw_score": 80, "teacher_score": 94},
        {"case_id": "D", "raw_score": 85, "teacher_score": 93},
    ]
    calibrator = fit_calibrator(records, ["A", "B", "C", "D"])
    predictions = [predict_calibrated_score(score, calibrator) for score in range(55, 91, 5)]

    assert predictions == sorted(predictions)
    assert calibrator["sample_count"] == 4


def test_calibration_artifact_does_not_read_heldout_score_for_fit(tmp_path) -> None:
    """确认校准产物只保存四份训练点，盲测样本仅以编号出现。"""
    results_root = tmp_path / "results"
    results_root.mkdir()
    train_ids = ["CASE-001", "CASE-003", "CASE-004", "CASE-005"]
    heldout_ids = ["CASE-002", "CASE-006"]
    truth_cases = []
    for index, case_id in enumerate(train_ids + heldout_ids):
        truth_cases.append({"case_id": case_id, "teacher_score": 60 + index * 5})
    for index, case_id in enumerate(train_ids):
        result = {
            "report": {
                "evaluation_context": {
                    "scoring": {"architecture": "evidence_v2", "raw_score": 62 + index * 7}
                }
            }
        }
        (results_root / f"{case_id}.json").write_text(
            json.dumps(result), encoding="utf-8"
        )
    truth_file = tmp_path / "ground_truth.json"
    truth_file.write_text(json.dumps({"cases": truth_cases}), encoding="utf-8")
    output_file = tmp_path / "calibrator.json"
    artifact = fit_calibration_artifact(
        results_root,
        truth_file,
        train_ids,
        heldout_ids,
        output_file,
        tmp_path / "split.json",
    )

    assert [item["case_id"] for item in artifact["points"]] == train_ids
    assert all(item["case_id"] not in heldout_ids for item in artifact["points"])
    assert artifact["evaluation_split"]["heldout_scores_used_for_fit"] is False


def test_evidence_v2_runs_full_scheme_chain_without_model_numeric_scores() -> None:
    """确认新版四个专项与综合 Agent 能完整跑通并生成旧前端兼容分数。"""
    client = FakeEvidenceLLMClient()
    report = generate_scheme_review(client, build_scheme_context())

    assert report["overall_score"] == 78
    assert report["evaluation_context"]["scoring"]["architecture"] == "evidence_v2"
    assert report["agent_evaluations"][0]["details"]["score_source"] == (
        "backend_level_mapping_v1"
    )
    assert len(client.client.chat.completions.calls) == 5


def build_evidence_payload(requirement_id: str) -> dict:
    """构造一份四项均为良好的证据输出。"""
    return {
        "observed_facts": [
            {"statement": "首层设主入口和门厅。", "source": "首层平面", "confidence": "high"}
        ],
        "confidence": "medium",
        "summary": "功能主线清楚，局部关系仍可深化。",
        "criterion_assessments": {
            name: {
                "level": 3,
                "reason": "主要关系成立。",
                "evidence": "首层平面与设计说明相互印证。",
                "confidence": "medium",
            }
            for name in FUNCTION_EVIDENCE_SPEC["sub_scores"]
        },
        "requirement_checks": [
            {
                "requirement_id": requirement_id,
                "status": "not_met",
                "evidence": "图纸未设置货梯。",
                "confidence": "high",
            }
        ],
        "must_fix": [
            {"text": "货梯缺失。", "evidence": "图纸未见。", "confidence": "medium"}
        ],
        "should_improve": ["继续明确后勤流线。"],
        "optional_improvements": ["可补充流线分析图。"],
        "strengths": ["主入口和公共空间关系清楚。"],
        "missing_information": [],
        "uncertain_observations": [],
    }


def build_evaluation(score: float, checks: list[dict]) -> dict:
    """构造总分层所需的最小专项结果。"""
    return {
        "agent_type": "function_agent",
        "score": score,
        "details": {
            "confidence": "medium",
            "requirement_checks": checks,
            "missing_information": [],
            "uncertain_observations": [],
        },
    }


def requirement_check(rule: dict, status: str, confidence: str) -> dict:
    """构造一条带原任务书规则的核对结果。"""
    return {
        **rule,
        "requirement_id": rule["id"],
        "status": status,
        "confidence": confidence,
        "evidence": "测试证据",
    }


def build_scheme_context() -> dict:
    """构造新版方案评图的最小上下文。"""
    return {
        "project_name": "社区记忆馆",
        "building_type": "公共文化建筑",
        "owner_name": "匿名学生",
        "grade": "大二",
        "design_stage": "方案阶段",
        "description": "围绕公共展览与档案阅读组织空间。",
        "task_book_text": "建筑面积约1200平方米，采用框架结构。",
        "task_book_summary": "公共文化建筑课程设计。",
        "task_book_profile": {
            "has_task_book": True,
            "structured_requirements": [],
            "dimension_weights": {
                "function_agent": 30,
                "site_agent": 20,
                "form_agent": 25,
                "structure_agent": 25,
            },
        },
        "structured_requirements": [],
        "dimension_weights": {
            "function_agent": 30,
            "site_agent": 20,
            "form_agent": 25,
            "structure_agent": 25,
        },
        "scoring_architecture": "evidence_v2",
        "score_calibration": None,
        "drawing_scope": "仅用于自动化测试。",
        "drawings": [],
        "references": [],
        "missing_information": [],
        "enabled_agents": [],
    }


class FakeEvidenceLLMClient:
    """提供新版证据输出的稳定假模型。"""

    def __init__(self) -> None:
        """初始化与真实客户端一致的调用字段。"""
        completions = FakeEvidenceCompletions()
        self.client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
        self.model = "fake-vision"
        self.structured_output_mode = "json_object"
        self.max_tokens = 2200
        self.image_detail = "high"
        self.extra_body = None
        self.reasoning_effort = None
        self.agent_timeout_seconds = 50
        self.review_timeout_seconds = 285


class FakeEvidenceCompletions:
    """依次返回四个证据专项和一个综合报告。"""

    criteria_by_call = {
        1: ["功能满足", "功能分区", "流线分析", "平面丰富性"],
        2: ["场地解读", "总图组织", "入口与到达", "环境回应"],
        3: ["形体生成", "空间构图", "几何秩序", "形式功能协同"],
        4: ["结构体系", "跨度与支撑", "构造可行性", "结构空间协同"],
    }

    def __init__(self) -> None:
        """保存调用记录。"""
        self.calls = []

    def create(self, **kwargs):
        """按调用位置返回合法 JSON。"""
        self.calls.append(kwargs)
        index = len(self.calls)
        if index == 5:
            payload = {
                "summary": "专项证据已汇总。",
                "must_fix": [],
                "should_improve": ["继续补充跨图纸印证。"],
                "optional_improvements": ["可补充分析图。"],
                "strengths": ["空间主线清楚。"],
            }
        else:
            payload = {
                "observed_facts": [
                    {"statement": "可见主要空间关系。", "source": "测试图纸", "confidence": "high"}
                ],
                "confidence": "medium",
                "summary": "专项主线基本清楚。",
                "criterion_assessments": {
                    name: {
                        "level": 3,
                        "reason": "主要关系成立。",
                        "evidence": "测试图纸。",
                        "confidence": "medium",
                    }
                    for name in self.criteria_by_call[index]
                },
                "requirement_checks": [],
                "must_fix": [],
                "should_improve": ["继续深化。"],
                "optional_improvements": ["可补充表达。"],
                "strengths": ["已有设计基础。"],
                "missing_information": [],
                "uncertain_observations": [],
            }
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload, ensure_ascii=False)))]
        )
