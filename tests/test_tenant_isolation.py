"""v0.9.0 C3 — 多租户隔离 CI（fail-closed 文件边界 + OOS-1v2 绊线 + R-T-GATE）。

**docstring 显式区分两类（Stage3 #10）**：
- **绊线（tripwire · 列缺席）**：OOS-1v2 改写自原 OOS-1 tripwire —— 租户库 schema 无 tenant_id/project_id 列
  （行级租户列对 LogicForm 编译器 fail-open）。见 `test_tripwire5_*`。
- **隔离（isolation · fail-closed + 文件边界）**：无 ctx raise / db_dir 解析 / 双租户文件隔离 / R-T-GATE。
  见 `test_iso*`。这是 C 方案真正的隔离载体（≠ 绊线的「列不存在」静态检查）。

fixtures：tmp_db_path（tests/conftest.py）已建 platform.db + seed tenant#1(db_dir='.')；autouse 设 tenant#1 ctx。
"""
import concurrent.futures
import contextvars
import subprocess
from pathlib import Path

import pytest

from knot.core import tenant_context as tc
from knot.repositories import base, tenant_repo

# ─────────────────────── 隔离（fail-closed + 文件边界）───────────────────────

def test_iso1_get_conn_fail_closed_no_ctx(tmp_db_path):
    """① 无 tenant ctx → get_conn raise TenantContextError（fail-closed，无全局回退 — 反 catalog 回退语义）。"""
    tok = tc._active_tenant_ctx.set(None)   # 清 ctx（覆盖 autouse tenant#1）
    try:
        with pytest.raises(tc.TenantContextError):
            base.get_conn()
    finally:
        tc._active_tenant_ctx.reset(tok)


def test_iso2_get_conn_resolves_db_dir_production_layout(tmp_db_path):
    """② set ctx(db_dir='tenants/2') → get_conn 解析到 anchor.parent/tenants/2/knot.db。

    production-layout（db_dir='tenants/N' 非仅 '.' — Stage3 #8：防路径拼接只在 '.' 下成立的假绿）。
    """
    anchor_parent = Path(tmp_db_path).parent
    tok = tc._active_tenant_ctx.set({"id": 2, "slug": "t2", "name": "T2", "status": "active", "db_dir": "tenants/2"})
    try:
        assert base._tenant_db_path() == anchor_parent / "tenants" / "2" / "knot.db"
        c = base.get_conn(); c.close()
        assert (anchor_parent / "tenants" / "2" / "knot.db").exists()
    finally:
        tc._active_tenant_ctx.reset(tok)


def test_iso3_double_tenant_file_isolation(tmp_db_path):
    """③ 双租户库文件级隔离：tenant#2 库写入不泄漏到 tenant#1 库（C 方案文件边界 = 真隔离载体）。

    tenant#2 建为 suspended（双 active 会触发单租户解析器 raise，见 ⑥）；此处仅 repo 层显式 set ctx 验隔离。
    """
    conn = tenant_repo.get_platform_conn()
    conn.execute("INSERT INTO tenants (id,slug,name,status,db_dir) VALUES (2,'t2','T2','suspended','tenants/2')")
    conn.commit(); conn.close()
    tok = tc._active_tenant_ctx.set(tenant_repo.get_tenant(2))
    try:
        c2 = base.get_conn()
        c2.execute("CREATE TABLE IF NOT EXISTS _probe (x INTEGER)")
        c2.execute("INSERT INTO _probe VALUES (42)"); c2.commit(); c2.close()
    finally:
        tc._active_tenant_ctx.reset(tok)
    # tenant#1（autouse db_dir='.'）库不应有 tenant#2 的 _probe 表
    c1 = base.get_conn()
    got = c1.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='_probe'").fetchall()
    c1.close()
    assert not got, "tenant#2 的 _probe 表泄漏进了 tenant#1 库（文件隔离破）"


def test_iso_executor_copy_context_isolation(tmp_db_path):
    """§5 线程复用测（Stage3 #4）：copy_context().run 传播 ctx 到 worker 且不泄漏进复用线程。

    模拟 run_in_executor(copy_context().run, …)：worker 内有 ctx（get_conn 成功）；同线程复用后无 copy_context
    → fresh ctx → fail-closed raise（证 ctx.run 未把 tenant ctx 残留进线程池）。
    """
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    try:
        ctx = contextvars.copy_context()   # 捕获 autouse tenant#1 ctx

        def _with_ctx():
            c = base.get_conn(); c.close(); return "GOT"
        assert pool.submit(lambda: ctx.run(_with_ctx)).result() == "GOT"

        def _no_ctx():
            try:
                base.get_conn(); return "GOT"
            except tc.TenantContextError:
                return "FAIL_CLOSED"
        assert pool.submit(_no_ctx).result() == "FAIL_CLOSED", "ctx.run 不应把 tenant ctx 泄漏进复用线程"
    finally:
        pool.shutdown()


