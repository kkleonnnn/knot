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
from knot.core.tenant_context import OWNER_TENANT_ID, TenantContextError
from knot.repositories import platform_audit_repo  # 同层（Contract 4 禁 repositories → services）
from knot.repositories import platform_migrations as _pm  # v0.9.15：平台库 schema/迁移已拆出（size gate）


def init_platform_db() -> None:
    """建 platform.db + schema + additive 迁移（幂等）。

    ⚠️ **薄壳，刻意保留**：实现已搬到 `platform_migrations`（v0.9.15 size gate），
    但全仓 10+ 处调用点写的都是 `tenant_repo.init_platform_db()` ——
    保留本壳让那些调用点 **byte-equal 不变**（照 `base.py` re-export
    `migrations._migrate_uploads_*` 的既有做法）。连接获取仍在本模块。
    """
    _pm.init_platform_db(get_platform_conn)


def _run_platform_migrations(conn) -> None:
    """[兼容壳] 见 `platform_migrations.run_platform_migrations`（测按此名引用）。"""
    _pm.run_platform_migrations(conn)


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


def get_tenant_by_slug(slug: str) -> dict | None:
    """按 slug 取租户 —— **不过滤 status**（v0.9.15，供开通编排用）。

    ⚠️ **命名约定（本文件已有，此处沿用）**：`get_*` = 原样取行、**不过滤** status；
    `resolve_*` = 只返「**可服务**」的（`status=='active'`）。
    ⭐ **为什么开通需要不过滤的那一种**：开通要判断「这个 slug 是不是已经存在」，
    而**已存在的往往正是 `suspended`** 的那些（本片开通出来的租户恒 suspended）
    ⇒ 用 `resolve_tenant_by_slug` 会把它们看成「不存在」，于是重复开通撞
    `UNIQUE(slug)` 抛裸异常 —— 那正是「可重试」失效的形态。
    ⚠️ **严禁**把本函数接进请求/登录路径：那两条**必须**走 `resolve_*`
    （B-2 承重 —— 否则平台方停用租户后，该租户用户手里 7 天有效期内的 JWT 继续可用）。
    """
    conn = get_platform_conn()
    row = conn.execute("SELECT * FROM tenants WHERE slug=?", (slug,)).fetchone()
    conn.close()
    return dict(row) if row else None


#: `update_tenant` 允许改的字段白名单（v0.9.8）。
#: ⚠️ **刻意不含** `id` / `slug` / `created_at`：前两个是身份（改它等于换租户，而 `slug` 还是登录链接的一部分），
#: `created_at` 是事实。要改身份类字段应当是一次显式评审的迁移，不是走这个通用写口。
#: ⚠️ **v0.9.15 d4：`db_dir` 已从本白名单移出** —— `db_dir` 建成后**永不重写**。
#: **为什么**：它是那个租户全部数据的**物理位置**。改它 = 让该租户指向另一个（或不存在的）库，
#: 而**数据不会跟着搬** ⇒ 「租户还在、数据不见了」，且旧目录变成无人引用的孤儿。
#: 真要搬数据必须是一次**显式的迁移**（停用 → 搬文件 → 校验 → 改指向），不是走通用写口改一个字段。
#: ⇒ 与 `id`/`slug`/`created_at` 同一条理由，只是它更狠：那三个改了是「身份错”，这个改了是「数据没了」。
_MUTABLE_TENANT_FIELDS = ("status", "allowed_http_hosts", "allowed_webhook_hosts", "name")

