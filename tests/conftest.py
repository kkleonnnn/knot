"""tests/conftest.py — 全局 fixture（v0.4.5 R-37 master key 隔离 + tmp_db_path）。

R-37：测试 master key 用 monkeypatch.setenv + autouse fixture 隔离；
严禁 import-time 污染生产 env。所有测试默认拿到一个固定的测试 key，
单独需要测「缺失 / 无效」场景的测试用 monkeypatch.delenv / setenv 自己覆盖。
"""
import os
import tempfile

import pytest

# 固定测试 master key — 守护者 Q4 决策：硬编码胜过 env-driven。
# ⚠️ 该 key 仅用于测试；严禁用于任何生产环境 / staging / 真实部署。
# 该 key 不是 secret — 任何人均可调 Fernet.generate_key() 产出等价 key；
# 硬编码是为测试可重现性（避免 CI 多 worker / 并行测试时 env 污染）。
# 移除/改动测试时需同步更新。
TEST_MASTER_KEY = "QwlGZIGjzEryd93omq5UGR5ATZ6mTMm70NmS4o331Xk="
TEST_JWT_SECRET = "test-only-jwt-secret-32-chars-min-len-padding"

# v0.6.0.8 MUST-1：测试 JWT_SECRET 必须 import 前设置（main.py fail-fast 在 import 时跑）
# os.environ 直写而非 monkeypatch — autouse fixture 时机太晚（module import 已发生）
os.environ.setdefault("JWT_SECRET", TEST_JWT_SECRET)

# v0.6.5.2 F4-1（守护者 Stage 3 硬条件）：KNOT_TOTP_REQUIRED 必须 import 前设 false。
# main.py 模块级 apply_rollout_session_invalidation() 在 import 时跑（同 init_db / _seed_prompts）；
# 默认 "true" 会在 import 时对 default DB 误 bump 全员 token_version。autouse L下方 的 setenv
# 是 function-scoped（import 后才生效，太晚）—— 同款 import-timing 陷阱（见 JWT_SECRET 上行）。
# 模块级 setdefault 使 rollout bump 在 import 时确定性走 totp_not_required skip。
# 验「真 default-on」rollout 行为的守护测试用 monkeypatch.delenv("KNOT_TOTP_REQUIRED") 揭真默认。
os.environ.setdefault("KNOT_TOTP_REQUIRED", "false")

# v0.6.5.3 flaky 根因修：禁用测试期 startup audit auto-purge。该 hook 的 fire-and-forget
# create_task（不 await）延迟执行时 get_conn() 读 *当前* monkeypatched SQLITE_DB_PATH（已是
# 后续测试的 tmp DB）→ purge 线程与该测试 init_db 的 PRAGMA journal_mode=WAL 抢锁 →
# "database is locked" 随机落点 ERROR（非确定性 = PYTHONHASHSEED 影响调度时机）。
# 模块级 setdefault（hook 在 startup event 读 env；须 main import 前 / 首个 TestClient 前设）。
os.environ.setdefault("KNOT_SKIP_STARTUP_AUTO_PURGE", "1")


def _reset_module_level_caches():
    """v0.6.5.3 flaky 修：清三类模块级可变缓存（跨测试 state 泄露根因 class）。

    每个 client/tmp_db_path fixture 用独立 tmp SQLite + os.unlink 删除；下列缓存若持有
    指向已删 tmp DB 的 engine / 跨测试数据 → 后续测试命中作废缓存 → sqlite error / 数据污染。
    按 import 失败容忍（早期 commit / 部分模块未建场景）。dispose 释放连接池 best-effort。
    """
    try:
        from knot.services import engine_cache
        for _entry in list(engine_cache._engine_cache.values()):
            try:
                _eng = _entry.get("engine") if isinstance(_entry, dict) else None
                if _eng is not None and hasattr(_eng, "dispose"):
                    _eng.dispose()
            except Exception:
                pass
        engine_cache._engine_cache.clear()
    except ImportError:
        pass
    try:
        from knot.api import admin as _admin_mod
        _admin_mod._DS_STATS_CACHE["data"] = None
        _admin_mod._DS_STATS_CACHE["ts"] = 0.0
    except (ImportError, AttributeError):
        pass
    try:
        from knot.services import totp_service as _totp_svc
        _totp_svc._TOKEN_VERSION_CACHE.clear()
    except (ImportError, AttributeError):
        pass


@pytest.fixture(autouse=True)
def _master_key_for_tests(monkeypatch):
    """为每个测试默认设置 KNOT_MASTER_KEY；清空 lru_cache 防 fixture 间污染（R-40）。

    v0.6.0 F13/F14.2 单源化：直接走 KNOT_MASTER_KEY 路径
    （v0.5.0 双源兼容已撤回；test_env_dual_source.py 已删）。
    """
    monkeypatch.setenv("KNOT_MASTER_KEY", TEST_MASTER_KEY)
    # v0.6.5.0 R-2FA-4：默认 off 隔离全套（默认翻 on 后，未 enroll 的 admin fixture 会在
    # 所有受保护端点吃 403）。验「真 default-on」的守护测试用 monkeypatch.delenv 揭真默认。
    monkeypatch.setenv("KNOT_TOTP_REQUIRED", "false")
    # 清 lru_cache（防上一测试持有了不同 key 的 adapter）
    try:
        from knot.core.crypto.fernet import get_crypto_adapter
        get_crypto_adapter.cache_clear()
    except ImportError:
        pass  # commit #1 之前 crypto 模块还没建
    # v0.6.0.23 — 重置 rate limiter（测试 client 共享同 IP；防 login 限流跨测试污染）
    try:
        from knot.api._rate_limit import _reset_for_tests
        _reset_for_tests()
    except ImportError:
        pass  # v0.6.0.23 之前 _rate_limit 模块还没建
    # v0.6.5.3 flaky 修：清模块级可变缓存防测试间 state 泄露。三类缓存（TTL）survive 跨测试，
    # 此前无 autouse 清理：① engine_cache._engine_cache 缓存 engine 指向 tmp DB（tmp 删后命中
    # → engine.connect() sqlite "unable to open" ERROR）② admin._DS_STATS_CACHE 跨测试 stats 数据污染
    # ③ totp_service._TOKEN_VERSION_CACHE token_version 残留。非确定性触发（PYTHONHASHSEED）→ flaky。
    _reset_module_level_caches()
    yield
    try:
        from knot.core.crypto.fernet import get_crypto_adapter
        get_crypto_adapter.cache_clear()
    except ImportError:
        pass


@pytest.fixture()
def tmp_db_path(monkeypatch):
    """临时 SQLite — repositories / scripts 测试共用（v0.4.5 hoist）。

    base.py 在 import 时把 SQLITE_DB_PATH 拷进自己的命名空间，所以 monkeypatch
    必须直接打 base 模块（不是 config 单例）。
    """
    fd, path = tempfile.mkstemp(suffix=".db", prefix="knot_test_")
    os.close(fd)
    os.unlink(path)  # 让 init_db() 自己创建

    from knot.repositories import base as base_mod
    monkeypatch.setattr(base_mod, "SQLITE_DB_PATH", path)
    base_mod.init_db()

    # v0.6.0.20：seed admin 默认 must_change_password=1（生产环境必须改密）；
    # 测试场景统一 reset 让业务 API 可调；专门测改密的用例在 test_force_change_password.py 自己设回 1
    from knot.repositories import user_repo
    admin = user_repo.get_user_by_username("admin")
    if admin and admin.get("must_change_password"):
        user_repo.update_user(admin["id"], must_change_password=0)

    yield path

    if os.path.exists(path):
        os.unlink(path)
