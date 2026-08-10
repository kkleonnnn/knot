"""**2 个 active 租户下进程必须能启动**（v0.9.19 P-b —— lift 的唯一硬阻塞）。

## 缺陷
启动序有 **4 处** `resolve_single_tenant()`，而它在 active ≠ 1 时 **raise**：
prompt seed · TOTP rollout · audit purge · C4 存量迁移（**函数体第一行，最先炸**）。
⇒ lift 之后（或运维激活第二家公司之后）**下一次重启就 CrashLoopBackOff，两家一起挂**。

## 为什么既有测盖不到
- `tests/conftest.py` 设 `KNOT_SKIP_STARTUP_MIGRATION=1` ⇒ 跳过 C4 那条；
- `tests/api/test_two_tenant_e2e_isolation.py` 的 fixture **自己写着**
  「必须在只有 1 个 active 时 import `main`，第二租户在 import 之后才插入」。
⇒ **两者结构上都不可能覆盖「2 active 下启动」这件事** ⇒ 只能起**子进程**。

## ⛔ 本文件的写法警告（一次真实事故的直接产物）
执行者曾用 `KNOT_DATA_DIR=<临时目录>` 造「隔离环境」，而**真正控制路径的是 `SQLITE_DB_PATH`**
⇒ 那些探针**全打在真实开发库上**，制造了一个 active 租户，
**让本地 dev server 从那天起就起不来** —— 而执行者把那次崩溃读成了「实验成功复现」。

⭐ **教训**：**实验结果（BOOT FAILED）与环境错误的症状完全一样**
⇒ **造实验环境时，第一件事是验证「我确实在实验环境里」，而不是直接看实验结果。**
⇒ 故本文件每次跑子进程前，**先断言平台库路径落在临时目录内**（`_assert_isolated`）。
"""
from __future__ import annotations

import json
import subprocess
import sys
import textwrap

import pytest
from cryptography.fernet import Fernet

#: 子进程里先自证隔离，再干活 —— 任何一步不满足就**立刻退出**，绝不落到真实库上。
_PREAMBLE = """
    import json, os, pathlib, sys
    from knot.config import SQLITE_DB_PATH
    from knot.repositories import tenant_repo

    _tmp = os.environ["KNOT_TEST_TMPDIR"]
    _plat = str(tenant_repo._platform_db_path())
    if not (str(SQLITE_DB_PATH).startswith(_tmp) and _plat.startswith(_tmp)):
        print(json.dumps({"fatal": "NOT-ISOLATED", "sqlite": str(SQLITE_DB_PATH), "platform": _plat}))
        sys.exit(9)
"""


def _run(body: str, tmp_path, timeout: int = 120, extra_env: dict | None = None) -> tuple[int, str, str]:
    """在子进程里跑 `_PREAMBLE + body`，`SQLITE_DB_PATH` 指向 tmp_path。"""
    proc = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(_PREAMBLE) + textwrap.dedent(body)],
        capture_output=True, text=True, timeout=timeout, check=False,
        env={
            "PATH": "/usr/bin:/bin", "HOME": "/tmp", "PYTHONPATH": ".",
            "SQLITE_DB_PATH": str(tmp_path / "knot.db"),
            "KNOT_TEST_TMPDIR": str(tmp_path),
            "KNOT_LOG_FORMAT": "json", "LOG_LEVEL": "WARNING",
            # ⚠️ 刻意**不设** KNOT_SKIP_STARTUP_MIGRATION —— C4 那条正是要测的第 4 处
            # ⚠️ **必须是合法 Fernet key**（不是任意 44 字符）——
            #    实施期实证：填 `"k"*44` ⇒ 子进程报「缺少加密主密钥」而退出
            #    ⇒ 两条测都红，而**红的理由与被测缺陷无关** ⇒ 我一度分不清是缺陷还是环境。
            #    这正是「实验结果与环境错误症状相同」的又一实例。
            "JWT_SECRET": "t" * 40, "KNOT_MASTER_KEY": Fernet.generate_key().decode(),
            **(extra_env or {}),
        },
    )
    return proc.returncode, proc.stdout, proc.stderr


def _guard_isolation(rc: int, out: str):
    """把「环境没隔离」与「实验失败」**分开报** —— 它们的症状一样，成因完全不同。"""
    if rc == 9:
        pytest.fail(
            f"⛔ 子进程**没有落在临时目录里** ⇒ 它会写真实库。实验作废，先修环境：\n  {out.strip()}\n"
            "（这正是那次污染真实开发库的形状：实验结果与环境错误的症状一样。）"
        )


def test_boot_succeeds_with_two_active_tenants(tmp_path):
    """⭐ **本片的核心判据**：2 个 active 租户下 `import knot.main` 成功。

    层 = **启动路径（端到端）**（不是单元 —— 那 4 处都在模块级/启动钩子里）。
    revert-to-bad：把启动序任一处改回 `resolve_single_tenant()` ⇒ 本测红，
    stderr 里是 `TenantContextError: 单租户解析器要求恰 1 个 active tenant；实际 2`。
    """
    rc, out, err = _run("""
        tenant_repo.init_platform_db()
        tenant_repo.seed_default_tenant()
        c = tenant_repo.get_platform_conn()
        c.execute("INSERT INTO tenants (slug,name,db_dir,status) VALUES ('t2','T2','tenants/2','active')")
        c.commit(); c.close()
        n = len(tenant_repo.list_active_tenants())
        assert n == 2, f"前提不成立：active={n}"

        import knot.main   # noqa: F401  ← 被测的就是这一行
        print(json.dumps({"ok": True, "active": n}))
    """, tmp_path)
    _guard_isolation(rc, out)
    assert rc == 0, (
        f"2 个 active 租户下启动失败（exit={rc}）——\n"
        f"stderr 尾部：\n{err[-1200:]}\n"
        "⇒ 启动序里仍有 `resolve_single_tenant()`（它在 active≠1 时 raise）。"
    )
    assert json.loads(out.strip().splitlines()[-1])["active"] == 2


