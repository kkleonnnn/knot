"""v0.9.4 step 5 — 请求级租户解析（middleware 从 JWT tid 取租户）契约测。

本片把「这个请求读哪家公司的库」从「假设全站只有一家」换成「读 token 里的 tid」。
最危险的失败**不是崩**，而是**静默落到别家公司的库**（OOS-1v2 fail-open）。因此本文件的重心是：
1. **无法解析时绝不回退**（`test_no_*_leaves_ctx_unset` 三测 + `test_R15_no_generic_fallback` 静态守护）
2. **解析口径不得比 `HTTPBearer` 更严** —— 更严 = 「middleware 不设 ctx + 鉴权照样放行」
   → 端点碰 DB → **500**（`test_R16_not_stricter_than_httpbearer`）
3. **不设 ctx ≠ 放行**：无 token 的 4 条路由 + 静态 + docs + OPTIONS 预检不得 500（`test_noauth_*`）
4. **B-4 新失败模式**「ctx 非 None 但是错的租户」已接上 tripwire（`test_B4_drift_*`）

fixtures：`tmp_db_path`（conftest）已建 platform.db + seed tenant#1(db_dir='.')；autouse 设 tenant#1 ctx。
"""
import ast
import pathlib
from datetime import datetime, timedelta

import jwt
import pytest
from fastapi.security import HTTPBearer
from fastapi.security.utils import get_authorization_scheme_param
from starlette.requests import Request

from knot.api import tenant_resolution as tr
from knot.api.deps import JWT_ALGORITHM, _get_secret
from knot.core import tenant_context as tc
from knot.core.tenant_context import TenantContextError

_REPO = pathlib.Path(__file__).resolve().parents[1]


def _mk_request(auth_header=None, path="/api/conversations", method="GET"):
    """最小 Starlette Request（middleware 只读 headers + url.path）。"""
    headers = [] if auth_header is None else [(b"authorization", auth_header.encode())]
    return Request({
        "type": "http", "method": method, "path": path, "raw_path": path.encode(),
        "headers": headers, "query_string": b"", "scheme": "http",
        "server": ("test", 80), "root_path": "",
    })


def _tok(tid=1, user_id=1, ver=1, **extra):
    p = {"sub": str(user_id), "ver": ver, "exp": datetime.utcnow() + timedelta(hours=1)}
    if tid is not None:
        p["tid"] = tid
    p.update(extra)
    return jwt.encode(p, _get_secret(), algorithm=JWT_ALGORITHM)


# ─── 1. 正常路径 ────────────────────────────────────────────────────────


def test_resolves_tenant_from_jwt_tid(tmp_db_path):
    """token 里的 tid → 解析出对应租户（这就是本片的目的）。"""
    t = tr.resolve_for_request(_mk_request(f"Bearer {_tok(tid=1)}"))
    assert t is not None and t["id"] == 1


# ─── 2. ⭐ 绝不回退（OOS-1v2 fail-open 守护） ────────────────────────────


@pytest.mark.parametrize("header,why", [
    (None, "完全没有 Authorization 头（SPA / 静态 / 登录页 / OPTIONS 预检）"),
    ("", "空头"),
    ("Bearer", "只有 scheme 没有 token"),
    ("Bearer ", "scheme + 空 token"),
    ("Basic dXNlcjpwYXNz", "非 Bearer scheme"),
    ("Bearer garbage.not.a.jwt", "畸形 JWT"),
])
def test_unusable_credential_leaves_ctx_unset(tmp_db_path, header, why):
    """⭐ 凭证不可用 → 返 **None**（middleware 届时不设 ctx），**绝不回退到默认租户**。

    回退 = 静默跨租户供数（OOS-1v2 最核心的那条）。fail-closed 的代价是 401/500，可接受；
    fail-open 的代价是 A 公司看到 B 公司的数据，不可接受。
    """
    assert tr.resolve_for_request(_mk_request(header)) is None, f"应返 None：{why}"


def test_expired_token_leaves_ctx_unset(tmp_db_path):
    """过期 token → None（不因「签名对」就放行）。"""
    expired = jwt.encode({"sub": "1", "ver": 1, "tid": 1,
                          "exp": datetime.utcnow() - timedelta(hours=1)},
                         _get_secret(), algorithm=JWT_ALGORITHM)
    assert tr.resolve_for_request(_mk_request(f"Bearer {expired}")) is None


