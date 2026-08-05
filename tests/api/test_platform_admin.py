"""闸门：平台面平行认证路径（v0.9.5 D2'/D3'）—— 密钥闸 / 语法不相交 / 互斥信任域 / fail-closed。

对应 Stage 1' 验收 3 / 4 / 4b / 4c / 5 / 6 / 7c / 9 / 11 + D3' 响应契约。
"""
from __future__ import annotations

import ast
import pathlib

import pytest

from knot.api import platform_admin as pa

_ENV = pa.PLATFORM_TOKEN_ENV
_GOOD = "kpa_" + "b" * 40          # 合规：前缀 ✓ 无 `.` ✓ 长度 44 ≥ 32 ✓
_URL = "/api/platform/tenants"


def _hdr(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}"}


class _Rec:
    """替身 logger —— 只记录，供断言 WARN 的**有无**与**内容**。"""

    def __init__(self):
        self.calls = []

    def warning(self, msg, *args):
        self.calls.append((msg, args))


# ─── 验收 3 / 4b：密钥闸（未配 & 不合规 → 503；未配**不** WARN）────────────


def test_unset_returns_503_and_emits_no_warning(client, monkeypatch):
    """验收 3 + must-fix #1②：未配置 → **503**，且**不** WARN（未配 = 有意禁用）。

    「未配不 WARN」承重：否则每个没启用平台面的部署每次启动都喊一句
    ⇒ 运维被训练成忽略这条 WARN ⇒ 真正的「设了但弱」也被一起忽略。
    """
    monkeypatch.delenv(_ENV, raising=False)
    assert client.get(_URL, headers=_hdr("whatever")).status_code == 503

    rec = _Rec()
    monkeypatch.setattr(pa, "logger", rec)
    pa.warn_if_noncompliant()
    assert rec.calls == [], f"未配置时不应 WARN，实际：{rec.calls}"


@pytest.mark.parametrize("bad,why", [
    ("b" * 40, "缺前缀"),
    ("kpa_" + "b" * 20 + "." + "c" * 20, "含 `.`（与 JWT 语法域重叠）"),
    ("kpa_short", "长度 < 32"),
    ("eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.sig", "整枚 JWT 形态（缺前缀 + 含 `.`）"),
])
def test_noncompliant_secret_returns_503_and_warns(client, monkeypatch, bad, why):
    """⭐ 验收 4b：不合规密钥 → **503** + 启动期 WARN（**只**对「设了但不合规」）。

    四形态含**整枚 JWT** —— 这是 R1 要封的自我破坏路径：运维把一枚有效用户 JWT 配成平台密钥。
    JWS compact **恒含 2 个 `.`** ⇒ 禁 `.` 使合规平台密钥**在语法上不可能是 JWT**（结构不变量）。
    """
    monkeypatch.setenv(_ENV, bad)
    assert client.get(_URL, headers=_hdr(bad)).status_code == 503, f"{why} 应 503"

    rec = _Rec()
    monkeypatch.setattr(pa, "logger", rec)
    pa.warn_if_noncompliant()
    assert len(rec.calls) == 1, f"{why} 应恰好 WARN 一次，实际：{rec.calls}"


def test_warning_and_503_never_echo_the_secret_value(client, monkeypatch):
    """⭐⭐ must-fix #1③：WARN 与 503 **都不得回显密钥值** —— #262 是本仓自己的事故。

    `7491090` 修的正是 `f"{auth_value_env}={header_value!r}"` 把 env 明文插进异常
    ⇒ admin 可读出 `JWT_SECRET` / `KNOT_MASTER_KEY`。修法原文「只报 env 名，绝不报 env 值」。
    ⭐ 另断言 **503 的 detail 连「不合规原因」也不给** —— 未认证调用方若能读到「长度 < 32」，
    等于被告知本部署配了弱密钥、且能推出期望格式。原因只进服务端日志（执行者决定，理由在模块 docstring）。
    """
    secret = "kpa_SUPERSECRETVALUE_deadbeef_" + "z" * 12
    monkeypatch.setenv(_ENV, secret + ".")     # 加个点使其不合规（触发 WARN 路径）
    rec = _Rec()
    monkeypatch.setattr(pa, "logger", rec)
    pa.warn_if_noncompliant()
    blob = "".join(str(c) for c in rec.calls)
    assert secret not in blob and "SUPERSECRETVALUE" not in blob, f"WARN 回显了密钥：{blob}"
    assert _ENV in blob, "WARN 必须点名 env 名（否则运维不知道该改哪个变量）"

    r = client.get(_URL, headers=_hdr("x"))
    assert r.status_code == 503
    body = r.text
    assert "SUPERSECRETVALUE" not in body
    for leak in ("长度", "前缀", "kpa_", "."):
        if leak == ".":
            continue                          # JSON 里必然有 `.`，跳过这个无意义的子串
        assert leak not in body, f"503 detail 泄露了期望格式/原因：{leak!r} in {body!r}"


