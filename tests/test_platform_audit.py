"""闸门：平台侧审计 `platform_audit`（v0.9.8 · R-T-GATE R7）。

## 本文件最承重的一条是**原子性**
v0.9.8 草案曾把「首启审计写失败该 raise 还是吞」标为唯一影响可用性的决策；
守护者 §II 指出那个两难是**造出来的** —— 把审计 INSERT 与被记录的动作放**同一事务、单次 commit**
之后，「审计写失败」就不再是一个独立事件、与「动作失败」是**同一件事**。

⚠️ **而「拆成两次 commit」这个退化在全量里是看不见的**（守护者点名：功能都还在、测会照绿）
⇒ 判据必须能**表示那个事件**：让审计 INSERT 抛，然后断言**被记录的动作也没留下痕迹**。
   分两次 commit 的话，动作那半已经落盘 ⇒ 本测转红。

## actor 口径（别把 `whoami` 当 actor）
`'system:boot'`（启动期 seed）/ `'cli:<显式传入>'`（P2 的 CLI 强制 `--actor`）/ `None`。
⛔ 容器里 `whoami` = root/app user ⇒ 把「谁」记成 root ⇒ 本表的价值命题当场落空。
"""
from __future__ import annotations

import pytest

from knot.repositories import platform_audit_repo as par
from knot.repositories import tenant_repo


def _audit_rows(**kw) -> list[dict]:
    conn = tenant_repo.get_platform_conn()
    try:
        return par.list_recent(conn, **kw)
    finally:
        conn.close()


# ─── 原子性（must #5 —— 本文件判别力最高的一条）───────────────────────


def test_update_tenant_is_atomic_with_its_audit(tmp_db_path, monkeypatch):
    """⭐⭐ must #5：审计 INSERT 抛 ⇒ **`tenants` 的改动也不留**（同事务、单次 commit）。

    ⚠️ **这条测的存在理由 = 「拆成两次 commit」在全量里不可见**：
    功能都还在、别的测都照绿 ⇒ 那个退化会静默发生。本测的判据**能表示那个事件**。
    取材=revert：在 `update_tenant` 的 `UPDATE` 之后、审计 `insert` 之前插一个 `conn.commit()`
    → 动作那半已落盘 ⇒ 本测红（实测）。

    ⇒ 得到的性质比「审计写失败时 fail-closed」**更强**：
    **不存在「动作发生了但没记」，也不存在「记了但没发生」。**
    """
    before = tenant_repo.get_tenant(1)
    assert before is not None, "前提：fixture 已 seed tenant#1"

    def _boom(*a, **k):
        raise RuntimeError("模拟审计写失败")

    monkeypatch.setattr(par, "insert", _boom)
    with pytest.raises(RuntimeError):
        tenant_repo.update_tenant(1, name="被改过的名字", actor="cli:test")

    after = tenant_repo.get_tenant(1)
    assert after["name"] == before["name"], (
        f"审计写失败了，但 `tenants` 的改动**留下来了**（name: {before['name']!r} → {after['name']!r}）\n\n"
        "⇒ UPDATE 与审计 INSERT **不在同一个事务**里（或中间多了一次 `commit()`）。\n"
        "  那样就退回了「动作发生了但没记」这个失败模式 —— 而它正是本片刻意消掉的那个。\n"
        "  修法：两条语句用**同一个 conn**、中间**不 commit**，函数末尾**单次** `commit()`。"
    )
    assert after["updated_at"] is None or after["updated_at"] == before["updated_at"], (
        "`updated_at` 被 stamp 了但审计没写成 —— 同上，事务被拆开了")


