"""v0.9.4 step 13 — **双真租户端到端隔离**（正向证明）+ alg:none / 篡改 / 畸形头攻击面。

## 为什么必须有这个文件（我先前判断错了，记录）
我先前认定「A 的 token 打 B」在单租户下**协议上不可表达**（tid 进 token 后「A 的 token」语义就是
访问 A），于是只写了**反向**测（解析不出租户 → 绝不回退）。
**那个判断是错的**：只要在**测内**临时关掉 R-T-GATE、建两个**真**租户，就能做**正向**证明 ——
「tid=1 的 token 只看到租户 1 的数据、tid=2 只看到租户 2 的」。这才是整片的核心主张，
不能只靠「没回退」这类反向断言支撑。
（本文件的原型来自一个被 API 错误中断的审查 subagent 留在其独立 worktree 里的探针 ——
它想到了我没想到的做法。收成正式测并补齐断言。）

## ⚠️ R-T-GATE 只在**测内**被关
`monkeypatch.setattr(tr.tenant_repo, "assert_no_second_active_tenant_served", lambda: None)`
—— **生产码一行不改**。请求侧硬门本身另有守护测
（`tests/api/test_tenant_resolution_api.py::test_two_active_tenants_blocks_every_request`：
插第二 active 租户 → 每请求 fail-closed）。两者缺一不可：那条证明门**活着**，本文件证明门
一旦被合法解除（v0.9.5 lift），隔离**本身**成立。
"""
import base64
import json
import os
import shutil
import tempfile

import jwt
import pytest

from knot.api.deps import JWT_ALGORITHM, _get_secret
from tests.conftest import NoAmbientTenantTestClient

_MARK_USER = "ADMIN-OF-TENANT-{tid}"
_MARK_DOC = "SECRET-OF-TENANT-{tid}"


@pytest.fixture()
def two_tenants(monkeypatch):
    """建两个**真**租户（各自独立库文件 + 各自可检索的标记数据），返回 (client, {tid: token})。"""
    d = tempfile.mkdtemp(prefix="knot_2t_")
    anchor = os.path.join(d, "knot.db")

    from knot.core import tenant_context as tc
    from knot.repositories import base as base_mod
    from knot.repositories import knowledge_repo, tenant_repo, user_repo
    monkeypatch.setattr(base_mod, "SQLITE_DB_PATH", anchor)
    monkeypatch.setattr(tenant_repo, "SQLITE_DB_PATH", anchor)
    tenant_repo.init_platform_db()

    conn = tenant_repo.get_platform_conn()
    conn.execute("INSERT INTO tenants (id,slug,name,status,db_dir) "
                 "VALUES (1,'t1','T1','active','.')")
    conn.commit()
    conn.close()
    os.makedirs(os.path.join(d, "t2"), exist_ok=True)

    # ⚠️ `main.py` 模块级启动序会调 `resolve_single_tenant()` ⇒ **必须在只有 1 个 active 时** import。
    # （第二租户在 import 之后才插入 —— 顺序承重，调换即启动期 raise。）
    from knot.main import app

    conn = tenant_repo.get_platform_conn()
    conn.execute("INSERT INTO tenants (id,slug,name,status,db_dir) "
                 "VALUES (2,'t2','T2','active','t2')")
    conn.commit()
    conn.close()

    tokens = {}
    for tid in (1, 2):
        tok = tc.set_active_tenant(tenant_repo.get_tenant(tid))
        try:
            base_mod.init_db()
            admin = user_repo.get_user_by_username("admin")
            user_repo.update_user(admin["id"], must_change_password=0,
                                  display_name=_MARK_USER.format(tid=tid))
            knowledge_repo.create_knowledge_doc(_MARK_DOC.format(tid=tid), f"f{tid}.md", 1)
            from knot.api.deps import create_token
            tokens[tid] = create_token(admin["id"])
        finally:
            tc.reset_active_tenant(tok)

    # R-T-GATE **仅测内**解除（生产码不动，另有守护测证明它活着）
    from knot.api import tenant_resolution as tr
    monkeypatch.setattr(tr.tenant_repo, "assert_no_second_active_tenant_served", lambda: None)

    with NoAmbientTenantTestClient(app) as c:
        yield c, tokens
    shutil.rmtree(d, ignore_errors=True)


def _h(tok):
    return {"Authorization": f"Bearer {tok}"}


# ─── 1. ⭐ 正向隔离证明 ──────────────────────────────────────────────────


