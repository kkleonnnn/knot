"""v0.6.2.0 commit 6 — F6 TOTP 2FA 守护测试（γ3 强制 active 复核闸门）

覆盖 v2 LOCKED 13 红线 + NRP-1/2：
  R-PB-B1-1/8  Fernet enc_v1: 加密路径
  R-PB-B1-2    enroll 失败不锁死账号
  R-PB-B1-6    rate limit 5/min/user（verify）+ 3/hour/user（enroll）
  R-PB-B1-7    1 次码业界标准 + 10 recovery codes 格式
  R-PB-B1-9    R-46-Tx SQLite 事务（事务回滚 secret 未持久化）
  R-PB-B1-10   race 100× ± 5 守护（γ2 折中 + @race CI 独立 job 标记）
  R-PB-B1-11   audit_action +4（含 recovery_code_used）
  R-PB-B1-12   valid_window=1 ±30s 时钟漂移容忍
  R-PB-B1-13   JWT 吊销 user_secret_version
  NRP-1        cachetools per-key invalidate
"""
import sqlite3
from unittest.mock import patch

import pyotp
import pytest


# ─── autouse：每个测试前清 rate_limit bucket + token_version cache ──


@pytest.fixture(autouse=True)
def _reset_module_state():
    """v0.6.2.0 NRP-2 测试隔离：清 rate limit bucket + JWT cache 防 test 间污染。

    守护者第 16 次 active §II.1 议题 2（信息性）：未来 `_rate_limit` 模块新增 state
    （如 IP-based bucket / per-endpoint counter / per-route 限流）→ **本 fixture 必须同步更新**
    否则新 state 跨 test 泄露会导致间歇性失败。
    同理 `totp_service` 新增 module-level cache（如 user-info LRU / pyotp instance pool）也需扩。

    v0.6.5.2 F2：新增 `totp_enroll_complete:{uid}` 桶 — `_bucket._d.clear()` 全清已覆盖
    （新桶 key 与 init 桶同 dict）；契约：新增任何 enforce_* 桶无需改本 fixture（全清兜底）。
    """
    from knot.api._rate_limit import _bucket
    from knot.services import totp_service
    _bucket._d.clear()
    totp_service._TOKEN_VERSION_CACHE.clear()
    yield
    _bucket._d.clear()
    totp_service._TOKEN_VERSION_CACHE.clear()


# ─── R-PB-B1-12 valid_window=1 ±30s（直接验证 pyotp.verify 协议侧）──


def test_R_PB_B1_12_valid_window_pass_within_30s():
    """R-PB-B1-12：pyotp.verify(code, for_time=, valid_window=1) → ±30s 必通过。

    NRP-2：用 pyotp `for_time` 参数显式锁定时间（valid_window=1 容忍 ±1 步=±30s）。
    避 mock time.time（pyotp 内部用 datetime.now 不走 time.time）。
    """
    secret = pyotp.random_base32()
    totp = pyotp.TOTP(secret)
    t_base = 1700000000

    code = totp.at(t_base)
    for offset in [-30, 0, 30]:
        assert totp.verify(code, for_time=t_base + offset, valid_window=1), \
            f"t+{offset}s should pass with valid_window=1"


def test_R_PB_B1_12_valid_window_fail_beyond_60s():
    """R-PB-B1-12：±60s+ 必失败（防 NTP 偏移过宽弱化安全）。"""
    secret = pyotp.random_base32()
    totp = pyotp.TOTP(secret)
    t_base = 1700000000

    code = totp.at(t_base)
    for offset in [-90, -60, 60, 90]:
        assert not totp.verify(code, for_time=t_base + offset, valid_window=1), \
            f"t+{offset}s should fail with valid_window=1"


def test_R_PB_B1_12_service_layer_uses_valid_window():
    """R-PB-B1-12：totp_service 实际调用 pyotp.TOTP.verify 时必传 valid_window=1。

    grep service 源码确认参数（防未来误改 default 0）。
    """
    import inspect
    from knot.services import totp_service
    src = inspect.getsource(totp_service)
    # enroll_complete + verify 必含 valid_window=1
    assert "valid_window=1" in src, "totp_service 必含 valid_window=1（R-PB-B1-12）"


