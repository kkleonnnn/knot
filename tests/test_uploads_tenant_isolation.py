"""v0.9.2 — uploads.db per-tenant 化：resolver 隔离 + relocation 状态机 + ⭐ R2 回归守。

纯 in-process（set_active_tenant，永不 resolve_single_tenant → R-T-GATE 不动）。
重点：**R2 回归守**（relocation 在 _migrate_locked skip:migrated 时仍跑 —— 挂 anchor 分支则孤儿）+ 空-legal（MF4）。
"""
import sqlite3

import pytest

from knot.core import tenant_context as tc
from knot.core.tenant_context import reset_active_tenant, set_active_tenant


def _build_wellformed(path):
    """建有 ≥1 表的完好库（_db_wellformed → True → _migrate_locked skip:migrated）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(path)
    c.executescript("CREATE TABLE users (id INTEGER PRIMARY KEY); INSERT INTO users VALUES (1);")
    c.commit()
    c.close()


def _build_uploads(path, *, tables=("t_abc",)):
    path.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(path)
    for t in tables:
        c.execute(f'CREATE TABLE "{t}" (x INTEGER)')
        c.execute(f'INSERT INTO "{t}" VALUES (1)')
    c.commit()
    c.close()


@pytest.fixture
def reloc_env(tmp_path, monkeypatch):
    """tmp 数据根 + platform.db(tenant#1 db_dir='tenants/1' 生产布局)。"""
    from knot.repositories import base, tenant_repo
    anchor = tmp_path / "knot.db"
    monkeypatch.setattr(tenant_repo, "SQLITE_DB_PATH", str(anchor))
    monkeypatch.setattr(base, "SQLITE_DB_PATH", str(anchor))
    tenant_repo.init_platform_db()
    tenant_repo.seed_default_tenant(db_dir="tenants/1")
    return tmp_path, anchor


# ─────────────────────── resolver 跨租户隔离 ───────────────────────

def test_get_upload_engine_cross_tenant_distinct(reloc_env):
    """两租户 get_upload_engine → 不同文件 + 不同 engine（tenants/1 vs tenants/2）。"""
    from knot.services.upload_engine import get_upload_engine
    tok = set_active_tenant({"id": 1, "db_dir": "tenants/1"})
    try:
        e1 = get_upload_engine()
        u1 = str(e1.url)
    finally:
        reset_active_tenant(tok)
    tok = set_active_tenant({"id": 2, "db_dir": "tenants/2"})
    try:
        e2 = get_upload_engine()
        u2 = str(e2.url)
    finally:
        reset_active_tenant(tok)
    assert e1 is not e2
    assert u1.endswith("tenants/1/uploads.db") and u2.endswith("tenants/2/uploads.db"), (u1, u2)


def test_get_upload_engine_fail_closed(reloc_env):
    """无 tenant ctx → get_upload_engine raise TenantContextError（fail-closed）。"""
    from knot.services.upload_engine import get_upload_engine
    tok = tc._active_tenant_ctx.set(None)
    try:
        with pytest.raises(tc.TenantContextError):
            get_upload_engine()
    finally:
        tc._active_tenant_ctx.reset(tok)


def test_get_upload_engine_path_escape_blocked(reloc_env):
    """db_dir='../evil' 逃出数据根 → raise（MF5 路径校验）。"""
    from knot.services.upload_engine import get_upload_engine
    tok = set_active_tenant({"id": 9, "db_dir": "../evil"})
    try:
        with pytest.raises(tc.TenantContextError):
            get_upload_engine()
    finally:
        reset_active_tenant(tok)


# ─────────────────────── relocation 状态机 ───────────────────────

def test_relocation_first_migration(reloc_env):
    """首迁：data-root uploads.db(有 t_*) → tenants/1/uploads.db + 源移走 + relocation bak。"""
    from knot.repositories.uploads_relocation import relocate_uploads_once
    tmp, _anchor = reloc_env
    _build_uploads(tmp / "uploads.db")
    tdir = tmp / "tenants" / "1"
    assert relocate_uploads_once(tmp, tdir) == "relocated"
    assert (tdir / "uploads.db").exists() and not (tmp / "uploads.db").exists()
    assert (tmp / "uploads.db.pre-v0.9.2-relocation.bak").exists()
    c = sqlite3.connect(tdir / "uploads.db")
    assert c.execute("SELECT name FROM sqlite_master WHERE name='t_abc'").fetchone()
    c.close()


def test_relocation_empty_uploads_legal(reloc_env):
    """⭐ MF4：0 表 uploads.db **合法**（不套 C4「零表即 raise」）→ relocation 成功。"""
    from knot.repositories.uploads_relocation import relocate_uploads_once
    tmp, _anchor = reloc_env
    sqlite3.connect(tmp / "uploads.db").close()   # 0 表
    tdir = tmp / "tenants" / "1"
    assert relocate_uploads_once(tmp, tdir) == "relocated"
    assert (tdir / "uploads.db").exists()


def test_relocation_fresh_and_idempotent(reloc_env):
    """无 data-root uploads → skip:fresh（租户从未上传）；迁完再跑 → skip:relocated。"""
    from knot.repositories.uploads_relocation import relocate_uploads_once
    tmp, _anchor = reloc_env
    tdir = tmp / "tenants" / "1"
    assert relocate_uploads_once(tmp, tdir) == "skip:fresh"
    _build_uploads(tmp / "uploads.db")
    assert relocate_uploads_once(tmp, tdir) == "relocated"
    assert relocate_uploads_once(tmp, tdir) == "skip:relocated"


def test_relocation_orphan_marker_cleared_on_skip(reloc_env):
    """对抗 #1（C4 parity）：孤儿 `.uploads-relocating`（src 已迁走）→ skip 分支清除
    （否则日后 data-root 恢复时 marker 在 → 旁路安全阀覆盖 live target）。"""
    from knot.repositories.uploads_relocation import _MARKER, relocate_uploads_once
    tmp, _anchor = reloc_env
    tdir = tmp / "tenants" / "1"
    _build_uploads(tdir / "uploads.db")            # 已迁完（target 在、src 无）
    (tdir / _MARKER).write_text("orphan")
    assert relocate_uploads_once(tmp, tdir) == "skip:relocated"
    assert not (tdir / _MARKER).exists()           # 孤儿标记已清


def test_relocation_safety_valve(reloc_env):
    """src + target 已有 t_* 真数据 + 无 marker → raise（疑似违反铁律先上现网，拒覆盖）。"""
    from knot.repositories.uploads_relocation import relocate_uploads_once
    tmp, _anchor = reloc_env
    _build_uploads(tmp / "uploads.db", tables=("t_src",))
    tdir = tmp / "tenants" / "1"
    _build_uploads(tdir / "uploads.db", tables=("t_prod",))   # target 已有真数据
    with pytest.raises(RuntimeError, match="拒绝覆盖"):
        relocate_uploads_once(tmp, tdir)
    assert (tmp / "uploads.db").exists()   # 源保 last-good


# ─────────────────────── ⭐ R2 回归守（杀手 fix） ───────────────────────

def test_relocation_runs_on_skip_migrated(reloc_env):
    """⭐ R2 回归守：真实 v0.9.0→v0.9.2 升级 anchor 已迁走（_migrate_locked skip:migrated 早返）→
    relocation **仍执行**（挂 anchor-存在分支则不跑 = uploads 孤儿）。revert 挂回分支内 → 本测转红。"""
    from knot.repositories import tenancy_migration
    tmp, _anchor = reloc_env
    tdir = tmp / "tenants" / "1"
    _build_wellformed(tdir / "knot.db")          # v0.9.0 已迁：无 anchor、tenants/1/knot.db 完好 → skip:migrated
    _build_uploads(tmp / "uploads.db")           # data-root 孤儿 uploads.db
    knot_result = tenancy_migration.migrate_anchor_db_to_tenant_once()
    assert knot_result == "skip:migrated"        # knot 侧早返（不存在 anchor）
    assert (tdir / "uploads.db").exists()        # ⭐ relocation 仍跑（挂 anchor 分支则此处不存在）
    assert not (tmp / "uploads.db").exists()     # 源已移走