def test_foreign_signature_leaves_ctx_unset(tmp_db_path):
    """**别的密钥**签的 token（伪造）→ None。tid 是「自声明但被签名」的 claim。"""
    forged = jwt.encode({"sub": "1", "ver": 1, "tid": 1,
                         "exp": datetime.utcnow() + timedelta(hours=1)},
                        "not-our-secret-at-all-x", algorithm=JWT_ALGORITHM)
    assert tr.resolve_for_request(_mk_request(f"Bearer {forged}")) is None


@pytest.mark.parametrize("bad_tid", [None, "1", True, 0, -1, 1.0, [1], {"id": 1}])
def test_bad_tid_leaves_ctx_unset(tmp_db_path, bad_tid):
    """tid 缺失 / 类型错 / 非正 → None。

    `'1'` / `1.0` / `True` 三者尤其承重：实测 sqlite3 INTEGER affinity 会把它们都匹配到整型 id=1
    ⇒ 松了 tid 就是一个**可伪造的「选公司」参数**（虽然伪造需要过签名，但内部越界/降权场景仍成立）。
    """
    assert tr.resolve_for_request(_mk_request(f"Bearer {_tok(tid=bad_tid)}")) is None


def test_suspended_tenant_leaves_ctx_unset(tmp_db_path):
    """租户已停用 → None（B-2：`resolve_tenant_by_id` 过滤 status）。"""
    from knot.repositories import tenant_repo
    conn = tenant_repo.get_platform_conn()
    conn.execute("UPDATE tenants SET status='suspended' WHERE id=1")
    conn.commit()
    conn.close()
    assert tr.resolve_for_request(_mk_request(f"Bearer {_tok(tid=1)}")) is None


def test_unknown_tenant_leaves_ctx_unset(tmp_db_path):
    """tid 指向不存在的租户 → None。"""
    assert tr.resolve_for_request(_mk_request(f"Bearer {_tok(tid=4242)}")) is None


def test_R15_no_generic_fallback(tmp_db_path):
    """⭐ **静态守护**：`resolve_single_tenant` 在本模块内**只允许**出现在临时路径表那一支里。

    为何要静态守护而不只靠上面的行为测：将来有人为了「让它别崩」加一句
    `return tenant_repo.resolve_single_tenant()` 兜底，行为测在**单租户环境下全绿**
    （单租户时回退与正解等价！），而多租户上线后就是静默跨租户供数。
    ⇒ 单租户环境**测不出** fail-open，只能静态钉住。

    revert-to-bad：在 `resolve_for_request` 末尾把 `return tenant_repo.resolve_tenant_by_id(tid)`
    改成 `return tenant_repo.resolve_tenant_by_id(tid) or tenant_repo.resolve_single_tenant()`
    → 本测转红（上面所有行为测**仍全绿**）。
    """
    src = (_REPO / "knot" / "api" / "tenant_resolution.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next(n for n in tree.body
              if isinstance(n, ast.FunctionDef) and n.name == "resolve_for_request")
    calls = [n.lineno for n in ast.walk(fn)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
             and n.func.attr == "resolve_single_tenant"]
    # 允许的唯一位置：临时路径表那一支（`if request.url.path in _LEGACY_SINGLE_TENANT_PATHS:` 的子树内）
    allowed = set()
    for node in ast.walk(fn):
        if not isinstance(node, ast.If):
            continue
        gated_by_legacy_table = any(
            isinstance(n, ast.Name) and n.id == "_LEGACY_SINGLE_TENANT_PATHS"
            for n in ast.walk(node.test)
        )
        if gated_by_legacy_table:
            allowed |= {n.lineno for n in ast.walk(node)
                        if isinstance(n, ast.Call)
                        and getattr(n.func, "attr", None) == "resolve_single_tenant"}
    assert len(calls) == 1, f"预期恰 1 处 resolve_single_tenant，实得 {len(calls)} 处 @ {calls}"
    assert set(calls) == allowed, (
        f"resolve_single_tenant 出现在临时路径表分支之外（实得行 {calls}，分支内 {sorted(allowed)}）"
        f" —— 那是 OOS-1v2 禁的 fail-open 全局回退：单租户下与正解等价 ⇒ 行为测抓不到。"
    )


