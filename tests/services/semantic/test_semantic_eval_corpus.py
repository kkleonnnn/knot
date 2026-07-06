"""tests/services/semantic/test_semantic_eval_corpus.py — B6.2 Layer 1（v0.8.1）。

**key-free · 确定性 · 主 CI 强制**（放 tests/services/semantic/ 而非 tests/eval/ —— 守护者 §A collect-only 实测：
tests/eval 被 `ci.yml --ignore=tests/eval` 排除，Layer 1 须在 tests/eval 外才每-PR 强制）。

不跑 LLM：只验 ① corpus 良构 ② 每 hit case 期望 LogicForm **确定性编译覆盖**（0 LLM/DB，monkeypatch
metric_repo + 固定 time_ctx）③ 最小覆盖集（七刀主形 + 回退）④ classify scorer 逻辑（合成输入）。
真 accuracy（live parse）在 Layer 2（tests/eval/test_semantic_accuracy.py，@_REQUIRES_KEY opt-in）。
"""
from __future__ import annotations

import pytest

from knot.services.semantic import compiler
from knot.services.semantic.logicform import LogicForm
from tests.eval._semantic_eval import (
    catalog_arg,
    catalog_metrics,
    classify,
    eval_time_ctx,
    expected_canonicals,
    load_semantic_corpus,
    rates,
)

_CATALOG, _CASES = load_semantic_corpus()
_HIT_CASES = [c for c in _CASES if c["expect"]["mode"] == "hit"]
_FALLBACK_CASES = [c for c in _CASES if c["expect"]["mode"] == "fallback"]


# ── ① corpus 良构 ──────────────────────────────────────────────
def test_corpus_wellformed():
    seen_ids = set()
    for c in _CASES:
        assert c.get("id") and c["id"] not in seen_ids, f"case id 缺失/重复: {c.get('id')}"
        seen_ids.add(c["id"])
        assert c.get("question"), f"{c['id']}: question 缺失"
        assert c["expect"]["mode"] in ("hit", "fallback"), f"{c['id']}: mode 非法"
        if c["expect"]["mode"] == "hit":
            assert expected_canonicals(c), f"{c['id']}: hit case 须含 logicform/logicforms"


def test_catalog_wellformed():
    assert _CATALOG.get("tables") and _CATALOG.get("metrics"), "catalog 须含 tables + metrics"
    for m in catalog_metrics(_CATALOG):
        assert m.get("name"), "metric 须含 name"
        assert m.get("caliber") or m.get("lineage"), f"metric {m.get('name')}: 须 caliber 或 lineage"


# ── ② 每 hit case 期望 LogicForm 确定性编译覆盖（0 LLM/DB）────────
@pytest.mark.parametrize("case", _HIT_CASES, ids=[c["id"] for c in _HIT_CASES])
def test_hit_case_expected_lf_compiles(case, monkeypatch):
    """每个期望 canonical LF 经 compile_logicform 确定性编译成功（无 CompileError）。

    守护者 §A：这是「漏判-编译raise」根因的 CI 守护 —— 期望 LF 若编译器覆盖不到，live 时也会漏判。
    """
    import knot.repositories.metric_repo as mr
    monkeypatch.setattr(mr, "list_metrics", lambda cid=None: catalog_metrics(_CATALOG))
    cat, tc = catalog_arg(_CATALOG), eval_time_ctx()
    exp = case["expect"]
    raw = exp.get("logicforms") or [exp["logicform"]]
    for d in raw:
        lf = LogicForm.from_dict(d)
        sql = compiler.compile_logicform(lf, cat, tc)   # 不 raise = 编译覆盖 OK
        assert sql.strip(), f"{case['id']}: 编译产出空"


# ── ③ 最小覆盖集（七刀主形 + 回退各类）──────────────────────────
def test_corpus_minimal_coverage():
    tags = {t for c in _CASES for t in c.get("tags", [])}
    for need in ("dimension", "having", "window", "multi_base", "derived"):
        assert need in tags, f"corpus 缺覆盖: {need}（最小集须含七刀主形）"
    assert len(_HIT_CASES) >= 5, f"hit case 应 ≥5（当前 {len(_HIT_CASES)}）"
    assert len(_FALLBACK_CASES) >= 2, f"fallback case 应 ≥2（当前 {len(_FALLBACK_CASES)}）"


# ── ④ classify scorer 逻辑（合成输入，无 LLM）──────────────────
def test_classify_scorer_logic():
    hit_case = {"id": "h", "expect": {"mode": "hit", "logicform": {"metrics": ["gmv"], "dimensions": ["city"]}}}
    fb_case = {"id": "f", "expect": {"mode": "fallback"}}
    expected_lf = LogicForm.from_dict({"metrics": ["gmv"], "dimensions": ["city"]})
    wrong_lf = LogicForm.from_dict({"metrics": ["gmv"], "dimensions": ["region"]})   # 不同 canonical

    assert classify(hit_case, expected_lf, compile_ok=True) == "hit"
    assert classify(hit_case, wrong_lf, compile_ok=True) == "misjudge"       # 命中但错 = 误判
    assert classify(hit_case, expected_lf, compile_ok=False) == "miss"        # 编译 raise = 漏判
    assert classify(hit_case, None, compile_ok=False) == "miss"              # parse None = 漏判
    assert classify(fb_case, None, compile_ok=False) == "correct_fallback"    # 应回退且回退
    assert classify(fb_case, expected_lf, compile_ok=True) == "misjudge"      # 不该命中却命中 = 误判


def test_classify_multi_expected_logicforms():
    """expect.logicforms（≥1 集合，filter-heavy 逃生舱）：任一命中即算对。"""
    case = {"id": "m", "expect": {"mode": "hit", "logicforms": [
        {"metrics": ["gmv"], "filters": ["o.status='paid'"]},
        {"metrics": ["gmv"], "filters": ["o.status = 'paid'"]},   # 等价写法（canonical 不同）
    ]}}
    for d in case["expect"]["logicforms"]:
        assert classify(case, LogicForm.from_dict(d), compile_ok=True) == "hit"


def test_rates_aggregation():
    cases = [{"expect": {"mode": "hit"}}] * 8 + [{"expect": {"mode": "fallback"}}] * 2
    labels = ["hit"] * 7 + ["miss"] + ["correct_fallback"] * 2
    r = rates(labels, cases)
    assert r["should_hit"] == 8 and r["hit"] == 7 and r["misjudge"] == 0
    assert abs(r["hit_rate"] - 7 / 8) < 1e-9
