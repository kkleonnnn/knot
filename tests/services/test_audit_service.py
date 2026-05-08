"""tests/services/test_audit_service.py — v0.4.6 commit #2 守护测试（TDD）。

覆盖：
- R-47 repo.insert 失败 → fail-soft（business 不阻断）
- R-48 PII 字段名命中 → ••••redacted••••
- R-48/D7 嵌套 PII 在深度 3 内被 scrub；超过深度 3 整体 redact（防递归炸弹）
- R-51 actor 必从函数参数（token 解析后）取，client body actor_id 字段被忽略
- R-59 加密值（含 enc_v1: 前缀）也走 scrub —— 字段名命中即 redact
- R-62 v0.4.5 锁定的 6 类敏感字段**全部**被 scrub（与 settings_repo._SENSITIVE_KEYS 对齐）
- R-64 失败盲区可观测：模块级失败计数器 hook 预埋
- R-65 audit_service 不重定义异常类（守 errors 树复用）
"""
import pytest

from bi_agent.services import audit_service


_REDACTED = "••••redacted••••"


# ─── R-48 PII scrub 顶层 + 嵌套 ──────────────────────────────────────

def test_R48_pii_scrubbed_top_level():
    detail = {"action": "user.create", "password": "plaintext"}
    out = audit_service._scrub(detail)
    assert out["password"] == _REDACTED
    assert out["action"] == "user.create"  # 非 PII 不动


def test_R48_nested_pii_scrubbed_at_depth_2():
    detail = {"changes": {"new": {"api_key": "sk-real"}}}
    out = audit_service._scrub(detail)
    # depth 2 仍在限内（_MAX_DEPTH=3），api_key 应被 redact
    assert out["changes"]["new"]["api_key"] == _REDACTED


# ─── D7 递归深度限制 ────────────────────────────────────────────────

def test_D7_recursion_bomb_safely_truncated_at_depth_3():
    """构造深度 100 的嵌套，verify 不爆栈 + 深度超限处整体 redact。"""
    bomb = {"x": {}}
    cur = bomb
    for _ in range(100):
        cur["x"] = {"x": {}}
        cur = cur["x"]
    out = audit_service._scrub(bomb)
    # 不爆栈即通过；产物在某层后变成 redacted 标记
    s = str(out)
    assert _REDACTED in s


# ─── R-59 密文也不入（字段名命中即 redact）──────────────────────────

def test_R59_encrypted_value_not_in_audit():
    """v0.4.5 加密的 6 类字段，即使值是 enc_v1: 密文，也应被 scrub。"""
    detail = {
        "api_key": "enc_v1:gAAAAABp_real_ciphertext_xxx==",
        "doris_password": "enc_v1:another_ciphertext",
    }
    out = audit_service._scrub(detail)
    assert out["api_key"] == _REDACTED
    assert out["doris_password"] == _REDACTED
    assert "enc_v1:" not in str(out), "R-59：密文形式也不入 audit"


# ─── R-62 v0.4.5 全 6 类敏感字段回归 ────────────────────────────────

def test_R62_v045_sensitive_fields_all_scrubbed():
    """v0.4.5 R-38 / R-43 锁定的全部敏感字段必须命中 _PII_BLACKLIST。"""
    # 与 v0.4.5 user_repo._USER_ENCRYPTED_COLS + data_source_repo._DS_ENCRYPTED_COLS +
    # settings_repo._SENSITIVE_KEYS 完全一致
    v045_sensitive = [
        "api_key",            # users + 用户级
        "openrouter_api_key",  # users + app_settings
        "embedding_api_key",   # users + app_settings
        "doris_password",     # users
        "db_password",        # data_sources
    ]
    detail = {k: f"plain-secret-{k}" for k in v045_sensitive}
    detail["password"] = "user-password-too"   # bonus check（非 v0.4.5 加密但仍 PII）
    detail["password_hash"] = "bcrypt$..."
    out = audit_service._scrub(detail)
    for k in v045_sensitive + ["password", "password_hash"]:
        assert out[k] == _REDACTED, f"R-62 失败：{k} 未被 scrub"


