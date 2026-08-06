"""`reset_admin_password.py` 的强制 `--tenant` 守护（v0.9.15 · **一次真实事故换来的**）。

═══ 事故（Stage 4 守护者 #1 + 执行者的破坏性验证）═══
本脚本此前**完全没有参数解析** ⇒ 按 v0.9.15 开通端点 409 消息的指引执行
`… --tenant <slug>` 时，那个 flag 被**静默吞掉**，脚本照常跑 `resolve_single_tenant()`
⇒ **重置了「唯一 active 租户」（= 起源租户 / 部署方自己）的 admin 口令**，并打印 `✓ 已重置`。
**运维看不出任何异常。**

⭐ **这比「报 unrecognized arguments」糟得多** —— 不是命令失败，
是**动作静默作用在错误的对象上**。而这不是推理：它**真的发生过**（在真实库上）。

⇒ 本文件守三条：
  · 缺 `--tenant` ⇒ **非 0 退出 + 零写入**；
  · 目标不存在 ⇒ 同上（且消息指向 `GET /api/platform/tenants`，不鼓励 `ls data/tenants/` 猜）；
  · ⛔ **严禁把 `--tenant` 改回可选** —— 「可选 + 回退唯一 active」会让同一事故**原样复发**，
    而那个回退形态正是本仓 v0.9.4 记过的坑（登录 `company` 可选 ⇒ lift 后 fail-open）。
    **破坏性工具不得有默认目标。**
"""
from __future__ import annotations

import subprocess
import sys

import pytest

from knot.core import tenant_context as tc
from knot.repositories import base, tenant_repo

_MOD = "knot.scripts.reset_admin_password"


def _admin_hash() -> str | None:
    tok = tc.set_active_tenant(tenant_repo.get_tenant(1))
    try:
        conn = base.get_conn()
        try:
            row = conn.execute("SELECT password_hash FROM users WHERE username='admin'").fetchone()
            return row["password_hash"] if row else None
        finally:
            conn.close()
    finally:
        tc.reset_active_tenant(tok)


def _run(args: list[str], env_extra: dict | None = None):
    """子进程跑脚本 —— 必须是子进程：`argparse` 的必填校验走 `SystemExit`，
    而**退出码本身**就是被守护的性质之一。
    ⚠️ 不经管道读退出码（`cmd | tail` 的 `$?` 是 `tail` 的 —— 本会话踩过三次）。
    """
    import os

    env = dict(os.environ)
    env["SQLITE_DB_PATH"] = str(base.SQLITE_DB_PATH)   # 子进程须用同一个 tmp 数据根
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, "-m", _MOD, *args],
        capture_output=True, text=True, timeout=120, env=env,
        check=False,
    )


def test_missing_tenant_flag_exits_nonzero_with_zero_writes(tmp_db_path):
    """⭐ 缺 `--tenant` ⇒ 非 0 退出，且 admin 哈希**一个字节都没变**。

    ⚠️ 判据**两条都要**（v3.1-B #2「安全属性是什么没发生」）：
    只断「非 0 退出」不够 —— 真正要守的是**零写入**；
    只断「零写入」也不够 —— 静默成功（退出 0）正是事故的形态。
    取材=revert：把 `required=True` 改回可选并回退 `resolve_single_tenant()` ⇒ 本测红。
    """
    tenant_repo.init_platform_db()
    tenant_repo.seed_default_tenant()
    base.init_db()
    before = _admin_hash()
    assert before, "前提：tmp 库里已 seed admin"

    proc = _run([])

    assert proc.returncode != 0, (
        f"缺 `--tenant` 竟然成功退出（rc={proc.returncode}）—— 破坏性工具有了默认目标。\n"
        f"stdout={proc.stdout!r}\nstderr={proc.stderr!r}"
    )
    assert _admin_hash() == before, "缺 `--tenant` 却写了库 —— 那正是事故的形态"
    assert "--tenant" in (proc.stderr + proc.stdout), "拒绝消息没点名缺的是哪个参数"


def test_unknown_tenant_exits_nonzero_with_zero_writes_and_points_at_the_platform_endpoint(tmp_db_path):
    """目标不存在 ⇒ 非 0 + 零写入，且消息给出**可走的**查法。

    ⚠️ 消息里刻意**不**鼓励 `ls data/tenants/`：`db_dir` 是服务端生成的不透明随机串
    （v0.9.15 §1.1），靠目录名认租户会猜错。
    """
    tenant_repo.init_platform_db()
    tenant_repo.seed_default_tenant()
    base.init_db()
    before = _admin_hash()

    proc = _run(["--tenant", "no-such-tenant"])

    assert proc.returncode != 0, f"不存在的租户竟然成功（rc={proc.returncode}）"
    assert _admin_hash() == before, "对不存在的租户写了库"
    assert "/api/platform/tenants" in proc.stderr, (
        f"没给出可走的查法（应指向平台端点）：{proc.stderr!r}"
    )


def test_explicit_tenant_actually_resets_that_tenant(tmp_db_path):
    """⭐ **反向守护**：带上 `--tenant` 时它**真的**改了那个租户的 admin。

    没有这条，把脚本写成「一律拒绝」也能让上面两条通过 = 把功能删掉还绿。
    """
    tenant_repo.init_platform_db()
    tenant_repo.seed_default_tenant()
    base.init_db()
    before = _admin_hash()

    proc = _run(["--tenant", "default"], env_extra={"KNOT_INITIAL_ADMIN_PASSWORD": "TestOnlyPw-123456"})

    assert proc.returncode == 0, f"带 --tenant 却失败了：{proc.stderr!r}"
    assert _admin_hash() != before, "带 --tenant 却没有改动 admin 哈希 —— 功能被删掉了"
    # ⭐ 写之前必须把目标说出来（事故的核心是「动作发生了而对象没被说出来」）
    assert "slug='default'" in proc.stdout and "id=1" in proc.stdout, (
        f"执行前没有打印它将作用于哪个租户：{proc.stdout!r}"
    )


def test_tenant_flag_is_required_not_optional():
    """⛔ 静态钉住「必填」—— 防有人「顺手」改成可选 + 回退默认目标。

    ⚠️ 判据是 AST（不是文本）：要问的是「那个 `add_argument` 调用的 `required` 是不是 True」，
    而文本匹配答不了（`required=True` 可能出现在别的参数上、或在注释里）。
    """
    import ast
    import pathlib

    src = pathlib.Path("knot/scripts/reset_admin_password.py").read_text(encoding="utf-8")
    found = []
    for node in ast.walk(ast.parse(src)):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "add_argument"):
            continue
        names = [a.value for a in node.args if isinstance(a, ast.Constant)]
        if "--tenant" not in names:
            continue
        req = next((kw.value for kw in node.keywords if kw.arg == "required"), None)
        found.append(isinstance(req, ast.Constant) and req.value is True)

    assert found, "找不到 `--tenant` 的 add_argument 调用 —— 参数被删了？"
    assert all(found), (
        "`--tenant` 不再是 `required=True` ——\n"
        "  ⛔ 「可选 + 回退唯一 active 租户」会让 v0.9.15 那次事故**原样复发**\n"
        "     （flag 被吞 ⇒ 静默重置起源租户的 admin 口令，运维看不出异常）。\n"
        "  ⛔ 而那个回退形态本身也是本仓 v0.9.4 记过的坑（登录 `company` 可选 ⇒ lift 后 fail-open）。\n"
        "  **破坏性工具不得有默认目标。**"
    )
