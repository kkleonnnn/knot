"""`knot/scripts/set_tenant_status.py` 行为测（v0.9.20 P-c）。

## 为什么必须自带行为测（Stage 2 §5-④）
既有的 CLI 哨兵 `test_destructive_cli_requires_target.py` 对本脚本**结构上不可见**：
它的扫描面是「**调用 `resolve_single_tenant()` 的脚本**」，而本脚本不调它
（`_DOC_REQUIRED_FLAGS` 那份是**枚举**，已同片登记）。
⇒ 「缺参即拒绝、零写入」这条纪律在本脚本上**只能由本文件守**。

## oracle 一律内容级
断言取 **`platform_audit` 行数 + `tenants` 行的真实内容**，不是「有没有报错」——
本仓的教训：`update_tenant` 对不存在的 id **返 `False`、不抛、零审计**
⇒ 只看异常的判据会把「什么都没做」读成「做成了」。
"""
from __future__ import annotations

import os
import subprocess
import sys

import pytest
from cryptography.fernet import Fernet

_MOD = "knot.scripts.set_tenant_status"


def _env(tmp_path) -> dict:
    """⚠️ `SQLITE_DB_PATH` 才是控制路径的那个变量（**不是** `KNOT_DATA_DIR`）；
    `KNOT_MASTER_KEY` 必须是**合法 Fernet key**（不是任意 44 字符）——
    两条都是 v0.9.19 踩出来的（六问⑥：环境搭错的症状与实验失败一样）。"""
    return {
        "PATH": "/usr/bin:/bin", "HOME": "/tmp", "PYTHONPATH": ".",
        "SQLITE_DB_PATH": str(tmp_path / "knot.db"),
        "KNOT_TEST_TMPDIR": str(tmp_path),
        "JWT_SECRET": "t" * 40, "KNOT_MASTER_KEY": Fernet.generate_key().decode(),
        "KNOT_LOG_FORMAT": "json", "LOG_LEVEL": "WARNING",
    }


def _py(code: str, env: dict) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-c", code], env=env,
                          capture_output=True, text=True, timeout=120, check=False)


def _run(env: dict, *argv: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", _MOD, *argv], env=env,
                          capture_output=True, text=True, timeout=120, check=False)


_SETUP = """
import json, os, sys
from knot.repositories import tenant_repo as t
from knot.config import SQLITE_DB_PATH
_tmp = os.environ["KNOT_TEST_TMPDIR"]
if not str(t._platform_db_path()).startswith(_tmp) or not str(SQLITE_DB_PATH).startswith(_tmp):
    print("NOT-ISOLATED", t._platform_db_path(), SQLITE_DB_PATH); sys.exit(9)
t.init_platform_db(); t.seed_default_tenant()
c = t.get_platform_conn()
c.execute("INSERT INTO tenants (slug,name,db_dir,status) VALUES ('acme','Acme','tenants/x',?)", (STATUS,))
c.commit(); c.close()
print("SETUP-OK")
"""

_SNAPSHOT = """
import json
from knot.repositories import tenant_repo as t
c = t.get_platform_conn()
rows = [dict(r) for r in c.execute("SELECT id,slug,status FROM tenants ORDER BY id")]
n = c.execute("SELECT COUNT(*) FROM platform_audit").fetchone()[0]
print(json.dumps({"tenants": rows, "audit_rows": n}))
"""


def _setup(tmp_path, status: str) -> dict:
    env = _env(tmp_path)
    r = _py(_SETUP.replace("STATUS", repr(status)), env)
    if "NOT-ISOLATED" in r.stdout:
        pytest.fail(f"⛔ 子进程没落在临时目录里，实验作废：{r.stdout.strip()}")
    assert "SETUP-OK" in r.stdout, f"setup 失败：{r.stdout}\n{r.stderr[-800:]}"
    return env


