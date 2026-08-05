"""knot.repositories.base — connection helper + init_db。

WAL mode、Row factory、check_same_thread=False 与原 persistence 等价。
init_db() 集中执行 schema + 历史 ALTER TABLE 兼容迁移 + seed admin。
v0.8.22：历史迁移块拆入 knot.repositories.migrations（base.py 顶死 size-gate，v0.9.0 前置）；
本文件保留 get_conn / schema / init_db 编排 / seed admin。
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from knot.config import SQLITE_DB_PATH
from knot.core.logging_setup import logger
from knot.core.tenant_context import (  # v0.9.0 get_conn 双层解析（fail-closed）
    TenantContextError,  # v0.9.15 d2'：db_dir 逃出数据根时 raise（与 uploads 侧同型）
    current_tenant,
)
from knot.repositories import migrations

# 再导出上传库迁移函数：既有 base.<fn> 引用（tests / engine_cache 注释）与 init_db 内部调用保持 byte-equal。
from knot.repositories.migrations import (  # noqa: F401
    _migrate_uploads_db_once,  # [RETIRED] 保留供 test_migration_observability 历史覆盖
    _migrate_uploads_to_isolated_db_once,
)


def _tenant_db_path() -> Path:
    """当前 active tenant 的库路径（**fail-closed**：无 ctx → current_tenant() raise TenantContextError）。

    = 数据目录锚点 `SQLITE_DB_PATH.parent` / `tenant.db_dir` / `knot.db`。
    db_dir='tenants/1'(生产) → `.../data/tenants/1/knot.db`；db_dir='.'(测试) → `.../data/knot.db`
    （= 锚点本身，保直读 SQLITE_DB_PATH 的既有测试断言 byte-equal）。SQLITE_DB_PATH 是 str，须 Path() 包。

    ⭐ **v0.9.15 d2'：校验解析路径在数据根内（防 `db_dir='../x'` 逃出租户边界）。**
    补的是一条**既有**不对称 —— 同形状守护此前只有它的两个兄弟有，唯独主库这条没有：
      · `services/upload_engine.py::_tenant_uploads_path`（uploads 读侧）
      · `repositories/tenancy_migration`（C4 迁移写侧 —— v0.9.2 Stage 4 对抗 critic 命中才补）
    而 `get_conn()` 紧随本函数 `mkdir(parents=True, exist_ok=True)`
    ⇒ 没有本校验时，`db_dir='../evil'` 会**在数据根之外建目录并创建主库** = OOS-1v2 文件边界逃逸。
    ⚠️ **本校验不因「db_dir 由服务端生成」而可省**：运维直改平台库仍可写入任意值
    （同 v0.9.8 的诚实边界 —— 只声称代码路径受控）。
    判据与 uploads 侧**逐字同形**（`root != p.parent and root not in p.parents`）：
    刻意不发明第二种写法，否则两处会各自漂。
    """
    root = Path(SQLITE_DB_PATH).parent.resolve()
    t = current_tenant()
    p = (root / t["db_dir"] / "knot.db").resolve()
    if root != p.parent and root not in p.parents:
        # ⭐ **必须留痕**（v0.9.15 Stage 4 #3）：fail-closed 顺序是对的（raise 在 `get_conn` 的
        #   `mkdir` 之前 ⇒ 逃逸目录不会被创建），但**请求路径会把它折成一条普通 401** ——
        #   `api/deps.py` 捕 `TenantContextError` → 自己的 `HTTPException(401, "TENANT_UNAVAILABLE")`
        #   ⇒ 原消息被丢弃 ⇒ 一次 **OOS-1v2 文件边界违规**与「租户停用/不存在」**无法区分**，
        #   且全程零日志 ⇒ **事件不留痕**。
        #   ⇒ 在**抛处**记（这里才是「事情真的发生的那一行」）。先例：v0.9.9 漂移写平台审计 · v0.9.6/.10 启动期 WARN。
        #
        # ⚠️ **两条写法约束，都是踩过才知道的**：
        # ① **必须 f-string，不能用 stdlib 的 `extra={...}`** —— `logger` 是 **loguru**，
        #    kwargs **只喂 `str.format()`**；消息无占位符 ⇒ 整个 dict **被静默丢弃**
        #    ⇒ 只剩裸串「发生了逃逸」而**不说是谁**。实测：本行初版正是那样，输出 `'tenant_db_path_escape\n'`。
        #    （= 本仓「消息说的对吗」第 ④ 种失效的新形态：打印了，而什么也没说。）
        # ② **只记 `tenant_id` + `db_dir`，⛔ 不记 `p` / `root`** —— 它们由 `SQLITE_DB_PATH`
        #    派生 = **env 派生值**，进日志即 #262 家族（v0.9.7 那条 egress 拒绝消息就是这么泄的
        #    内网主机清单）；`test_no_env_value_in_messages` 的 f-string 支正好覆盖这里。
        #    诊断力不减：非法的是 `db_dir` 本身，`root` 运维自己就知道。
        logger.error(f"tenant_db_path_escape: tenant_id={t['id']} db_dir={t['db_dir']!r} —— 解析后逃出数据根，已拒绝建库")
        raise TenantContextError(f"租户库路径逃出数据根：{p} 不在 {root} 内（db_dir 非法）")
    return p


def get_conn() -> sqlite3.Connection:
    """租户库连接（v0.9.0 **fail-closed 双层解析**：无 tenant ctx → raise TenantContextError）。

    SQLITE_DB_PATH env 语义降级为「数据目录锚点」（parent 派生 platform.db 与 tenants/），不引新 env。
    32 消费文件 0 改动（仍调 get_conn()）；平台库连接走 tenant_repo.get_platform_conn（ctx-free）。
    """
    p = _tenant_db_path()
    p.parent.mkdir(parents=True, exist_ok=True)  # 租户库目录（tenants/<id>/）缺失即建 — 首启/迁移/测试自洽
    conn = sqlite3.connect(p, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


_SCHEMA_SQL = (Path(__file__).parent / "schema.sql").read_text(encoding="utf-8")


def init_db():
    """启动期建表 + 历史兼容迁移 + seed admin。

    编排序（迁移块拆入 migrations.py，逐块 byte-equal 保序）：
    pre-schema → executescript → post-schema → seed admin → 上传库隔离迁移 → startup cleanup。
    """
    conn = get_conn()
    migrations.run_pre_schema_migrations(conn)
    conn.executescript(_SCHEMA_SQL)
    migrations.run_post_schema_migrations(conn)

    # Seed admin（v0.3.1：通过 bcrypt 直接哈希避免 repos→services 反向依赖）
    # ⚠️ R-LP-v3-EX-3-1（default-admin 弱口令债正式红线）承重代码；grounded 引文锚点
    #    "1.0 公测前必清的安全债" 随 must_change_password 列注释搬至 migrations.run_post_schema_migrations。
    if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
        import secrets

        import bcrypt

        from knot.config import DEFAULT_DB_HOST, DEFAULT_DB_PORT
        # v0.8.20 F7（R-LP-v3-EX-3-1）：seed admin 初始口令 —— env KNOT_INITIAL_ADMIN_PASSWORD 优先，
        # 无则**随机强口令** + 一次性日志打印。消除「跨部署同一已知 admin123 + 首启竞态」（攻击者抢先
        # 首登→白名单内改密+enroll 夺 admin）。must_change_password=1 仍保留（首登强制改）。
        _env_pwd = os.environ.get("KNOT_INITIAL_ADMIN_PASSWORD", "").strip()
        _init_pwd = _env_pwd or secrets.token_urlsafe(12)
        seed_pwd = bcrypt.hashpw(_init_pwd.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        conn.execute(
            "INSERT INTO users (username, password_hash, display_name, role, doris_host, doris_port, must_change_password) "
            "VALUES (?, ?, '管理员', 'admin', ?, ?, 1)",
            ("admin", seed_pwd, DEFAULT_DB_HOST, DEFAULT_DB_PORT),
        )
        if _env_pwd:
            logger.info("seed admin 初始口令来自 KNOT_INITIAL_ADMIN_PASSWORD（首登须改密 must_change_password=1）")
        else:
            logger.warning(
                f"🔑 seed admin 随机初始口令（仅此一次打印）：admin / {_init_pwd} —— 立即登录改密；"
                f"生产建议用 KNOT_INITIAL_ADMIN_PASSWORD 指定。"
            )
        conn.execute("INSERT INTO semantic_layer (content) VALUES ('')")

    # v0.8.19a F1（上传问数隔离）：存量上传表 t_* 从主库 knot.db 迁往**独立** uploads.db
    # （逆 v0.2.4 合并，仅数据表；元数据 file_uploads 留主库）。⚠️ 旧 _migrate_uploads_db_once
    # （把 uploads.db 吞回主库）已**退役、不再调用**——若重新接线会把隔离后的 uploads.db 再吞回主库
    # （守护者 Stage 3 F1 catch）。
    _migrate_uploads_to_isolated_db_once(conn)

    migrations.run_startup_cleanup(conn)

    conn.commit()
    conn.close()
