"""⭐ 验收：启动期 audit 自动清理的**原子认领**（v0.9.23 R10'-C）。

## 它证什么
N 个副本同时启动 ⇒ **只有 1 个**该跑 purge。原实现是 read-then-write
（读 `last_purge_at` → 判 7 天 → 跑），N 副本会同时判「该跑」⇒ N 个并发 chunk DELETE。

## ⚠️⚠️ 三条判据形状是评审逼出来的（六问②/①），改回去就测不到东西了

1. **必须真子进程 + 共同 barrier**：既有样板 `test_startup_with_multiple_tenants.py`
   用的是 `subprocess.run` = **顺序阻塞** ⇒ N 个进程**根本不重叠** ⇒ 无论实现是不是原子的都「恰 1 个成功」
   ⇒ 判据恒绿。本文件用 `Popen × N` + **同一个 wall-clock 起跑点**。
2. **oracle = 各进程自报的认领结果，不是 DELETE 行数**：审计表为空时 DELETE **不可观测**
   ⇒ 用行数当判据会在「什么都没发生」和「正确地只清了一次」之间无法区分。
3. **必须双态**：`missing-row`（全新部署，`app_settings` 里**没有那一行**）与 `stale-row` 各一条。
   ⚠️ 只测 stale 态会漏掉本片最严重的那个缺陷 —— 原方案的 `UPDATE … WHERE` 在
   **行不存在时 rowcount=0** ⇒ **全新部署永不 purge**，而那种实现在 stale 态下**完全正常**。

## ⚠️ 隔离自证（六问⑥）
子进程开头**先自证 `SQLITE_DB_PATH` 指向本测的 tmp 目录**，不满足立刻 `exit 9`
—— 「环境没隔离」与「实验失败」必须报成两条**不同**的消息，否则会把污染读成结果。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time

import pytest
from cryptography.fernet import Fernet

_PREAMBLE = '''
import json, os, sys, time
_root = os.environ["KNOT_DATA_ROOT_EXPECT"]
from knot.repositories.base import SQLITE_DB_PATH
if _root not in str(SQLITE_DB_PATH):
    print(json.dumps({{"isolation": False, "path": str(SQLITE_DB_PATH)}}))
    sys.exit(9)          # ⚠️ 与「实验失败」用**不同**的退出码 + 不同的消息
# ── barrier：所有子进程等同一个 wall-clock 起跑点（`subprocess.run` 顺序阻塞造不出竞态）──
_t0 = float(os.environ["KNOT_TEST_BARRIER_TS"])
while time.time() < _t0:
    time.sleep(0.002)
'''

_BODY = '''
from knot.core.tenant_context import reset_active_tenant, set_active_tenant
from knot.repositories import tenant_repo
from knot.services import audit_service

row = tenant_repo.get_tenant(1)
tok = set_active_tenant(row)
try:
    claimed = audit_service.claim_auto_purge(days=7)
finally:
    reset_active_tenant(tok)
print(json.dumps({{"isolation": True, "claimed": bool(claimed)}}))
'''


@pytest.fixture
def data_root(tmp_path):
    """建好平台库 + 租户库的 tmp 数据根（认领读写的是**租户库** `app_settings`）。"""
    key = Fernet.generate_key().decode()          # ⚠️ 一次生成、传给全部子进程（B-O10 ①）
    anchor = tmp_path / "knot.db"
    env = {**os.environ, "SQLITE_DB_PATH": str(anchor), "KNOT_MASTER_KEY": key,
           "KNOT_SKIP_STARTUP_AUTO_PURGE": "1", "KNOT_DATA_ROOT_EXPECT": str(tmp_path),
           "PYTHONPATH": os.getcwd()}
    code = _PREAMBLE.replace("{{", "{").replace("}}", "}") + '''
from knot.repositories import base, tenant_repo
from knot.core.tenant_context import reset_active_tenant, set_active_tenant
tenant_repo.init_platform_db()
tenant_repo.seed_default_tenant(db_dir="tenants/1")
tok = set_active_tenant(tenant_repo.get_tenant(1))
try:
    base.init_db()
finally:
    reset_active_tenant(tok)
print(json.dumps({"isolation": True, "setup": "ok"}))
'''
    env["KNOT_TEST_BARRIER_TS"] = str(time.time())
    r = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=180,
                       check=False)  # 刻意 —— 本文件显式判 rc（rc==9 = 环境没隔离，与失败区分）
    assert r.returncode == 0, f"fixture 建库失败 (rc={r.returncode}): {r.stdout[-800:]}{r.stderr[-800:]}"
    return env


def _race(env, n=4):
    """`Popen × n` + 共同 barrier ⇒ 返回各进程自报的 claimed 列表。"""
    env = {**env, "KNOT_TEST_BARRIER_TS": str(time.time() + 2.5)}
    code = (_PREAMBLE + _BODY).replace("{{", "{").replace("}}", "}")
    procs = [subprocess.Popen([sys.executable, "-c", code], env=env,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
             for _ in range(n)]
    out = []
    for p in procs:
        so, se = p.communicate(timeout=180)
        if p.returncode == 9:
            pytest.fail(f"⛔ **环境没隔离**（不是实验失败）：{so.strip()}")
        assert p.returncode == 0, f"子进程 rc={p.returncode}\nSTDOUT:{so[-600:]}\nSTDERR:{se[-800:]}"
        out.append(json.loads(so.strip().splitlines()[-1]))
    assert all(r["isolation"] for r in out), f"隔离自证未通过: {out}"
    return [r["claimed"] for r in out]


def test_missing_row_exactly_one_replica_claims(data_root):
    """⭐⭐ **missing-row 态**（全新部署：`app_settings` 里没有那一行）⇒ 认领成功的进程**恰 1 个**。

    ⚠️ **这一条是本文件最承重的**：原方案用纯 `UPDATE … WHERE`，在行不存在时 `rowcount=0`
    ⇒ **0 个进程认领成功 ⇒ 全新部署永不 purge**，而那种实现在 stale-row 态下表现完全正常。
    """
    claimed = _race(data_root, n=4)
    assert sum(claimed) == 1, (
        f"认领成功的进程应恰 1 个，实际 {sum(claimed)}（各进程: {claimed}）—— "
        "0 = 全新部署永不 purge（纯 UPDATE 的 rowcount 恒 0）；>1 = N 个并发 DELETE 打同一租户库"
    )


def test_stale_row_exactly_one_replica_claims(data_root):
    """⭐ **stale-row 态**：已有一个很旧的 `last_purge_at` ⇒ 仍然恰 1 个认领成功。"""
    seed = '''
from knot.core.tenant_context import reset_active_tenant, set_active_tenant
from knot.repositories import settings_repo, tenant_repo
tok = set_active_tenant(tenant_repo.get_tenant(1))
try:
    settings_repo.set_app_setting("audit.last_purge_at", "2020-01-01T00:00:00")
finally:
    reset_active_tenant(tok)
print(json.dumps({"isolation": True, "seeded": True}))
'''
    env = {**data_root, "KNOT_TEST_BARRIER_TS": str(time.time())}
    code = _PREAMBLE.replace("{{", "{").replace("}}", "}") + seed
    r = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=180,
                       check=False)  # 刻意 —— 本文件显式判 rc（rc==9 = 环境没隔离，与失败区分）
    assert r.returncode == 0, f"seed 失败: {r.stdout[-600:]}{r.stderr[-600:]}"

    claimed = _race(data_root, n=4)
    assert sum(claimed) == 1, f"stale 态认领成功应恰 1 个，实际 {sum(claimed)}（{claimed}）"


def test_recent_purge_means_nobody_claims(data_root):
    """⭐ **负对照**：刚清过（`last_purge_at` = now）⇒ **零个**进程认领。

    ⚠️ 没有这一条，「恰 1 个」可以被「无条件让第一个进程认领」这种实现满足 ——
    那样每次重启都会 purge 一遍，7 天阈值形同不存在。
    """
    seed = '''
import datetime as _dt
from knot.core.tenant_context import reset_active_tenant, set_active_tenant
from knot.repositories import settings_repo, tenant_repo
tok = set_active_tenant(tenant_repo.get_tenant(1))
try:
    settings_repo.set_app_setting("audit.last_purge_at", _dt.datetime.now().isoformat(timespec="seconds"))
finally:
    reset_active_tenant(tok)
print(json.dumps({"isolation": True, "seeded": True}))
'''
    env = {**data_root, "KNOT_TEST_BARRIER_TS": str(time.time())}
    code = _PREAMBLE.replace("{{", "{").replace("}}", "}") + seed
    r = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=180,
                       check=False)  # 刻意 —— 本文件显式判 rc（rc==9 = 环境没隔离，与失败区分）
    assert r.returncode == 0, f"seed 失败: {r.stdout[-600:]}{r.stderr[-600:]}"

    claimed = _race(data_root, n=3)
    assert sum(claimed) == 0, f"刚清过却仍有 {sum(claimed)} 个进程认领（7 天阈值失效）"


def test_failed_purge_can_be_retried_next_window(data_root):
    """⭐⭐ 验收 MF7：**认领成功但 purge 失败** ⇒ 下一个窗口**仍可认领**（不是 7 天内永不重试）。

    ⚠️ 这条防的是我采纳评审意见时**自己引入的回归**：若认领时就把 `last_purge_at` 推到 now，
    purge 抛错（会被调用方 `except` 吞成一条 WARN）之后 7 天内不再重试 ⇒ 审计表无限增长。
    ⇒ 认领必须用**独立标记**，与「完成」标记分开。
    **判据 = `last_purge_at` 在只认领、未成功的情况下必须仍为空。**
    """
    probe = '''
from knot.core.tenant_context import reset_active_tenant, set_active_tenant
from knot.repositories import settings_repo, tenant_repo
from knot.services import audit_service
tok = set_active_tenant(tenant_repo.get_tenant(1))
try:
    first = audit_service.claim_auto_purge(days=7)     # 认领成功，但**故意不跑 purge**（模拟抛错）
    done = settings_repo.get_app_setting("audit.last_purge_at", "")
    second = audit_service.claim_auto_purge(days=7)    # 同窗口内再认领 ⇒ 应失败
finally:
    reset_active_tenant(tok)
print(json.dumps({"isolation": True, "first": first, "done_marker": done, "second": second}))
'''
    env = {**data_root, "KNOT_TEST_BARRIER_TS": str(time.time())}
    code = _PREAMBLE.replace("{{", "{").replace("}}", "}") + probe
    r = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=180,
                       check=False)  # 刻意 —— 本文件显式判 rc（rc==9 = 环境没隔离，与失败区分）
    assert r.returncode == 0, f"探针失败: {r.stdout[-600:]}{r.stderr[-600:]}"
    got = json.loads(r.stdout.strip().splitlines()[-1])

    assert got["first"] is True, f"首次应认领成功: {got}"
    assert got["done_marker"] == "", (
        f"⛔ 认领动作污染了「完成」标记（`last_purge_at`={got['done_marker']!r}）—— "
        "purge 抛错后会被当成「已清理」，7 天内不再重试"
    )
    assert got["second"] is False, f"同一窗口内应认领失败（防重复）: {got}"