# ─── 3. ⭐ 临时路径表不得静默增长 ────────────────────────────────────────


def test_R14_legacy_paths_exact():
    """⭐ 临时表**精确内容**断言 —— 增项必须是显式决策，不能顺手加。

    表里每一项都是「本请求没有能决定租户的 JWT」的例外；每加一项就多一条绕过 tid 解析的路径。
    step 7 会摘掉 `/api/auth/login`（改为按 `?c=<slug>` 自建 ctx），届时本测同步改为 1 项。
    """
    assert tr._LEGACY_SINGLE_TENANT_PATHS == frozenset({
        "/api/auth/login",
        "/api/bi/scheduler/tick",
    }), (
        "临时路径表变了。增项 = 多一条绕过 tid 解析的路径，必须走显式决策 + 写明摘除条件；"
        "减项（step 7 摘 login）请同步本断言。"
    )


# ─── 4. ⭐ 解析口径与 HTTPBearer 一致（500 洞守护） ──────────────────────


_HEADER_FORMS = [
    None, "", "Bearer", "Bearer ", "bearer {t}", "BEARER {t}", "BeArEr {t}",
    "Bearer {t}", "Bearer  {t}", " Bearer {t}", "Bearer\t{t}",
    "Basic {t}", "Token {t}", "{t}", "Bearer {t} extra", "Bearer {t}\t",
]


@pytest.mark.parametrize("form", _HEADER_FORMS)
def test_R16_not_stricter_than_httpbearer(tmp_db_path, form):
    """⭐ **生产的 `_bearer_payload` 不得比 `HTTPBearer` 更严**（否则是 500 洞）。

    不一致的两个方向后果不对称：
    - 我们更宽松 → 最坏是设了 ctx 而随后被 401，**无害**。
    - 我们**更严** → middleware 认为没凭证（不设 ctx）而 HTTPBearer 认为有（鉴权继续走）
      → 端点碰 DB 撞 fail-closed → **500**。合法用户在特定 header 写法下整站不可用。

    判据 = 「**若 HTTPBearer 交出的凭证本身能验签通过，我们就必须也解析成功**」。

    ⚠️ **本测初版是同义反复**（自我记录）：初版在测试里用 `get_authorization_scheme_param`
    自己算一遍解析结果，再与 HTTPBearer 比 —— **根本没调生产代码** ⇒ 生产怎么写都绿。
    revert 实测：把生产改成大小写敏感的手写 `partition(" ")` + `scheme == "Bearer"`，初版
    **61 测全绿**。改为直接调 `tr._bearer_payload` 后同一 revert → `bearer`/`BEARER`/`BeArEr` 三例转红。
    教训：断言里若不出现被测函数名，先怀疑它在测标准库。

    **手写版更严的机制恰两条（实测坐实，非推测）**：
    `get_authorization_scheme_param` = `partition(" ")` **加 `param.strip()`**；我们的 scheme 比较
    **大小写不敏感**。于是手写严格版在三种写法上更严 → 各自都是一次 500：
      · `bearer <tok>`（**RFC 7235 允许小写 scheme**，HTTPBearer 今天就收）
      · `Bearer  <tok>`（双空格 —— 库 strip 掉，手写版留着前导空格致验签失败）
      · `Bearer <tok>\t`（尾部 tab，同上）
    `Bearer\t<tok>`（scheme 后是 tab）两边都拒 ⇒ 本测跳过它，不做无意义断言。
    """
    real = _tok(tid=1)
    header = None if form is None else form.replace("{t}", real)
    req = _mk_request(header)

    creds = _httpbearer_credentials(header)
    # HTTPBearer 交出的凭证是否本身可用（可验签）？双空格等写法下它交出的是带前导空格的串 → 验签失败
    theirs_usable = False
    if creds is not None:
        try:
            jwt.decode(creds, _get_secret(), algorithms=[JWT_ALGORITHM])
            theirs_usable = True
        except jwt.InvalidTokenError:
            theirs_usable = False

    ours_usable = tr._bearer_payload(req) is not None      # ← 真·被测函数

    if theirs_usable:
        assert ours_usable, (
            f"我们比 HTTPBearer 更严：header={header!r} —— HTTPBearer 交出可验签的凭证，"
            f"而 _bearer_payload 返 None ⇒ middleware 不设 ctx + 鉴权放行 → 端点 500。"
        )


