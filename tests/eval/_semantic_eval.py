"""tests/eval/_semantic_eval.py — B6.2 语义 eval 共享 helper（v0.8.1）。

corpus 加载（real-preferred-then-example，镜像 conftest._pick）+ 期望 canonical 集 + classify scorer。
Layer 1（tests/services/semantic/test_semantic_eval_corpus.py，key-free）与 Layer 2
（tests/eval/test_semantic_accuracy.py，@_REQUIRES_KEY live）共用（导入路径 `from tests.eval._semantic_eval import ...`，
镜像既有 `tests._route_count`）。

classify 语义（守护者 §D-4/§E LOCKED）：
- 命中 (hit)      = mode==hit 且产出 LogicForm 编译成功 且 canonical ∈ 期望集（复现期望确定性 LF）。
- 误判 (misjudge) = 产出命中（编译成功）但 canonical ∉ 期望集；或 mode==fallback 却命中（不该命中而命中）。
- 漏判 (miss)     = mode==hit 但产出 None / 编译 raise（应命中却回退）。
- 正确回退         = mode==fallback 且产出 None / 编译 raise。
canonical **保序不归一** → 检「确定性复现」非「语义等价」；filter-heavy case 用 expect.logicforms（≥1 期望集）。
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import yaml

from knot.services.semantic.logicform import LogicForm

HERE = Path(__file__).parent


def _pick(real: str, example: str) -> Path:
    for name in (real, example):
        p = HERE / name
        if p.exists():
            return p
    return HERE / example


def load_semantic_corpus() -> tuple[dict, list[dict]]:
    """(catalog, cases)：优先 semantic_cases.yaml（真 OHX，gitignored），缺失回退 .example（假域）。"""
    p = _pick("semantic_cases.yaml", "semantic_cases.example.yaml")
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return data.get("catalog", {}), data.get("cases", [])


def catalog_arg(catalog: dict) -> dict:
    """→ compile_logicform 的 catalog 参数（{catalog_id, tables}）。"""
    return {"catalog_id": catalog.get("catalog_id", 1), "tables": catalog.get("tables", [])}


def catalog_metrics(catalog: dict) -> list[dict]:
    """→ metric_repo.list_metrics 的 monkeypatch 返回值 / parse_to_logicform 的 metrics 入参。"""
    return catalog.get("metrics", [])


def eval_time_ctx() -> SimpleNamespace:
    """确定性 time_ctx（Layer 1 编译覆盖 + Layer 2 canonical 定钟；窗口值固定）。"""
    return SimpleNamespace(
        this_month_to_latest=("2026-06-01", "2026-06-21"),
        this_month=("2026-06-01", "2026-06-30"),
        this_week=("2026-06-15", "2026-06-21"),
        this_year_to_latest=("2026-01-01", "2026-06-21"),
        last_7_days_to_latest=("2026-06-15", "2026-06-21"),
        today=("2026-06-21", "2026-06-21"),
        yesterday=("2026-06-20", "2026-06-20"),
        # v0.9 前语义激活收官：补真 OHX 语料用到的窗（last_month 10 案 / last_week / last_year）——
        # additive，2026-06-21 锚点一致；否则 eval 跑到这些窗 AttributeError 崩。
        last_month=("2026-05-01", "2026-05-31"),
        last_week=("2026-06-08", "2026-06-14"),
        last_year=("2025-01-01", "2025-12-31"),
        this_year=("2026-01-01", "2026-12-31"),  # 整年（≠ this_year_to_latest 至今）
    )


# ── eval 保真度：模型 + business_rules 解析（committed 测 + scripts 共用单一真相源）──
# 2026-07-18 教训：eval 用 haiku（默认）+ 不传 business_rules → 假回归（生产 parser = sonnet-4.6 + 带 rules）。
# 所有 eval 入口须用生产同款模型/参数，否则边缘能力（率派生/outer/自由 filter）被测成假失败。
def resolve_eval_model(cli_model: str | None = None) -> tuple[str, str]:
    """→ (model, source)。cli > env EVAL_MODEL > 生产 agent_model_config.sql_planner(DB best-effort) > haiku 兜底。"""
    import json
    import os
    if cli_model:
        return cli_model, "cli"
    env_m = os.getenv("EVAL_MODEL", "").strip()
    if env_m:
        return env_m, "env EVAL_MODEL"
    try:  # best-effort：真部署下取生产模型；CI/无 DB 时静默兜底 haiku
        from knot.repositories.settings_repo import get_app_setting
        prod = (json.loads(get_app_setting("agent_model_config", "") or "{}").get("sql_planner") or "").strip()
        if prod:
            return prod, "生产 agent_model_config.sql_planner"
    except Exception:
        pass
    return "anthropic/claude-haiku-4.5", "兜底默认"


def resolve_business_rules(catalog: dict) -> tuple[str, str]:
    """→ (business_rules, source)。corpus catalog 自包含优先 → catalog_loader(生产同源) → 空。

    生产 parser 调用带 business_rules（query_steps.py，v0.7.19 库表时效路由）；eval 须同参。
    """
    br = (catalog.get("business_rules") or "").strip()
    if br:
        return br, "corpus catalog.business_rules"
    # v0.9.3 R-8'：catalog 载体 per-tenant 化后，无 tenant ctx 读 `_cl.BUSINESS_RULES` 会 raise
    # TenantContextError（fail-closed）。此前这里被裸 `except Exception: pass` 吞成 "（无）" →
    # eval 命中率下滑会被误判成「语义层回归」（2026-07-18 假回归同型）。故**把缺 ctx 与真无规则分开报**，
    # 让降级在 eval 输出里可见（source 标签即诊断），而不是静默。
    try:
        from knot.services.agents import catalog as _cl
        rules = _cl.BUSINESS_RULES
    except Exception as e:
        from knot.core.tenant_context import TenantContextError
        if isinstance(e, TenantContextError):
            return "", "（无 — 缺 tenant ctx：CLI/harness 须显式 set_active_tenant，见 R-8'）"
        return "", f"（无 — catalog 读失败：{type(e).__name__}）"
    if (rules or "").strip():
        return rules, "catalog_loader.BUSINESS_RULES"
    return "", "（无）"


def expected_canonicals(case: dict) -> set[str]:
    """hit case 的期望 canonical 集（唯一形 expect.logicform 或 ≥1 集合 expect.logicforms）。"""
    exp = case["expect"]
    raw = exp.get("logicforms") or ([exp["logicform"]] if exp.get("logicform") is not None else [])
    return {LogicForm.from_dict(d).to_canonical_json() for d in raw}


def classify(case: dict, produced_lf, compile_ok: bool) -> str:
    """→ 'hit' | 'misjudge' | 'miss' | 'correct_fallback'。

    produced_lf: LogicForm | None（parser 产出）；compile_ok: 该 LF 是否确定性编译成功（无 CompileError）。
    """
    mode = case["expect"]["mode"]
    produced_hit = produced_lf is not None and compile_ok
    if mode == "fallback":
        return "correct_fallback" if not produced_hit else "misjudge"
    # mode == "hit"
    if not produced_hit:
        return "miss"
    return "hit" if produced_lf.to_canonical_json() in expected_canonicals(case) else "misjudge"


def rates(labels: list[str], cases: list[dict]) -> dict:
    """三率聚合。命中率 = 命中 / 应命中数；误判数 = misjudge（含 fallback 误命中）；漏判率 = miss / 应命中数。"""
    should_hit = sum(1 for c in cases if c["expect"]["mode"] == "hit")
    hit = labels.count("hit")
    misjudge = labels.count("misjudge")
    miss = labels.count("miss")
    return {
        "should_hit": should_hit,
        "hit": hit,
        "misjudge": misjudge,
        "miss": miss,
        "correct_fallback": labels.count("correct_fallback"),
        "hit_rate": (hit / should_hit) if should_hit else 0.0,
        "miss_rate": (miss / should_hit) if should_hit else 0.0,
    }