# ─────────────────────── R-T-GATE ───────────────────────

def _add_second_active_tenant():
    conn = tenant_repo.get_platform_conn()
    conn.execute("INSERT INTO tenants (id,slug,name,status,db_dir) VALUES (2,'t2','T2','active','tenants/2')")
    conn.commit()
    conn.close()


def test_iso6_r_t_gate_single_active_tenant(tmp_db_path):
    """⑥ R-T-GATE：**`assert_no_second_active_tenant_served` 本尊**（v0.9.4 D5 首次真实现）。

    ⚠️ **v0.9.4 §II-4 重指**：本测此前 docstring 写着该函数名、**实际测的是 `resolve_single_tenant`**
    —— 即「文档声称 vs 实际」的同一 gap 在测层复制了一遍。D5 真实现后重指本尊。
    **只对 >1**（R3）：1 active 通过；2 active → raise。
    """
    tenant_repo.assert_no_second_active_tenant_served()      # 1 active → 通过（不 raise）
    _add_second_active_tenant()
    with pytest.raises(tc.TenantContextError, match="R-T-GATE"):
        tenant_repo.assert_no_second_active_tenant_served()  # 2 active → fail-closed


def test_iso6_gate_allows_zero_active(tmp_db_path):
    """⑥ 续 · **R3 裁定**：门**只对 >1** —— `0 active` 必须**放过**（不 raise）。

    若对 0 也 raise（原 `resolve_single_tenant` 的 `!=1`），唯一租户被 suspend 时整站含
    `POST /api/auth/login` 全部 500 ⇒ 与②「登录失败统一返 401 账号或密码错误」直接打架。
    0 active 的语义交上层：受保护 API 因无可解析租户自然 401。
    """
    conn = tenant_repo.get_platform_conn()
    conn.execute("UPDATE tenants SET status='suspended'")
    conn.commit()
    conn.close()
    assert tenant_repo.list_active_tenants() == []
    tenant_repo.assert_no_second_active_tenant_served()      # 0 active → 不得 raise
    with pytest.raises(tc.TenantContextError):
        tenant_repo.resolve_single_tenant()                   # 对照：旧解析器对 0 仍 raise（未改其语义）


def test_iso6_resolve_tenant_by_id_filters_status(tmp_db_path):
    """⑥ 续 · **B-2 承重**：`resolve_tenant_by_id` 必须过滤 status —— suspended 返 None。

    否则平台方停用租户后，其用户手里 7 天有效期内的 JWT 继续正常查询（停用形同虚设）。
    对照断言 `get_tenant` **仍返** suspended 行（`test_iso3` 依赖该行为，本片刻意不改它）。
    """
    assert tenant_repo.resolve_tenant_by_id(1)["id"] == 1
    assert tenant_repo.resolve_tenant_by_id(999) is None      # 不存在
    conn = tenant_repo.get_platform_conn()
    conn.execute("UPDATE tenants SET status='suspended' WHERE id=1")
    conn.commit()
    conn.close()
    assert tenant_repo.resolve_tenant_by_id(1) is None, "suspended 租户不得被解析为可服务"
    assert tenant_repo.get_tenant(1)["status"] == "suspended", "get_tenant 语义不变（test_iso3 依赖）"