def _httpbearer_credentials(header):
    """跑真实 `HTTPBearer(auto_error=False)` 拿它的 credentials（None 表示它也不认）。"""
    import asyncio
    res = asyncio.run(HTTPBearer(auto_error=False)(_mk_request(header)))
    return None if res is None else res.credentials


# ─── 5. R-T-GATE 顺序 ──────────────────────────────────────────────────


def test_gate_runs_before_tid_resolution(tmp_db_path):
    """D5：R-T-GATE 硬门在解析之前 —— 2 个 active 租户 → 无论 token 如何都 raise。

    revert-to-bad：把 `assert_no_second_active_tenant_served()` 那行挪到函数末尾 / 删掉 → 本测转红。
    """
    from knot.repositories import tenant_repo
    conn = tenant_repo.get_platform_conn()
    conn.execute("INSERT INTO tenants (id,slug,name,status,db_dir) "
                 "VALUES (2,'t2','T2','active','tenants/2')")
    conn.commit()
    conn.close()
    with pytest.raises(TenantContextError, match="R-T-GATE"):
        tr.resolve_for_request(_mk_request(f"Bearer {_tok(tid=1)}"))
    # 连「完全没凭证」也必须被 gate 挡住（证明 gate 在最前，不是解析失败后才跑）
    with pytest.raises(TenantContextError, match="R-T-GATE"):
        tr.resolve_for_request(_mk_request(None))


# ─── 6. B-4 租户漂移 tripwire（kk 决策②「做，要接上」） ─────────────────


def test_B4_drift_tripwire_has_production_call_site():
    """`assert_tenant_context` 此前 **0 生产调用点**（写了没接）；本片必须接上。

    revert-to-bad：删掉 `deps.py` 里那次调用 → 本测转红。
    """
    src = (_REPO / "knot").rglob("*.py")
    sites = []
    for py in src:
        if "tenant_context.py" in str(py):
            continue          # 定义处不算调用点
        for i, line in enumerate(py.read_text(encoding="utf-8").splitlines(), 1):
            if "assert_tenant_context(" in line and not line.strip().startswith("#"):
                sites.append(f"{py.relative_to(_REPO)}:{i}")
    assert sites, "assert_tenant_context 无生产调用点 —— B-4 漂移检查没接上"


def test_B4_drift_detected(tmp_db_path):
    """⭐ 新失败模式「ctx 非 None 但是错的租户」被抓住。

    `get_conn` 只判 ctx 是否为 None ⇒ **对本模式免疫**（按错 tid 建槽也会命中并返 200）。
    这正是 tripwire 存在的理由。
    """
    from knot.core.tenant_context import assert_tenant_context
    tok = tc.set_active_tenant({"id": 1, "db_dir": "."})
    try:
        assert_tenant_context(1)          # 一致 → 不抛
        with pytest.raises(TenantContextError, match="漂移"):
            assert_tenant_context(2)      # ctx 是 1、token 声明 2 → 抛
    finally:
        tc.reset_active_tenant(tok)


# ─── 7. step 6：漂移告警（结构化 WARN + 计数器） ──────────────────────────


def _loguru_sink():
    """挂 loguru sink 抓日志。

    ⚠️ **必须挂 loguru sink，不能用 `caplog`** —— 本仓 logger 是 loguru（`core/logging_setup`），
    `caplog` 只抓 stdlib logging ⇒ 用它写这类测是**同义反复**（v0.9.3 F-3' 已实证：把内容拼进
    日志后 caplog 版仍绿）。
    """
    from loguru import logger as _lg
    sink: list = []
    hid = _lg.add(lambda m: sink.append(str(m)), level="DEBUG", format="{message}")
    return sink, hid


