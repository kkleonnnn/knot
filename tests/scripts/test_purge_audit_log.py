"""tests/scripts/test_purge_audit_log.py — v0.4.6 commit #5 守护测试。

R-66 复用 v0.4.5 模式 / R-49 retention 默认 / R-57 meta-audit
"""
from pathlib import Path

import pytest

from bi_agent.repositories import audit_repo, settings_repo


def _seed_n_old_rows(n: int):
    """直接走 sqlite3 写入「100 天前」的 audit_log 行（绕过 created_at 默认值）。"""
    import sqlite3

    from bi_agent.repositories.base import get_conn
    conn = get_conn()
    for i in range(n):
        conn.execute(
            "INSERT INTO audit_log (actor_id, actor_role, actor_name, action, resource_type, "
            "resource_id, success, detail_json, created_at) "
            "VALUES (?, 'admin', 'a', 'user.update', 'user', ?, 1, '{}', "
            "datetime('now','localtime','-100 days'))",
            (1, str(i)),
        )
    conn.commit()
    conn.close()


def _seed_n_recent_rows(n: int):
    """新数据（默认 created_at = now）。"""
    for i in range(n):
        audit_repo.insert(
            actor_id=2, actor_role="admin", actor_name="a",
            action="user.create", resource_type="user", resource_id=str(i),
        )


# ─── R-49 retention 默认 90 天 ────────────────────────────────────────

def test_R49_default_retention_90_days(tmp_db_path):
    """app_settings 中 audit.retention_days 缺失时，默认应取 90。"""
    val = settings_repo.get_app_setting("audit.retention_days", "90")
    assert val == "90"


# ─── purge 主流程 ────────────────────────────────────────────────────

def test_purge_deletes_old_only(tmp_db_path):
    """老行（>90 天）被删；新行保留。"""
    _seed_n_old_rows(5)
    _seed_n_recent_rows(3)

    from bi_agent.scripts import purge_audit_log
    stats = purge_audit_log.purge(dry_run=False)

    assert stats["deleted"] == 5
    remaining = audit_repo.list_filtered(page=1, size=200)
    # 注：purge 自身入 audit_log（R-57 meta-audit），所以剩 3 + 1
    assert len(remaining) >= 3
    assert all(r["action"] != "user.update" for r in remaining)  # 老行的 action 已清


def test_R66_purge_dry_run_does_not_write(tmp_db_path):
    """R-66 dry-run 0 副作用：不删 + 不创 bak。"""
    _seed_n_old_rows(3)

    from bi_agent.scripts import purge_audit_log
    stats = purge_audit_log.purge(dry_run=True)

    assert stats["deleted"] == 3  # dry-run 仍统计 would_delete
    # 老行仍在
    rows = audit_repo.list_filtered(page=1, size=200)
    assert len([r for r in rows if r["action"] == "user.update"]) == 3
    # bak 不应创建
    db_dir = Path(tmp_db_path).parent
    baks = list(db_dir.glob(f"{Path(tmp_db_path).name}.audit-purge-*.bak"))
    assert not baks, "dry-run 严禁创建 bak"


def test_R66_purge_creates_timestamped_backup(tmp_db_path):
    """R-66 + v0.4.5 模式：真跑生成 timestamped .bak。"""
    _seed_n_old_rows(2)

    from bi_agent.scripts import purge_audit_log
    stats = purge_audit_log.purge(dry_run=False)

    bak = stats.get("backup_path")
    assert bak is not None, "R-66：必须生成 .bak"
    assert "audit-purge-" in bak, "bak 命名带版本号"
    assert Path(bak).exists()


def test_R66_purge_uses_audit_repo_delete_older_than(tmp_db_path, monkeypatch):
    """R-66：purge 必须复用 commit #1 的 audit_repo.delete_older_than，不重写 SQL。"""
    called = {"n": 0}
    real = audit_repo.delete_older_than

    def _spy(days, dry_run=False):
        called["n"] += 1
        return real(days, dry_run=dry_run)

    monkeypatch.setattr(audit_repo, "delete_older_than", _spy)
    from bi_agent.scripts import purge_audit_log
    purge_audit_log.purge(dry_run=False)
    assert called["n"] >= 1


# ─── R-57 meta-audit：purge 自身入 log ────────────────────────────────

def test_R57_purge_run_creates_meta_audit_entry(tmp_db_path):
    """purge 真跑后，audit_log 应有一条 action='audit.purge'。"""
    _seed_n_old_rows(2)
    from bi_agent.scripts import purge_audit_log
    purge_audit_log.purge(dry_run=False)

    rows = audit_repo.list_filtered(action="audit.purge", page=1, size=10)
    assert len(rows) == 1
    assert rows[0]["actor_id"] is None  # 脚本场景 actor=None
    assert rows[0]["detail_json"].get("deleted_count") == 2


def test_R57_purge_dry_run_no_meta_audit(tmp_db_path):
    """dry-run 不写 → 不入 meta-audit。"""
    _seed_n_old_rows(2)
    from bi_agent.scripts import purge_audit_log
    purge_audit_log.purge(dry_run=True)

    rows = audit_repo.list_filtered(action="audit.purge", page=1, size=10)
    assert len(rows) == 0