def _snapshot(env: dict) -> dict:
    import json
    r = _py(_SNAPSHOT, env)
    assert r.returncode == 0, r.stderr[-800:]
    return json.loads(r.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize("argv", [
    (),                                   # 两个都缺
    ("--tenant", "acme"),                 # 缺 --status
    ("--status", "suspended"),            # 缺 --tenant
])
def test_missing_required_flag_refuses_and_writes_nothing(tmp_path, argv):
    """⭐ **破坏性工具不得有默认目标**：缺任一必填参数 ⇒ 非 0 退出 + **平台库逐字不变**。

    ⚠️ oracle **不是**「有没有报错」，而是 `tenants` 行内容 + `platform_audit` 行数
    —— v0.9.15 的事故形态正是「命令看起来跑了、动作静默作用在错误对象上」。

    revert-to-bad：给 `--tenant` 或 `--status` 任一加上 `default=...` ⇒ 本测红
    （它会真的去改某个租户，快照随之变化）。
    """
    env = _setup(tmp_path, "active")
    before = _snapshot(env)
    r = _run(env, *argv)
    assert r.returncode != 0, f"缺参竟然成功了：{r.stdout}"
    assert _snapshot(env) == before, "缺参时发生了写入 —— 破坏性工具的零写入承诺被破坏"


def test_unknown_tenant_exits_nonzero_and_writes_nothing(tmp_path):
    """⭐ 目标不存在 ⇒ 非 0 退出 + 零写入。

    ⚠️ **为什么单列**：`update_tenant` 对不存在的 id **返 `False`、不抛、零审计**
    ⇒ 若 CLI 不看返回值，它会打印「已完成」而其实什么都没做
    （v0.9.15「打印了 ✓ 而对象是错的」的近亲）。
    """
    env = _setup(tmp_path, "active")
    before = _snapshot(env)
    r = _run(env, "--tenant", "no-such-tenant", "--status", "suspended")
    assert r.returncode != 0
    assert _snapshot(env) == before


def test_activating_non_owner_is_refused_and_lists_every_blocker(tmp_path):
    """⭐⭐ **激活非起源租户被拒**，且**一次把所有阻塞项报全**。

    两类阻塞必须都出现：
      · **[代偿门]** 三条租户盲能力（`tenant_repo.update_tenant` 里那道门）；
      · **[预检]** 这一家自己的配置缺口（allowlist 未配 / 库没建出来）。
    ⚠️ 一次报全是刻意的：分两轮报会让运维改完一项再撞下一项。

    revert-to-bad：把 CLI 的激活分支改成直接调写口 ⇒ 仍会被门拒（好），
    但**丢掉预检那几条** ⇒ 本测红并点名少了哪类。
    """
    env = _setup(tmp_path, "suspended")
    before = _snapshot(env)
    r = _run(env, "--tenant", "acme", "--status", "active")
    out = r.stdout + r.stderr
    assert r.returncode != 0, "非起源租户竟然被激活了"
    assert "[代偿门]" in out and "[预检]" in out, f"两类阻塞没有都报出来：\n{out}"
    for needle in ("allowlist", "env", "DB 坐标"):
        assert needle in out, f"代偿门那三条里少了 {needle!r}：\n{out}"
    assert _snapshot(env) == before, "被拒时发生了写入"


def test_suspending_writes_and_lands_exactly_one_audit_row(tmp_path):
    """⭐ 停用（= lift 的**回退路径**）真的写入，且**恰好**多一条审计。

    ⚠️ 断言 `audit_rows` 的**增量恰为 1**，不是「>0」——
    「写口被调了两次」与「被调了一次」在 `>0` 下不可区分。
    """
    env = _setup(tmp_path, "active")
    before = _snapshot(env)
    r = _run(env, "--tenant", "acme", "--status", "suspended")
    assert r.returncode == 0, r.stdout + r.stderr
    after = _snapshot(env)
    assert [t["status"] for t in after["tenants"] if t["slug"] == "acme"] == ["suspended"]
    assert after["audit_rows"] == before["audit_rows"] + 1, (
        f"审计增量应恰为 1，实得 {after['audit_rows'] - before['audit_rows']}"
    )


def test_dry_run_writes_nothing_but_names_the_target(tmp_path):
    """⭐ `--dry-run` 零写入，**但必须打印它解析到了谁**。

    ⚠️ 后半句是承重的（CLAUDE.md v3.1-B #1 的但书）：只读预览可以保留，
    但**必须说出目标** —— v0.9.15 事故的核心正是「动作发生了而对象没被说出来」。
    """
    env = _setup(tmp_path, "active")
    before = _snapshot(env)
    r = _run(env, "--tenant", "acme", "--status", "suspended", "--dry-run")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "acme" in r.stdout and "dry-run" in r.stdout.lower()
    assert _snapshot(env) == before, "dry-run 竟然写入了"


def test_noop_is_distinguished_from_a_real_change(tmp_path):
    """⭐ 「本来就是这个状态」**不写、不记审计**，且说得出来。

    ⚠️ 否则审计里会出现 `{"status": {"from": "active", "to": "active"}}`
    ⇒ **分不清「真改了」与「本来就是」**（Stage 2 §5 提出）。
    """
    env = _setup(tmp_path, "active")
    before = _snapshot(env)
    r = _run(env, "--tenant", "acme", "--status", "active")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "本来就是" in r.stdout
    assert _snapshot(env) == before


def test_allowlist_preflight_is_derived_not_hardcoded():
    """⭐ 预检的 allowlist 列名必须**从 `_MUTABLE_TENANT_FIELDS` 派生**。

    ⚠️ 硬编两个名字 ⇒ **第三份 allowlist 落地时预检静默漏检**
    （v0.9.18 `_REDACTED_IN_AUDIT` 原话：「只补第二个名字的话，第三份来时会原样重演，
    且没有任何东西会提醒你」）。

    判据：临时给 `_MUTABLE_TENANT_FIELDS` 加一个 `allowed_*` 列，
    派生函数**必须跟着多一项**（而不是仍返回两项）。
    """
    from knot.repositories import tenant_repo
    from knot.scripts import set_tenant_status as sts

    base = sts._allowlist_columns()
    assert base, "派生出 0 个 allowlist 列 —— 派生失败必须响亮，而不是静默通过"

    orig = tenant_repo._MUTABLE_TENANT_FIELDS
    try:
        tenant_repo._MUTABLE_TENANT_FIELDS = (*orig, "allowed_smtp_hosts")
        assert "allowed_smtp_hosts" in sts._allowlist_columns(), (
            "新增的 allowlist 列没有被预检自动纳入 —— 列名是硬编的"
        )
    finally:
        tenant_repo._MUTABLE_TENANT_FIELDS = orig
