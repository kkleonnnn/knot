"""破坏性 CLI 的审计留痕（`BL-v0915-3`）—— **一次真实对账失败换来的**。

v0.9.15 那次 `reset_admin_password` 重置在系统里**查无此事**：审计表里有 5 次 `auth.login_fail`、
有端点侧的 `user.password_reset`，唯独没有脚本那一次 ⇒ 「口令什么时候被谁改的」事后无从对账。
⇒ 「同一件事经端点做有痕、经 CLI 做无痕」这处不对称，就是本文件守的东西。

⚠️ **最要紧的那条不是「有没有审计行」，是「同事务」** —— 见
`test_password_reset_audit_and_update_are_one_transaction` 的 docstring：
只断「有审计行」的话，**旧实现（两个事务 + fail-soft）也会绿**。
"""
from __future__ import annotations

import ast
import inspect
import pathlib
import sqlite3
import typing

import pytest

from knot.core import tenant_context as tc
from knot.models.audit import AuditAction, AuditResourceType
from knot.repositories import audit_repo, base, tenant_repo
from knot.scripts import purge_audit_log, reset_admin_password
from knot.services import cli_audit

_REPO = pathlib.Path(__file__).resolve().parents[2]


def _prepare() -> dict:
    tenant_repo.init_platform_db()
    tenant_repo.seed_default_tenant()
    base.init_db()
    return tenant_repo.get_tenant(1)


def _admin_hash() -> str | None:
    tok = tc.set_active_tenant(tenant_repo.get_tenant(1))
    try:
        conn = base.get_conn()
        try:
            r = conn.execute("SELECT password_hash FROM users WHERE username='admin'").fetchone()
            return r["password_hash"] if r else None
        finally:
            conn.close()
    finally:
        tc.reset_active_tenant(tok)


def _rows(action: str) -> list[dict]:
    tok = tc.set_active_tenant(tenant_repo.get_tenant(1))
    try:
        return audit_repo.list_filtered(action=action, page=1, size=50)
    finally:
        tc.reset_active_tenant(tok)


# ══════════════ ① 同事务（本文件的核心）══════════════

def test_password_reset_audit_and_update_are_one_transaction(tmp_db_path, monkeypatch):
    """⭐⭐ 审计写失败 ⇒ **口令一个字节都没变**（记录与被记录的动作是同一个事件）。

    ⚠️ **oracle 为什么必须是「哈希变没变」而不是「有没有审计行」**（v3.1-B #7 顶班自查）：
    旧实现（`audit_service.log` 自开连接 + R-47 fail-soft 吞异常）在**正常路径上也会**留下审计行
    ⇒ 「有审计行」这个判据**分不清两个实现**。能分清的只有注入失败时的行为：
      · 旧实现：UPDATE 已 commit、审计被吞 ⇒ 哈希**变了**、脚本还打印 ✓（= 事故形态）
      · 现实现：同一事务未 commit ⇒ 哈希**没变**、异常上抛
    取材=注入：把 `audit_repo.insert` 换成抛错 ⇒ 若退回旧实现，本测红。

    ⚠️ 断言**无条件执行**（v3.1-B #2「安全属性是什么没发生」）——
    不把它放进 `pytest.raises`，否则守护被摘掉时会停在 `DID NOT RAISE` 而真属性根本不断。
    """
    _prepare()
    before = _admin_hash()
    assert before, "前提：tmp 库里已 seed admin"

    def _boom(**kw):
        raise RuntimeError("注入：审计写失败")

    monkeypatch.setattr(audit_repo, "insert", _boom)
    try:
        reset_admin_password.main(["--tenant", "1"])
    except Exception:                     # noqa: BLE001 —— 真属性的断言必须无条件跑
        pass

    assert _admin_hash() == before, (
        "审计写失败了，而口令**已经被改**（哈希变了）—— 说明审计与动作不在同一个事务里。\n"
        "    这正是 v0.9.15 那次「重置了但查无此事」的形态：动作生效、记录丢失。\n"
        "    修法不是重试审计，是让两者共用一次 commit（见 services/cli_audit §②）。"
    )


