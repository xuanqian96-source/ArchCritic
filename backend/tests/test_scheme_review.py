"""验证方案阶段多 Agent 顺序评审和综合报告结构。"""

import json
from types import SimpleNamespace

import pytest

from app.agents.scheme_review import (
    ModelOutputTruncatedError,
    create_json_completion,
    generate_scheme_review,
    iter_scheme_review_events,
    specialist_report_to_evaluation,
)
from app.agents.prompts.scheme_agents_v1 import SCHEME_SPECIALIST_SPECS
from app.config import Settings


def test_scheme_review_calls_specialists_in_order_and_keeps_all_images():
    """确认方案阶段会顺序调用专项 Agent 和综合评审 Agent。"""
    llm_client = FakeSchemeLLMClient()
    report = generate_scheme_review(llm_client, build_context())

    assert [item["agent_type"] for item in report["agent_evaluations"]] == [
        "function_agent",
        "site_agent",
        "form_agent",
        "structure_agent",
        "review_agent",
    ]
    assert report["summary"] == "四个专项结果已汇总，方案可以继续深化。"
    assert report["overall_score"] == 71.2
    assert "功能满足" in report["agent_evaluations"][0]["details"]["sub_scores"]
    assert "场地解读" in report["agent_evaluations"][1]["details"]["sub_scores"]
    assert len(llm_client.client.chat.completions.calls) == 5
    assert llm_client.client.chat.completions.calls[1]["max_tokens"] == 2200
    assert llm_client.client.chat.completions.calls[4]["max_tokens"] == 2200
    image_counts = [
        count_images(call["messages"][1]["content"])
        for call in llm_client.client.chat.completions.calls
    ]
    assert image_counts == [2, 2, 2, 2, 0]


def test_scheme_review_events_expose_each_agent_state():
    """确认流式接口可显示每个 Agent 的开始和结束状态。"""
    events = list(iter_scheme_review_events(FakeSchemeLLMClient(), build_context()))
    agent_events = [
        (item["status"], item["agent_type"])
        for item in events
        if item["event"] == "agent"
    ]

    assert agent_events == [
        ("start", "function_agent"),
        ("done", "function_agent"),
        ("start", "site_agent"),
        ("done", "site_agent"),
        ("start", "form_agent"),
        ("done", "form_agent"),
        ("start", "structure_agent"),
        ("done", "structure_agent"),
        ("start", "review_agent"),
        ("done", "review_agent"),
    ]
    assert events[-1]["event"] == "report"


def test_scheme_review_default_budget_stays_under_five_minutes():
    """确认默认方案评审预算不会超过五分钟。"""
    settings = Settings()

    assert settings.llm_review_timeout_seconds <= 285


def test_specialist_uncertainty_is_not_promoted_to_confirmed_issue():
    """确认专项不确定观察只保留在详情，不进入确定问题列表。"""
    report = {
        "overall_score": 80,
        "summary": "场地关系基本成立。",
        "strengths": ["入口回应街巷。"],
        "must_fix": ["主入口缺少必要过渡。"],
        "should_improve": ["补充室外空间层次。"],
        "optional_improvements": [],
        "missing_information": [],
        "uncertain_observations": ["后勤入口文字较小，暂时无法确认。"],
        "sub_scores": {},
        "confidence": "medium",
        "observed_facts": [],
    }
    evaluation = specialist_report_to_evaluation(
        SCHEME_SPECIALIST_SPECS["site_agent"], report
    )

    assert evaluation["issues"] == ["主入口缺少必要过渡。"]
    assert evaluation["details"]["uncertain_observations"] == [
        "后勤入口文字较小，暂时无法确认。"
    ]


def test_scheme_review_reports_model_length_cutoff():
    """确认模型截断输出时会给出明确错误。"""
    client = SimpleNamespace(
        client=SimpleNamespace(chat=SimpleNamespace(completions=LengthCutoffCompletions()))
    )

    with pytest.raises(ModelOutputTruncatedError):
        create_json_completion(client, {"model": "fake"})


def test_model_connection_error_is_retried_once():
    """确认短暂连接错误只重试一次，并能继续解析同一请求。"""
    completions = RetryOnceCompletions()
    client = SimpleNamespace(
        client=SimpleNamespace(chat=SimpleNamespace(completions=completions))
    )

    result = create_json_completion(client, {"model": "fake"})

    assert result == {"ok": True}
    assert completions.calls == 2


def build_context() -> dict:
    """构造包含两张图纸的方案上下文。"""
    return {
        "project_name": "城市共享展亭",
        "building_type": "小型公共建筑",
        "owner_name": "学生甲",
        "grade": "大三建筑学",
        "design_stage": "方案阶段",
        "description": "入口面向城市道路，首层布置展厅、服务台与公共卫生间。",
        "task_book_summary": "按小型公共建筑核对基础功能。",
        "drawing_scope": "本次包含平面图和总平面图。",
        "missing_information": [],
        "references": [],
        "drawings": [
            {
                "drawing_type": "plan",
                "original_name": "plan.png",
                "analysis_purpose": "功能和流线",
                "model_file_url": "oss://plan.png",
                "file_url": "/uploads/plan.png",
                "mime_type": "image/png",
                "usable_for_model": True,
            },
            {
                "drawing_type": "site",
                "original_name": "site.png",
                "analysis_purpose": "场地和入口",
                "model_file_url": "oss://site.png",
                "file_url": "/uploads/site.png",
                "mime_type": "image/png",
                "usable_for_model": True,
            },
        ],
    }


