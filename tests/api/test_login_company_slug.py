"""v0.9.4 step 7 — 登录带公司代号 + 统一错误 + 五分支各恰一次 bcrypt（D4'/D4'-b/D4''）。

kk 2026-07-27 三条拍板落在本文件：
① 每家公司一条**专属登录链接**（代号在网址 `?c=<slug>`，前端回传请求体 `company`）——
   复用**已存在**的 `tenants.slug`（NOT NULL UNIQUE）⇒ 不需要 user_directory 表、不需要用户名
   全局唯一，各租户照样可各有 `admin`（避开与 seed 逻辑的正面冲突）。
② 登录失败**四类（实为五类）同一句「账号或密码错误」**，防公司/账号枚举。
③ per-tenant 初始口令**延后**（已登记 R-T-GATE 清单）。

**统一错误必须堵住两条通道，缺一不可**：
- 「读得到的差异」→ 同一 status + 同一 detail（`test_five_failure_branches_identical_response`）
- 「耗时差异」→ 每支各跑恰一次 bcrypt（`test_five_branches_each_run_exactly_one_bcrypt`）
  F-5 裁定：CI 主门用**确定性的调用计数**，不用墙钟阈值 —— 两天前 `test_R53` 的绝对阈值假红
  就是墙钟阈值在共享 runner 上不可靠的实证。
"""
import pytest

from knot.services import auth_service

_UNIFIED = "账号或密码错误"


def _login(client, username="admin", password="admin123", company=None):
    body = {"username": username, "password": password}
    if company is not None:
        body["company"] = company
    return client.post("/api/auth/login", json=body)


def _suspend_tenant(tid=1):
    from knot.repositories import tenant_repo
    conn = tenant_repo.get_platform_conn()
    conn.execute("UPDATE tenants SET status='suspended' WHERE id=?", (tid,))
    conn.commit()
    conn.close()


def _make_inactive_user(username="ghost_inactive"):
    """建一个 is_active=0 的用户（分支④）。`create_user` 返 bool 且要 5 个 doris 参数（既有签名）。"""
    from knot.repositories import user_repo
    ok = user_repo.create_user(username, auth_service.hash_password("realpass123"),
                               username, "user", "", 9030, "", "", "")
    assert ok, f"建用户失败（重名？）：{username}"
    row = user_repo.get_user_by_username(username)
    user_repo.update_user(row["id"], is_active=0)
    assert user_repo.get_user_by_username(username)["is_active"] == 0, "前提：用户须为停用态"
    return username


# ─── 1. 正常路径：带代号 / 不带代号 ─────────────────────────────────────


def test_login_with_correct_company_slug_succeeds(client):
    """带正确公司代号 → 200，且签出的 token 指向该公司。"""
    import jwt
    r = _login(client, company="default")
    assert r.status_code == 200, r.text[:200]
    assert jwt.decode(r.json()["token"], options={"verify_signature": False})["tid"] == 1


def test_login_without_company_still_works_while_gate_locked(client):
    """不带代号 → 回退到唯一 active 租户。

    ⚠️ 这是**有条件的临时允许**：允许的唯一理由是 R-T-GATE 仍硬锁第二租户 ⇒ 单租户下
    「唯一 active」与「按代号解析」等价。**已登记 R-T-GATE 清单：lift 前必须把 `company` 改必填**，
    否则「不带代号 → 随便进某家公司」= OOS-1v2 fail-open。
    现在不直接必填的原因：会把当前内测部署的所有人挡在门外（老链接无 `?c=`）。
    """
    assert _login(client).status_code == 200


def test_login_with_wrong_case_slug_is_rejected(client):
    """代号**精确匹配**（大小写敏感）：`Default` ≠ `default` → 统一 401。

    为何不做大小写不敏感：`slug` 的 UNIQUE 本身大小写敏感 ⇒ `abc` 与 `ABC` 可同时存在，
    不敏感匹配只能返一行 = **不确定地把用户送进某家公司**。链接是系统生成的，精确匹配代价可忽略。
    """
    r = _login(client, company="Default")
    assert r.status_code == 401 and r.json()["detail"] == _UNIFIED, r.text[:160]