def test_seed_emits_create_audit_in_same_transaction(tmp_db_path):
    """首启 seed ⇒ 恰一条 `platform.tenant_create`，含 slug **快照**与 `actor='system:boot'`。

    slug 冗余是刻意的：审计的价值在**事后**可读，只存 tenant_id 的话租户被删/改名后
    那条记录就退化成一个无意义的数字。
    """
    rows = _audit_rows()
    creates = [r for r in rows if r["action"] == "platform.tenant_create"]
    assert len(creates) == 1, f"seed 应恰产生 1 条 create 审计；实际 {len(creates)}（全部：{rows}）"
    r = creates[0]
    assert (r["tenant_id"], r["tenant_slug"], r["actor"]) == (1, "default", "system:boot"), r
    assert r["source"] == "startup", r


# ─── 变更审计的内容（must #2 / #3）─────────────────────────────────────


def test_update_records_before_and_after(tmp_db_path):
    """must #2：`detail` 记 before→after，且 `tenants.updated_at` 被 stamp。"""
    assert tenant_repo.update_tenant(1, status="suspended", actor="cli:kk", source="cli:test") is True
    r = _audit_rows()[0]
    assert r["action"] == "platform.tenant_update" and r["actor"] == "cli:kk", r
    assert '"from": "active"' in r["detail_json"] and '"to": "suspended"' in r["detail_json"], r
    assert tenant_repo.get_tenant(1)["updated_at"], "updated_at 未被 stamp"


def test_allowlist_change_records_that_it_changed_not_the_content(tmp_db_path):
    """⭐ must #3：`allowed_http_hosts` 的变更**只记「已变更」，不记内容**。

    ⚠️ **判据是内容级**：断言「一个确实写进去的 host 字面**不出现在** `detail_json` 里」
    ⇒ 换个写法继续记（只记第一条 / 记条目数 / 记一部分）同样会红。
    **为什么必须如此**：那份清单是部署方的**内网主机清单**（#262 同族），
    而 `GET /api/platform/audit` **会返回 `detail_json`** ⇒ 记了就等于经端点吐出去。
    取材=revert：把 `detail[k] = "changed"` 改成 `{"from":…, "to": v}` → 本测红。
    """
    secret = "internal-secret-9x.corp.local"
    tenant_repo.update_tenant(1, allowed_http_hosts=secret, actor="cli:kk")
    detail = _audit_rows()[0]["detail_json"]
    assert secret not in detail, (
        f"审计 detail 记下了 allowlist 的**内容**（泄漏 {secret!r}）：{detail}\n"
        "⇒ 那是部署方的内网主机清单，且 `GET /api/platform/audit` 会返回 detail_json。"
    )
    assert "allowed_http_hosts" in detail, f"至少要记「这个字段变过」：{detail}"


# ─── 白名单 fail-closed ───────────────────────────────────────────────


@pytest.mark.parametrize("field", ["id", "slug", "created_at", "wat"])
def test_update_rejects_fields_outside_whitelist(field, tmp_db_path):
    """白名单外字段 ⇒ `ValueError`（**不静默忽略**）。

    静默忽略会让「我改了但没生效」变成一个**无提示**的坑。
    `id` / `slug` / `created_at` 刻意不可改：前两个是身份（`slug` 还是登录链接的一部分），
    第三个是事实 ⇒ 改它们应当走一次显式评审的迁移，而不是通用写口。
    """
    with pytest.raises(ValueError, match="不接受字段"):
        tenant_repo.update_tenant(1, **{field: "x"})


def test_update_missing_tenant_returns_false_without_audit(tmp_db_path):
    """不存在的租户 ⇒ 返 False 且**不留审计**（没发生的事不该有记录）。"""
    n_before = len(_audit_rows(limit=200))
    assert tenant_repo.update_tenant(9999, name="x") is False
    assert len(_audit_rows(limit=200)) == n_before, "对不存在的租户写了审计"


# ─── ctx-free（must #4 —— 平台审计与租户审计的分野）────────────────────