def test_boot_still_succeeds_with_one_active_tenant(tmp_path):
    """⭐ **正对照**：1 个 active（今天的现网形态）仍然启动成功。

    ⚠️ 没有这一条的话，一个「把启动序整个删掉」的实现也能让上一条变绿 ——
    那是 fail-closed 式的假通过（本仓 v0.9.7 立的形状）。
    """
    rc, out, err = _run("""
        tenant_repo.init_platform_db()
        tenant_repo.seed_default_tenant()
        import knot.main   # noqa: F401
        print(json.dumps({"ok": True, "active": len(tenant_repo.list_active_tenants())}))
    """, tmp_path)
    _guard_isolation(rc, out)
    assert rc == 0, f"单租户下启动失败（exit={rc}）：\n{err[-1200:]}"
    assert json.loads(out.strip().splitlines()[-1])["active"] == 1


def test_startup_sequence_has_no_single_tenant_resolver(tmp_path):
    """⭐ **哨兵**：`main.py` 与 C4 迁移里不得再出现 `resolve_single_tenant`。

    ⚠️ 它守的不是「代码整齐」，而是**上面那条测的可持续性**：
    上面那条只在**跑得到的那些启动分支**上有判别力；
    将来有人在一个**条件分支**里加回 `resolve_single_tenant()`（例如某个 env 才走的路径），
    子进程测**可能跑不到那一支**而静默放过。⇒ 结构性判据补上这个盲区。

    revert-to-bad：在 `main.py` 任意处加回一次调用 ⇒ 本测红并点名文件与行号。
    """
    import ast
    import pathlib

    hits = []
    for rel in ("knot/main.py", "knot/repositories/tenancy_migration.py"):
        src = pathlib.Path(rel).read_text(encoding="utf-8")
        for n in ast.walk(ast.parse(src)):
            if isinstance(n, ast.Call) and getattr(n.func, "attr", None) == "resolve_single_tenant":
                hits.append(f"{rel}:{n.lineno}")
    assert not hits, (
        f"启动序里仍有 `resolve_single_tenant()`：{hits}\n"
        "⇒ 它在 active≠1 时 raise ⇒ 第二家公司一激活，下次重启整个平台起不来。"
    )


def test_initial_admin_password_env_applies_only_to_owner_tenant(tmp_path):
    """⭐ **D3**：`KNOT_INITIAL_ADMIN_PASSWORD` 只对起源租户生效。

    ⛔ 原写法读**全局** env ⇒ 启动的逐租户 `init_db()` 循环给每个缺库的租户 seed 出
    **同一个已知口令** ⇒ 「A 公司的人能进 B 公司」。
    ⚠️ 这是 seed 口令的**第二个入口** —— 开通端点那条本来就是 per-tenant 随机。

    ⭐ **一条测同时带正反两侧**（缺任一侧都不成立）：
    - 反：非起源租户**不能**用 env 口令登录 ⇒ 抓住「A 能进 B」；
    - 正：起源租户**仍能** ⇒ 抓住「一刀切改随机」会让部署方拿不到自己的初始口令。
    revert-to-bad：去掉 `if _is_owner()` ⇒ 反侧红；让 owner 也随机 ⇒ 正侧红。
    """
    rc, out, err = _run("""
        import bcrypt
        from knot.core import tenant_context as tc
        from knot.repositories import base

        tenant_repo.init_platform_db()
        tenant_repo.seed_default_tenant()
        c = tenant_repo.get_platform_conn()
        c.execute("INSERT INTO tenants (slug,name,db_dir,status) VALUES ('t2','T2','tenants/2','active')")
        c.commit(); c.close()

        got = {}
        for _t in tenant_repo.list_tenants():
            tok = tc.set_active_tenant(_t)
            try:
                base.init_db()
                h = base.get_conn().execute(
                    "SELECT password_hash FROM users WHERE username=?", ("admin",)
                ).fetchone()[0]
                got[str(_t["id"])] = bcrypt.checkpw(b"SHARED-SECRET-123", h.encode())
            finally:
                tc.reset_active_tenant(tok)
        print(json.dumps(got))
    """, tmp_path, extra_env={"KNOT_INITIAL_ADMIN_PASSWORD": "SHARED-SECRET-123"})
    _guard_isolation(rc, out)
    assert rc == 0, f"子进程失败：\n{err[-1200:]}"
    got = json.loads(out.strip().splitlines()[-1])
    assert got.get("1") is True, (
        f"起源租户**不能**用 env 口令登录了（{got}）—— 部署方将拿不到自己的初始口令。"
    )
    assert got.get("2") is False, (
        f"⛔ 非起源租户**也能**用同一个 env 口令登录（{got}）\n"
        "⇒ 「A 公司的人能进 B 公司」—— seed 口令的启动循环入口没堵。"
    )
