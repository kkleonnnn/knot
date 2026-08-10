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
            # ⭐ `password_hash` 自 v0.9.19 D3 起**必须显式设**：
            # `KNOT_INITIAL_ADMIN_PASSWORD`（conftest 设为 admin123）只对**起源租户**生效，
            # 非起源租户 seed 的是**随机口令**。本文件下方多条测用 `admin123` 登录 **t2**，
            # 此前之所以能通过，靠的正是 D3 修掉的那个缺陷（「A 公司的口令能进 B 公司」）。
            # ⇒ 登录口令由**本测自己设定**，与部署方的 seed 口令解耦。
            import bcrypt as _bcrypt
            user_repo.update_user(
                admin["id"], must_change_password=0,
                display_name=_MARK_USER.format(tid=tid),
                password_hash=_bcrypt.hashpw(b"admin123", _bcrypt.gensalt()).decode())
            knowledge_repo.create_knowledge_doc(_MARK_DOC.format(tid=tid), f"f{tid}.md", 1)
            from knot.api.deps import create_token
            tokens[tid] = create_token(admin["id"])
        finally:
            tc.reset_active_tenant(tok)

    # ⭐ v0.9.20（P-c）：R-T-GATE 已 lift ⇒ 原先那行「仅测内」解除门的 monkeypatch **已删除**。
    # ⚠️ 它与生产码里那一行是**同一件事实的两半** —— 只删一边没有任何意义：
    #    实测（Stage 1 §0.2）只删 monkeypatch 而留着门 ⇒ **18 failed / 3 passed**
    #    （门是 `resolve_for_request` 第一行，本 fixture 造的正是 2 个 active 租户）；
    #    仍绿的 3 条恰好都**不走 HTTP 请求**，交叉印证是同一个成因。
    # ⇒ 本文件从此是**真·双租户**下的端到端隔离验收，不再是「预演」。
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


# ─── 4. ⭐ 守护者 Q2：让「company 可选」安全的**承重性质**（此前未测） ──────


def test_no_slug_login_with_two_active_tenants_is_401(two_tenants):
    """⭐ **无代号 + 2 个 active 租户 → 统一 401，绝不「挑一个」租户。**

    守护者 Q2 指出：让「`company` 可选」得以接受的，正是这条**结构性**性质 ——
    `_resolve_login_tenant` 无 slug 时走 `resolve_single_tenant()`，而它在 active **≠1** 时 **raise**
    ⇒ 第二租户一激活，无代号登录**立刻全部 401**。所以万一 lift 时忘了把 `company` 改必填，
    后果是**可用性**（老链接失效），**不是跨租户访问**。
    **而这条性质此前没有任何测**（守护者 grep `company|no_slug|without` 全空）—— 本测补齐，
    并作为 **lift 前的 positive check**。

    本测跑在 gate 已（测内）解除的双租户环境 = **模拟 lift 后的状态**，正是要证的那个场景。
    revert-to-bad：把 `_resolve_login_tenant` 的无 slug 分支改成
    `return tenant_repo.list_active_tenants()[0]`（「挑第一个」）→ 本测转红（会返 200 + token）。
    """
    c, _tokens = two_tenants
    r = c.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 401, f"无代号 + 2 租户应统一 401，实得 {r.status_code} {r.text[:200]}"
    assert r.json()["detail"] == "账号或密码错误", r.text[:200]
    # 绝不能「挑一个」把 token 发出去 —— 那就是 OOS-1v2 fail-open
    assert "token" not in r.text and "need_totp" not in r.text, r.text[:200]


@pytest.mark.parametrize("tid,slug", [(1, "t1"), (2, "t2")])
def test_slug_login_selects_the_right_tenant(two_tenants, tid, slug):
    """⭐ 正向：带代号登录 → 进**对应**那家公司（签出 token 的 tid 与库内数据都对）。

    与上一条互补：那条证「没代号时不乱猜」，这条证「有代号时选对」。两条合起来才是
    「专属登录链接」的完整契约。
    revert-to-bad：把 `resolve_tenant_by_slug` 的 `WHERE slug=?` 改成 `WHERE id=1` → tid=2 组转红。
    """
    c, _tokens = two_tenants
    r = c.post("/api/auth/login",
               json={"username": "admin", "password": "admin123", "company": slug})
    assert r.status_code == 200, r.text[:200]
    tok = r.json()["token"]
    assert jwt.decode(tok, options={"verify_signature": False})["tid"] == tid, r.text[:200]
    assert r.json()["user"]["display_name"] == _MARK_USER.format(tid=tid), r.text[:200]
    # 再用它读业务表，确认真落在该租户的库文件上
    r2 = c.get("/api/knowledge", headers=_h(tok))
    assert _MARK_DOC.format(tid=tid) in r2.text, r2.text[:300]
    assert _MARK_DOC.format(tid=2 if tid == 1 else 1) not in r2.text, r2.text[:300]


def test_unknown_slug_login_is_401_and_indistinguishable(two_tenants):
    """未知代号 → 与「密码错」**逐字相同**的 401（防公司枚举 —— 在**真有两家**的环境下再验一次）。"""
    c, _tokens = two_tenants
    bad_slug = c.post("/api/auth/login",
                      json={"username": "admin", "password": "admin123", "company": "t3-nope"})
    bad_pw = c.post("/api/auth/login",
                    json={"username": "admin", "password": "wrong-pw-zz", "company": "t1"})
    assert bad_slug.status_code == bad_pw.status_code == 401
    assert bad_slug.text == bad_pw.text, (
        f"「代号不存在」与「密码错」响应不同 ⇒ 可枚举公司：\n  {bad_slug.text[:120]}\n  {bad_pw.text[:120]}"
    )


