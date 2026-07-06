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
    )


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
