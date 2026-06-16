"""tests/services/test_catalog_race — v0.6.2.6 段 4 (A1 并发半) commit 4 守护测试。

覆盖（并发隔离端到端）：
- R-PB-A1-21 race 100× **0 交叉污染（布尔严格，非 TOTP ±5 数值容差）**：
  asyncio.gather 100 并发，各灌不同 active catalog_id → 每 query 读自己的（async 上下文隔离）
- R-PB-A1-22 出口不泄漏：copy_context().run(set) 不泄漏外层（请求作用域）
- 第②③层 assert：current==expected pass / mismatch → context_violation audit（attempted/expected 落库）+ raise

注：catalog race ≠ TOTP race（rate limit 数值容差 ±5）；catalog 数据串仓 1 次即隔离失败 → 0 污染布尔严格。
无生产中间件 reset（Starlette http 中间件无法在 SSE 流后 reset + query.py 440 cap）→ 靠 asyncio
task 隔离（每请求新 task + ContextVar per-task）保不泄漏，本 race 100× + copy_context 证之（R-PB-A1-22）。
"""
import asyncio
import contextvars

import pytest

from knot.models.errors import CatalogContextException
from knot.repositories.base import get_conn
from knot.services import query_helper
from knot.services.agents import catalog as catalog_loader


def _content(cid):
    return {"lexicon": {}, "tables": [], "business_rules": f"rule-{cid}",
            "relations": [], "catalog_id": cid}


# ─── R-PB-A1-21 race 100× 0 交叉污染（布尔严格）──────────────────────

@pytest.mark.race
def test_race_100x_no_cross_contamination():
    """100 并发各灌不同 catalog_id（单双号交替）→ 每 query 读自己的（0 交叉污染，布尔严格）。"""
    async def one_query(cid):
        catalog_loader.set_active_catalog_ctx(_content(cid))
        await asyncio.sleep(0)  # async gap — 让其他 task 穿插（暴露污染）
        await asyncio.sleep(0)
        cur = catalog_loader.current_catalog()
        return cur["catalog_id"], cur["business_rules"]

    async def run():
        return await asyncio.gather(*[one_query(i) for i in range(1, 101)])

    results = asyncio.run(run())
    for i, (cid, br) in enumerate(results, start=1):
        # 布尔严格：0 交叉污染（非 ±容差）— catalog 串仓 1 次即隔离失败
        assert cid == i, f"race 污染：query {i} 读到 catalog_id={cid}（期望 {i}）"
        assert br == f"rule-{i}"


# ─── R-PB-A1-22 出口不泄漏（请求作用域 — task 隔离）──────────────────

def test_contextvar_no_leak_across_contexts():
    """copy_context().run(set) 不泄漏外层（每请求新 task → ContextVar per-task 隔离）。"""
    def _inner():
        catalog_loader.set_active_catalog_ctx(_content(42))
        return catalog_loader.current_catalog()["catalog_id"]
    assert contextvars.copy_context().run(_inner) == 42
    # 外层上下文未被 copy_context 内 set 影响（不泄漏）
    assert catalog_loader.current_catalog()["catalog_id"] is None


def test_concurrent_tasks_isolated_default_none():
    """新 task 默认 ContextVar None（未 set 的 query 回退全局）— task 隔离基础。"""
    async def unset_task():
        return catalog_loader.current_catalog()["catalog_id"]

    async def run():
        return await asyncio.gather(unset_task(), unset_task())
    assert asyncio.run(run()) == [None, None]


# ─── 第②③层 assert + context_violation audit（attempted/expected 落库）──

def test_assert_catalog_context_pass_when_match(tmp_db_path):
    """current == expected → assert 通过（单 Task 无漂移）。"""
    catalog_loader.set_active_catalog_ctx(_content(3))
    try:
        query_helper.assert_catalog_context(3, {"id": 1, "username": "admin", "role": "admin"})  # 不抛
    finally:
        catalog_loader.set_active_catalog_ctx(None)


def test_assert_catalog_context_raises_and_audits_on_mismatch(tmp_db_path):
    """current != expected → context_violation audit（attempted/expected 落库）+ raise CatalogContextException。"""
    catalog_loader.set_active_catalog_ctx(_content(1))  # 当前 ctx catalog_id=1
    try:
        with pytest.raises(CatalogContextException) as exc:
            query_helper.assert_catalog_context(5, {"id": 1, "username": "admin", "role": "admin"})  # expected=5 ≠ 1
        assert exc.value.attempted_catalog_id == 1 and exc.value.expected_catalog_id == 5
    finally:
        catalog_loader.set_active_catalog_ctx(None)
    # context_violation audit 落库 + attempted/expected detail（R-PB-A1-23）
    conn = get_conn()
    rows = [dict(r) for r in conn.execute(
        "SELECT action, detail_json, catalog_id FROM audit_log WHERE action='catalog.context_violation'"
    ).fetchall()]
    conn.close()
    assert any('"attempted_catalog_id": 1' in r["detail_json"]
               and '"expected_catalog_id": 5' in r["detail_json"]
               and int(r["catalog_id"]) == 5 for r in rows)


def test_assert_skips_when_expected_none(tmp_db_path):
    """expected None（capture fail-soft 回退全局）→ assert 跳过（不抛）。"""
    query_helper.assert_catalog_context(None, {"id": 1, "username": "admin", "role": "admin"})  # 不抛