@pytest.mark.parametrize("tid", [1, 2])
def test_token_reads_only_its_own_tenant_data(two_tenants, tid):
    """⭐ **本片核心主张的正向证明**：tid=N 的 token 只读到租户 N 的数据，看不到另一家的。

    两个维度各查一次（用户表 + 业务表），因为它们经不同代码路径拿 ctx：
    `/api/auth/me` 走 `get_current_user`（tid 门 + 漂移比对）；`/api/knowledge` 走业务仓库
    （`get_conn` 双层库解析）。
    revert-to-bad：让 `resolve_for_request` 恒返 tenant#1（模拟「忽略 tid」）→ tid=2 那组转红。
    """
    c, tokens = two_tenants
    other = 2 if tid == 1 else 1

    r = c.get("/api/auth/me", headers=_h(tokens[tid]))
    assert r.status_code == 200, r.text[:200]
    assert r.json()["display_name"] == _MARK_USER.format(tid=tid), r.text[:200]

    r2 = c.get("/api/knowledge", headers=_h(tokens[tid]))
    assert r2.status_code == 200, r2.text[:200]
    assert _MARK_DOC.format(tid=tid) in r2.text, r2.text[:300]
    assert _MARK_DOC.format(tid=other) not in r2.text, (
        f"⭐ 跨租户泄漏：租户 {tid} 的 token 看到了租户 {other} 的数据 —— {r2.text[:300]}"
    )


def test_two_tenants_really_use_distinct_db_files(two_tenants):
    """前提校验：两租户的 `db_dir` 确实不同（否则上一条测在「同一个库」上跑 = 同义反复）。"""
    from knot.repositories import tenant_repo
    dirs = {t["id"]: t["db_dir"] for t in tenant_repo.list_active_tenants()}
    assert dirs == {1: ".", 2: "t2"}, f"两租户未落在不同库文件上：{dirs}"


# ─── 2. tid 攻击面（篡改 / 类型 / 不存在 / alg:none） ─────────────────────


def test_tid_tampered_without_resign_is_401(two_tenants):
    """改 payload 里的 tid 但**不重签** → 401（tid 是「自声明但**被签名**」的 claim）。"""
    c, tokens = two_tenants
    head, payload, sig = tokens[1].split(".")
    body = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    body["tid"] = 2
    forged = base64.urlsafe_b64encode(json.dumps(body).encode()).decode().rstrip("=")
    r = c.get("/api/auth/me", headers=_h(f"{head}.{forged}.{sig}"))
    assert r.status_code == 401, r.text[:200]


def test_alg_none_token_is_401(two_tenants):
    """⭐ `alg: none` 无签名 token → 401（`jwt.decode(..., algorithms=["HS256"])` 拒收）。

    这条我先前**完全没测**（探针提醒的）。若哪天有人把 `algorithms` 写宽/写成从 header 取，
    攻击者可自造任意 payload（含任选 tid）**完全无需密钥** = 全租户任意访问。
    """
    c, _tokens = two_tenants
    head = base64.urlsafe_b64encode(
        json.dumps({"alg": "none", "typ": "JWT"}).encode()).decode().rstrip("=")
    body = base64.urlsafe_b64encode(
        json.dumps({"sub": "1", "ver": 1, "tid": 2, "exp": 9999999999}).encode()
    ).decode().rstrip("=")
    assert c.get("/api/auth/me", headers=_h(f"{head}.{body}.")).status_code == 401


@pytest.mark.parametrize("bad_tid", [2.0, "2", True, 0, -2, 99])
def test_resigned_token_with_bad_tid_is_401(two_tenants, bad_tid):
    """**用真密钥重签**（模拟拿到签名能力的内部越权）+ 畸形/越界 tid → 一律 401。

    `"2"` / `2.0` / `True` 尤其承重：sqlite3 INTEGER affinity 实测三者都能匹配整型 id ⇒
    松了 tid 就是一个可**任选公司**的参数。`99` = 不存在的租户（不得回退到任何默认租户）。
    """
    c, tokens = two_tenants
    _h0, payload, _s = tokens[1].split(".")
    body = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    body["tid"] = bad_tid
    tok = jwt.encode(body, _get_secret(), algorithm=JWT_ALGORITHM)
    r = c.get("/api/auth/me", headers=_h(tok))
    assert r.status_code == 401, f"tid={bad_tid!r} → {r.status_code} {r.text[:160]}"


# ─── 3. 畸形 Authorization 头：端到端不得 5xx ────────────────────────────


def test_malformed_authorization_headers_never_5xx(two_tenants):
    """⭐ 端到端补齐（此前只在解析器单元层验过 parity）。

    「中间件认为没凭证（不设 ctx）而 HTTPBearer 认为有（鉴权继续）」的组合 = 端点碰 DB → **500**。
    合法用户在特定 header 写法下整站不可用，比某个端点坏严重得多。
    含 `Bearer <5000 个 A>`（超长）与重复 Bearer（`Bearer a Bearer a`）—— 探针提醒的两种。
    """
    c, tokens = two_tenants
    t = tokens[1]
    variants = [
        "", "Bearer", "Bearer ", " Bearer " + t, "Basic " + t, "Bearer " + t + "extra",
        "Bearer ...", "Bearer a.b.c", "Bearer " + "A" * 5000,
        "Bearer " + t + " " + t, "bearer\t" + t, "Bearer " + t + "\t",
        "Bearer  " + t, "BEARER " + t, "Bearer " + t.rsplit(".", 1)[0],
    ]
    bad = []
    for h in variants:
        r = c.get("/api/auth/me", headers={"Authorization": h})
        if r.status_code >= 500:
            bad.append((h[:40], r.status_code))
    assert not bad, f"以下 Authorization 写法致 5xx（合法用户会整站不可用）：{bad}"