def test_drift_emits_structured_warning_and_increments_counter(tmp_db_path):
    """⭐ 真漂移（ctx 设了但对不上）→ 固定事件名 WARN + 计数器 +1。

    事件名 `tenant_ctx_drift` 是**固定串**，便于运维 grep / 挂告警规则。
    revert-to-bad：删掉 `assert_tenant_context` 里的 `logger.warning(...)` → 本测转红。
    """
    from loguru import logger as _lg
    sink, hid = _loguru_sink()
    before = tc.tenant_drift_count()
    tok = tc.set_active_tenant({"id": 1, "db_dir": "."})
    try:
        with pytest.raises(TenantContextError, match="漂移"):
            tc.assert_tenant_context(2)
    finally:
        tc.reset_active_tenant(tok)
        _lg.remove(hid)
    blob = "".join(sink)
    assert "tenant_ctx_drift" in blob, f"没抓到固定事件名（sink 失效则本测退化为同义反复）：{blob[:200]}"
    assert "expected=2" in blob and "actual=1" in blob, blob[:200]
    assert tc.tenant_drift_count() == before + 1, "计数器未 +1"


def test_unset_ctx_is_not_reported_as_drift(tmp_db_path):
    """⭐ **未 set ≠ 漂移**：不告警、不计数。

    这是**噪音抑制契约**，不是洁癖：step 5 起「token 声明的租户已停用/不存在 → middleware 不设 ctx」
    是**预期路径**。若把它算成漂移，每个这类请求刷一条 WARN ⇒ **真漂移信号被淹没**。
    revert-to-bad：把 `assert_tenant_context` 里 `current is None` 那支也走 WARN+计数 → 本测转红。
    """
    from loguru import logger as _lg
    sink, hid = _loguru_sink()
    before = tc.tenant_drift_count()
    tok = tc._active_tenant_ctx.set(None)
    try:
        with pytest.raises(TenantContextError):
            tc.assert_tenant_context(1)
    finally:
        tc.reset_active_tenant(tok)
        _lg.remove(hid)
    assert "tenant_ctx_drift" not in "".join(sink), "未 set 被误报成漂移 → 真信号会被噪音淹没"
    assert tc.tenant_drift_count() == before, "未 set 被误计入漂移计数"


def test_drift_log_never_leaks_db_dir_or_paths(tmp_db_path):
    """漂移日志**只记 id**，不得记 `db_dir` / 路径（同 v0.9.3 F-3' 观测纪律：只记规模/来源，不记内容）。

    钉死方式：把 db_dir 设成可检索标记串，断言它不出现在任何一行日志里。
    revert-to-bad：把 `current` 整个 dict 拼进 log → 本测转红。
    """
    from loguru import logger as _lg
    sink, hid = _loguru_sink()
    tok = tc.set_active_tenant({"id": 1, "db_dir": "tenants/MARKER_SECRET_DBDIR_9x"})
    try:
        with pytest.raises(TenantContextError):
            tc.assert_tenant_context(2)
    finally:
        tc.reset_active_tenant(tok)
        _lg.remove(hid)
    blob = "".join(sink)
    assert "tenant_ctx_drift" in blob, "sink 失效（否则下一条断言退化为同义反复）"
    assert "MARKER_SECRET_DBDIR_9x" not in blob, f"漂移日志泄漏 db_dir：{blob[:300]}"


def test_R10_no_drift_audit_action_added():
    """⭐ R-10：本片**刻意不新增 `AuditAction`** —— LOCKED 的 audit-on-drift **仍未结清**。

    审计要写「哪个平台租户」，依赖 v0.9.5 platform/tenant admin 鉴权拆分的口径；且 `core` 层零
    services 依赖也让 audit 写入不能落在 `tenant_context`。本片的替代物 = WARN + 计数器。

    断言写成「**没有任何 action 含 drift**」而非「action 总数 == N」—— 后者会被将来任何无关的
    新 action 打红（假红），前者精确对应 R-10 的主张。同时断言替代机制**存在**（否则「没加审计」
    可能只是「什么都没做」）。
    """
    import typing

    from knot.models.audit import AuditAction
    actions = typing.get_args(AuditAction)
    assert actions, "AuditAction Literal 取不到成员 —— 断言已失效"
    drifty = [a for a in actions if "drift" in a.lower()]
    assert not drifty, (
        f"新增了漂移相关 AuditAction {drifty} —— R-10 明示本片不结清 audit-on-drift；"
        f"若确要结清，须走 v0.9.5 platform admin 拆分并同步撤掉本断言 + 撤掉未结清登记。"
    )
    assert callable(tc.tenant_drift_count), "替代机制（计数器）缺失 —— 「没加审计」不能等于「什么都没做」"