def test_iso6a_platform_tenants_route_is_read_only_and_platform_gated():
    """⑥a（v0.9.5 拆自 `test_iso6_no_platform_tenants_route`）：平台只读端点**存在**且分类 = `PLATFORM_SECRET`。

    ⭐ **为什么拆**：原测断言「路由集不含 `/api/platform/tenants`」，但读它的 docstring 与断言消息
    （「**0.1 才建开通端点骨架**」/「**第二租户开通端点**不应在 v0.9.0 路由集」）——
    它真正守的是「**开通（写）端点不该存在**」，路径字面只是当时的实现手段。
    v0.9.5 加的是**只读**端点 ⇒ **不违反原意图、但违反原实现** ⇒ 拆成
    ⑥a（本条：读端点存在且被平台密钥守）+ ⑥b（前缀零写面 = 原意图，且**比原测更强**）。
    """
    import sys
    from pathlib import Path
    _t = str(Path(__file__).resolve().parent)
    if _t not in sys.path:
        sys.path.insert(0, _t)
    from _route_policy import PLATFORM_SECRET, build_actual_policy_map

    m = build_actual_policy_map()
    key = "GET /api/platform/tenants"
    assert key in m, f"平台只读端点消失了（{key}）—— 它是 `require_platform_secret` 的唯一消费者（R-C3）"
    assert m[key] == PLATFORM_SECRET, (
        f"{key} 的策略是 {m[key]}，应为 {PLATFORM_SECRET} —— "
        "平台端点落进租户域或公开域都是认证面事故"
    )


def test_iso6b_no_write_methods_under_platform_prefix():
    """⑥b（v0.9.5）：`/api/platform/` 前缀下**不得有任何写方法** —— 原 ⑥ 的真实意图，且更强。

    原测只挡一个**路径字面**；本测挡**整个前缀的写面** ⇒ 直接守 E2 / R-v095-6
    （本片零 platform 写操作；租户开通/停用骨架不在本片）。
    取材=注入：`app.post("/api/platform/whatever")` → 本测红。
    """
    from fastapi.routing import APIRoute

    from knot.main import app
    from tests._route_count import flatten_app_routes

    writes = sorted(
        f"{m} {r.path}"
        for r in flatten_app_routes(app)
        if isinstance(r, APIRoute) and r.path.startswith("/api/platform/")
        for m in (r.methods or ())
        if m in ("POST", "PUT", "PATCH", "DELETE")
    )
    assert not writes, (
        f"`/api/platform/` 下出现写方法：{writes}\n"
        "E2（资深 2026-07-29 拍板）：本片**不引入 platform 写操作** —— 因为平台侧动作"
        "**没有审计落点**（`audit_service.log` → `get_conn` = 租户库；平台动作无租户库可写），"
        "而「建/停租户」正是最需要审计的动作。⇒ 要加写端点，先做平台审计落点（B-3 之后）。"
    )


# ─────────────────────── 平台库 vs 租户库表划分 ───────────────────────

def test_iso4_platform_db_only_tenants_table(tmp_db_path):
    """④ platform.db 表集合 == {tenants}（防业务表漂回平台库 — 平台库最小化起步）。"""
    conn = tenant_repo.get_platform_conn()
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    tables.discard("sqlite_sequence")   # AUTOINCREMENT 副表
    assert tables == {"tenants"}, f"platform.db 应仅含 tenants 表；实际 {tables}"


# ───────── 平台库 additive 迁移（v0.9.7 must #14 · 本仓第一条平台迁移）─────────

#: v0.9.7 前的 `tenants` 建表语句**逐字副本** —— 用来造「存量平台库」。
#: ⚠️ 刻意**写死**而不是从 `platform_schema.sql` 里裁剪：本测要造的是**过去那个版本**的库，
#: 若跟着当前 schema 走，将来 schema 再加列时本测会**自动跟着变**⇒ 它就不再是「存量库」了，
#: 而是「当前库」⇒ 迁移测静默失去意义（绿而无判别力）。
_PRE_V097_TENANTS_DDL = """
CREATE TABLE tenants (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    slug        TEXT    NOT NULL UNIQUE,
    name        TEXT    NOT NULL,
    status      TEXT    NOT NULL DEFAULT 'active',
    db_dir      TEXT    NOT NULL,
    created_at  TEXT    DEFAULT (datetime('now','localtime'))
);
"""


def _platform_cols():
    conn = tenant_repo.get_platform_conn()
    try:
        return {r[1] for r in conn.execute("PRAGMA table_info(tenants)").fetchall()}
    finally:
        conn.close()


