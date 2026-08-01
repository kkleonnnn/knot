"""knot.repositories.tenant_repo — 平台库(platform.db) 连接 + tenants 表 CRUD + 单租户解析器。

平台库存平台元数据（v0.9.0 仅 tenants 表）；租户库 = `SQLITE_DB_PATH.parent / db_dir / knot.db`
（`base.get_conn` 双层解析）。存量迁移（pre-tenancy knot.db → tenant#1 库）在 `tenancy_migration.py`。

`get_platform_conn` **ctx-free**（不经 fail-closed `get_conn`）—— 供启动序 platform bootstrap +
tenant 解析 + C4 迁移；否则自身撞 fail-closed 门（chicken-and-egg）。
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from knot.config import SQLITE_DB_PATH
from knot.core.tenant_context import TenantContextError
from knot.repositories import platform_audit_repo  # 同层（Contract 4 禁 repositories → services）

_PLATFORM_SCHEMA = (Path(__file__).parent / "platform_schema.sql").read_text(encoding="utf-8")

# v0.9.0 生产 tenant#1 库目录（相对 SQLITE_DB_PATH.parent）；存量迁移把 knot.db 迁入此处。
DEFAULT_TENANT_DB_DIR = "tenants/1"


def _platform_db_path() -> Path:
    """平台库路径 = 数据目录锚点(SQLITE_DB_PATH.parent) / platform.db（不引新 env）。"""
    return Path(SQLITE_DB_PATH).parent / "platform.db"


def get_platform_conn() -> sqlite3.Connection:
    """平台库连接（**ctx-free** — 不经 fail-closed get_conn）。"""
    conn = sqlite3.connect(_platform_db_path(), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _run_platform_migrations(conn) -> None:
    """平台库 additive 迁移（**本仓第一条** —— v0.9.7）。

    ⚠️ **为什么必须有这个函数**：`platform_schema.sql` 只有 `CREATE TABLE IF NOT EXISTS`
    ⇒ 对**已存在**的 `platform.db`，往 schema 里加列是**完全无效**的（executescript 直接 no-op）。
    此前平台库从未加过列，故一直没暴露；v0.9.7 是第一次。
    范式照租户库 `repositories/migrations.py`（18 处先例）：幂等 `PRAGMA table_info` → `ALTER TABLE ADD COLUMN`。
    """
    # v0.9.7 B-3 ③: tenants.allowed_http_hosts —— per-tenant egress allowlist（部署方控制）。
    # 新库由 platform_schema.sql 的 CREATE 直接带上；本 ALTER 兜住存量库。三态语义见该文件注释。
    cols = {row[1] for row in conn.execute("PRAGMA table_info(tenants)").fetchall()}
    if "allowed_http_hosts" not in cols:
        conn.execute("ALTER TABLE tenants ADD COLUMN allowed_http_hosts TEXT")

    # v0.9.8: tenants.updated_at —— 平台元数据变更时间线（此前缺 ⇒「谁改了 db_dir」无时间线）。
    # ⭐ **本条是本机制的第二个用户** —— 它顺带证明「加平台列」不是一次性动作而是可组合的：
    #   从**既无 allowed_http_hosts 也无 updated_at** 的 pre-v0.9.7 存量库升级，一次调用后两列都在
    #   （守护者 M4：只从 pre-v0.9.8 起测只能证明「第二条能跑」，证明不了「两条能串起来」）。
    # 逐块重读列集 —— 照 `migrations.py` 的既有惯用（同一张表 `users` 在 :57/:121/:148 读了三次）。
    # ⚠️ **理由是「块间独立」，不是「否则会坏」**（实施期取材证伪了我原先写的诊断）：
    #   对 additive-only 且检查**不同**列的迁移，顶部取一次快照**永远足够** ——
    #   陈旧快照缺的正是要加的列，条件照样成立。重读的价值在于每块自包含
    #   ⇒ 将来插入/重排迁移块时不必回溯前面改了什么。**别据此写「不重读就会坏」的测。**
    cols = {row[1] for row in conn.execute("PRAGMA table_info(tenants)").fetchall()}
    if "updated_at" not in cols:
        conn.execute("ALTER TABLE tenants ADD COLUMN updated_at TEXT")


def init_platform_db() -> None:
    """建 platform.db + executescript(platform schema) + additive 迁移（幂等 · IF NOT EXISTS）。"""
    conn = get_platform_conn()
    conn.executescript(_PLATFORM_SCHEMA)
    _run_platform_migrations(conn)      # v0.9.7：executescript 后 —— 存量库加列的唯一途径
    conn.commit()
    conn.close()


def list_tenants() -> list:
    conn = get_platform_conn()
    rows = conn.execute("SELECT * FROM tenants ORDER BY id").fetchall()
    conn.close()
    return [dict(r) for r in rows]


#: 平台只读端点的**显式列白名单**（v0.9.5 D3' —— 禁 `SELECT *`）。
#: **为什么**：B-3 已排期给平台层加 per-tenant `http_spec` 凭据 + per-tenant 初始口令
#: ⇒ 那时 `SELECT *` 会**自动**把新列吐进 HTTP 响应。这是已登记的路线，不是假设风险。
#: 新增平台列时**不会**自动进这个列表 ⇒ 要吐必须显式加，且过 `TenantPublic` 第二道。
_PUBLIC_COLS = ("id", "slug", "name", "status", "db_dir", "created_at")


def list_tenants_public() -> list:
    """平台只读端点专用：**显式投影**，不用 `SELECT *`（见 `_PUBLIC_COLS` 注释）。"""
    conn = get_platform_conn()
    rows = conn.execute(
        f"SELECT {', '.join(_PUBLIC_COLS)} FROM tenants ORDER BY id"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def list_active_tenants() -> list:
    conn = get_platform_conn()
    rows = conn.execute("SELECT * FROM tenants WHERE status='active' ORDER BY id").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_tenant(tenant_id: int) -> dict | None:
    conn = get_platform_conn()
    row = conn.execute("SELECT * FROM tenants WHERE id=?", (tenant_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


#: `update_tenant` 允许改的字段白名单（v0.9.8）。
#: ⚠️ **刻意不含** `id` / `slug` / `created_at`：前两个是身份（改它等于换租户，而 `slug` 还是登录链接的一部分），
#: `created_at` 是事实。要改身份类字段应当是一次显式评审的迁移，不是走这个通用写口。
_MUTABLE_TENANT_FIELDS = ("status", "db_dir", "allowed_http_hosts", "name")


def seed_default_tenant(db_dir: str = DEFAULT_TENANT_DB_DIR) -> None:
    """seed 恰 1 行 tenant#1（幂等：tenants 非空则跳）。生产 db_dir='tenants/1'；测试传 '.'。

    ⭐ **v0.9.8：INSERT 与平台审计在同一事务、单次 commit** —— 见 `platform_audit_repo` 模块 docstring。
    ⇒ 「审计写失败」与「seed 失败」是**同一件事**，不存在「建了租户但没记」。
    ⇒ 也**不需要**为「审计写不进去时该 raise 还是继续」定一条策略（那个两难是造出来的）。
    """
    conn = get_platform_conn()
    if conn.execute("SELECT COUNT(*) FROM tenants").fetchone()[0] == 0:
        conn.execute(
            "INSERT INTO tenants (id, slug, name, status, db_dir) VALUES (1, 'default', '默认租户', 'active', ?)",
            (db_dir,),
        )
        platform_audit_repo.insert(
            conn, action="platform.tenant_create", tenant_id=1, tenant_slug="default",
            actor="system:boot", source="startup", detail={"db_dir": db_dir, "seed": True},
        )
        conn.commit()          # ⚠️ **单次** commit —— 拆成两次就把上面那条性质丢了
    conn.close()


def update_tenant(tenant_id: int, *, actor: str | None = None, source: str | None = None,
                  **fields) -> bool:
    """**平台元数据变更的单一写口**（v0.9.8）：校验字段 → stamp `updated_at` → 写审计 → 单次 commit。

    Returns:
        True = 有行被改；False = 该租户不存在（不抛 —— 调用方按需处理）。

    Raises:
        ValueError: 传了白名单外的字段（**fail-closed**：不静默忽略未知字段 ——
            静默忽略会让「我改了但没生效」变成一个无提示的坑）。

    ⭐ **UPDATE 与审计 INSERT 在同一事务、单次 commit**（D3 / 守护者 §II）：
    ⇒ **不存在「改了但没记」或「记了但没改」**。这比「审计写失败时 fail-closed」更强。
    ⚠️ 审计的 `detail` 记**变更前后值**，但 `allowed_http_hosts` **只记「已变更」不记内容**
    （它是部署方的内网主机清单 —— #262 同族；且该端点会返回 `detail_json`）。

    ⚠️ **本函数不是唯一的物理写入途径** —— 运维直接 `sqlite3 UPDATE` 仍绕过它（DEPLOY.md 记为
    应急手段）。⇒ 本片**不声称**「所有平台变更都被审计」，只声称**代码路径**上的变更被审计。
    """
    bad = set(fields) - set(_MUTABLE_TENANT_FIELDS)
    if bad:
        raise ValueError(
            f"update_tenant 不接受字段 {sorted(bad)}；可改字段 = {list(_MUTABLE_TENANT_FIELDS)}。"
            "（`id` / `slug` / `created_at` 刻意不可改 —— 那是身份与事实，改它应走显式评审的迁移。）"
        )
    if not fields:
        return False

    conn = get_platform_conn()
    try:
        row = conn.execute("SELECT * FROM tenants WHERE id=?", (tenant_id,)).fetchone()
        if row is None:
            return False
        before = dict(row)

        sets = ", ".join(f"{k}=?" for k in fields) + ", updated_at=datetime('now','localtime')"
        conn.execute(f"UPDATE tenants SET {sets} WHERE id=?",  # noqa: S608 — 键已过白名单
                     (*fields.values(), tenant_id))

        # detail：逐字段记 before→after；allowlist 只记「已变更」（内容是部署方内网主机清单）
        detail = {}
        for k, v in fields.items():
            if k == "allowed_http_hosts":
                detail[k] = "changed"      # ⛔ 绝不记内容（#262 同族 + 该端点返回 detail_json）
            else:
                detail[k] = {"from": before.get(k), "to": v}
        platform_audit_repo.insert(
            conn, action="platform.tenant_update", tenant_id=tenant_id,
            tenant_slug=before.get("slug"), actor=actor, source=source, detail=detail,
        )
        conn.commit()          # ⚠️ **单次** commit —— 拆成两次就丢了原子性（配套测会红）
        return True
    finally:
        conn.close()


def resolve_tenant_by_id(tenant_id: int) -> dict | None:
    """v0.9.4 D6：按 tid 解析**可服务**租户 —— 存在**且** `status=='active'` 才返，否则 `None`。

    为何不改 `get_tenant` 本身：`tests/test_tenant_isolation.py:56` 依赖它能取出 suspended 行来验文件级隔离。
    ⭐ **B-2 承重**：`get_tenant` 不过滤 status（`SELECT * WHERE id=?`）⇒ 若 tenant_resolution 直接用它，
    平台方停用租户后，该租户用户手里 **7 天有效期**（`deps.py:78` `JWT_EXPIRE_HOURS=24*7`）内的 JWT
    **继续正常查询** —— 停用形同虚设。故解析路径必须走本函数。
    返 `None`（而非 raise）让调用方决定语义：受保护 API → 401；不在此处表达 HTTP 语义。
    """
    t = get_tenant(tenant_id)
    if t is None or t.get("status") != "active":
        return None
    return t


def resolve_tenant_by_slug(slug: str) -> dict | None:
    """v0.9.4 D4''：按**公司代号**（`tenants.slug`）解析**可服务**租户 —— 存在且 active 才返，否则 `None`。

    kk 2026-07-27 决策①「每家公司一条专属登录链接」的落点：链接携带 `?c=<slug>`，登录端点据此
    在**建 ctx 之前**（ctx-free，读平台库）定位租户。
    ⭐ **复用已存在的 `tenants.slug`**（`NOT NULL UNIQUE`）带来的最大连带收益：**不需要**新建
    user_directory 表、**不需要**用户名全局唯一 ⇒ 各租户照样可各有 `admin`
    （避开与 seed 逻辑的正面冲突）。

    **精确匹配（大小写敏感）**：`slug` 的 UNIQUE 是大小写敏感的 ⇒ 若这里做大小写不敏感匹配，
    理论上 `abc` 与 `ABC` 两行都可能存在而本函数只能返一行 = **不确定地把用户送进某个租户**。
    链接是系统生成的、不靠人手打 ⇒ 精确匹配代价可忽略，换来「绝不会解析歧义」。
    返 `None` 而非 raise：调用方（登录端点）要把它折进**统一的**「账号或密码错误」，
    否则「代号不存在」与「代号存在但口令错」可区分 = **公司枚举**（kk 决策②）。
    """
    conn = get_platform_conn()
    row = conn.execute(
        "SELECT * FROM tenants WHERE slug=? AND status='active'", (slug,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def assert_no_second_active_tenant_served() -> None:
    """R-T-GATE 请求侧硬门（v0.9.4 D5 —— **首次真实现**）：active 租户 **>1** 即 fail-closed。

    ⭐ **B-1 承重**：LOCKED（`docs/plans/v0.9.0-oos1-ceremony-multitenant-base.md:150`）把本函数指定为硬 CI，
    但**此前全仓无任何实现** —— 真正在挡的只是 `resolve_single_tenant()` 抛错的**副作用**。v0.9.4 把请求
    路径改为「按 JWT tid 解析」后，`len(active)` 这条判定就不在请求路径上了 ⇒ 必须显式补，否则 R-T-GATE
    在请求侧**无声消失**。

    ⭐ **只对 `>1`**（守护者 Stage 3 R3/MF3 裁定，**不是** `!=1`）：
      - 名副其实（"no **second** active"）；
      - `0 active` 交给上层语义：受保护 API 因无可解析租户自然 401，**登录端点得以返回锁定的
        `401 账号或密码错误`**（②统一错误）而不是 500。若此处对 0 也 raise，唯一租户被 suspend 时
        整站含 login 全部 500，与②直接打架。

    **lift 片**（**非 v0.9.5** —— 那片只做鉴权拆分、R-T-GATE 一行不动）**= 删掉本函数的唯一调用点
    （一行）** —— 语义单点、可 review。⚠️ lift 的前置条件见 CLAUDE.md 的 R-T-GATE 就绪清单。
    """
    n = len(list_active_tenants())
    if n > 1:
        raise TenantContextError(
            f"R-T-GATE：检测到 {n} 个 active 租户，隔离栈就绪前不得同时服务多租户 —— 拒绝服务（fail-closed）。"
            "就绪清单见 CLAUDE.md §R-T-GATE（per-tenant file catalog / http_spec 凭据 / egress 域化 / "
            "开通口令 / 鉴权拆分 / audit-on-drift）"
        )


def resolve_single_tenant() -> dict:
    """v0.9.0 单租户解析器：platform.db tenants 恰 1 active → 返之；0 或 >1 → raise（fail-closed）。

    多租户解析（JWT tid → 库）= 0.1。>1 active 由 R-T-GATE `assert_no_second_active_tenant_served` 挡
    （0.9.0~0.2 期间隔离栈未就绪，永远只有 1 个可服务租户）。
    """
    active = list_active_tenants()
    if len(active) != 1:
        raise TenantContextError(
            f"单租户解析器要求恰 1 个 active tenant；实际 {len(active)}"
            "（R-T-GATE：第二租户开通须待隔离栈就绪 — uploads/凭据/egress/catalog/调度器/缓存键/开通口令）"
        )
    return active[0]
