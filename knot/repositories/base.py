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
from knot.repositories import migrations

# 再导出上传库迁移函数：既有 base.<fn> 引用（tests / engine_cache 注释）与 init_db 内部调用保持 byte-equal。
from knot.repositories.migrations import (  # noqa: F401
    _migrate_uploads_db_once,  # [RETIRED] 保留供 test_migration_observability 历史覆盖
    _migrate_uploads_to_isolated_db_once,
)


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(SQLITE_DB_PATH, check_same_thread=False)
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