# ─── 2. ⭐ 五分支同一响应（防公司/账号枚举） ─────────────────────────────


def test_five_failure_branches_identical_response(client):
    """⭐ 五个失败分支的 (status, body) **必须逐字相同**。

    任何差异都是枚举通道：能区分「代号不存在」→ 枚举公司；能区分「用户不存在」→ 枚举账号。
    revert-to-bad：把任一分支的 detail 改成别的字面（如「公司代号无效」）→ 本测转红。
    """
    inactive = _make_inactive_user()
    got = {}
    got["③用户不存在"] = _login(client, username="no_such_user_xyz")
    got["④用户已停用"] = _login(client, username=inactive, password="realpass123")
    got["⑤口令错"] = _login(client, password="wrong-password-zz")
    got["①代号不存在"] = _login(client, company="no-such-company-xyz")
    # ②租户停用必须最后做（它会让 ③④⑤ 不可达）
    _suspend_tenant()
    got["②租户停用"] = _login(client, company="default")

    shapes = {k: (r.status_code, r.text) for k, r in got.items()}
    uniq = set(shapes.values())
    assert len(uniq) == 1, (
        "五分支响应不一致 ⇒ 可枚举公司/账号：\n"
        + "\n".join(f"  {k}: {v[0]} {v[1][:90]}" for k, v in shapes.items())
    )
    assert next(iter(uniq))[0] == 401
    assert got["⑤口令错"].json()["detail"] == _UNIFIED


def test_failure_response_never_leaks_branch_reason(client):
    """审计里记的 `reason`（user_not_found / user_inactive / bad_password）**绝不进响应体**。"""
    for kw in ("user_not_found", "user_inactive", "bad_password", "tenant", "slug", "company"):
        r = _login(client, username="no_such_user_xyz")
        assert kw not in r.text, f"响应泄漏分支原因关键字 {kw!r}：{r.text[:160]}"


# ─── 3. ⭐ 每支恰一次 bcrypt（F-5 确定性门，非墙钟） ──────────────────────


@pytest.fixture()
def bcrypt_counter(monkeypatch):
    """统计 `bcrypt.checkpw` 调用次数。

    刻意计 **bcrypt.checkpw 本身**（而非 `auth_service.verify_password` 包装）——
    包装可能被绕过/内联，计到底层才钉得住「真的跑了一次密码哈希」。
    先 warm up 假 hash：它走 `bcrypt.hashpw`（不计入 checkpw），否则首个分支会多算。
    """
    auth_service.consume_password_time("warmup")     # 建 _dummy_hash（hashpw，不计）
    calls = []
    real = auth_service.bcrypt.checkpw

    def counting(*a, **kw):
        calls.append(1)
        return real(*a, **kw)

    monkeypatch.setattr(auth_service.bcrypt, "checkpw", counting)
    return calls


def test_five_branches_each_run_exactly_one_bcrypt(client, bcrypt_counter):
    """⭐ D4'-b/R4：五个失败分支**各恰一次** bcrypt。

    **为何必须显式补**：`authenticate` 原是短路 `and` ⇒ 只有「口令错」那支跑 bcrypt，其余四支
    立即返回。统一文案只堵住读得到的差异，**耗时差异仍可测** ⇒ 攻击者据此枚举公司/账号。
    revert-to-bad：删掉 `authenticate_with_reason` 里任一 `consume_password_time(...)`
    或登录端点里代号分支那一处 → 该分支计数变 0 → 本测转红。
    """
    inactive = _make_inactive_user()
    cases = [
        ("③用户不存在", lambda: _login(client, username="no_such_user_xyz")),
        ("④用户已停用", lambda: _login(client, username=inactive, password="realpass123")),
        ("⑤口令错", lambda: _login(client, password="wrong-password-zz")),
        ("①代号不存在", lambda: _login(client, company="no-such-company-xyz")),
    ]
    counts = {}
    for name, fn in cases:
        bcrypt_counter.clear()
        r = fn()
        counts[name] = len(bcrypt_counter)
        assert r.status_code == 401, f"{name} 应 401，实得 {r.status_code}"
    _suspend_tenant()
    bcrypt_counter.clear()
    assert _login(client, company="default").status_code == 401
    counts["②租户停用"] = len(bcrypt_counter)

    bad = {k: v for k, v in counts.items() if v != 1}
    assert not bad, (
        f"以下分支的 bcrypt 次数 ≠ 1 ⇒ 耗时可区分 = 枚举通道：{bad}（全部：{counts}）"
    )


