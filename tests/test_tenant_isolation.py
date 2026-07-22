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

def test_iso6_r_t_gate_single_active_tenant(tmp_db_path):
    """⑥ R-T-GATE `assert_no_second_active_tenant_served`：resolve_single_tenant 恰 1 active；>1 → raise。"""
    assert tenant_repo.resolve_single_tenant()["id"] == 1
    conn = tenant_repo.get_platform_conn()
    conn.execute("INSERT INTO tenants (id,slug,name,status,db_dir) VALUES (2,'t2','T2','active','tenants/2')")
    conn.commit(); conn.close()
    with pytest.raises(tc.TenantContextError):
        tenant_repo.resolve_single_tenant()   # 2 active → fail-closed（隔离栈未就绪，不放第二租户）


def test_iso6_no_platform_tenants_route():
    """⑥ 续：路由集合不含 `/api/platform/tenants`（0.1 才建开通端点骨架 — R-T-GATE 接线未放开）。"""
    from knot.main import app
    from tests._route_count import app_route_paths
    paths = app_route_paths(app)
    assert not any("/api/platform/tenants" in p for p in paths), "第二租户开通端点不应在 v0.9.0 路由集"


# ─────────────────────── 平台库 vs 租户库表划分 ───────────────────────

def test_iso4_platform_db_only_tenants_table(tmp_db_path):
    """④ platform.db 表集合 == {tenants}（防业务表漂回平台库 — 平台库最小化起步）。"""
    conn = tenant_repo.get_platform_conn()
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    tables.discard("sqlite_sequence")   # AUTOINCREMENT 副表
    assert tables == {"tenants"}, f"platform.db 应仅含 tenants 表；实际 {tables}"


def test_iso8_flatten_route_snapshot():
    """⑧ flatten 路由精确计数（app_route_paths；精确 == 144 非 >=80 软下限 — Stage3 #9：增/删路由即红）。"""
    from knot.main import app
    from tests._route_count import flatten_app_routes
    assert len(flatten_app_routes(app)) == 144, "路由数漂移（C2/C3 应 0 新增路由；middleware 非 route）"


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