# ─── R-PB-B1-5 last_used_at 更新（守护者第 16 次议题 1 顺手补）─


def test_R_PB_B1_5_verify_updates_last_used_at(client, auth_headers):
    """R-PB-B1-5：verify 成功后 users.totp_last_used_at 必更新（5 次/月警报基线）。

    守护者第 16 次 active §I 议题 1 — 防 set_totp_last_used_at 未来被误删。
    """
    from knot.services import totp_service

    init = client.post("/api/totp/enroll-init", headers=auth_headers).json()
    code = pyotp.TOTP(init["secret"]).now()
    r = client.post("/api/totp/enroll-complete", headers=auth_headers,
                    json={"secret": init["secret"], "code": code})
    assert r.status_code == 200

    # 直接 service.verify 触发 last_used_at 更新（API 端点也走同 service）
    fresh_code = pyotp.TOTP(init["secret"]).now()
    ok = totp_service.verify(1, fresh_code)
    assert ok is True

    from knot.repositories import base
    conn = sqlite3.connect(base.SQLITE_DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT totp_last_used_at FROM users WHERE id=1").fetchone()
    conn.close()
    assert row["totp_last_used_at"] is not None, \
        "verify 成功后 last_used_at 必更新（5 次/月警报基线）"


# ─── R-PB-B1-1/8 Fernet enc_v1: 加密路径（集成测试）─────────────


def test_R_PB_B1_1_secret_fernet_encrypted_in_db(client, auth_headers):
    """R-PB-B1-1/8：enroll 完成后 sqlite3 直读 users.totp_secret 必含 enc_v1: 前缀。"""
    init = client.post("/api/totp/enroll-init", headers=auth_headers).json()
    secret = init["secret"]
    code = pyotp.TOTP(secret).now()
    complete = client.post("/api/totp/enroll-complete", headers=auth_headers,
                           json={"secret": secret, "code": code})
    assert complete.status_code == 200, f"enroll-complete failed: {complete.text}"

    from knot.repositories import base
    conn = sqlite3.connect(base.SQLITE_DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT totp_secret FROM users WHERE username='admin'").fetchone()
    conn.close()
    assert row["totp_secret"] is not None
    assert row["totp_secret"].startswith("enc_v1:"), \
        f"totp_secret 必 Fernet enc_v1: 前缀；实际首 30 字符: {row['totp_secret'][:30]}"
    assert secret not in row["totp_secret"], "明文 secret 严禁出现在 DB"


# ─── R-PB-B1-9 R-46-Tx 事务回滚 ────────────────────────────────────


def test_R_PB_B1_9_R46Tx_rollback_secret_not_persisted(client, auth_headers):
    """R-PB-B1-9：mock totp_repo.insert_recovery_codes_in_tx 失败 → secret 不持久化。"""
    from knot.services import totp_service

    init = client.post("/api/totp/enroll-init", headers=auth_headers).json()
    secret_plain = init["secret"]
    code = pyotp.TOTP(secret_plain).now()

    with patch("knot.repositories.totp_repo.insert_recovery_codes_in_tx",
               side_effect=sqlite3.IntegrityError("simulated insert failure")):
        with pytest.raises(sqlite3.IntegrityError):
            totp_service.enroll_complete(1, secret_plain, code)

    from knot.repositories import base
    conn = sqlite3.connect(base.SQLITE_DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT totp_secret, totp_enrolled_at FROM users WHERE id=1").fetchone()
    conn.close()
    assert row["totp_secret"] is None, "secret 必回滚（不持久化）"
    assert row["totp_enrolled_at"] is None


# ─── R-PB-B1-13 JWT 吊销 e2e + NRP-1 cachetools per-key invalidate ──


def test_R_PB_B1_13_reset_invalidates_old_jwt(client, auth_headers):
    """R-PB-B1-13：admin reset TOTP → 该用户旧 JWT 立即 401 JWT_REVOKED。"""
    from knot.repositories import user_repo
    from knot.services import totp_service

    init = client.post("/api/totp/enroll-init", headers=auth_headers).json()
    code = pyotp.TOTP(init["secret"]).now()
    client.post("/api/totp/enroll-complete", headers=auth_headers,
                json={"secret": init["secret"], "code": code})

    # admin reset 自己（实际 path 是 admin reset other user；这里测核心 token_version 机制）
    totp_service.reset(user_id=1)

    me = client.get("/api/auth/me", headers=auth_headers)
    assert me.status_code == 401, f"reset 后旧 JWT 应 401；实际 {me.status_code}"

    new_ver = user_repo.get_token_version(1)
    assert new_ver >= 2, f"reset 后 token_version 应 ≥2；实际 {new_ver}"


def test_R_PB_B1_13_change_password_invalidates_old_jwt(client, auth_headers):
    """R-PB-B1-13 + γ1：change_password 后旧 JWT 立即 401（OWASP A07:2021 防御）。"""
    resp = client.post("/api/auth/change-password", headers=auth_headers,
                       json={"old_password": "admin123", "new_password": "newpass123!"})
    assert resp.status_code == 200

    me = client.get("/api/auth/me", headers=auth_headers)
    assert me.status_code == 401, \
        f"change_password 后旧 JWT 应 401；实际 {me.status_code}（γ1 OWASP 防御）"


def test_NRP_1_cachetools_per_key_invalidate_only():
    """NRP-1：reset user_a 不污染 user_b 的 token_version cache。严禁 cache.clear() 全清。"""
    from knot.services import totp_service

    cache = totp_service._TOKEN_VERSION_CACHE
    cache[100] = 5
    cache[200] = 3

    totp_service.invalidate_token_version_cache(100)

    assert 100 not in cache, "user_a cache 应被清"
    assert 200 in cache, "user_b cache 严禁被波及（NRP-1）"
    assert cache[200] == 3


# ─── R-PB-B1-7 业界标准 1 次码 + recovery codes 格式 ─────────────


def test_R_PB_B1_7_enroll_returns_10_recovery_codes(client, auth_headers):
    """R-PB-B1-7：单次 6 位码验证通过 → 返 10 个 ABCDE-12345 格式 recovery codes。"""
    init = client.post("/api/totp/enroll-init", headers=auth_headers).json()
    code = pyotp.TOTP(init["secret"]).now()
    r = client.post("/api/totp/enroll-complete", headers=auth_headers,
                    json={"secret": init["secret"], "code": code})
    assert r.status_code == 200, f"enroll-complete failed: {r.text}"
    codes = r.json()["recovery_codes"]
    assert len(codes) == 10, f"应返 10 个 recovery codes；实际 {len(codes)}"
    for c in codes:
        assert len(c) == 11, f"recovery code 长度应 11；实际 {len(c)} ({c})"
        assert c[5] == "-", f"位置 5 应是 -；实际 ({c})"


def test_recovery_code_single_use(client, auth_headers):
    """单次使用语义：recovery code 第二次使用必失败。"""
    from knot.services import totp_service

    init = client.post("/api/totp/enroll-init", headers=auth_headers).json()
    code = pyotp.TOTP(init["secret"]).now()
    r = client.post("/api/totp/enroll-complete", headers=auth_headers,
                    json={"secret": init["secret"], "code": code})
    assert r.status_code == 200
    rc = r.json()["recovery_codes"][0]

    assert totp_service.consume_recovery(1, rc) is True
    assert totp_service.consume_recovery(1, rc) is False


# ─── R-PB-B1-2 enroll 失败不锁死账号 ───────────────────────────────


def test_R_PB_B1_2_enroll_failure_does_not_lock_account(client, auth_headers):
    """R-PB-B1-2：enroll-complete 错误码失败 → totp_enrolled_at 仍 NULL；用户可重新 enroll。"""
    init = client.post("/api/totp/enroll-init", headers=auth_headers).json()
    r = client.post("/api/totp/enroll-complete", headers=auth_headers,
                    json={"secret": init["secret"], "code": "000000"})
    assert r.status_code == 400

    from knot.repositories import base
    conn = sqlite3.connect(base.SQLITE_DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT totp_enrolled_at FROM users WHERE id=1").fetchone()
    conn.close()
    assert row["totp_enrolled_at"] is None, "失败 enroll 不应锁死账号"

    # 用户可重新 enroll（同 init 后再 complete with 正确 code）
    correct_code = pyotp.TOTP(init["secret"]).now()
    r2 = client.post("/api/totp/enroll-complete", headers=auth_headers,
                     json={"secret": init["secret"], "code": correct_code})
    assert r2.status_code == 200, f"重新 enroll 应可成功；实际 {r2.text}"


# ─── R-PB-B1-11 audit_action +4 入库守护 ─────────────────────────


def test_R_PB_B1_11_enroll_audit_action_inserted(client, auth_headers):
    """R-PB-B1-11：enroll API 路径触发 user.totp.enroll audit INSERT。

    reset / recovery_code_used 走 api 端点（admin reset 需 require_admin；
    recovery_code_used 在 verify 端点 login_recovery 流程）— audit 调用点在 api 层。
    本测仅 enroll 路径；Literal 完整性由 test_R_PB_B1_11_audit_action_literal 守护。
    """
    init = client.post("/api/totp/enroll-init", headers=auth_headers).json()
    code = pyotp.TOTP(init["secret"]).now()
    r = client.post("/api/totp/enroll-complete", headers=auth_headers,
                    json={"secret": init["secret"], "code": code})
    assert r.status_code == 200

    from knot.repositories import base
    conn = sqlite3.connect(base.SQLITE_DB_PATH)
    actions = {r[0] for r in conn.execute(
        "SELECT DISTINCT action FROM audit_log WHERE action LIKE 'user.totp.%'"
    ).fetchall()}
    conn.close()
    assert "user.totp.enroll" in actions, \
        f"enroll-complete API 应触发 user.totp.enroll audit；实际 actions: {actions}"


def test_R_PB_B1_11_audit_action_literal_contains_4_totp():
    """R-PB-B1-11：AuditAction Literal 含 4 个 TOTP action（commit 4 落地）。"""
    import typing

    from knot.models.audit import AuditAction
    actions = set(typing.get_args(AuditAction))
    expected = {"user.totp.enroll", "user.totp.verify_failed",
                "user.totp.reset", "user.totp.recovery_code_used"}
    assert expected <= actions, f"AuditAction Literal 缺失：{expected - actions}"


# ─── R-72 routes count smoke（4 新 totp routes）────────────────────


def test_routes_count_v062_totp_endpoints():
    """v0.6.2.0 commit 3+5 加 4 TOTP endpoints；R-72 routes 必含全 4 个。

    v0.6.2.5 commit 7：经 app_route_paths 动态展平（FastAPI 0.137+ _IncludedRouter 懒包装）。
    """
    from knot.main import app

    from tests._route_count import app_route_paths
    paths = app_route_paths(app)
    expected = {"/api/totp/enroll-init", "/api/totp/enroll-complete",
                "/api/totp/verify", "/api/totp/reset"}
    assert expected <= paths, f"4 TOTP endpoints 必全存在；缺失 {expected - paths}"


# ─── R-PB-B1-10 race 100× ± 5（γ2 折中 + @race mark CI 独立 job）─


@pytest.mark.race
def test_R_PB_B1_10_race_100x_rate_limit_within_tolerance(client, auth_headers):
    """R-PB-B1-10：100× verify 错误码 → rate_limited ≥ 90（误差 ≤ γ2 ±5）。

    rate_limit 5/min/user → 最多 5 次允许 + ≥ 95 次 rate-limited。误差 ≤ 5 容忍 CI 抖动。
    NRP-2 sustained：autouse fixture 已清 bucket（隔离前测影响）。
    """
    # Step 1: enroll admin
    init = client.post("/api/totp/enroll-init", headers=auth_headers).json()
    code = pyotp.TOTP(init["secret"]).now()
    enroll = client.post("/api/totp/enroll-complete", headers=auth_headers,
                         json={"secret": init["secret"], "code": code})
    assert enroll.status_code == 200

    # Step 2: re-login → 应返 {need_totp: true, interim_token}
    login = client.post("/api/auth/login",
                        json={"username": "admin", "password": "admin123"})
    assert login.status_code == 200, f"login failed: {login.text}"
    body = login.json()
    assert body.get("need_totp") is True, \
        f"enroll 后 login 应返 need_totp；实际 {body}"
    interim_token = body["interim_token"]

    # Step 3: 100× 错误码 verify（用 interim_token + 错误 code）
    rate_limited_count = 0
    success_count = 0
    for _ in range(100):
        r = client.post("/api/totp/verify",
                        json={"interim_token": interim_token, "code": "000000"})
        if r.status_code == 429:
            rate_limited_count += 1
        elif r.status_code == 200:
            success_count += 1

    # rate_limit 5/min/user → ≥ 95 次 rate-limited；γ2 误差 ≤ 5
    assert rate_limited_count >= 90, \
        f"rate-limited 应 ≥90；实际 {rate_limited_count}（γ2 ±5）"
    assert success_count == 0, "错误码不应成功"


# ─── v0.6.5.2 F2 — enroll-complete 独立分桶（白屏 enroll 卡死根因） ──────


def test_F2_enroll_complete_not_blocked_by_exhausted_init_bucket(client, auth_headers):
    """v0.6.5.2 F2：打满 enroll-init 桶（3/hour）后，enroll-complete 仍 200。

    旧 bug：init 与 complete 共用 totp_enroll 桶 → 一次正常绑定耗 init 预算 +
    屏 remount 重调 init → complete 被 init 桶拖死 429 卡死 1 小时。
    F2 分桶后 complete 走独立 totp_enroll_complete 桶（10/hour）→ 不受 init 桶影响。
    """
    secret = None
    for _ in range(3):  # 打满 init 桶（3/hour）
        r = client.post("/api/totp/enroll-init", headers=auth_headers)
        assert r.status_code == 200
        secret = r.json()["secret"]
    # 第 4 次 init 必 429（证 init 桶确已满）
    r4 = client.post("/api/totp/enroll-init", headers=auth_headers)
    assert r4.status_code == 429, f"init 桶应已满；实际 {r4.status_code}"
    # 但 enroll-complete 走独立桶 → 仍 200（核心断言：不被 init 桶拖死）
    code = pyotp.TOTP(secret).now()
    rc = client.post("/api/totp/enroll-complete", headers=auth_headers,
                     json={"secret": secret, "code": code})
    assert rc.status_code == 200, \
        f"enroll-complete 不应被耗尽的 init 桶阻塞；实际 {rc.status_code} {rc.text}"


def test_F2_enroll_complete_retry_under_10_then_succeeds(client, auth_headers):
    """v0.6.5.2 F2：enroll-complete 错码重试 <10 次（桶上限）→ 正确码仍可成功。

    错码返 400（业务失败，非限流）；5 错 + 1 正确 = 6 < 10 桶上限 → 不触顶。
    """
    init = client.post("/api/totp/enroll-init", headers=auth_headers).json()
    secret = init["secret"]
    for _ in range(5):  # 5 次错码（< 10 桶上限）
        r = client.post("/api/totp/enroll-complete", headers=auth_headers,
                        json={"secret": secret, "code": "000000"})
        assert r.status_code == 400, f"错码应 400 非 429；实际 {r.status_code}"
    # 正确码仍可成功（桶未触顶）
    code = pyotp.TOTP(secret).now()
    r = client.post("/api/totp/enroll-complete", headers=auth_headers,
                    json={"secret": secret, "code": code})
    assert r.status_code == 200, \
        f"<10 错码后正确码应成功；实际 {r.status_code} {r.text}"
