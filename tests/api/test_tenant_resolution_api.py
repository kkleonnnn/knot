"""v0.9.4 step 5 — 租户解析的**端点级**契约（HTTP 层，走真中间件）。

⚠️ **本文件的每一条断言在 step 5a 之前都是同义反复。** 原因（实测）：`tests/conftest.py` 的
autouse fixture 给每个测试都设了 tenant#1 ctx，而 TestClient 在同一 contextvars 上下文里跑 app
⇒ **app 继承那份「环境 ctx」**，中间件设不设结果一样。实测把 `resolve_for_request` 整个改成
`return None`（中间件永不解析租户）→ **全量 1437 测全绿**。
step 5a 的 `NoAmbientTenantTestClient` 在 HTTP 调用期间清掉环境 ctx，同一条 sabotage 变成
**262 failed**（integration+api 子集）⇒ 本文件才谈得上「验过」。

生产环境本来就没有环境 ctx（每请求一个干净 asyncio task）⇒ 被环境 ctx 削弱的只是**测试的证明力**，
不是产品行为。
"""
from datetime import datetime, timedelta

import jwt
import pytest

from knot.api.deps import JWT_ALGORITHM, _get_secret
from knot.core.tenant_context import TenantContextError


def _sign(**payload):
    """用**真密钥**签任意 payload（伪造签名的场景另测；此处专测 claim 内容）。"""
    payload.setdefault("exp", datetime.utcnow() + timedelta(hours=1))
    return jwt.encode(payload, _get_secret(), algorithm=JWT_ALGORITHM)


def _bearer(tok):
    return {"Authorization": f"Bearer {tok}"}


# ─── 1. ⭐ 中间件真的在解析（此前零覆盖的那条） ──────────────────────────


def test_middleware_actually_resolves_tenant(client, admin_token):
    """⭐ **本片最承重的一条**：正常 token → 端点 200。

    在 step 5a 之前**没有任何测试**在验这件事（中间件被改成永不解析仍全绿）。
    revert-to-bad：在 `resolve_for_request` 里插一句 `return None` → 本测 + 大量既有测转红。
    """
    r = client.get("/api/auth/me", headers=_bearer(admin_token))
    assert r.status_code == 200, r.text[:200]
    assert r.json()["username"] == "admin"


# ─── 2. tid 门：存量 token / 错 tid / 停用租户 —— 一律 401，**不是 500** ──


def test_legacy_token_without_tid_gets_401(client):
    """D8：升级前签发的 token **无 tid** → 401 `JWT_NO_TID`（判别式是 tid 有无，不是 ver）。

    **必须是 401 而不是 500**：前端 401 拦截器会清 token + 跳登录（体验 = 被登出，可接受）；
    500 则是白屏。现网 `Recreate` 部署（关掉再起）⇒ 新旧版本不同时 serving ⇒ 无抖动循环。
    """
    r = client.get("/api/auth/me", headers=_bearer(_sign(sub="1", ver=1)))
    assert r.status_code == 401, r.text[:200]
    assert r.json()["detail"] == "JWT_NO_TID"


def test_token_with_unknown_tid_gets_401_not_500(client):
    """真签名 + tid 指向不存在的租户 → 401 `TENANT_UNAVAILABLE`。

    这是**内部越权模拟**：拿到签名能力的人若能任选 tid，就能选别家公司。
    结果必须是 401，且**绝不能**因「解析不出就回退」而变成 200（那是 OOS-1v2 fail-open）。
    """
    r = client.get("/api/auth/me", headers=_bearer(_sign(sub="1", ver=1, tid=4242)))
    assert r.status_code == 401, r.text[:200]
    assert r.json()["detail"] == "TENANT_UNAVAILABLE"


@pytest.mark.parametrize("bad_tid", ["1", True, 0, -1, 1.0])
def test_token_with_malformed_tid_gets_401(client, bad_tid):
    """D9 严格类型（sqlite3 INTEGER affinity 实测 `'1'`/`1.0`/`True` 都能匹配整型 id=1）。"""
    r = client.get("/api/auth/me", headers=_bearer(_sign(sub="1", ver=1, tid=bad_tid)))
    assert r.status_code == 401, f"tid={bad_tid!r} → {r.status_code} {r.text[:120]}"


def test_suspended_tenant_token_gets_401(client, admin_token):
    """租户被停用后，**它原本有效的 token 立刻失效**（401，不是 200 也不是 500）。

    revert-to-bad：把 `resolve_tenant_by_id` 换成不过滤 status 的 `get_tenant` → 本测转红
    （停用租户仍被解析出来 → 200）。
    """
    from knot.repositories import tenant_repo
    conn = tenant_repo.get_platform_conn()
    conn.execute("UPDATE tenants SET status='suspended' WHERE id=1")
    conn.commit()
    conn.close()
    r = client.get("/api/auth/me", headers=_bearer(admin_token))
    assert r.status_code == 401, r.text[:200]
    assert r.json()["detail"] == "TENANT_UNAVAILABLE"


def test_forged_signature_gets_401(client):
    """别的密钥签的 token（含合法 tid）→ 401。tid 是「自声明但**被签名**」的 claim。"""
    forged = jwt.encode({"sub": "1", "ver": 1, "tid": 1,
                         "exp": datetime.utcnow() + timedelta(hours=1)},
                        "totally-different-secret-x", algorithm=JWT_ALGORITHM)
    assert client.get("/api/auth/me", headers=_bearer(forged)).status_code == 401


