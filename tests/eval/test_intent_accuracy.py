"""tests/eval/test_intent_accuracy.py — v0.4.0 Clarifier intent 分类准确率门禁。

两层防线：
  1. 本地：mapping 完整性 / 用例 yaml 内 intent ↔ display_hint 一致（无 LLM，CI 必跑）
  2. live：跑 80 条 case 通过 Clarifier，统计准确率 ≥ 90%（需 OPENROUTER_API_KEY）

对应手册 §6.4。
"""
from __future__ import annotations

import os

import pytest

from tests.eval.conftest import load_cases

from bi_agent.services.knot.orchestrator import (
    INTENT_TO_HINT,
    VALID_INTENTS,
    run_clarifier,
)

CASES = load_cases()

_REQUIRES_KEY = pytest.mark.skipif(
    not os.getenv("OPENROUTER_API_KEY"),
    reason="需要 OPENROUTER_API_KEY 才能跑 LLM 准确率门禁",
)


# ── Layer 1：纯本地，CI 必跑 ──────────────────────────────────────────


def test_valid_intents_have_layout_mapping():
    """7 类 intent 必须全部在 INTENT_TO_HINT 中有 layout 映射。"""
    for intent in VALID_INTENTS:
        assert intent in INTENT_TO_HINT, f"intent {intent!r} 缺 layout 映射"
    # 反向：mapping 不能多出未知 intent
    assert set(INTENT_TO_HINT.keys()) == set(VALID_INTENTS)


def test_each_case_intent_in_valid_set():
    """每条 case 的 expects.intent 必须是 7 类之一。"""
    for case in CASES:
        intent = case["expects"]["intent"]
        assert intent in VALID_INTENTS, f"[{case['id']}] 非法 intent {intent!r}"


def test_each_case_display_hint_matches_intent():
    """case 的 expects.display_hint 必须等于 INTENT_TO_HINT[intent]。"""
    for case in CASES:
        intent = case["expects"]["intent"]
        expected_hint = INTENT_TO_HINT[intent]
        actual_hint = case["expects"]["display_hint"]
        assert actual_hint == expected_hint, (
            f"[{case['id']}] display_hint 与 intent 不一致："
            f"intent={intent} 应映射到 {expected_hint}，但 yaml 写了 {actual_hint!r}"
        )


def test_export_button_visibility_only_on_detail():
    """detail intent 的 export_button_visible=true，其他全部 false。"""
    for case in CASES:
        intent = case["expects"]["intent"]
        visible = case["expects"]["export_button_visible"]
        if intent == "detail":
            assert visible is True, f"[{case['id']}] detail 应 export_button_visible=true"
        else:
            assert visible is False, (
                f"[{case['id']}] {intent} intent 不应显示导出按钮，但 yaml 写了 true"
            )


def test_each_intent_has_at_least_8_cases():
    """每类 intent 至少 8 条用例（手册 §6 要求）。"""
    from collections import Counter
    counts = Counter(c["intent"] for c in CASES)
    for intent in VALID_INTENTS:
        assert counts[intent] >= 8, f"intent {intent!r} 仅 {counts[intent]} 条，少于 8"


def test_total_cases_at_least_80():
    assert len(CASES) >= 80, f"用例总数 {len(CASES)} < 80"


# ── Layer 2：live LLM accuracy 门禁 ──────────────────────────────────


@_REQUIRES_KEY
def test_intent_classification_accuracy_at_least_90pct(fake_schema):
    """跑全部 case 通过 Clarifier，统计 intent 准确率，要求 ≥ 90%。"""
    correct = 0
    failures: list[tuple[str, str, str]] = []
    model = os.getenv("EVAL_MODEL", "google/gemini-2.0-flash-001")
    or_key = os.getenv("OPENROUTER_API_KEY", "")

    for case in CASES:
        history: list = []
        if case.get("history_required"):
            # 给 history_dependent case 一个最小历史，模拟"上一题"
            history = [{
                "question": "昨天注册用户数",
                "sql": "SELECT COUNT(*) FROM users WHERE DATE(created_at) = DATE_SUB(CURDATE(), INTERVAL 1 DAY)",
                "rows": [{"cnt": 8}],
            }]

        result = run_clarifier(
            case["question"], fake_schema, history,
            model_key=model, openrouter_api_key=or_key,
        )
        expected = case["expects"]["intent"]
        actual = result.get("intent")
        if actual == expected:
            correct += 1
        else:
            failures.append((case["id"], expected, actual or "<none>"))

    total = len(CASES)
    accuracy = correct / total if total else 0
    msg = (
        f"intent 准确率 {accuracy:.2%} ({correct}/{total}) < 90%。"
        f" 失败前 10 条：{failures[:10]}"
    )
    assert accuracy >= 0.9, msg