# ─── 5. 守护者 Q5：兜底分支的可追溯性（基础设施故障不得静默变 401） ────────


def test_infra_failure_is_logged_not_silently_401(two_tenants, monkeypatch):
    """⭐ Q5：读租户库抛 `sqlite3.Error` 时仍返 401（客户端行为不变），但**必须留日志**。

    守护者裁定：`get_current_user` 函末 `except Exception` 把 `get_token_version_cached` /
    `get_user_by_id` 的 `sqlite3.Error` 折成「凭证无效」⇒ 磁盘/权限/库损坏时该租户**全体用户**
    看到认证错误，而此前**零日志痕迹** = 基础设施故障被静默误诊成认证问题。
    本片按 should-fix **只加日志**（窄化成 503 留 backlog，那会改客户端可见行为）。
    revert-to-bad：删掉那句 `logger.exception` → 本测转红。
    """
    import sqlite3

    from loguru import logger as _lg

    from knot.services import totp_service
    c, tokens = two_tenants

    def boom(_uid):
        raise sqlite3.OperationalError("disk I/O error（模拟磁盘/权限故障）")

    monkeypatch.setattr(totp_service, "get_token_version_cached", boom)
    sink: list = []
    hid = _lg.add(lambda m: sink.append(str(m)), level="DEBUG", format="{message}")
    try:
        r = c.get("/api/auth/me", headers=_h(tokens[1]))
    finally:
        _lg.remove(hid)
    assert r.status_code == 401, f"行为须不变（仍 401），实得 {r.status_code}"
    blob = "".join(sink)
    assert "兜底分支吞异常" in blob, (
        f"基础设施故障被静默折成 401 且无日志痕迹（运维无法追溯）：{blob[-400:]}"
    )
    assert "disk I/O error" in blob, f"日志未含原始异常（`logger.exception` 才带 traceback）：{blob[-400:]}"


# ─── 6. 守护者 §IV note：两条「本片赖以成立却零正向覆盖」的主张 ────────────


@pytest.mark.parametrize("tid,slug", [(1, "t1"), (2, "t2")])
def test_login_audit_row_lands_in_the_right_tenant_db(two_tenants, tid, slug):
    """⭐ B-5 audit 路由：登录成功的审计行必须落在**该公司自己的**库里，不能串到另一家。

    守护者 §IV 指出这条零正向覆盖。它承重是因为：登录端点**自建 ctx**，而 audit 在 set 之后调 ——
    若 set 用错租户（或 audit 早于 set），审计行就写进别家公司的库 = 安全记录错位且难察觉。
    revert-to-bad：把 `login` 里的 `audit(...)` 移到 `set_active_tenant` **之前** → 本测转红
    （MF3 修后它会直接抛 `TenantContextError`；R-13 哨兵亦会红 = 双重覆盖）。
    """
    from knot.core import tenant_context as tc
    from knot.repositories import audit_repo, tenant_repo
    c, _tokens = two_tenants
    r = c.post("/api/auth/login",
               json={"username": "admin", "password": "admin123", "company": slug})
    assert r.status_code == 200, r.text[:200]

    def _login_rows(t):
        tok = tc.set_active_tenant(tenant_repo.get_tenant(t))
        try:
            return [x for x in audit_repo.list_filtered(page=1, size=200)
                    if x["action"] == "auth.login_success"]
        finally:
            tc.reset_active_tenant(tok)

    assert _login_rows(tid), f"租户 {tid} 库内没有本次登录的审计行"
    other = 2 if tid == 1 else 1
    assert not _login_rows(other), f"⭐ 审计行串到了租户 {other} 的库（安全记录错位）"


@pytest.mark.parametrize("tid", [1, 2])
def test_interim_tid_selects_the_tenant_for_2fa_path(two_tenants, tid):
    """⭐ 「2FA 也走公司代号」：interim 里的 tid **就是**决定 verify 阶段读哪家库的东西。

    守护者 §IV 指出这条零正向覆盖。链条：带代号登录 → 该租户 ctx 内签发 interim（tid=该租户）
    → verify 时 `interim_session` **只**靠 interim 的 tid 重建 ctx（不靠 Authorization、不靠单租户回退）。
    本测直接钉中间那一跳：在租户 N 的 ctx 内签 interim，然后**从 ctx 之外**进 `interim_session`，
    块内必须是租户 N 且读到租户 N 的用户。
    revert-to-bad：把 `interim_session` 的 `resolve_tenant_by_id(payload["tid"])` 换成
    `resolve_single_tenant()` → 双 active 下抛错/选错 → 本测转红。
    """
    from knot.api.totp import create_interim_token, interim_session
    from knot.core import tenant_context as tc
    from knot.repositories import tenant_repo, user_repo
    _c, _tokens = two_tenants

    tok = tc.set_active_tenant(tenant_repo.get_tenant(tid))
    try:
        interim = create_interim_token(1, 1)          # 在租户 N 的 ctx 内签发
    finally:
        tc.reset_active_tenant(tok)

    outer = tc.set_active_tenant(None)                 # 刻意从「无 ctx」进入
    try:
        with interim_session(interim) as (payload, user_id):
            assert payload["tid"] == tid, payload
            assert tc.current_tenant()["id"] == tid, tc.current_tenant()
            assert user_repo.get_user_by_id(user_id)["display_name"] == _MARK_USER.format(tid=tid)
    finally:
        tc.reset_active_tenant(outer)