def test_password_reset_writes_audit_with_no_credential(tmp_db_path, monkeypatch):
    """正向：真跑写一条 `user.password_reset`，且 **detail 里搜不到口令**。

    反向守护上一条 —— 没有这条，把审计整个删掉也能让上一条通过（哈希不变 ⇔ 什么都没发生）。

    ⚠️ **用 `monkeypatch.setenv` 而不是手搓 `os.environ[...] = ` + `pop`**：
    本测初版就是后者，实测**污染了整个 session** —— `conftest.py` 用
    `os.environ.setdefault("KNOT_INITIAL_ADMIN_PASSWORD", "admin123")`（模块级，只设一次），
    而 `pop` 把它**永久删掉**了 ⇒ 后续 3 个 owner-gate 测直接 ERROR。
    ⇒ 与 v0.9.15 禁 `monkeypatch.undo()` **同一族**：手搓 save/restore 而没真 restore，只是换了语法。
    """
    _prepare()
    monkeypatch.setenv("KNOT_INITIAL_ADMIN_PASSWORD", "TestOnlyPw-abcdef")
    reset_admin_password.main(["--tenant", "1"])

    rows = [r for r in _rows("user.password_reset") if (r["detail_json"] or {}).get("via") == "cli"]
    assert len(rows) == 1, f"CLI 重置没留下恰好一条审计行：{rows}"
    d = rows[0]["detail_json"]
    assert d["script"] == "reset_admin_password" and d["tenant_id"] == 1 and d["tenant_slug"] == "default"
    assert rows[0]["actor_id"] is None, "CLI 无租户内身份，编一个 actor 比留空更糟"
    assert "TestOnlyPw-abcdef" not in str(rows[0]), f"审计行里出现了口令明文：{rows[0]}"
    assert "$2b$" not in str(rows[0]), f"审计行里出现了 bcrypt 哈希片段：{rows[0]}"


def test_record_password_reset_cannot_receive_a_credential():
    """⭐ 结构级：`record_password_reset` 的签名里**不存在**任何能承载凭据的参数。

    比「detail 里没有口令」强一层 —— 后者是当下的事实，前者让「把口令传进审计」**写不出来**。
    """
    params = set(inspect.signature(cli_audit.record_password_reset).parameters)
    assert params == {"conn", "tenant", "user_id"}, f"签名变了：{params}"
    forbidden = {"password", "pwd", "secret", "hash", "pwd_hash", "password_hash", "detail"}
    assert not (params & forbidden), f"签名里出现可承载凭据的参数：{params & forbidden}"


# ══════════════ ② purge：谁触发的才是判别式 ══════════════

def test_purge_cli_records_even_when_nothing_was_deleted(tmp_db_path):
    """⭐ 人触发的破坏性动作**不论结果**都要可追溯 —— 删 0 行也必须留痕。

    「跑了、什么都没删」与「压根没跑」在事后对账时必须可区分（这正是本片起因的另一形态）。
    取材：把条件退回 `deleted > 0` ⇒ 本测红。
    """
    _prepare()
    stats = purge_audit_log.purge(dry_run=False, trigger="cli")
    assert stats["deleted"] == 0, "前提：新库里没有够老的行（若变了，本测的判别力也变了）"
    rows = [r for r in _rows("audit.purge") if (r["detail_json"] or {}).get("trigger") == "cli"]
    assert len(rows) == 1, f"CLI 真跑删 0 行时没留痕：{rows}"


def test_purge_auto_stays_conditional(tmp_db_path):
    """⭐ 反向：`auto` **保持** `deleted > 0` 条件（每次启动都跑，无条件记会把审计表刷满噪声）。

    没有这条，「无条件记」会被顺手推广到 auto，而那是 v0.9.9 明确判过的反面
    （预期路径刻意不记）。判别式是「**谁触发的**」，不是「删了几行」。
    """
    _prepare()
    purge_audit_log.purge(dry_run=False, trigger="auto")
    rows = [r for r in _rows("audit.purge") if (r["detail_json"] or {}).get("trigger") == "auto"]
    assert rows == [], f"auto 删 0 行却留了痕（噪声）：{rows}"


def test_purge_cli_entrypoint_passes_the_cli_trigger(tmp_db_path):
    """`trigger="cli"` 这个值**文档声明已久却从无生产者** —— 本测钉住它现在有了。

    判据是 AST（不是文本）：要问的是「`_main` 里那次 `purge(...)` 调用的 `trigger` 实参是什么」。
    """
    src = (_REPO / "knot/scripts/purge_audit_log.py").read_text(encoding="utf-8")
    found = []
    for n in ast.walk(ast.parse(src)):
        if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "purge":
            for kw in n.keywords:
                if kw.arg == "trigger" and isinstance(kw.value, ast.Constant):
                    found.append(kw.value.value)
    assert found == ["cli"], f"CLI entrypoint 没传 trigger='cli'（实测 {found}）"


# ══════════════ ③ 迁移 + 收敛点 ══════════════

