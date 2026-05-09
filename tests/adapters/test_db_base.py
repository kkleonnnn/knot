"""adapters/db/base 契约单测。"""
from knot.adapters.db.base import BusinessDBAdapter, is_safe_sql


def test_is_safe_sql_select():
    ok, _ = is_safe_sql("SELECT * FROM users WHERE id = 1")
    assert ok


def test_is_safe_sql_rejects_drop():
    ok, msg = is_safe_sql("DROP TABLE users")
    assert not ok
    assert msg


def test_is_safe_sql_rejects_delete():
    ok, _ = is_safe_sql("DELETE FROM users")
    assert not ok


def test_is_safe_sql_rejects_insert():
    ok, _ = is_safe_sql("INSERT INTO users (id) VALUES (1)")
    assert not ok


def test_is_safe_sql_rejects_update():
    ok, _ = is_safe_sql("UPDATE users SET name='x'")
    assert not ok


def test_is_safe_sql_rejects_stacked():
    ok, _ = is_safe_sql("SELECT 1; DROP TABLE users")
    assert not ok


def test_is_safe_sql_allows_show():
    ok, _ = is_safe_sql("SHOW TABLES")
    assert ok


def test_protocol_runtime_check():
    class FakeAdapter:
        def execute_query(self, sql, max_rows=500):
            return [], None

        def get_schema(self, databases=None, max_tables=20):
            return ""

        def check_readonly_grants(self):
            return True, []

        def test_connection(self):
            return True, None

    assert isinstance(FakeAdapter(), BusinessDBAdapter)


def test_protocol_runtime_check_rejects_partial():
    class PartialAdapter:
        def execute_query(self, sql):
            return [], None

    # missing other methods
    assert not isinstance(PartialAdapter(), BusinessDBAdapter)