def test_success_path_runs_exactly_one_bcrypt(client, bcrypt_counter):
    """成功路径也恰一次（对照组：否则「各支 1 次」可能是靠成功支多跑凑出来的）。"""
    bcrypt_counter.clear()
    assert _login(client).status_code == 200
    assert len(bcrypt_counter) == 1, f"成功路径 bcrypt {len(bcrypt_counter)} 次"


# ─── 4. R-13：登录入口无条件清 ctx ──────────────────────────────────────


def test_login_clears_inherited_ctx_at_entry(client, admin_token, monkeypatch):
    """⭐ R-13：登录入口清 ctx —— 「清 ctx 到 set-ctx 之间」读 ctx 必须**当场崩**。

    为何承重（B-5）：前端 axios 拦截器会把 Authorization 带到登录请求上，middleware 据此把 ctx
    设成那张 token 的公司。若登录不清，`_resolve_login_tenant` 之前的任何 ctx 读取都会串到那家公司。

    ⚠️ **本测初版是同义反复**（自我记录）：初版发的登录请求**不带 Authorization** ⇒ middleware
    本来就没设 ctx ⇒ 入口「清」的时候没东西可清，删掉 `clear_active_tenant()` 也一样 RAISED。
    revert 实测：删清空 → **29 测全绿**。改为**带一张有效 token** 发登录请求（middleware 会设 ctx）
    后，同一 revert 才转红。教训：**验「清空」的测，必须先确保有东西可清。**

    单租户下「串到别家公司」协议上不可表达 ⇒ 这里测的是**不变量本身**（前缀内读 ctx 即 raise），
    不假装验了跨租户场景。
    """
    from knot.api import auth as auth_mod
    from knot.core import tenant_context as tc
    seen = {}
    real = auth_mod._resolve_login_tenant

    def spy(company):
        try:
            seen["ctx"] = tc.current_tenant()["id"]
        except tc.TenantContextError:
            seen["ctx"] = "RAISED"
        return real(company)

    monkeypatch.setattr(auth_mod, "_resolve_login_tenant", spy)
    # 带有效 token ⇒ middleware 会把 ctx 设成 tenant#1（= 有东西可清，本测才有判别力）
    r = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"},
                    headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200, r.text[:160]
    assert seen["ctx"] == "RAISED", (
        f"登录入口未清 ctx：解析租户前读到 ctx={seen['ctx']} —— 带 Authorization 时会串到那张 token 的公司"
    )


def test_login_entry_clear_precondition_middleware_does_set_ctx(client, admin_token, monkeypatch):
    """上一条测的**前提校验**：带 token 的登录请求，middleware 确实会设 ctx。

    没有这条，上一条测一旦因「middleware 不再设 ctx」而恒 RAISED，就会静默退化成同义反复
    （正是它初版踩的坑）。此处把那个前提显式钉住。
    """
    from knot.api import auth as auth_mod
    from knot.core import tenant_context as tc
    seen = {}
    real = auth_mod._resolve_login_tenant

    def spy(company):
        seen["ctx_before_clear_would_be"] = tc._active_tenant_ctx.get()
        return real(company)

    # 把入口清空临时换成 no-op，观察 middleware 到底设没设
    monkeypatch.setattr(auth_mod, "clear_active_tenant", lambda: tc._active_tenant_ctx.set(
        tc._active_tenant_ctx.get()))
    monkeypatch.setattr(auth_mod, "_resolve_login_tenant", spy)
    client.post("/api/auth/login", json={"username": "admin", "password": "admin123"},
                headers={"Authorization": f"Bearer {admin_token}"})
    got = seen.get("ctx_before_clear_would_be")
    assert got is not None and got.get("id") == 1, (
        f"前提不成立：带有效 token 时 middleware 没设 ctx（实得 {got}）"
        f" ⇒ 上一条 R-13 测会退化成同义反复"
    )