def count_images(content: list[dict]) -> int:
    """统计一次模型调用收到的图纸数量。"""
    return len([item for item in content if item.get("type") == "image_url"])


class FakeSchemeLLMClient:
    """提供稳定 JSON 的假模型客户端。"""

    def __init__(self) -> None:
        """初始化与真实 OpenAI 客户端一致的字段。"""
        completions = FakeCompletions()
        self.client = SimpleNamespace(
            chat=SimpleNamespace(completions=completions)
        )
        self.model = "fake-vision-model"
        self.structured_output_mode = "json_object"
        self.max_tokens = 2200
        self.image_detail = "high"
        self.extra_body = None
        self.reasoning_effort = None
        self.agent_timeout_seconds = 50
        self.review_timeout_seconds = 285


class FakeCompletions:
    """按调用顺序返回五个 Agent 的模拟结果。"""

    def __init__(self) -> None:
        """保存调用记录。"""
        self.calls = []

    def create(self, **kwargs):
        """返回当前 Agent 对应的 JSON。"""
        self.calls.append(kwargs)
        index = len(self.calls)
        if index == 1:
            payload = function_payload()
        elif index == 5:
            payload = {
                "summary": "四个专项结果已汇总，方案可以继续深化。",
                "must_fix": ["入口与后勤关系仍需明确。"],
                "should_improve": ["补充场地到达和结构表达。"],
                "optional_improvements": ["补充分析图说明几何生成。"],
                "strengths": ["公共空间与场地关系已有基础。"],
            }
        else:
            payload = specialist_payload(index)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload, ensure_ascii=False)))]
        )


class LengthCutoffCompletions:
    """模拟模型因为输出长度上限而截断。"""

    def create(self, **kwargs):
        """返回被截断的结果。"""
        del kwargs
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    finish_reason="length",
                    message=SimpleNamespace(content='{"summary": "未完成"'),
                )
            ]
        )


class RetryOnceCompletions:
    """第一次模拟连接错误，第二次返回合法 JSON。"""

    def __init__(self) -> None:
        """记录调用次数。"""
        self.calls = 0

    def create(self, **kwargs):
        """首次抛出同名连接异常，随后成功。"""
        del kwargs
        self.calls += 1
        if self.calls == 1:
            error_type = type("APIConnectionError", (RuntimeError,), {})
            raise error_type("temporary")
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok": true}'))]
        )


def function_payload() -> dict:
    """返回功能与流线 Agent 可校验的模拟结果。"""
    return {
        "observed_facts": {
            "楼梯": "看见一处垂直交通。",
            "电梯": "不确定。",
            "卫生间": "看见公共卫生间。",
            "主入口": "看见。",
            "车库入口": "不确定。",
            "报告厅": "未看见。",
            "服务台": "看见。",
        },
        "confidence": "medium",
        "summary": "功能与流线基本成立。",
        "sub_scores": {
            "功能满足": score_item(21, 30),
            "功能分区": score_item(18, 25),
            "流线分析": score_item(17, 25),
            "平面丰富性": score_item(14, 20),
        },
        "must_fix": ["后勤入口关系需明确。"],
        "should_improve": ["补充次要流线。"],
        "optional_improvements": ["补充功能分析图。"],
        "strengths": ["公共功能已形成基本框架。"],
        "missing_information": [],
        "uncertain_observations": [],
    }


def specialist_payload(index: int) -> dict:
    """返回场地、形式或结构 Agent 的模拟结果。"""
    score_names = {
        2: ["场地解读", "总图组织", "入口与到达", "环境回应"],
        3: ["形体生成", "空间构图", "几何秩序", "形式功能协同"],
        4: ["结构体系", "跨度与支撑", "构造可行性", "结构空间协同"],
    }[index]
    max_scores = [25, 25, 25, 25] if index < 4 else [30, 25, 25, 20]
    return {
        "observed_facts": ["图纸显示出当前专项可核对的关系。"],
        "confidence": "medium",
        "summary": f"专项 {index} 评审完成。",
        "sub_scores": {
            name: score_item(round(max_score * 0.7), max_score)
            for name, max_score in zip(score_names, max_scores)
        },
        "must_fix": [f"专项 {index} 的关键关系需明确。"],
        "should_improve": [f"专项 {index} 可以补充表达。"],
        "optional_improvements": [f"专项 {index} 可以继续深化。"],
        "strengths": [f"专项 {index} 已有基础。"],
        "missing_information": [],
        "uncertain_observations": [],
    }


def score_item(score: int, max_score: int) -> dict:
    """构造一个评分项。"""
    return {
        "score": score,
        "max_score": max_score,
        "reason": "图纸和说明支持该判断。",
        "evidence": "图纸观察。",
    }