def test_migration_dry_run_writes_no_audit(tmp_db_path):
    """dry-run 一律不写 —— 规则在 helper 里（三处各写一遍就是三份会漂的判断）。"""
    t = _prepare()
    tok = tc.set_active_tenant(t)
    try:
        cli_audit.record_migration(t, {"rows_scanned": 9}, dry_run=True)
        assert _rows("crypto.migrate_encrypt") == [], "dry-run 竟然写了审计"
        cli_audit.record_migration(t, {"rows_scanned": 9, "rows_updated": 2,
                                       "fields_encrypted": 3, "backup_path": "/data/x.bak"}, dry_run=False)
    finally:
        tc.reset_active_tenant(tok)
    rows = _rows("crypto.migrate_encrypt")
    assert len(rows) == 1, f"真跑没写审计：{rows}"
    d = rows[0]["detail_json"]
    assert d["rows_scanned"] == 9 and d["fields_encrypted"] == 3
    assert "backup_path" not in d, (
        f"`backup_path` 进了审计 detail —— 它由 `SQLITE_DB_PATH` 派生 = **env 派生值**，"
        f"进审计即 #262 家族（v0.9.7 那条 egress 消息就是这么泄出内网主机清单的）：{d}"
    )


def test_new_literal_and_resource_type_have_an_emit():
    """新 Literal / resource_type 必须有生产者（v3.1-B #6），与 metric/bi 两处 per-prefix 守护同形。"""
    assert "crypto.migrate_encrypt" in typing.get_args(AuditAction)
    assert "crypto" in typing.get_args(AuditResourceType)
    src = (_REPO / "knot/services/cli_audit.py").read_text(encoding="utf-8")
    assert '"crypto.migrate_encrypt"' in src and '"crypto"' in src, (
        "新 Literal 无 emit —— 声明了没人产就是死码（v3.1-B #6）"
    )


_LOW_LEVEL_AUDIT = ("knot.repositories.audit_repo.insert", "knot.services.audit_service.log")


