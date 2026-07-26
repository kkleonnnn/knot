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


def test_relocation_corrupt_target_fail_closed(reloc_env):
    """⭐ 守护者 Stage 4 §II（C4-parity）：src 已迁走 + target **损坏** → raise（拒以损坏 uploads 库起服务）。
    修前仅凭 `target.exists()` 返 skip:relocated → 建引擎于坏库、运行时静默失败无 halt。
    revert 去掉 `_uploads_wellformed` 门 → 本测转红。"""
    from knot.repositories.uploads_relocation import relocate_uploads_once
    tmp, _anchor = reloc_env
    tdir = tmp / "tenants" / "1"
    tdir.mkdir(parents=True, exist_ok=True)
    (tdir / "uploads.db").write_bytes(b"THIS IS NOT A SQLITE DATABASE" * 8)   # quick_check 读不出
    with pytest.raises(RuntimeError, match="损坏"):
        relocate_uploads_once(tmp, tdir)


def _build_corrupt_but_magic_valid(path, *, mode):
    """建「sqlite magic 头完好、实体已坏」的库 —— 专杀「探针退化成只看头/大小」的 mutant。

    mode='truncate' → 截断 60%（limb i：`DatabaseError: database disk image is malformed`）
    mode='cellptr'  → 清坏 page3+ 的 cell pointer array（**limb ii**：quick_check 返非 'ok' 长串，此前零覆盖）
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(path)
    c.execute('CREATE TABLE "t_a" (x INTEGER, s TEXT)')
    c.executemany('INSERT INTO "t_a" VALUES (?,?)', [(i, "payload-" * 8) for i in range(3000)])
    c.commit()
    c.close()
    if mode == "truncate":
        with open(path, "r+b") as f:
            f.truncate(int(path.stat().st_size * 0.6))
    else:
        raw = bytearray(path.read_bytes())
        for off in range(8192, len(raw), 4096):
            raw[off + 8:off + 40] = b"\xff" * 32
        path.write_bytes(bytes(raw))
    assert path.read_bytes()[:16] == b"SQLite format 3\x00", "前提：magic 头须完好（否则杀不到头探针 mutant）"


@pytest.mark.parametrize("mode", ["truncate", "cellptr"])
def test_relocation_corrupt_target_probe_strength(reloc_env, mode):
    """⭐ Stage 4 对抗（AV-D mutant）：**magic 头完好但实体已坏**的 target 也必须 halt ——
    钉住探针强度：若 `_uploads_unhealthy_reason` 退化成「看 magic / 看大小」，本测转红（垃圾字节测不会）。
    两 mode 分别覆盖 limb i（raise）与 **limb ii（quick_check 返非 ok 串，此前零覆盖）**。"""
    from knot.repositories.uploads_relocation import relocate_uploads_once
    tmp, _anchor = reloc_env
    tdir = tmp / "tenants" / "1"
    _build_corrupt_but_magic_valid(tdir / "uploads.db", mode=mode)
    with pytest.raises(RuntimeError, match="拒绝以损坏库起服务"):
        relocate_uploads_once(tmp, tdir)


def test_relocation_resume_with_unreadable_target_self_heals(reloc_env):
    """⭐ Stage 4 对抗（AV-B/AV-D/critic 三方独立命中）：src 在 + marker 在 + target **读不出**（`_backup_db` 半写残片）
    → 必须自愈（'resumed'），而非让 sqlite `.backup()` 抛 DatabaseError 裸逃出 main.py:90 → **永久 boot crash-loop**。
    留证：坏字节整体移存 .pre-resume；自愈后 target 完好含 src 表。
    revert（无条件 `_backup_db_atomic`）→ 本测转红（DatabaseError）。"""
    from knot.repositories.uploads_relocation import _MARKER, relocate_uploads_once
    tmp, _anchor = reloc_env
    tdir = tmp / "tenants" / "1"
    _build_uploads(tmp / "uploads.db", tables=("t_src",))     # data-root 源 = last-good
    tdir.mkdir(parents=True, exist_ok=True)
    (tdir / "uploads.db").write_bytes(b"HALF-WRITTEN GARBAGE" * 16)
    (tdir / _MARKER).write_text("in-progress")                # 上次 relocation 被打断
    assert relocate_uploads_once(tmp, tdir) == "resumed"
    preserved = list(tdir.glob("uploads.db.pre-resume*"))
    assert preserved, "坏 target 的字节应留证移存（不得静默丢弃）"
    assert b"HALF-WRITTEN GARBAGE" in preserved[0].read_bytes()
    c = sqlite3.connect(tdir / "uploads.db")                  # 自愈后 target 完好且含 src 的表
    try:
        assert c.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        assert c.execute("SELECT name FROM sqlite_master WHERE name='t_src'").fetchone()
    finally:
        c.close()
    assert not (tdir / _MARKER).exists()


def test_migration_rejects_db_dir_escaping_data_root(reloc_env):
    """⭐ Stage 4 对抗（critic 命中 · 4 lens 全漏）：db_dir='../evil' → 写侧（会 unlink 源）必须拒迁。
    读侧 resolver 早有此守卫（test_get_upload_engine_path_escape_blocked），写侧此前**无** →
    knot.db/uploads.db 会被搬到数据根外并删源 = OOS-1v2 文件边界逃逸。一处守 C4 + uploads 两条路径。"""
    from knot.repositories import tenancy_migration, tenant_repo
    tmp, anchor = reloc_env
    conn = tenant_repo.get_platform_conn()
    try:
        conn.execute("UPDATE tenants SET db_dir='../evil' WHERE id=1")
        conn.commit()
    finally:
        conn.close()
    _build_wellformed(anchor)                                 # 有锚点待迁 → 若无守卫就会真搬出去
    with pytest.raises(RuntimeError, match="逃出数据根"):
        tenancy_migration.migrate_anchor_db_to_tenant_once()
    assert anchor.exists(), "拒迁后锚点必须原地保留（绝不能已删源）"
    assert not (tmp.parent / "evil").exists(), "绝不能在数据根外建租户目录"


def test_relocated_uploads_is_the_file_resolver_serves(reloc_env):
    """⭐ Stage 4 对抗（critic 命中）：**端到端接上本 PATCH 两个新模块** —— relocation 搬完之后，
    `get_upload_engine()` 解析到的正是那个被搬过去的文件、且能读到搬过来的表。
    此前 relocation 测与 resolver 测两半互不相交（critic：正因如此才漏掉写侧含容缺口）。"""
    from knot.repositories.uploads_relocation import relocate_uploads_once
    from knot.services.upload_engine import get_upload_engine
    tmp, _anchor = reloc_env
    tdir = tmp / "tenants" / "1"
    _build_uploads(tmp / "uploads.db", tables=("t_e2e",))
    assert relocate_uploads_once(tmp, tdir) == "relocated"
    tok = set_active_tenant({"id": 1, "db_dir": "tenants/1"})
    try:
        eng = get_upload_engine()
        assert str(eng.url).endswith("tenants/1/uploads.db"), str(eng.url)
        with eng.connect() as c:
            assert c.exec_driver_sql("SELECT COUNT(*) FROM t_e2e").fetchone()[0] == 1
    finally:
        reset_active_tenant(tok)


def test_relocation_skip_relocated_empty_target_still_legal(reloc_env):
    """⭐ §II 收紧**不误伤 MF4**：0 表 target（租户从未上传）在 skip 路径仍合法 → skip:relocated。
    若误复用 C4 `_db_wellformed`（零表即 False）→ 本测转红。"""
    from knot.repositories.uploads_relocation import relocate_uploads_once
    tmp, _anchor = reloc_env
    tdir = tmp / "tenants" / "1"
    tdir.mkdir(parents=True, exist_ok=True)
    sqlite3.connect(tdir / "uploads.db").close()      # 0 表合法空
    assert relocate_uploads_once(tmp, tdir) == "skip:relocated"


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
