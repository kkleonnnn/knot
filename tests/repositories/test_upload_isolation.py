"""v0.8.19a F1 上传隔离守护 — 引擎脱离主库 / 存量迁移 / 旧迁移退役不吞回。

守护者 Stage 3 must-fix #1：上传问数引擎必须与主库 knot.db 物理隔离；旧 _migrate_uploads_db_once
（把 uploads.db 吞回主库）已退役，绝不能把隔离后的 uploads.db 再吞回主库。
"""
from pathlib import Path

import sqlalchemy

from knot.adapters.db import doris
from knot.repositories import base as base_mod
from knot.repositories import upload_repo
from knot.services.upload_engine import get_upload_engine


def test_upload_engine_points_at_isolated_uploads_db():
    """F1 隔离铁律：上传问数引擎指向独立 uploads.db，绝不指主库 knot.db（v0.9.2：per-tenant resolver）。"""
    url = str(get_upload_engine().url)   # autouse tenant#1 ctx（db_dir='.'）
    assert url.endswith("uploads.db"), url
    assert not url.endswith("knot.db"), url


def test_migrate_existing_uploads_to_isolated_db(tmp_db_path):
    """存量 t_* 从主库迁往 uploads.db：行数保留 + 主库侧删除 + uploads 侧建立。"""
    uploads_db = Path(base_mod.SQLITE_DB_PATH).parent / "uploads.db"
    conn = base_mod.get_conn()
    try:
        conn.execute('CREATE TABLE "t_legacy" (a INTEGER, b TEXT)')
        conn.execute('INSERT INTO "t_legacy" VALUES (1, \'x\'), (2, \'y\')')
        conn.commit()
        upload_repo.create_file_upload(user_id=1, filename="legacy.csv",
                                       table_name="t_legacy", row_count=2, columns=["a", "b"])
        base_mod._migrate_uploads_to_isolated_db_once(conn)
        gone = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='t_legacy'"
        ).fetchone()
        assert gone is None, "存量表应从主库 knot.db 删除"
        conn.execute(f"ATTACH DATABASE '{uploads_db.as_posix()}' AS up")
        n = conn.execute('SELECT COUNT(*) FROM up."t_legacy"').fetchone()[0]
        assert n == 2, "行数应保留"
        conn.execute("DETACH DATABASE up")
    finally:
        conn.close()
        if uploads_db.exists():
            uploads_db.unlink()


def test_new_uploads_db_not_swallowed_by_retired_migration(tmp_db_path):
    """退役旧迁移不吞回：uploads.db 里的隔离表在 init_db 后不得被复制进主库 knot.db。"""
    uploads_db = Path(base_mod.SQLITE_DB_PATH).parent / "uploads.db"
    eng = doris.create_sqlite_engine(str(uploads_db))
    with eng.connect() as c:
        c.execute(sqlalchemy.text('CREATE TABLE "t_iso" (x INTEGER)'))
        c.execute(sqlalchemy.text('INSERT INTO "t_iso" VALUES (1)'))
        c.commit()
    eng.dispose()
    try:
        base_mod.init_db()  # 含新隔离迁移；不含退役的吞回迁移
        conn = base_mod.get_conn()
        swallowed = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='t_iso'"
        ).fetchone()
        conn.close()
        assert swallowed is None, "uploads.db 的表绝不能被吞回主库 knot.db（旧迁移已退役）"
    finally:
        if uploads_db.exists():
            uploads_db.unlink()


def test_migrate_conflict_normalized_schema_recovers(tmp_db_path):
    """v0.9.2 对抗 #2：同名 t_* 在主库(原始 DDL) + uploads(归一化 DDL) 但列签名+行数一致（WAL split-commit
    残留场景）→ 归一化列签名比判等 → 删主库冗余、**不 fail-closed abort**（raw DDL 文本比会误 raise → 永久 abort）。"""
    uploads_db = Path(base_mod.SQLITE_DB_PATH).parent / "uploads.db"
    conn = base_mod.get_conn()
    try:
        conn.execute('CREATE TABLE "t_x" ("a" REAL, "b" TEXT)')   # 主库：原始 DDL（引号+空格）
        conn.execute("INSERT INTO \"t_x\" VALUES (1.0, 'y')")
        conn.commit()
        upload_repo.create_file_upload(user_id=1, filename="x.csv", table_name="t_x", row_count=1, columns=["a", "b"])
        eng = doris.create_sqlite_engine(str(uploads_db))         # uploads：归一化 DDL（无引号无空格），同列类型+同数据
        with eng.connect() as c:
            c.execute(sqlalchemy.text("CREATE TABLE t_x(a REAL,b TEXT)"))
            c.execute(sqlalchemy.text("INSERT INTO t_x VALUES (1.0, 'y')"))
            c.commit()
        eng.dispose()
        base_mod._migrate_uploads_to_isolated_db_once(conn)       # 列签名/行数一致 → 删主库冗余，不 raise
        gone = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='t_x'").fetchone()
        assert gone is None, "归一化列签名判等 → 主库冗余副本应删（非 raw-DDL 误判冲突 abort）"
    finally:
        conn.close()
        if uploads_db.exists():
            uploads_db.unlink()