def _direct_audit_calls(path: pathlib.Path) -> dict[str, int]:
    """{限定名: 行号} —— 该文件里**真的调用**了哪个底层审计写口（AST，按 import 解析限定名）。

    ⭐ **两个测共用这一次测量**（正向找违规 / 反向找过期豁免）——
    ⚠️ 反向那条初版用的是**裸子串** `q.rsplit(".")[-1] in text`（即拿 `log` 去搜文本），
    实测**假通过**：它命中的是本仓某个文件里**讨论** `audit_service.log` 的一行注释。
    ⇒ R-SENTINEL-AST 的根因原话：**讨论一个名字的文件必然含有那个名字**
    ⇒ 「这个调用是否存在」这个问题，文本匹配在原理上答不了。
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    mods: dict[str, str] = {}
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and n.module:
            for a in n.names:
                mods[a.asname or a.name] = f"{n.module}.{a.name}"
    out: dict[str, int] = {}
    for n in ast.walk(tree):
        if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)):
            continue
        b = getattr(n.func.value, "id", None)
        if b is None:
            continue
        q = f"{mods.get(b, b)}.{n.func.attr}"
        if q in _LOW_LEVEL_AUDIT:
            out.setdefault(q, n.lineno)
    return out


#: **允许**绕过 `cli_audit` 直连底层审计写口的站点 → 理由（表态清单，非豁免清单）。
#: ⚠️ 这一条是本 chore 里我自己的哨兵**先判错、再收窄**得来的，理由值得留全：
_DIRECT_AUDIT_OK = {
    ("purge_audit_log.py", "knot.services.audit_service.log"):
        "⭐ `purge()` **不是 CLI 专属写者** —— 服务端启动期 auto-purge（`main.py` import 的正是"
        "这个函数）走同一条路。若改走 `cli_audit`（它刻意**抛**异常），一次审计写失败就会"
        "**崩掉 boot** —— 而 R-47 fail-soft 在服务端路径上正是对的。"
        "两条路由 `trigger` 字段区分（auto / manual / cli），无需第二个写口。"
        "⇒ `cli_audit` 的适用面是「**只有 CLI 会走**的写者」。",
}


def test_destructive_clis_go_through_the_single_audit_choke_point():
    """⭐ 破坏性 CLI **不得**自己直连 `audit_repo.insert` / `audit_service.log`（除表态清单）。

    ⚠️ 判据 AST 按限定名（R-SENTINEL-AST）—— 文本匹配在这里必自匹配：
    本文件与 `cli_audit` 都在**讨论**这两个名字。
    收敛点只有一处，才谈得上「actor 恒 None / detail 白名单 / dry-run 不写」是**一份**判断而非三份。

    ⚠️⚠️ **本测初版把 `purge_audit_log` 也判成违规 —— 那是哨兵错了，不是代码错了**：
    `purge()` 被 CLI 与服务端 auto-purge 共用 ⇒ 它必须保持 fail-soft。
    ⇒ 一般化：**「唯一写口」这类规则的作用面是「只有该形态会走的写者」**；
    一个被服务端共用的函数不属于它，强行统一会把 CLI 的「宁可不做也要留痕」
    错误地施加到「审计失败不得阻断业务」的路径上 —— 两条**互斥**的正确策略。
    """
    offenders = []
    for name in ("reset_admin_password.py", "migrate_encrypt_v045.py", "purge_audit_log.py"):
        for q, lineno in _direct_audit_calls(_REPO / "knot/scripts" / name).items():
            if (name, q) not in _DIRECT_AUDIT_OK:
                offenders.append(f"{name}:{lineno} 直连 {q}")
    assert not offenders, (
        "破坏性 CLI 绕过了唯一审计写口 `services.cli_audit`：\n  " + "\n  ".join(offenders)
        + "\n⇒ 绕过它就绕过了「actor 恒 None」「detail 白名单（⛔ backup_path）」「dry-run 不写」"
          "\n   这三条判断 —— 而它们只有在一处才是**一份**判断。"
          "\n⇒ 若该站点**确实**被服务端共用（fail-soft 是对的），把理由写进 `_DIRECT_AUDIT_OK`。"
    )


def test_the_direct_audit_exemptions_are_not_stale():
    """⚠️ 反向：表态清单里不得留**已经不成立**的条目（否则清单会祝福一个不存在的站点）。

    与 v0.9.15 `_IMPLICIT_FALLBACK_OK` 的反向条同形 —— 那次的教训是清单本身也会过期。
    """
    for (name, q) in _DIRECT_AUDIT_OK:
        p = _REPO / "knot/scripts" / name
        assert p.exists(), f"表态清单里的 {name} 已不存在 —— 清单过期"
        calls = _direct_audit_calls(p)
        assert q in calls, (
            f"{name} 已不再调用 {q}（AST 实测），却仍在表态清单里 —— 请删掉该条目。\n"
            f"    该文件真正调用的底层写口：{calls or '（无）'}"
        )


def test_audit_repo_insert_without_conn_is_unchanged(tmp_db_path):
    """⚠️ 加 `conn=` 参数**不得**改变原路径：不传时仍自开连接、自 commit、自 close。

    唯一生产调用方 `audit_service.log` 走的正是这条 ⇒ 它必须 byte-equal。
    判据 = 不传 conn 时数据**真的落盘**（另开只读连接读得到），而非「函数没抛错」。
    """
    _prepare()
    tok = tc.set_active_tenant(tenant_repo.get_tenant(1))
    try:
        aid = audit_repo.insert(actor_id=None, actor_role=None, actor_name=None,
                                action="user.create", resource_type="user")
        assert aid
        c = sqlite3.connect(f"file:{base._tenant_db_path()}?mode=ro", uri=True)
        try:
            n = c.execute("SELECT COUNT(*) FROM audit_log WHERE id=?", (aid,)).fetchone()[0]
        finally:
            c.close()
        assert n == 1, "不传 conn 时没有自行 commit —— 原路径被改坏了"
    finally:
        tc.reset_active_tenant(tok)


@pytest.mark.parametrize("fn", ["record_password_reset", "record_migration"])
def test_helper_never_swallows_audit_failures(fn, tmp_db_path, monkeypatch):
    """⛔ helper **不得**吞审计写失败（那正是 `audit_service.log` 的 R-47 fail-soft 干的事）。

    CLI 的正确行为与请求路径相反：**宁可动作做不了，也不要做了查不到。**
    """
    t = _prepare()

    def _boom(**kw):
        raise RuntimeError("注入")

    monkeypatch.setattr(audit_repo, "insert", _boom)
    tok = tc.set_active_tenant(t)
    raised = None
    try:
        if fn == "record_password_reset":
            conn = base.get_conn()
            try:
                cli_audit.record_password_reset(conn, tenant=t, user_id=1)
            finally:
                conn.close()
        else:
            cli_audit.record_migration(t, {"rows_scanned": 1}, dry_run=False)
    except Exception as e:                # noqa: BLE001
        raised = e
    finally:
        tc.reset_active_tenant(tok)
    assert raised is not None, f"{fn} 把审计写失败吞掉了 —— 调用方会以为记上了"
