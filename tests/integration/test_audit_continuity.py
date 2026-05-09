"""tests/integration/test_audit_continuity.py — v0.5.0 R-75 审计日志连续性守护（TDD）。

R-75：DB rename 后 v0.4.6 产生的 audit_log 表数据完整无损 + rename 前写的行 rename 后可读。
（守护者答资深架构师维度 1 —— 一致性 / R-50 审计契约）
"""
import tempfile
from pathlib import Path


def test_R75_audit_log_rows_survive_db_rename(monkeypatch):
    """rename 前写 1 条 audit + rename 后 GET /api/admin/audit-log 见原行。

    端到端验证：v0.4.6 audit_log schema → v0.5.0 DB rename → 数据可读。
    """
    with tempfile.TemporaryDirectory() as tmp:
        data_dir = Path(tmp)
        old_db = data_dir / "bi_agent.db"

        # 1. 模拟 v0.4.6 状态：直接初始化老 db + 写 audit_log
        from knot.repositories import base as base_mod
        monkeypatch.setattr(base_mod, "SQLITE_DB_PATH", str(old_db))
        base_mod.init_db()

        from knot.repositories import audit_repo
        audit_repo.insert(
            actor_id=1,
            actor_role="admin",
            actor_name="alice",
            action="user.create",
            resource_type="user",
            resource_id="42",
            success=1,
            detail_json='{"username":"newbie"}',
            client_ip="127.0.0.1",
            user_agent="pytest",
            request_id="req-001",
        )

        # 2. 跑 DB rename migration
        from knot.scripts.migrate_db_rename_v050 import migrate_db_rename
        result = migrate_db_rename(data_dir)
        assert result["status"] == "migrated"

        # 3. rename 后切到 knot.db；audit_log 表必须可读且数据完整
        new_db = data_dir / "knot.db"
        assert new_db.exists()

        monkeypatch.setattr(base_mod, "SQLITE_DB_PATH", str(new_db))
        # 现有表保留，无需 init_db
        rows = audit_repo.list_filtered(size=10)
        assert len(rows) == 1, "rename 前写的 audit 行必须保留"
        row = rows[0]
        assert row["actor_name"] == "alice"
        assert row["action"] == "user.create"
        assert row["client_ip"] == "127.0.0.1"
        assert row["user_agent"] == "pytest"


def test_R75_v045_encrypted_fields_survive_rename(monkeypatch):
    """v0.4.5 加密字段 + v0.4.6 audit 字段同时迁移：加密数据 rename 后仍可解密。

    防止 rename 过程破坏 enc_v1: 字段（守护者答资深维度 1 隐藏漏点 1：
    Contract 7 forbidden_modules 同步 + DB rename 对 enc_v1: 透明）。
    """
    with tempfile.TemporaryDirectory() as tmp:
        data_dir = Path(tmp)
        old_db = data_dir / "bi_agent.db"

        from knot.repositories import base as base_mod
        monkeypatch.setattr(base_mod, "SQLITE_DB_PATH", str(old_db))
        base_mod.init_db()

        # 写一个含加密 doris_password 的 user（repo 透明加密）
        from knot.repositories import user_repo
        user_repo.create_user(
            "alice",
            "h",
            "salt",
            "admin",
            "host",
            9030,
            "u",
            "secret-pwd",
            "db",
        )
        u_before = user_repo.get_user_by_username("alice")
        assert u_before["doris_password"] == "secret-pwd"

        # rename
        from knot.scripts.migrate_db_rename_v050 import migrate_db_rename
        migrate_db_rename(data_dir)
        new_db = data_dir / "knot.db"

        # 切到新 DB；加密字段仍可解
        monkeypatch.setattr(base_mod, "SQLITE_DB_PATH", str(new_db))
        u_after = user_repo.get_user_by_username("alice")
        assert u_after["doris_password"] == "secret-pwd", (
            "R-75：rename 后加密字段必须仍可解密"
        )
