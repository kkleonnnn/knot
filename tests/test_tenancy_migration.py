"""v0.9.0 C4 — pre-tenancy 存量迁移测试（锚点 knot.db → tenant#1 库）。

`migrate_anchor_db_to_tenant_once()` 直调验证（不经 main import → 不受 KNOT_SKIP_STARTUP_MIGRATION gate）：
COPY+强校验+last-good + crash-resume 状态机 + real-data 守护 + uploads 备份不迁。

锚点/target 建为最小 4 表库（users/conversations/audit_log/data_sources）—— 迁移 COPY 出的 target 与锚点
byte-identical，故表集合/行数校验恒过；测试重点在**状态机分支 + 守护 + 备份/回滚**语义，非 schema 保真。
"""
import sqlite3

import pytest

from knot.repositories import base, tenancy_migration, tenant_repo

_migrate = tenancy_migration.migrate_anchor_db_to_tenant_once


def _build_db(path, *, users=0, convs=0, encrypted_ds=False):
    """建最小 4 表库（模拟 pre-tenancy 真库）；encrypted_ds → 插 1 条加密 db_password 以验 decrypt 烟测。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(path)
    c.executescript(
        "CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT);"
        "CREATE TABLE conversations (id INTEGER PRIMARY KEY);"
        "CREATE TABLE audit_log (id INTEGER PRIMARY KEY);"
        "CREATE TABLE data_sources (id INTEGER PRIMARY KEY, db_password TEXT, http_config TEXT);"
    )
    for i in range(users):
        c.execute("INSERT INTO users (username) VALUES (?)", (f"u{i}",))
    for _ in range(convs):
        c.execute("INSERT INTO conversations DEFAULT VALUES")
    if encrypted_ds:
        from knot.core.crypto import encrypt
        c.execute("INSERT INTO data_sources (db_password) VALUES (?)", (encrypt("s3cr3t"),))
    c.commit()
    c.close()


@pytest.fixture
def mig_env(tmp_path, monkeypatch):
    """tmp 数据目录 + platform.db(tenant#1 db_dir='tenants/1' 生产布局)；锚点由各测试自建。

    生产布局（db_dir='tenants/1' 非 '.'）—— target ≠ 锚点 → 迁移真正跑（'.' 会 skip:same-path）。
    """
    anchor = tmp_path / "knot.db"
    monkeypatch.setattr(tenant_repo, "SQLITE_DB_PATH", str(anchor))
    monkeypatch.setattr(base, "SQLITE_DB_PATH", str(anchor))
    tenant_repo.init_platform_db()
    tenant_repo.seed_default_tenant(db_dir="tenants/1")
    return tmp_path, anchor


def test_mig_fresh_deploy_skip(mig_env):
    """全新部署（无锚点、无 target）→ skip:fresh（不建任何库，留给 per-tenant init_db）。"""
    tmp, _anchor = mig_env
    assert _migrate() =="skip:fresh"
    assert not (tmp / "tenants" / "1" / "knot.db").exists()


def test_mig_same_path_skip(tmp_path, monkeypatch):
    """db_dir='.'（target==锚点，测试布局）→ skip:same-path（锚点不动）。"""
    anchor = tmp_path / "knot.db"
    monkeypatch.setattr(tenant_repo, "SQLITE_DB_PATH", str(anchor))
    monkeypatch.setattr(base, "SQLITE_DB_PATH", str(anchor))
    tenant_repo.init_platform_db()
    tenant_repo.seed_default_tenant(db_dir=".")
    _build_db(anchor, users=1)
    assert _migrate() =="skip:same-path"
    assert anchor.exists()


def test_mig_first_migration(mig_env):
    """首迁：锚点有数据(含加密凭据) + target 无 → migrated；target 得全量数据 + 锚点 rename→.pre-tenancy.bak。"""
    tmp, anchor = mig_env
    _build_db(anchor, users=3, convs=2, encrypted_ds=True)
    assert _migrate() =="migrated"
    target = tmp / "tenants" / "1" / "knot.db"
    assert target.exists()
    c = sqlite3.connect(target)
    assert c.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 3
    assert c.execute("SELECT COUNT(*) FROM conversations").fetchone()[0] == 2
    c.close()
    assert not anchor.exists()                              # 锚点已 rename 走
    assert (tmp / "knot.db.pre-tenancy.bak").exists()       # 备份在（回滚源）


def test_mig_idempotent(mig_env):
    """幂等：迁完（锚点→.bak，target 有）再调 → skip:migrated（不重迁）。"""
    _tmp, anchor = mig_env
    _build_db(anchor, users=2)
    assert _migrate() =="migrated"
    assert _migrate() =="skip:migrated"


def test_mig_crash_resume(mig_env):
    """抗 crash 续跑：锚点在 + target 是残片（空/无真数据）→ resumed（删残片重迁，target 被锚点数据覆盖）。"""
    tmp, anchor = mig_env
    _build_db(anchor, users=3)
    target = tmp / "tenants" / "1" / "knot.db"
    _build_db(target, users=1)   # 模拟上次 crash 在 copy 后 rename 前留的残片（1 seed user）
    assert _migrate() == "resumed"
    c = sqlite3.connect(target)
    assert c.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 3   # 锚点数据覆盖残片
    c.close()
    assert not anchor.exists()


def test_mig_real_data_guard(mig_env):
    """守护：锚点在 + target 已有真业务数据（>1 用户）→ raise（疑似违反铁律先上现网，拒覆盖保双方）。"""
    tmp, anchor = mig_env
    _build_db(anchor, users=3)
    target = tmp / "tenants" / "1" / "knot.db"
    _build_db(target, users=5, convs=1)   # target 有真数据（非残片）
    with pytest.raises(RuntimeError, match="拒绝覆盖"):
        _migrate()
    assert anchor.exists()   # 锚点保 last-good（不动）
    c = sqlite3.connect(target)
    assert c.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 5   # target 数据未被覆盖
    c.close()


def test_mig_resume_with_marker_overwrites_even_real_data(mig_env):
    """crash-after-copy 续跑：target 有真数据 **但有 `.c4-migrating` 标记**（本迁移崩在 finalize 前）→
    属合法 resume，覆盖重迁（不触发安全阀 raise）—— 消歧「本迁移写的」vs「prod 独立写入」。"""
    tmp, anchor = mig_env
    _build_db(anchor, users=3)
    target = tmp / "tenants" / "1" / "knot.db"
    _build_db(target, users=9, convs=4)          # target 有真数据（模拟本迁移已 copy 完）
    (tmp / "tenants" / "1" / ".c4-migrating").write_text("in-progress")  # 但标记在 = 本迁移进行中
    assert _migrate() == "resumed"
    c = sqlite3.connect(target)
    assert c.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 3   # 被锚点数据覆盖（非 9）
    c.close()
    assert not (tmp / "tenants" / "1" / ".c4-migrating").exists()       # 完成 → 标记清除


def test_mig_marker_cleaned_on_success(mig_env):
    """成功迁移后 `.c4-migrating` 标记必须清除（否则下次启动误判 in-progress）。"""
    tmp, anchor = mig_env
    _build_db(anchor, users=2)
    _migrate()
    assert not (tmp / "tenants" / "1" / ".c4-migrating").exists()


def test_mig_verify_fail_keeps_last_good(mig_env, monkeypatch):
    """校验不过 → 删 target 保锚点 last-good + raise（fail-closed 中止启动，绝不丢数据）。"""
    tmp, anchor = mig_env
    _build_db(anchor, users=2)
    monkeypatch.setattr(tenancy_migration, "_verify_migrated_db",
                        lambda src, dst: (_ for _ in ()).throw(RuntimeError("模拟校验失败")))
    with pytest.raises(RuntimeError, match="迁移校验失败"):
        _migrate()
    assert anchor.exists()                                       # 锚点 last-good（不动）
    assert not (tmp / "tenants" / "1" / "knot.db").exists()      # target 已删（不留半成品）


def test_mig_real_data_guard_config_only_no_second_user(mig_env):
    """【对抗 CRITICAL 修】广义 real-data 判据：target 仅 1 用户 + 0 会话，但配了 data_source（用户内容表非空）
    + 无标记 → 仍触发安全阀 raise（原 users>1/convs>0 判据会漏判 → 静默覆盖活跃租户库 = 数据丢失）。"""
    tmp, anchor = mig_env
    _build_db(anchor, users=1)
    target = tmp / "tenants" / "1" / "knot.db"
    _build_db(target, users=1, convs=0, encrypted_ds=True)   # 1 用户 0 会话，但有 1 条 data_source
    with pytest.raises(RuntimeError, match="拒绝覆盖"):
        _migrate()
    assert anchor.exists()
    c = sqlite3.connect(target)
    assert c.execute("SELECT COUNT(*) FROM data_sources").fetchone()[0] == 1   # 未被覆盖
    c.close()


def test_mig_verify_rejects_empty_db(mig_env):
    """【对抗修】强校验拒空库：0 表的 src/dst 不得判为迁移成功（防并发 empty-vs-empty 假过 → 服务空库）。"""
    tmp, _anchor = mig_env
    empty = tmp / "empty.db"
    sqlite3.connect(empty).close()   # 建 0 表空库
    with pytest.raises(RuntimeError, match="无表"):
        tenancy_migration._verify_migrated_db(empty, empty)


def test_mig_skip_migrated_rejects_empty_target_with_bak(mig_env):
    """【对抗修】skip:migrated 完好性校验：锚点已迁走 + target 空/损坏 + 有 .pre-tenancy.bak
    → raise（掉电致 target 未落盘 → 拒以空库起服务，人工从 .bak 恢复）。"""
    tmp, anchor = mig_env
    target = tmp / "tenants" / "1" / "knot.db"
    target.parent.mkdir(parents=True, exist_ok=True)
    sqlite3.connect(target).close()                                  # 空/损坏 target（0 表）
    (tmp / (anchor.name + ".pre-tenancy.bak")).write_bytes(b"x")     # 有 .bak（锚点已迁走）
    # 锚点不存在（未 _build_db）→ 命中 not anchor_exists + target 空 + 有 .bak 分支
    with pytest.raises(RuntimeError, match="空库起服务|人工"):
        _migrate()


def test_mig_lock_file_created_and_released(mig_env):
    """flock：迁移创建数据根 .c4-migration.lock 并正常释放（跨进程串行化载体；完成后锁文件留存无害）。"""
    tmp, anchor = mig_env
    _build_db(anchor, users=1)
    _migrate()
    assert (tmp / ".c4-migration.lock").exists()   # 锁文件建立（O_CREAT）


def test_mig_uploads_backed_up_not_moved(mig_env):
    """uploads.db 备份不迁：迁后 uploads.db 留原位 + 生成 .pre-tenancy.bak，且未进租户目录
    （engine_cache._upload_engine import 期绑数据根，relocation=v0.9.1）。"""
    tmp, anchor = mig_env
    _build_db(anchor, users=1)
    up = tmp / "uploads.db"
    _build_db(up, users=0)
    _migrate()
    assert up.exists()                                            # 留原位（不迁）
    assert (tmp / "uploads.db.pre-tenancy.bak").exists()          # 备份在
    assert not (tmp / "tenants" / "1" / "uploads.db").exists()    # 未迁进租户目录