def test_platform_audit_writes_without_any_tenant_ctx(tmp_db_path):
    """⭐ must #4：**无 tenant ctx 时平台审计仍可写**；同一状态下**租户审计写不了**。

    这条对比就是「平台审计为什么必须存在」的机制证据：
    - 租户审计 `audit_service.log` → `audit_repo.insert` → `get_conn` = **租户库**
      ⇒ 无 tenant ctx 时 fail-closed（`get_conn` raise）⇒ **平台动作根本没有落点**
        （这正是 v0.9.5 E2「不引入平台写操作」的理由原文）。
    - 平台审计走 `get_platform_conn()` —— **ctx-free**，正是为启动序/平台面设计的。

    ⚠️ **为什么这条测有判别力**：若哪天有人「顺手统一」把平台审计改走 `get_conn`，
    功能在**请求路径**上照常（那里有 ctx）⇒ 全量照绿，**只有启动期与 CLI 会崩**。
    本测把那个差异钉在**没有 ctx**的状态上。
    取材=injection：把 `tenant_repo.update_tenant` 里的 `get_platform_conn()` 换成
    `repositories.base.get_conn()` → 本测红（无 ctx 时 raise）。
    ⚠️ 注意注入点**不在** `platform_audit_repo` —— 它的连接是**调用方注入**的，
    模块内没有「连接来源」可改。（我第一版 docstring 写错了这个目标，实测时发现。）
    """
    from knot.core.tenant_context import (
        TenantContextError,
        clear_active_tenant,
        reset_active_tenant,
    )

    tok = clear_active_tenant()
    try:
        # ① 平台侧：无 ctx 也能写
        assert tenant_repo.update_tenant(1, name="无 ctx 也能改", actor="cli:test") is True, (
            "无 tenant ctx 时平台元数据写口失败了 —— 它必须 ctx-free"
            "（走 `get_platform_conn`，不是租户库的 `get_conn`）")
        rows = _audit_rows()
        assert rows[0]["action"] == "platform.tenant_update", rows[0]

        # ② 租户侧：同一状态下写不了（这就是平台审计必须存在的原因）
        from knot.services import audit_service
        with pytest.raises(TenantContextError):
            audit_service.log(actor=None, action="auth.login_fail", resource_type="user")
    finally:
        reset_active_tenant(tok)


# ═══════════════════════════════════════════════════════════════════════
#  四条哨兵（D7 · commit 7）
# ═══════════════════════════════════════════════════════════════════════

import ast  # noqa: E402  — 哨兵段专用
import pathlib  # noqa: E402
import typing  # noqa: E402

_KNOT = pathlib.Path(__file__).resolve().parents[1] / "knot"


def _py_files() -> list[pathlib.Path]:
    return sorted(_KNOT.rglob("*.py"))


# ─── 哨兵 1：Literal **精确集合** + 每条 ≥1 emit（must #7 · 守护者 M1）──


def _insert_emit_actions() -> set[str]:
    """AST 扫全仓 `platform_audit_repo.insert(... action="...")` 的 action 字面量。

    ⚠️ 按 **AST 标识符**判定（R-SENTINEL-AST）：同时认 `insert(...)`（裸名）与
    `platform_audit_repo.insert(...)`（属性）两种调用形态 —— 否则换个 import 风格就绕过了。
    """
    out: set[str] = set()
    for path in _py_files():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            name = getattr(fn, "attr", None) or getattr(fn, "id", None)
            if name != "insert":
                continue
            for kw in node.keywords:
                if kw.arg == "action" and isinstance(kw.value, ast.Constant):
                    out.add(kw.value.value)
    return out


