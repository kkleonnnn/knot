"""v0.6.5.3 — 测试隔离硬化守护（flaky 根因 + 防御性缓存清理）.

⭐ 真因（grounded 完整 traceback）：startup hook `_audit_auto_purge_if_stale` 用
`asyncio.create_task(_maybe_purge())` fire-and-forget（不 await）。该任务延迟执行时
`get_conn()` 读 *当前* monkeypatched SQLITE_DB_PATH —— 此刻已是 *后续* 测试的 tmp DB →
purge 线程持该 DB 的 WAL 锁 ⟷ 该测试 init_db 的 `PRAGMA journal_mode=WAL` 抢锁 →
`sqlite3.OperationalError: database is locked` 随机落点 ERROR（非确定性 = PYTHONHASHSEED
影响事件循环调度时机）。修：conftest 模块级 KNOT_SKIP_STARTUP_AUTO_PURGE=1 → hook 早返不建任务。

附带防御（任务点名的相邻风险，非本 flaky 真因）：清三类模块级可变缓存防其它隔离泄露。
"""
from __future__ import annotations

from unittest.mock import patch

import pytest


# ─── 主修守护：startup auto-purge 测试期跳过（防 fire-and-forget WAL 锁竞争）──


@pytest.mark.asyncio
async def test_auto_purge_skipped_when_env_set(monkeypatch):
    """KNOT_SKIP_STARTUP_AUTO_PURGE=1 → hook 早返，不 create_task（消除孤儿 purge 任务）。"""
    monkeypatch.setenv("KNOT_SKIP_STARTUP_AUTO_PURGE", "1")
    from knot.main import _audit_auto_purge_if_stale
    with patch("asyncio.create_task") as mock_ct:
        await _audit_auto_purge_if_stale()
    assert not mock_ct.called, "env=1 时严禁创建 fire-and-forget purge 任务（WAL 锁竞争根因）"


@pytest.mark.asyncio
async def test_auto_purge_runs_when_env_unset(monkeypatch):
    """未设 env → 正常 create_task（证 guard 是条件式跳过，非永久禁用 — 生产行为不变）。

    side_effect close 协程：mock 拦截 create_task → _maybe_purge() 协程不被运行，
    显式 close 避免 "coroutine was never awaited" RuntimeWarning。
    """
    monkeypatch.delenv("KNOT_SKIP_STARTUP_AUTO_PURGE", raising=False)
    from knot.main import _audit_auto_purge_if_stale
    with patch("asyncio.create_task", side_effect=lambda coro: coro.close()) as mock_ct:
        await _audit_auto_purge_if_stale()
    assert mock_ct.call_count == 1, "未设 env 时应正常创建 purge 任务（guard 条件式非永久跳过）"


def test_conftest_sets_skip_auto_purge_env():
    """conftest 模块级须设 KNOT_SKIP_STARTUP_AUTO_PURGE=1（防有人误删 → flaky 复发）。"""
    import os
    assert os.environ.get("KNOT_SKIP_STARTUP_AUTO_PURGE") == "1", \
        "conftest 模块级须 setdefault KNOT_SKIP_STARTUP_AUTO_PURGE=1（startup purge WAL 竞争修）"


# ─── 防御性：模块级缓存跨测试清理（确定性证明 autouse 清理生效）──────────
# 投毒 → autouse _reset_module_level_caches 清 → 断言空；禁用清理则 test_b 必红（非空洞）。


def test_a_poison_module_level_caches():
    """投毒三类模块级缓存（engine 指向 object / stale stats / token_version）。"""
    from knot.api import admin as admin_mod
    from knot.services import engine_cache, totp_service

    engine_cache._engine_cache[(999999, "poison-group")] = {
        "engine": object(), "schema": "", "databases": [], "ts": 9e18,
    }
    admin_mod._DS_STATS_CACHE["data"] = {"poisoned": True}
    admin_mod._DS_STATS_CACHE["ts"] = 9e18
    totp_service._TOKEN_VERSION_CACHE[999999] = 12345

    assert (999999, "poison-group") in engine_cache._engine_cache
    assert admin_mod._DS_STATS_CACHE["data"] == {"poisoned": True}
    assert totp_service._TOKEN_VERSION_CACHE.get(999999) == 12345


def test_b_autouse_cleared_all_poison():
    """autouse _reset_module_level_caches 应已清掉 test_a 全部投毒（禁用清理则本测试红）。"""
    from knot.api import admin as admin_mod
    from knot.services import engine_cache, totp_service

    assert (999999, "poison-group") not in engine_cache._engine_cache, \
        "_engine_cache 未被 autouse 清 → engine 跨测试泄露"
    assert len(engine_cache._engine_cache) == 0
    assert admin_mod._DS_STATS_CACHE["data"] is None
    assert admin_mod._DS_STATS_CACHE["ts"] == 0.0
    assert totp_service._TOKEN_VERSION_CACHE.get(999999) is None
