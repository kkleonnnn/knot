"""tests/eval/test_semantic_accuracy.py — B6.2 Layer 2（v0.8.1）：live parser 命中率门禁。

**live LLM · opt-in**（@_REQUIRES_KEY skip-if-no-key；eval-live.yml `pytest tests/eval` 已自动纳入 —— cron/
manual/`run-eval` label 触发）。对每 case live `parse_to_logicform` → 编译 → classify → 三率 →
**assert 命中率 ≥ 0.9 AND 误判数 == 0**（对标 v0.4.0 intent ≥90% 门禁 + 误判=0 硬安全线）。

守护者 §E LOCKED：
- 单跑 hard-assert + 护栏 —— 命中率阈值留 buffer（假域 .example 设计成稳 ≥95%），误判=0 硬保留；flaky
  主翻 hit↔fallback（抖命中率数字）非 hit↔误判 → 误判线相对稳；先跑几轮 opt-in 收波动分布。
- **假域 .example = harness 自检**（应 ~100%）；**真准确率 = kk 在 gitignored semantic_cases.yaml（真 OHX）跑本测**。
- DB-free：monkeypatch metric_repo.list_metrics = corpus catalog metrics + 固定 time_ctx（parse 需 live LLM，compile/canonical 确定性）。
"""
from __future__ import annotations

import asyncio
import os

import pytest

from knot.services.semantic import compiler, parser
from tests.eval._semantic_eval import (
    catalog_arg,
    catalog_metrics,
    classify,
    eval_time_ctx,
    load_semantic_corpus,
    rates,
    resolve_business_rules,
    resolve_eval_model,
)

_REQUIRES_KEY = pytest.mark.skipif(
    not os.getenv("OPENROUTER_API_KEY"),
    reason="需要 OPENROUTER_API_KEY 才能跑 live parser 命中率门禁",
)

_CATALOG, _CASES = load_semantic_corpus()
# 保真度（2026-07-18）：模型 = 生产 sql_planner（非 haiku 默认）+ 带 business_rules；否则假回归。
_MODEL = resolve_eval_model()[0]
_BR_CACHE: dict = {}


def _business_rules() -> str:
    """⭐ v0.9.3 R-8'：**必须在测执行期求值，不能在模块 import / pytest collection 期**。

    collection 期 conftest 的 autouse tenant ctx 尚未起 ⇒ catalog 载体 per-tenant 后读
    `_cl.BUSINESS_RULES` 会抛 `TenantContextError` → 被 harness 吞成 "" → live 门在
    **business_rules 缺失**下跑 → 命中率下滑会被误判成「语义层回归」。
    这正是 2026-07-18 假回归的同型复发 —— 而本参数本身就是那次事故的产物，绝不能被静默拆掉。
    故：① 延迟到测体内求值（此时有 ctx）；② `[0]` 会丢掉唯一诊断，这里把 source 标签打出来
    并对「缺 ctx」硬断言，让降级**响亮失败**而非静默改变门禁语义。
    """
    if "v" not in _BR_CACHE:
        rules, src = resolve_business_rules(_CATALOG)
        print(f"[eval] business_rules 来源={src} 长度={len(rules)}")
        assert "缺 tenant ctx" not in src, (
            f"business_rules 因缺 tenant ctx 静默为空（src={src}）—— 会造成假回归（R-8'）；"
            "eval 入口须在有 tenant ctx 时求值"
        )
        _BR_CACHE["v"] = rules
    return _BR_CACHE["v"]

# 门禁阈值（守护者 §E-1 护栏 b：假域留 buffer，稳 ≥95% 再 assert ≥90%）
_HIT_RATE_GATE = 0.90
_MISJUDGE_GATE = 0   # 误判=0 硬安全线（守护者 §E-1 护栏 c）


async def _parse_one(question: str, metrics: list[dict]):
    res = await parser.parse_to_logicform(
        question, metrics, model_key=_MODEL, openrouter_api_key=os.getenv("OPENROUTER_API_KEY", ""),
        business_rules=_business_rules(),  # 生产同参（query_steps.py:235）；测执行期求值 — R-8'
    )
    return res.get("logicform")


@_REQUIRES_KEY
def test_parser_hit_rate_and_zero_misjudge(monkeypatch):
    import knot.repositories.metric_repo as mr
    metrics = catalog_metrics(_CATALOG)
    monkeypatch.setattr(mr, "list_metrics", lambda cid=None: metrics)
    cat, tc = catalog_arg(_CATALOG), eval_time_ctx()

    # B6.4 v0.8.2：harness 须模型**生产语义决策**（parse → guard → compile），非仅 parse+compile
    # —— 否则跨期对比 guard（在 run_semantic_compile_step）被绕过，同比 fallback case 会误判为 misjudge。
    from knot.services.query_steps import _period_comparison_unrepresented

    labels, detail = [], []
    for case in _CASES:
        lf = asyncio.run(_parse_one(case["question"], metrics))
        compile_ok = False
        if lf is not None and _period_comparison_unrepresented(case["question"], lf, metrics):
            compile_ok = False                          # B6.4 guard 拒识 → refuse（= 生产 engine=llm 回退）
        elif lf is not None:
            try:
                compiler.compile_logicform(lf, cat, tc)
                compile_ok = True
            except compiler.CompileError:
                compile_ok = False
        label = classify(case, lf, compile_ok)
        labels.append(label)
        if label in ("misjudge", "miss"):
            detail.append(f"{case['id']}={label}(lf={lf.to_canonical_json() if lf else None})")

    r = rates(labels, _CASES)
    msg = (f"命中率 {r['hit_rate']:.2%} ({r['hit']}/{r['should_hit']}) · 误判 {r['misjudge']} · "
           f"漏判 {r['miss']} · 正确回退 {r['correct_fallback']}。问题项：{detail[:15]}")
    assert r["misjudge"] == _MISJUDGE_GATE, f"误判须 == 0（带徽标错口径）；{msg}"
    assert r["hit_rate"] >= _HIT_RATE_GATE, f"命中率 < {_HIT_RATE_GATE:.0%}；{msg}"