def test_platform_audit_literals_exactly_match_emits():
    """⭐ must #7 / 守护者 M1：`platform.*` Literal 与 emit **精确集合相等**（两个方向都封）。

    照 `tests/api/test_metric_invariant_guards.py:77` 的先例形式（`==` 而不是「≥1 emit」）：
    - **`==` 封住「声明了但从不 emit」** —— 死声明（v0.9.5 E4「零消费者 = 死码」同族）；
    - **也封住「emit 了但没声明」** —— 裸字符串绕过 Literal。
    「≥1 emit」只封前者。

    ⇒ **P2 加 `platform.tenant_suspend` / `tenant_delete` 时本测会红** ——
    逼「Literal + emit + 守护」三者**同片**落地。这是刻意的强制，不是麻烦。
    取材=injection：往 Literal 加一个值（不加 emit）→ 红；或写一处 `action="platform.wat"` → 也红。
    """
    from knot.models.platform_audit import PlatformAuditAction

    declared = set(typing.get_args(PlatformAuditAction))
    emitted = {a for a in _insert_emit_actions() if a.startswith("platform.")}
    assert declared == emitted, (
        f"平台审计动作的**声明**与**emit**不一致：\n"
        f"  声明了却从不 emit：{sorted(declared - emitted)}   ← 死声明\n"
        f"  emit 了却没声明：{sorted(emitted - declared)}     ← 裸字符串绕过 Literal\n\n"
        "若你在加新动作（如 P2 的 suspend/delete）：**Literal + emit + 本测的期望**必须同片改 ——\n"
        "那正是本测存在的目的（v0.9.8 D2：只声明有生产者的动作）。"
    )


# ─── 哨兵 2：`detail` 不得含凭据 / env 值（must #8）─────────────────────


_FORBIDDEN_IN_DETAIL = ("auth_value", "password", "token", "secret", "master_key")


def test_detail_call_sites_do_not_pass_credential_identifiers():
    """must #8：`insert(... detail=…)` 的**字面量 dict** 里不得出现凭据类标识符；
    且**调用方模块零 env 读取**。

    ⚠️⚠️ **本哨兵能查什么、不能查什么（诚实收窄 —— v3.1-B 第 11 条）**：
    `detail` 在 `update_tenant` 里是**运行期构造的变量** ⇒ AST **看不进去**
    ⇒ 本测**不能**证明「detail 里绝无敏感值」。它守的是两条**可静态判定**的路径：
    - ① 调用点直接传 dict 字面量、其中出现 `auth_value` / `password` / `token` / … 这类键或名；
    - ② 调用方模块**读进程 env**（那是 env 值进 detail 的必经之路 —— #262 同族）。
    **allowlist 内容那条由行为测覆盖**（`test_allowlist_change_records_that_it_changed_not_the_content`
    用内容级 oracle 断言「一个确实写进去的 host 不出现在 detail_json 里」）。
    ⇒ 静态 + 行为**两条一起**才构成 D7-② 的完整守护；单看任一条都不够。

    取材=injection：在 `update_tenant` 的 detail 里加 `{"token": x}` → ① 红；
    在 `tenant_repo` 里加一行 `os.environ.get("X")` → ② 红。
    """
    callers: set[pathlib.Path] = set()
    bad_literals: list[str] = []

    for path in _py_files():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if (getattr(node.func, "attr", None) or getattr(node.func, "id", None)) != "insert":
                continue
            if not any(kw.arg == "action" for kw in node.keywords):
                continue                     # 不是平台审计的 insert
            callers.add(path)
            for kw in node.keywords:
                if kw.arg != "detail":
                    continue
                for sub in ast.walk(kw.value):
                    tok = None
                    if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                        tok = sub.value.lower()
                    elif isinstance(sub, ast.Name):
                        tok = sub.id.lower()
                    elif isinstance(sub, ast.Attribute):
                        tok = sub.attr.lower()
                    if tok and any(f in tok for f in _FORBIDDEN_IN_DETAIL):
                        bad_literals.append(
                            f"{path.relative_to(_KNOT.parent)}:{sub.lineno} → {tok!r}")

    assert not bad_literals, (
        "平台审计的 `detail` 里出现了凭据类标识符：\n  " + "\n  ".join(bad_literals)
        + "\n\n⚠️ `GET /api/platform/audit` **返回 `detail_json`** ⇒ 写进去就等于经端点吐出去（#262 同族）。"
    )

    env_readers = []
    for path in sorted(callers):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in ("environ", "getenv"):
                env_readers.append(f"{path.relative_to(_KNOT.parent)}:{node.lineno} → os.{node.attr}")
    assert callers, "没找到任何平台审计的调用点 —— 本测在空集上通过（探针没到达）"
    assert not env_readers, (
        "平台审计的**调用方模块**开始读进程 env：\n  " + "\n  ".join(env_readers)
        + "\n\n⇒ 那是 env 值进 `detail` 的必经之路，而该字段会经端点返回（#262 同族）。"
    )