#: 审计**只记「已变更」、绝不记内容**的字段 —— 它们是部署方内网主机清单，而
#: `GET /api/platform/audit` 会原样返回 `detail_json`（#262 同族）。
#: ⭐ **是集合不是硬编单名**（v0.9.18 P-a）：原为 `if k == "allowed_http_hosts"`；只补第二个名字的话，
#: **第三份 allowlist 来时会原样重演，且没有任何东西会提醒你**。
#: 完整理由 + 派生哨兵见 `tests/test_allowlist_column_registration.py`（不登记在此即红）。
_REDACTED_IN_AUDIT = frozenset({"allowed_http_hosts", "allowed_webhook_hosts"})


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
            "（`id` / `slug` / `created_at` / `db_dir` 刻意不可改 —— 前三个是身份与事实；"
            "`db_dir` 是数据的**物理位置**，改它数据不会跟着搬 ⇒ 「租户还在、数据不见了」。"
            "要搬数据请走显式迁移：停用 → 搬文件 → 校验 → 改指向。）"
        )
    if not fields:
        return False

    # ── v0.9.15 d4：起源租户不得被停用 ────────────────────────────────────
    # ⚠️ **为什么单独挡它**：`resolve_single_tenant()` 只要求「恰 1 个 active」，
    #   **不要求那一个是起源租户**（`OWNER_TENANT_ID`）⇒ 停用 tenant#1 + 有个 active tenant#2 时
    #   **boot 会成功**，而 file catalog 层（`catalog_loaders.load_file_layer` 的 owner-gate）
    #   对被服务的那个租户**静默返回全空** —— 部署方写的真实库表/词典/业务口径整体消失，
    #   而查询不报错、只是「什么都查不到」。v0.9.6 只加了启动期 WARN 兜可诊断性，根治在此。
    # ⚠️ **为什么不能用共用谓词 `is_owner_tenant()`**（我第一版就是这么写的，错的）：
    #   它**不接参数** —— 它答的是「**我当前服务的**是不是起源租户」（读 ctx、无 ctx 时 fail-closed），
    #   而这里要问的是「**这个 id** 是不是起源租户」。**两个不同的问题。**
    #   且 `update_tenant` **必须能在无 ctx 下工作**（v0.9.8 立的，有专测
    #   `test_platform_audit.py::…无 ctx 也能改`）⇒ 用那个谓词会直接把无 ctx 路径打死。
    #   ⇒ 用**常量** `OWNER_TENANT_ID`（那才是共享真相源），并沿用本仓的严格 int 纪律
    #   （`type(x) is int` —— `True == 1` 且 `1.0 == 1`，宽松比较会把 `True`/`1.0` 当成 owner）。
    _is_owner_id = type(tenant_id) is int and tenant_id == OWNER_TENANT_ID
    if fields.get("status") is not None and fields["status"] != "active" and _is_owner_id:
        raise ValueError(
            f"拒绝把**起源租户**（id={tenant_id}）改为 {fields['status']!r} —— "
            "起源租户是 file catalog 层（部署方的真实库表/词典/业务口径）的唯一归属者。\n"
            "  停用它 ⇒ 若另有 active 租户则 boot 仍成功，而 file 层对被服务租户**静默变空** "
            "（查询不报错、只是什么都查不到）。\n"
            "  ⇒ 真要下线整个部署，请停服务进程，而不是把起源租户标成 suspended。"
        )

    # ── ⛔ v0.9.20 P-c：**临时代偿门** —— 非起源租户不得被激活 ──────────────
    # ⚠️⚠️ **这道门是代偿控制，不是修复。摘除条件写在下面，别单独摘。**
    #
    # **为什么需要它**：lift R-T-GATE 之前，唯一可服务的租户**恒是起源租户**
    #   （禁停用起源租户 + 门禁第二 active）⇒ 唯一的 tenant admin 就是**部署方本人**
    #   ⇒ 三条「租户盲」的能力今天**无害**（**逐条见下方 raise 的消息** —— 不在此复述，
    #     免得两处漂开）。**lift 正是第一次把它们交给非部署方。**
    #   出处：`api/admin/datasources.py` 的 SSRF 守卫函数体第一行就 return（非 http 一律放行）·
    #   `config/settings.PROVIDER_API_KEYS`（12 处站点的回退末跳）· `repositories/base.py` 的 seed INSERT。
    #
    # ⭐ **门在这一行、不在激活 CLI 里** —— 完整理由见
    #   `tests/test_file_catalog_owner_gate.py::test_rtgate_compensating_gate_still_blocks_activation`
    #   的 docstring（一句话：CLI 是**决策点**，能力在下方 `UPDATE tenants SET`）。
    #
    # 🔓 **摘除条件（三条全部租户域化后，本门连同其测一并删除）**：
    #   ① SQL 数据源出网纳入 per-tenant allowlist；② LLM key 去掉 env 回退（非起源租户 fail-closed）；
    #   ③ seed 不再写部署方 DB 坐标。守护：`test_rtgate_compensating_gate_still_blocks_activation`。
    #
    # ⚠️ **诚实边界**：运维直接 `sqlite3 UPDATE` 仍绕过本门（与上面那道守卫同）。
    if fields.get("status") == "active" and not _is_owner_id:
        raise ValueError(
            f"拒绝激活非起源租户（id={tenant_id}）—— R-T-GATE 虽已 lift，但仍有 **3 条能力是租户盲的**，"
            "激活等于把它们交给非部署方：\n"
            "  ① SQL 数据源出网**零 allowlist**（该租户 admin 可让服务端连部署方内网任意 host:port）\n"
            "  ② LLM API key 回退到**进程 env**（该租户不填 key 就花部署方的账、以部署方账号出境）\n"
            "  ③ 新租户 admin 行**预填部署方内网 DB 坐标**\n"
            "⇒ 三条全部租户域化后，删掉本门（tenant_repo 内，注释里写了摘除条件）即可激活。\n"
            "⇒ 若你确知在做什么且必须现在激活：直接改平台库（DEPLOY「多租户运维门」），"
            "但那**不会留审计**，且上述三条风险照旧。"
        )

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
            if k in _REDACTED_IN_AUDIT:    # ⛔ 绝不记内容（#262 同族 + 该端点返回 detail_json）
                detail[k] = "changed"      # ⭐ 集合而非硬编单名 —— 见 `_REDACTED_IN_AUDIT` 的理由
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


def resolve_single_tenant() -> dict:
    """v0.9.0 单租户解析器：platform.db tenants 恰 1 active → 返之；0 或 >1 → raise（fail-closed）。

    ⚠️ **v0.9.20（P-c）起 R-T-GATE 已 lift** —— 原先「>1 active 由请求侧硬门挡住」的前提**不再成立**，
    该门（`assert_no_second_active_tenant_served`）连同其唯一调用点已**物理删除**。
    ⇒ 本函数**不在请求路径上**（请求一律按 JWT `tid` 解析），它只服务于**明确要求「恰 1 个 active」**
    的少数场景 —— AST 实测生产码剩 3 处：`api/auth.py`（登录无代号回退）+ CLI 2 处
    （`purge_audit_log` 仅 dry-run 可达 / `scan_secrets_at_rest` 只读）。

    ⚠️ **它在 active ≠ 1 时 raise 的语义未变**，且这正是 `auth.py` 那处的行为依据：
    第二家公司一激活，**不带 `?c=<代号>` 的登录一律 401**（不会「挑一个租户」）——
    那是**可用性**问题（老链接失效，产品迁移动作），**不是**跨租户访问。
    """
    active = list_active_tenants()
    if len(active) != 1:
        raise TenantContextError(
            f"单租户解析器要求恰 1 个 active tenant；实际 {len(active)}"
            "（R-T-GATE：第二租户开通须待隔离栈就绪 — uploads/凭据/egress/catalog/调度器/缓存键/开通口令）"
        )
    return active[0]