def test_single_predicate_is_shared_by_warn_and_request_path(monkeypatch):
    """⭐ 验收 4c / must-fix #1①：启动 WARN 与请求期 503 **共用同一个 predicate**。

    结构断言（AST）：`warn_if_noncompliant` 与 `require_platform_secret` **都**调用
    `rejection_reason`，且模块内**只有这一个**判定函数。
    一个值两处读、两处规则 = 刚在前置 chore 治过的「N 份清单」病 —— 那次的教训是
    「安全性只能来自结构不变量」，故这里也用结构断言而非行为对比。
    """
    src = pathlib.Path(pa.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    callers = {}
    for fn in tree.body:
        if isinstance(fn, ast.FunctionDef):
            callers[fn.name] = {
                n.func.id for n in ast.walk(fn)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
            }
    for who in ("warn_if_noncompliant", "require_platform_secret"):
        assert "rejection_reason" in callers.get(who, set()), (
            f"`{who}` 未调用共用谓词 `rejection_reason` —— 两处各自判定会漂移")
    # 谓词唯一：模块内不得出现第二个「像判定」的函数名
    assert not [n for n in callers if n.endswith("_reason") and n != "rejection_reason"], (
        f"出现了第二个判定函数：{sorted(callers)}")


# ─── 验收 4 / 5：比对与解析 ────────────────────────────────────────────────


def test_wrong_token_returns_401(client, monkeypatch):
    """验收 4：配置合规但凭证不匹配 → **401**（与 503「未启用」区分开）。"""
    monkeypatch.setenv(_ENV, _GOOD)
    assert client.get(_URL, headers=_hdr("kpa_" + "wrong" * 8)).status_code == 401
    assert client.get(_URL).status_code == 401                      # 完全无 header
    assert client.get(_URL, headers={"Authorization": f"Basic {_GOOD}"}).status_code == 401


@pytest.mark.parametrize("header", [
    f"Bearer {_GOOD}",
    f"bearer {_GOOD}",            # RFC：scheme 大小写不敏感
    f"Bearer  {_GOOD}",           # 双空格
    f"Bearer {_GOOD}\t",          # 尾 tab
    f"BEARER {_GOOD}",
    f"Bearer {_GOOD}x",           # 值不匹配
    "Bearer ",
])
def test_rfc_variants_expectation_derived_from_parser(client, monkeypatch, header):
    """⭐ 验收 5：期望值**从 `get_authorization_scheme_param` 同源算出**，**不手抄 200/401 表**。

    ⚠️ 手抄期望表会让本测在上游改语义时变成「**在测标准库的旧行为**」——
    本仓已栽过一次（v0.9.4 `test_R16` 初版**没调生产函数**、自己算答案，revert 后仍绿 = tautology）。
    ⇒ 这里只断言「**生产行为 == 参考解析器推出的行为**」，不写死状态码。
    实测（F19）：参考实现是 `partition(" ")` + `param.strip()` ⇒ 双空格/尾 tab/小写 scheme
    在**合规**实现下都应 **200**；若有人换回手搓 `auth[7:]`，双空格那格会变 401 → 本测红。
    """
    from fastapi.security.utils import get_authorization_scheme_param

    monkeypatch.setenv(_ENV, _GOOD)
    scheme, param = get_authorization_scheme_param(header)
    expected = 200 if (scheme.lower() == "bearer" and param == _GOOD) else 401
    got = client.get(_URL, headers={"Authorization": header}).status_code
    assert got == expected, (
        f"header={header!r}：参考解析器给出 scheme={scheme!r} param={param!r} ⇒ 应 {expected}，实际 {got}。"
        "\n若这里失败且你刚改了解析方式 —— 大概率是换回了手搓 `auth[7:]`（R-v095-3 禁）。"
    )


# ─── 验收 6：不设 tenant ctx、不触租户库 ──────────────────────────────────


def test_platform_request_never_touches_tenant_db_or_sets_ctx(client, monkeypatch):
    """⭐ 验收 6 / R-v095-1：平台请求**不触 `base.get_conn`**、**不设 tenant ctx**。

    平台请求不属于任何租户；碰租户库就是把「先假装在某个租户里」这个 fail-open 形状请回来。
    取材=注入：让 `base.get_conn` 一被调用就炸 —— 若 handler 或其下游碰了它，本测红。
    """
    from knot.repositories import base as base_mod

    def _boom():
        raise AssertionError("平台路径调用了 base.get_conn() —— 违反 R-v095-1")

    monkeypatch.setenv(_ENV, _GOOD)
    monkeypatch.setattr(base_mod, "get_conn", _boom)
    r = client.get(_URL, headers=_hdr(_GOOD))
    assert r.status_code == 200, r.text


# ─── 验收 7c：双凭证矩阵（互斥信任域的行为证明）────────────────────────────


def test_dual_credential_matrix(client, monkeypatch, admin_token):
    """⭐ 验收 7c：租户 JWT 只能进租户路由 / 平台密钥只能进平台路由（4 格全钉）。

    这是 D5' 那条「互斥信任域」的**行为**证明（分类器那条是**结构**证明）。
    """
    monkeypatch.setenv(_ENV, _GOOD)
    tenant_url = "/api/admin/users"

    grid = {
        ("tenant_jwt", "tenant_route"): client.get(tenant_url, headers=_hdr(admin_token)).status_code,
        ("tenant_jwt", "platform_route"): client.get(_URL, headers=_hdr(admin_token)).status_code,
        ("platform_key", "platform_route"): client.get(_URL, headers=_hdr(_GOOD)).status_code,
        ("platform_key", "tenant_route"): client.get(tenant_url, headers=_hdr(_GOOD)).status_code,
    }
    assert grid[("tenant_jwt", "tenant_route")] == 200, grid
    assert grid[("platform_key", "platform_route")] == 200, grid
    assert grid[("tenant_jwt", "platform_route")] == 401, (
        f"租户 admin 的 JWT 竟能进平台端点：{grid}")
    assert grid[("platform_key", "tenant_route")] == 401, (
        f"平台密钥竟能进租户端点：{grid}")


# ─── 验收 9：中间件对 opaque 密钥不 5xx（F15 钉住）─────────────────────────


@pytest.mark.parametrize("tok", [
    "kpa_" + "a" * 40,          # 合规平台密钥
    "aaa.bbb.ccc",              # 含点、像 JWT
    "a" * 40,
    "",
])
def test_middleware_does_not_5xx_on_opaque_bearer(client, monkeypatch, tok):
    """⭐ 验收 9：tenant middleware **恒先于** Depends，会拿平台密钥去 `jwt.decode`。

    F15 已实测 6 形态干净返 `None`；本测把它**钉成回归**（防将来解析改动引入 5xx，
    那会让平台面在中间件层就崩，而 D2' 刻意**不加**路径白名单 —— 白名单是 v0.9.4 避开的漂移源）。
    ⚠️ **非 ASCII 不在本测覆盖**：HTTP header 按规范是 ASCII，httpx 在**客户端**就
    `UnicodeEncodeError`（实测）⇒ 那条路径**走 HTTP 根本到不了**。真正可达的是
    **非 ASCII 的 env 值** —— 由 `test_non_ascii_configured_secret_does_not_500` 覆盖。
    """
    monkeypatch.setenv(_ENV, _GOOD)
    r = client.get(_URL, headers=_hdr(tok))
    assert r.status_code < 500, f"token={tok[:20]!r} 触发 {r.status_code}：{r.text[:200]}"


def test_non_ascii_configured_secret_does_not_500(monkeypatch):
    """⭐ `secrets.compare_digest` 对**含非 ASCII 的 str** 会抛 `TypeError` ⇒ 生产必须 encode 成 bytes。

    **可达路径不是 header 而是 env**：HTTP header 按规范 ASCII（httpx 在客户端就
    `UnicodeEncodeError`，实测），但 **env 值可以是非 ASCII** ——
    运维粘一个带中文/emoji 的密钥完全可能。若生产用 `compare_digest(str, str)`，
    那一刻是 **500**（未处理异常）而不是 401。
    取材=revert：把生产的 `.encode(...)` 去掉 → 本测转 `TypeError`（红）。
    ⚠️ 在**依赖层**直接调（不经 HTTP）—— 因为经 HTTP 到不了（见上）。
    """
    monkeypatch.setenv(_ENV, "kpa_中文密钥" + "z" * 30)

    class _Req:
        headers = {"authorization": "Bearer kpa_" + "z" * 40}

    with pytest.raises(Exception) as ei:      # noqa: B017 — 就是要看它是哪一种
        pa.require_platform_secret(_Req())
    from fastapi import HTTPException
    assert isinstance(ei.value, HTTPException) and ei.value.status_code == 401, (
        f"应是 401（凭证不匹配），实际 {type(ei.value).__name__}: {ei.value} —— "
        "若是 TypeError 说明生产在用 compare_digest(str, str)，非 ASCII env 值会 500")


# ─── 验收 11：第二 active 租户 → 平台端点同样 fail-closed ──────────────────


def test_platform_endpoint_is_not_an_escape_hatch_under_second_tenant(tmp_db_path, monkeypatch):
    """⭐⭐ 验收 11：出现第二个 active 租户时，**平台端点同样 fail-closed**。

    `assert_no_second_active_tenant_served()` 是 `resolve_for_request` 的**第一行**
    （在 Bearer 解析与路径判断**之前**）⇒ 整站含平台面全 raise。
    ⇒ **别把这个端点当运维逃生舱** —— 它恰在多租户出问题时不可用。
    本测存在的意义就是把这个反直觉的事实钉住，免得后人在故障预案里依赖它。
    照仓内既有口径（`test_tenant_resolution.py::test_gate_runs_before_tid_resolution`）
    在 `resolve_for_request` 层断言，而非走 HTTP（HTTP 层会是 500，信息量更低）。
    """
    from knot.api import tenant_resolution as tr
    from knot.core.tenant_context import TenantContextError
    from knot.repositories import tenant_repo

    conn = tenant_repo.get_platform_conn()
    conn.execute("INSERT INTO tenants (id,slug,name,status,db_dir) "
                 "VALUES (2,'t2','T2','active','tenants/2')")
    conn.commit()
    conn.close()
    monkeypatch.setenv(_ENV, _GOOD)

    class _Req:
        def __init__(self, path, hdr):
            self.headers = {"authorization": hdr} if hdr else {}
            self.url = type("U", (), {"path": path})()

    with pytest.raises(TenantContextError, match="R-T-GATE"):
        tr.resolve_for_request(_Req(_URL, f"Bearer {_GOOD}"))


# ─── D3' 响应契约：显式投影两道 ────────────────────────────────────────────


def test_response_shape_and_no_store(client, monkeypatch):
    """D3'：`Cache-Control: no-store` + 响应字段恰为 `TenantPublic` 的六个。"""
    monkeypatch.setenv(_ENV, _GOOD)
    r = client.get(_URL, headers=_hdr(_GOOD))
    assert r.status_code == 200, r.text
    assert r.headers.get("cache-control") == "no-store"
    rows = r.json()
    assert rows and set(rows[0]) == {"id", "slug", "name", "status", "db_dir", "created_at"}


def test_new_platform_column_does_not_leak_through(client, monkeypatch):
    """⭐ D3' / Stage 3 R8 前半：新增平台列**不得**自动流进响应（两道投影各自都能挡）。

    **为什么这不是假设风险**：B-3 已排期给平台层加 per-tenant `http_spec` 凭据 +
    per-tenant 初始口令 ⇒ 届时 `SELECT *` + dict 直转会**自动**把它们吐出去。
    取材=注入：给 `tenants` 加一列并写入敏感值 → 断言响应里没有它。
    revert-to-bad：把路由改回 `tenant_repo.list_tenants()`（`SELECT *`）**且**去掉
    `response_model` → 本测红（两道都在时，去掉任一道仍绿 —— 这是刻意的纵深）。
    """
    from knot.repositories import tenant_repo

    conn = tenant_repo.get_platform_conn()
    conn.execute("ALTER TABLE tenants ADD COLUMN initial_admin_password TEXT")
    conn.execute("UPDATE tenants SET initial_admin_password='S3CRET-INITIAL-PW'")
    conn.commit()
    conn.close()

    monkeypatch.setenv(_ENV, _GOOD)
    r = client.get(_URL, headers=_hdr(_GOOD))
    assert r.status_code == 200, r.text
    assert "S3CRET-INITIAL-PW" not in r.text, "新增平台列泄漏进响应"
    assert "initial_admin_password" not in r.text


# ─── v0.9.8：`GET /api/platform/audit`（must #6）────────────────────────

_AUDIT_URL = "/api/platform/audit"


def test_audit_endpoint_shares_the_same_secret_gate(client, monkeypatch):
    """must #6 前半：新端点与 `/tenants` **共用同一道密钥闸** —— 未配 503 / 错密钥 401 / 对 200。

    ⚠️ 为什么要单独测而不是「反正用了同一个 Depends」：`require_platform_secret` 是**依赖工厂之外**
    的普通依赖，漏挂它**不会有任何编译期信号** —— 而路由策略快照虽然会红，但那是
    **依赖层**的快照（chore 的硬注记：**快照绿 ≠ 授权完好**，函数体内授权它看不见）。
    ⇒ 端点层再钉一次。
    """
    monkeypatch.delenv(_ENV, raising=False)
    assert client.get(_AUDIT_URL, headers=_hdr("whatever")).status_code == 503

    monkeypatch.setenv(_ENV, _GOOD)
    assert client.get(_AUDIT_URL, headers=_hdr("kpa_" + "z" * 40)).status_code == 401
    r = client.get(_AUDIT_URL, headers=_hdr(_GOOD))
    assert r.status_code == 200, r.text


def test_audit_endpoint_returns_explicit_columns_including_detail(client, monkeypatch):
    """must #6 后半 + **M3 裁定**：响应恰为显式列集，且**含 `detail_json`**。

    ⭐ **`detail_json` 在投影里是一个有连带后果的裁定**：不返回它，事故现场读不到
    「`db_dir` 从什么改成了什么」⇒ 端点退化成 v0.9.5 E4 警告过的**死载荷**。
    ⇒ **连带后果**：`tests/test_platform_audit.py` 那条「凭据/allowlist 内容不得进 `detail`」的哨兵
    **由此成为本端点的承重守护**。⛔ 放松那条哨兵的人必须知道本端点也随之破防。

    取材=revert：把 `PlatformAuditEntry` 的 `detail_json` 删掉 → 本测红（键缺席）。
    """
    monkeypatch.setenv(_ENV, _GOOD)
    rows = client.get(_AUDIT_URL, headers=_hdr(_GOOD)).json()
    assert rows, "fixture 已 seed tenant#1 ⇒ 至少应有一条 platform.tenant_create"
    assert set(rows[0]) == {
        "id", "ts", "actor", "action", "tenant_id", "tenant_slug", "success", "detail_json", "source",
    }, f"响应列集漂移：{sorted(rows[0])}"
    assert rows[0]["action"] == "platform.tenant_create", rows[0]


def test_audit_endpoint_pagination_is_bounded_and_cursor_works(client, monkeypatch):
    """must #6 续：`limit` **有界**（超上限即 cap，不报错）+ `before_id` 游标生效。

    分页参数不该让运维卡住 ⇒ 超界 **cap 而非 422**；但**无界返回**是不可接受的
    （审计表会长，一次全量返回等于自制 DoS）。
    """
    from knot.repositories import platform_audit_repo, tenant_repo

    monkeypatch.setenv(_ENV, _GOOD)
    for i in range(4):
        tenant_repo.update_tenant(1, name=f"n{i}", actor="cli:test")

    # ⚠️ **判据必须是「传下去的 limit」，不能是「返回的行数」**（实施期取材证伪了第一版）：
    #   库里只有几条审计行 ⇒ `limit=999` 不 cap 时返回的仍是那几条、仍 ≤200 ⇒ 行数断言**照过**。
    #   ⇒ 「limit 无界」这个事件**在行数这个 oracle 里表示不出来**（v3.1-B 枚举表第 2 条）。
    #   ⇒ 改为拦截 repo 调用、断言**实际生效的 limit**。
    seen: list[int] = []
    _orig = platform_audit_repo.list_recent

    def _spy(conn, *, limit, before_id=None):
        seen.append(limit)
        return _orig(conn, limit=limit, before_id=before_id)

    monkeypatch.setattr(platform_audit_repo, "list_recent", _spy)
    all_rows = client.get(f"{_AUDIT_URL}?limit=999", headers=_hdr(_GOOD)).json()
    assert seen and seen[-1] <= pa._MAX_AUDIT_LIMIT, (
        f"limit=999 未被 cap —— 实际传给 repo 的是 {seen}（上限 {pa._MAX_AUDIT_LIMIT}）\n"
        "⇒ 无界返回：审计表会长，一次全量返回等于自制 DoS。"
    )
    monkeypatch.setattr(platform_audit_repo, "list_recent", _orig)
    all_rows = client.get(f"{_AUDIT_URL}?limit=999", headers=_hdr(_GOOD)).json()
    assert len(all_rows) > 1, "前提：至少有多条审计行，否则下面的排序/游标断言无判别力"
    assert [r["id"] for r in all_rows] == sorted((r["id"] for r in all_rows), reverse=True), "应按 id 倒序"

    cursor = all_rows[1]["id"]
    page = client.get(f"{_AUDIT_URL}?before_id={cursor}", headers=_hdr(_GOOD)).json()
    assert page and all(r["id"] < cursor for r in page), f"游标失效：{[r['id'] for r in page]}"


# ─── v0.9.15 d1：`POST /api/platform/tenants`（平台面第一个写端点）────────────

_BODY = {"slug": "acme", "name": "Acme Inc", "allowed_http_hosts": "api.acme.example"}


def test_create_shares_the_same_secret_gate(client, monkeypatch):
    """写端点与两个 GET **共用同一道密钥闸**：未配 503 / 错密钥 401 / 对 201。

    ⚠️ 为什么单独测而不是「反正挂了同一个 Depends」：`require_platform_secret` 是
    **依赖工厂之外**的普通依赖，漏挂它**不会有任何编译期信号**；而路由策略快照虽会红，
    那是**依赖层**的快照（chore 硬注记：**快照绿 ≠ 授权完好**）。⇒ 端点层再钉一次。
    """
    monkeypatch.delenv(_ENV, raising=False)
    assert client.post(_URL, json=_BODY, headers=_hdr("whatever")).status_code == 503

    monkeypatch.setenv(_ENV, _GOOD)
    assert client.post(_URL, json=_BODY, headers=_hdr("kpa_" + "z" * 40)).status_code == 401
    r = client.post(_URL, json=_BODY, headers=_hdr(_GOOD))
    assert r.status_code == 201, r.text


def test_create_forces_suspended_and_ignores_caller_supplied_status_and_db_dir(client, monkeypatch):
    """⭐ 调用方**无法**指定 `status` / `db_dir` —— 传了也不生效（Pydantic 不认这两个字段）。

    ⚠️ 这两条各自堵一个具体后果：
      · `status='active'` ⇒ 一个调用就造出第二 active 租户 ⇒ **全站**每请求 fail-closed；
      · `db_dir='../evil'` ⇒ 主库路径逃逸变成 **API 可达**（Stage 3 §I-1 blocking 的全部理由）。
    """
    monkeypatch.setenv(_ENV, _GOOD)
    r = client.post(
        _URL,
        json={**_BODY, "status": "active", "db_dir": "../evil"},
        headers=_hdr(_GOOD),
    )
    assert r.status_code == 201, r.text
    t = r.json()["tenant"]
    assert t["status"] == "suspended", "调用方传的 status 生效了 —— 会造出第二 active 租户"
    assert t["db_dir"].startswith("tenants/") and "evil" not in t["db_dir"], (
        f"调用方影响了 db_dir：{t['db_dir']!r} —— 路径逃逸变成 API 可达"
    )


def test_create_response_is_no_store_and_carries_the_one_time_password(client, monkeypatch):
    """响应含一次性明文口令 ⇒ **必须** `Cache-Control: no-store`（承重，不是礼节）。"""
    monkeypatch.setenv(_ENV, _GOOD)
    r = client.post(_URL, json=_BODY, headers=_hdr(_GOOD))
    assert r.status_code == 201, r.text
    assert r.headers.get("Cache-Control") == "no-store", (
        "响应体带明文口令却未禁缓存 —— 中间层可能落盘"
    )
    assert r.json()["initial_password"], "没返回初始口令 ⇒ 运维拿不到、只能去重置"


def test_initial_password_never_appears_in_the_list_endpoint(client, monkeypatch):
    """⭐ 口令**绝不**出现在 `GET /api/platform/tenants` —— 一次性凭据不得变成可反复读取。

    这条钉住「响应模型物理分开」那个决定：`TenantCreated` 带口令，`TenantPublic` 不带；
    若有人图省事把口令加进 `TenantPublic`，本测红。
    """
    monkeypatch.setenv(_ENV, _GOOD)
    pwd = client.post(_URL, json=_BODY, headers=_hdr(_GOOD)).json()["initial_password"]
    r = client.get(_URL, headers=_hdr(_GOOD))
    assert r.status_code == 200, r.text
    assert pwd not in r.text, "初始口令出现在列表端点里 —— 一次性凭据变成可反复读取"
    assert "initial_password" not in r.text
    assert "allowed_http_hosts" not in r.text, (
        "allowed_http_hosts 出现在列表响应里 —— 那是部署方内网主机清单"
    )


def test_create_conflicts_return_409_with_actionable_message(client, monkeypatch):
    """两条拒绝分支 → **409**，且消息给出可走的下一步（不是裸 500）。"""
    monkeypatch.setenv(_ENV, _GOOD)
    assert client.post(_URL, json=_BODY, headers=_hdr(_GOOD)).status_code == 201

    r = client.post(_URL, json=_BODY, headers=_hdr(_GOOD))       # 行 + 库都在 ⇒ 不续做
    assert r.status_code == 409, r.text
    assert "reset_admin_password" in r.json()["detail"], "409 没给出恢复出口"

    r2 = client.post(_URL, json={**_BODY, "slug": "default"}, headers=_hdr(_GOOD))
    assert r2.status_code == 409 and "正在服务中" in r2.json()["detail"]


def test_create_requires_allowed_http_hosts_but_accepts_empty_string(client, monkeypatch):
    """`allowed_http_hosts` **必填**（漏传 422）但 `''` 合法（= 部署方明确的「禁」）。

    ⚠️ v0.9.7 三态：`''` ≠ `NULL`（未配置 ⇒ 起源租户回退 env）
    ⇒ 不能用「留空 = 默认」，否则开通动作替部署方**静默选了一种语义**。
    """
    monkeypatch.setenv(_ENV, _GOOD)
    r = client.post(_URL, json={"slug": "x1", "name": "X"}, headers=_hdr(_GOOD))
    assert r.status_code == 422, f"漏传 allowed_http_hosts 竟被接受：{r.text}"

    r2 = client.post(
        _URL, json={"slug": "x2", "name": "X", "allowed_http_hosts": ""}, headers=_hdr(_GOOD)
    )
    assert r2.status_code == 201, r2.text