def test_R62_blacklist_synced_with_v045():
    """硬性断言：_PII_BLACKLIST 必须含 v0.4.5 全 6 类敏感字段名。"""
    required = {"api_key", "openrouter_api_key", "embedding_api_key",
                "doris_password", "db_password"}
    missing = required - audit_service._PII_BLACKLIST
    assert not missing, f"R-62：_PII_BLACKLIST 漏掉 v0.4.5 字段：{missing}"


# ─── R-51 actor 从 token 取 ──────────────────────────────────────────

def test_R51_actor_from_dict_param_not_payload(tmp_db_path):
    """actor 参数（来自 Depends(get_current_user)）优先于任何 detail 中的 actor_id。"""
    real_user = {"id": 1, "role": "admin", "username": "admin"}
    audit_service.log(
        actor=real_user,
        action="user.create",
        resource_type="user",
        resource_id=42,
        # 模拟客户端伪造（恶意）— 应被忽略
        detail={"actor_id": 999, "actor_name": "imposter"},
    )
    from bi_agent.repositories import audit_repo
    rows = audit_repo.list_filtered(page=1, size=10)
    assert len(rows) == 1
    assert rows[0]["actor_id"] == 1, "R-51：actor_id 必须来自 token，不能信 detail"
    assert rows[0]["actor_name"] == "admin"


def test_R51_anonymous_actor_allowed_for_failed_login(tmp_db_path):
    """D5：失败登录 actor=None；audit_repo.actor_id=NULL；actor_name 可记尝试的 username。"""
    audit_service.log(
        actor=None,
        action="auth.login_fail",
        resource_type="user",
        detail={"attempted_username": "alice"},
    )
    from bi_agent.repositories import audit_repo
    rows = audit_repo.list_filtered(page=1, size=10)
    assert len(rows) == 1
    assert rows[0]["actor_id"] is None


# ─── R-47 fail-soft + R-64 counter hook ─────────────────────────────

def test_R47_repo_insert_fails_business_continues(tmp_db_path, monkeypatch):
    """mock repo.insert 抛错 → audit_service.log 静默吞，不抛出。"""
    from bi_agent.repositories import audit_repo as ar

    def _boom(**kwargs):
        raise RuntimeError("simulated repo failure")

    monkeypatch.setattr(ar, "insert", _boom)

    # 不应抛 — fail-soft（R-47）
    audit_service.log(
        actor={"id": 1, "role": "admin", "username": "admin"},
        action="user.create",
        resource_type="user",
    )


def test_R64_failure_increments_metric_counter(tmp_db_path, monkeypatch):
    """R-64：写入失败时模块级 counter 累加（prometheus hook 预埋）。"""
    from bi_agent.repositories import audit_repo as ar

    def _boom(**kwargs):
        raise RuntimeError("simulated")

    monkeypatch.setattr(ar, "insert", _boom)

    before = audit_service.get_failure_count()
    audit_service.log(
        actor={"id": 1, "role": "admin", "username": "admin"},
        action="user.create", resource_type="user",
    )
    after = audit_service.get_failure_count()
    assert after == before + 1


# ─── R-65 errors 树复用守护 ──────────────────────────────────────────

def test_R65_audit_service_does_not_redefine_exceptions():
    """R-65 grep 守护：audit_service 模块不得定义新的 Exception 子类。"""
    import inspect
    src = inspect.getsource(audit_service)
    # 不允许 `class XxxError(Exception)` 或 `class XxxError(BIAgentError)`
    assert "class " not in src or "Error" not in src.split("class ", 1)[-1].split(":", 1)[0], \
        "R-65：audit_service 不得重定义 Exception 子类（必须复用 models/errors.py）"


# ─── service 层不强制 schema 校验（守护者前瞻提醒）─────────────────

def test_service_does_not_validate_business_schema(tmp_db_path):
    """守护者前瞻：service 层只 PII scrub，不做业务字段校验；
    detail 缺字段 / 多字段 / 空 dict 都应顺利写入。"""
    actor = {"id": 1, "role": "admin", "username": "admin"}
    # 三种调用形态都不应抛
    audit_service.log(actor=actor, action="user.create", resource_type="user", detail=None)
    audit_service.log(actor=actor, action="user.create", resource_type="user", detail={})
    audit_service.log(actor=actor, action="user.create", resource_type="user",
                      detail={"any_random_field": 123})
    from bi_agent.repositories import audit_repo
    rows = audit_repo.list_filtered(page=1, size=10)
    assert len(rows) == 3