# ─── 3. ⭐ 无 token 的路径不得 500（把人锁在门外 / 打断跨域） ─────────────


@pytest.mark.parametrize("path", ["/", "/anything/deep/path", "/docs", "/openapi.json"])
def test_noauth_get_paths_no_5xx(client, path):
    """SPA catch-all / docs / openapi：无 tenant ctx 也不得 5xx（须验它们不碰 DB）。

    实测清点：138 条 API 路由中恰 4 条无鉴权（login / totp-verify / scheduler-tick / SPA），
    另有 Mount：/openapi.json /docs /docs/oauth2-redirect /redoc /static /assets。
    """
    assert client.get(path).status_code < 500, path


@pytest.mark.parametrize("path", ["/api/auth/login", "/api/conversations"])
def test_options_preflight_no_5xx(client, path):
    """OPTIONS 预检：CORS 在 tenant middleware **内层** ⇒ 预检同样穿本中间件。

    若它 5xx，**所有跨域前端会被打断**（比某个端点坏严重得多）。
    """
    r = client.options(path, headers={"Origin": "http://x.test",
                                      "Access-Control-Request-Method": "GET"})
    assert r.status_code < 500, f"{path} → {r.status_code}"


def test_totp_verify_reachable_without_ctx(client):
    """`/api/totp/verify` 无鉴权、且**自建 ctx**（step 4 的 `interim_session`）⇒ 垃圾 interim 应 401 非 500。"""
    r = client.post("/api/totp/verify", json={"interim_token": "garbage", "code": "123456"})
    assert r.status_code == 401, r.text[:160]


# ─── 4. B-5：陈旧 Authorization 不得挡住登录 ─────────────────────────────


def test_login_works_despite_stale_authorization_header(client):
    """⭐ B-5：前端 axios 拦截器会把**陈旧 token**带到登录请求上 —— 登录必须照样成功。

    这正是「中间件永不 401」这个设计选择的收益：若中间件对畸形/无 tid token 直接 401，
    带着旧 token 的用户会**永远登不进来**（401 → 前端清 token + reload → 再登又带旧 token…）。
    revert-to-bad：让 `_bearer_payload` 解析失败时 raise 401 → 本测转红。
    """
    stale = _sign(sub="1", ver=1)          # 真签名但无 tid（= 升级前的存量 token）
    r = client.post("/api/auth/login",
                    json={"username": "admin", "password": "admin123"},
                    headers=_bearer(stale))
    assert r.status_code == 200, r.text[:200]
    assert "token" in r.json() or r.json().get("need_totp"), r.text[:200]


def test_login_issued_token_carries_tid_and_works(client):
    """端到端：登录 → 签出的 token 带 tid → 用它访问受保护端点 200。"""
    r = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200, r.text[:200]
    tok = r.json()["token"]
    assert jwt.decode(tok, options={"verify_signature": False})["tid"] == 1
    assert client.get("/api/auth/me", headers=_bearer(tok)).status_code == 200


# ─── 5. R-T-GATE 在请求路径上真的活着 ───────────────────────────────────


def test_two_active_tenants_blocks_every_request(client, admin_token):
    """D5：插入第二个 active 租户 → **每个请求** fail-closed（R-T-GATE 请求侧硬门）。

    这是**故意的**：隔离栈就绪前严禁服务第二租户。gate 只对 `>1` raise（0 active 交上层语义）。
    v0.9.5 lift = 删 `resolve_for_request` 里那一行。
    revert-to-bad：删掉 `assert_no_second_active_tenant_served()` → 本测转红（请求变 200）。
    """
    from knot.repositories import tenant_repo
    conn = tenant_repo.get_platform_conn()
    conn.execute("INSERT INTO tenants (id,slug,name,status,db_dir) "
                 "VALUES (2,'t2','T2','active','tenants/2')")
    conn.commit()
    conn.close()
    with pytest.raises(TenantContextError, match="R-T-GATE"):
        client.get("/api/auth/me", headers=_bearer(admin_token))


def test_zero_active_tenants_current_behavior_is_documented(client):
    """0 active 租户时**当前**行为：受保护端点 401；登录端点走临时表的 `resolve_single_tenant` → raise。

    ⚠️ **本测记录的是 step 5 的实况，不是终态。** 计划（D5）要求 0 active 时登录返回统一的
    「账号或密码错误」而非崩 —— 那要等 step 7 把 login 改成按 `?c=<slug>` 自建 ctx（届时本测改断言 401）。
    留此测是为了让 step 7 有个**必然会红的标记**，而不是让这个中间态悄悄留存。
    """
    from knot.repositories import tenant_repo
    conn = tenant_repo.get_platform_conn()
    conn.execute("UPDATE tenants SET status='suspended'")
    conn.commit()
    conn.close()
    # 受保护端点：无可解析租户 → 401（不回退）
    assert client.get("/api/auth/me",
                      headers=_bearer(_sign(sub="1", ver=1, tid=1))).status_code == 401
    # 登录端点：step 5 仍走 resolve_single_tenant ⇒ 0 active 抛（step 7 改为 401）
    with pytest.raises(TenantContextError):
        client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