def test_platform_migration_adds_column_to_legacy_db(tmp_db_path, monkeypatch):
    """⭐ must #14：**存量** platform.db（无该列）经 `init_platform_db()` 后**有**该列。

    ⚠️ **为什么这条测是必需的、不是形式主义**：`platform_schema.sql` 只有
    `CREATE TABLE IF NOT EXISTS` ⇒ 对已存在的库，往 schema 里加列**完全无效**
    （`executescript` 直接 no-op）。平台库此前从未加过列，所以这个盲区一直没暴露。
    没有 `_run_platform_migrations` 的话，**新库有列、存量库没列** —— 而存量库正是内测服那台。

    取材=revert：注释掉 `init_platform_db` 里的 `_run_platform_migrations(conn)` 那行 → 本测红。
    """
    import sqlite3

    # 造存量库：删掉 tmp_db_path 建好的，用 v0.9.7 **之前**的 DDL 重建
    p = tenant_repo._platform_db_path()
    p.unlink(missing_ok=True)
    conn = sqlite3.connect(p)
    conn.executescript(_PRE_V097_TENANTS_DDL)
    conn.execute("INSERT INTO tenants (id, slug, name, status, db_dir) VALUES (1,'default','默认租户','active','.')")
    conn.commit()
    conn.close()

    assert "allowed_http_hosts" not in _platform_cols(), "存量库构造失败 —— 它本就带该列，本测无判别力"

    tenant_repo.init_platform_db()

    assert "allowed_http_hosts" in _platform_cols(), (
        "存量 platform.db 升级后仍无 `allowed_http_hosts` 列。\n"
        "⚠️ `platform_schema.sql` 的 `CREATE TABLE IF NOT EXISTS` 对已存在的库是 no-op ——\n"
        "  加列的**唯一**途径是 `tenant_repo._run_platform_migrations`（v0.9.7 起，照 migrations.py 范式）。"
    )
    # 存量数据不得丢（ALTER ADD COLUMN 应保留行）
    assert tenant_repo.get_tenant(1)["slug"] == "default", "迁移把存量租户行弄丢了"


def test_platform_migration_is_idempotent(tmp_db_path):
    """must #14 续：连跑三次 `init_platform_db()` 不报错、列集不变（幂等）。

    幂等靠 `PRAGMA table_info` 判存在 —— 若改成裸 `ALTER TABLE ADD COLUMN`，
    第二次会抛 `duplicate column name` ⇒ **每次启动都崩**（启动序调它）。
    """
    before = _platform_cols()
    for _ in range(3):
        tenant_repo.init_platform_db()          # 不得抛
    assert _platform_cols() == before, "重复迁移改变了列集"
    assert "allowed_http_hosts" in before, "新库应由 platform_schema.sql 的 CREATE 直接带上该列"


def test_iso8_flatten_route_snapshot():
    """⑧ flatten 路由精确计数（精确 == 145 非 >=80 软下限 — Stage3 #9：增/删路由即红）。

    v0.9.5：144 → **145**（新增平台只读端点 `GET /api/platform/tenants`）。
    """
    from knot.main import app
    from tests._route_count import flatten_app_routes
    assert len(flatten_app_routes(app)) == 145, (
        "路由数漂移（v0.9.5 起 145 = 144 + `GET /api/platform/tenants`；middleware 非 route）")


# ─────────────────────── 绊线（tripwire · 列缺席 · OOS-1v2）───────────────────────

def test_tripwire5_tenant_db_no_tenant_columns(tmp_db_path):
    """⑤【绊线】租户库全表 schema 无 tenant_id/project_id 列（OOS-1v2：租户库内禁列 = 对 LogicForm 编译器
    fail-open 的静态防线；改写自原 OOS-1 tripwire）。租户归属列仅允许在平台库 tenants 表。"""
    conn = base.get_conn()
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    offenders = {}
    for t in tables:
        cols = [r[1] for r in conn.execute(f"PRAGMA table_info({t})")]
        bad = [c for c in cols if c in ("tenant_id", "project_id")]
        if bad:
            offenders[t] = bad
    conn.close()
    assert not offenders, f"OOS-1v2 绊线违反：租户库表含租户列 {offenders}（行级租户列 fail-open；隔离靠文件边界）"


# ─────────────────────── ⑦ gitignore（配 .gitignore **/data/tenants/）───────────────────────

def test_iso7_tenant_db_git_ignored():
    """⑦ 租户库文件被 .gitignore（**/data/tenants/）—— 防运行时库（含 seed admin 哈希）裸奔进 git。"""
    top = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                         capture_output=True, text=True).stdout.strip()
    r = subprocess.run(["git", "check-ignore", "knot/data/tenants/1/knot.db"],
                       cwd=top, capture_output=True, text=True)
    assert r.returncode == 0, "tenants/<id>/knot.db 必须被 .gitignore 忽略"
