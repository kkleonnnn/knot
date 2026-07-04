"""tests/repositories/test_migration_observability.py — v0.7.41 B2.3 回归守护。

_migrate_uploads_db_once 的 print → logger 可观测化：
- 成功路径 → logger.info（moved/skipped 计数）
- 失败路径 → logger.exception（带 traceback；吞掉的 migration 异常可观测价值全在栈）+ fail-soft 不 raise

原错误路径完全无测试（仅 print 静默吞）；本文件补最小守护，防回退 print / 静默崩。
"""
from __future__ import annotations

import sqlite3


class _LoggerSpy:
    def __init__(self):
        self.calls = {}

    def info(self, msg):
        self.calls["info"] = msg

    def exception(self, msg):
        self.calls["exception"] = msg


def test_migrate_uploads_error_path_logs_exception(tmp_path, monkeypatch):
    """畸形 uploads.db → except 分支走 logger.exception + fail-soft 不 raise。"""
    from knot.repositories import base as base_mod

    db_path = tmp_path / "knot.db"
    monkeypatch.setattr(base_mod, "SQLITE_DB_PATH", str(db_path))
    # 非法 sqlite 文件：ATTACH 后读 up.sqlite_master 必失败 → except 分支
    (tmp_path / "uploads.db").write_text("not a sqlite database")

    spy = _LoggerSpy()
    monkeypatch.setattr(base_mod, "logger", spy)

    conn = sqlite3.connect(str(db_path))
    base_mod._migrate_uploads_db_once(conn)  # fail-soft：不 raise
    conn.close()

    assert "exception" in spy.calls, "错误路径须走 logger.exception（非 print / 非静默）"
    assert "uploads.db merge" in spy.calls["exception"]


def test_migrate_uploads_success_path_logs_info(tmp_path, monkeypatch):
    """合法 uploads.db 含一张表 → 搬迁成功走 logger.info(moved=1)。"""
    from knot.repositories import base as base_mod

    db_path = tmp_path / "knot.db"
    monkeypatch.setattr(base_mod, "SQLITE_DB_PATH", str(db_path))
    up = sqlite3.connect(str(tmp_path / "uploads.db"))
    up.execute("CREATE TABLE up_user_1 (a INT)")
    up.execute("INSERT INTO up_user_1 VALUES (1)")
    up.commit()
    up.close()

    spy = _LoggerSpy()
    monkeypatch.setattr(base_mod, "logger", spy)

    conn = sqlite3.connect(str(db_path))
    base_mod._migrate_uploads_db_once(conn)
    conn.close()

    assert "info" in spy.calls, "成功路径须走 logger.info（非 print）"
    assert "moved=1" in spy.calls["info"]
    assert "exception" not in spy.calls