# ─── 哨兵 3 + 4：SQL 写面（must #9 / #9b）─────────────────────────────
#
# ⚠️ **这两条为什么用文本匹配而不是 AST**（R-SENTINEL-AST 要求写明理由）：
#   SQL 是**字符串字面量** —— AST 里看不到「这条语句动的是哪张表」，
#   标识符级判定在原理上答不了这个问题。⇒ 只能扫文本。


def _sql_hits(needle: str) -> list[str]:
    hits = []
    for path in _py_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if needle in line:
                hits.append(f"{path.relative_to(_KNOT.parent)}:{i}")
    return hits


def test_update_tenants_has_exactly_one_write_site():
    """must #9：全仓 `UPDATE tenants` **恰一处**（`tenant_repo.update_tenant` 这个单一写口）。

    ⚠️ **基线是「一处」不是「两处」** —— Stage 1' 我写成两处（把 `seed_default_tenant` 也算了），
    但那里是 **INSERT** 不是 UPDATE。写哨兵前实测得出的真实基线：**1**。
    ⇒ **第二处 `UPDATE tenants` 就意味着有人绕过了 choke point**（那条路径不会 stamp
    `updated_at`、也不会写审计）⇒ 本测红。
    取材=injection：在别处加一句 `conn.execute("UPDATE tenants SET name=?")` → 红并点名 `file:line`。
    """
    hits = _sql_hits("UPDATE tenants")
    assert len(hits) == 1, (
        f"`UPDATE tenants` 出现 {len(hits)} 处（应恰 1）：\n  " + "\n  ".join(hits)
        + "\n\n⇒ 平台元数据的**单一写口**是 `tenant_repo.update_tenant`（它 stamp `updated_at` + 同事务写审计）。\n"
          "  第二处 UPDATE 意味着有变更**绕过了审计与时间线**。"
    )
    assert "tenant_repo.py" in hits[0], f"唯一那处不在 tenant_repo：{hits[0]}"


def test_platform_audit_is_append_only():
    """⭐ must #9b / D7-④（守护者 §III）：全仓**零** `UPDATE platform_audit` / `DELETE FROM platform_audit`。

    **为什么现在就要这条**（守护者的理由，比「卫生」硬）：租户侧审计**已有**
    `knot/scripts/purge_audit_log.py` 这个**合法 DELETE 先例**，而平台审计的清理已登记 backlog
    ⇒ **那个脚本一定会来**。
    - **有本哨兵**：它必须是一次**显式、被评审**的改动；
    - **没有**：审计从「**只可追加的证据**」静默变成「**可编辑的记录**」——
      **而这一步不会有任何人注意到**（没有任何别的测会因此变红）。

    取材=injection：写一个 `conn.execute("DELETE FROM platform_audit WHERE ts < ?")` → 红。
    """
    hits = _sql_hits("UPDATE platform_audit") + _sql_hits("DELETE FROM platform_audit")
    assert not hits, (
        "`platform_audit` 出现了 UPDATE/DELETE：\n  " + "\n  ".join(hits)
        + "\n\n⛔ 平台审计是 **append-only** —— 只可追加的**证据**，不是可编辑的记录。\n"
          "若你在做清理（已登记 backlog）：这必须是一次**显式、被评审**的改动 ——\n"
          "  请在 PATCH 里说明保留期、谁能触发、以及删除动作本身是否要留痕。"
    )
