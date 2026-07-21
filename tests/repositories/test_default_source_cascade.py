"""v0.8.24 — data_source 删除级联清理 + 悬空治愈（repo/migration 层）。

覆盖 MF1/MF3/MF4/MF6：delete_datasource 级联清 user_sources/default_source_id/bi_reports（saved_reports
不动 R-S7）· 事务原子性（中途异常回滚）· datasource_exists decrypt-free · migration 治存量 + 幂等 + 空集不 wipe。
"""
import pytest

from knot.repositories import base, data_source_repo, migrations, user_repo


def _mk_report(created_by: int, data_source_id) -> int:
    conn = base.get_conn()
    conn.execute(
        "INSERT INTO bi_reports (title, sql_text, created_by, data_source_id) VALUES ('t', 's', ?, ?)",
        (created_by, data_source_id),
    )
    rid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    conn.close()
    return rid


def test_delete_datasource_nulls_default_source_id(tmp_db_path):
    admin = user_repo.get_user_by_username("admin")
    sid = data_source_repo.create_datasource(1, "x", "", "h", 9030, "u", "p", "d")
    user_repo.update_user(admin["id"], default_source_id=sid)
    data_source_repo.delete_datasource(sid)
    assert user_repo.get_user_by_id(admin["id"])["default_source_id"] is None


def test_delete_datasource_clears_user_sources(tmp_db_path):
    admin = user_repo.get_user_by_username("admin")
    sid = data_source_repo.create_datasource(1, "x", "", "h", 9030, "u", "p", "d")
    data_source_repo.set_user_sources(admin["id"], [sid])
    data_source_repo.delete_datasource(sid)
    assert sid not in data_source_repo.get_user_source_ids(admin["id"])


def test_delete_datasource_nulls_bi_reports(tmp_db_path):
    sid = data_source_repo.create_datasource(1, "x", "", "h", 9030, "u", "p", "d")
    rid = _mk_report(created_by=1, data_source_id=sid)
    data_source_repo.delete_datasource(sid)
    conn = base.get_conn()
    val = conn.execute("SELECT data_source_id FROM bi_reports WHERE id=?", (rid,)).fetchone()[0]
    conn.close()
    assert val is None


def test_datasource_exists(tmp_db_path):
    sid = data_source_repo.create_datasource(1, "x", "", "h", 9030, "u", "p", "d")
    assert data_source_repo.datasource_exists(sid) is True
    assert data_source_repo.datasource_exists(99999) is False


def test_delete_datasource_transaction_atomic(tmp_db_path, monkeypatch):
    """MF4：中途语句 raise → rollback，不留部分提交（user_sources/default 均保持）。"""
    admin = user_repo.get_user_by_username("admin")
    sid = data_source_repo.create_datasource(1, "x", "", "h", 9030, "u", "p", "d")
    user_repo.update_user(admin["id"], default_source_id=sid)
    data_source_repo.set_user_sources(admin["id"], [sid])

    real_get_conn = data_source_repo.get_conn

    class _FailConn:
        def __init__(self, c):
            self._c = c

        def execute(self, sql, *a):
            if "bi_reports" in sql:            # 第 3 条语句 → 前两条已执行未提交
                raise RuntimeError("boom")
            return self._c.execute(sql, *a)

        def commit(self):
            self._c.commit()

        def rollback(self):
            self._c.rollback()

        def close(self):
            self._c.close()

    monkeypatch.setattr(data_source_repo, "get_conn", lambda: _FailConn(real_get_conn()))
    with pytest.raises(RuntimeError):
        data_source_repo.delete_datasource(sid)
    # 不 monkeypatch.undo()：会连带撤掉 tmp_db_path fixture 的 SQLITE_DB_PATH patch（同一
    # function-scoped monkeypatch）；_FailConn 仅对 bi_reports SQL 抛错，下列断言查询走 wrapper 正常。

    # 全部回滚：源仍在 + default 仍指向 + user_sources 仍有
    assert data_source_repo.get_datasource(sid) is not None
    assert user_repo.get_user_by_id(admin["id"])["default_source_id"] == sid
    assert sid in data_source_repo.get_user_source_ids(admin["id"])


def test_migration_heals_dangling(tmp_db_path):
    """MF3/MF7：迁移无条件治已存在非空 DB 的悬空（default/user_sources/bi_reports）+ 二次幂等。"""
    admin = user_repo.get_user_by_username("admin")
    real_sid = data_source_repo.create_datasource(1, "real", "", "h", 9030, "u", "p", "d")  # 令 COUNT>0 护栏通过
    conn = base.get_conn()
    conn.execute("UPDATE users SET default_source_id=999 WHERE id=?", (admin["id"],))
    conn.execute("INSERT OR IGNORE INTO user_sources (user_id, source_id) VALUES (?, 999)", (admin["id"],))
    conn.execute("INSERT INTO bi_reports (title, sql_text, created_by, data_source_id) VALUES ('t','s',1,999)")
    conn.commit()
    conn.close()

    conn = base.get_conn()
    migrations.run_post_schema_migrations(conn)
    conn.commit()
    conn.close()

    assert user_repo.get_user_by_id(admin["id"])["default_source_id"] is None
    assert 999 not in data_source_repo.get_user_source_ids(admin["id"])
    conn = base.get_conn()
    assert conn.execute("SELECT COUNT(*) FROM bi_reports WHERE data_source_id=999").fetchone()[0] == 0
    conn.close()

    # 二次幂等 + 有效源未被误清
    conn = base.get_conn()
    migrations.run_post_schema_migrations(conn)
    conn.commit()
    conn.close()
    assert data_source_repo.get_datasource(real_sid) is not None


def test_migration_empty_datasources_no_wipe(tmp_db_path):
    """MF6/G2：data_sources 空时 COUNT 护栏 → 不清 user_sources（防 v0.9 per-tenant bootstrap 瞬时空态 mass-wipe）。"""
    admin = user_repo.get_user_by_username("admin")
    conn = base.get_conn()
    conn.execute("DELETE FROM data_sources")
    conn.execute("INSERT OR IGNORE INTO user_sources (user_id, source_id) VALUES (?, 5)", (admin["id"],))
    conn.commit()
    conn.close()

    conn = base.get_conn()
    migrations.run_post_schema_migrations(conn)
    conn.commit()
    conn.close()

    assert 5 in data_source_repo.get_user_source_ids(admin["id"])
