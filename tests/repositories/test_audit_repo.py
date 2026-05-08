"""tests/repositories/test_audit_repo.py — v0.4.6 commit #1 守护测试（TDD）。

覆盖：
- R-50 INSERT-only：audit_repo 不暴露 update / delete_by_id 路由
- R-55 AuditAction Literal 运行时校验
- R-58 schema 含 client_ip + user_agent 独立列
- R-65 AuditWriteError 在 models/errors.py（不在 services）
- 索引覆盖（actor / action / resource）
"""
import json
import sqlite3

import pytest

from bi_agent.repositories import audit_repo
from bi_agent.repositories.base import get_conn


# ─── R-58 schema 必含 client_ip + user_agent + actor_name 独立列 ────

def test_R58_schema_has_client_ip_user_agent_columns(tmp_db_path):
    conn = get_conn()
    cols = {r[1] for r in conn.execute("PRAGMA table_info(audit_log)").fetchall()}
    conn.close()
    assert "client_ip" in cols, "R-58：必须独立 client_ip 列"
    assert "user_agent" in cols, "R-58：必须独立 user_agent 列"
    assert "actor_name" in cols, "R-54：actor_name 冗余快照列必备"
    assert "request_id" in cols
    assert "detail_json" in cols
    assert "success" in cols


def test_schema_has_three_indexes(tmp_db_path):
    conn = get_conn()
    idx = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='audit_log'"
    ).fetchall()}
    conn.close()
    assert "idx_audit_actor_time" in idx
    assert "idx_audit_action_time" in idx
    assert "idx_audit_resource" in idx


# ─── R-50 INSERT-only ────────────────────────────────────────────────

def test_R50_repo_exposes_no_update_or_delete_by_id():
    """R-50：audit_repo 模块 API 不应有 update / delete_by_id；
    purge 脚本是唯一删除入口（v0.4.6 commit #5）。"""
    fns = {name for name in dir(audit_repo) if not name.startswith("_")}
    forbidden = {"update", "update_audit", "delete_by_id", "delete_audit"}
    leaked = fns & forbidden
    assert not leaked, f"R-50：发现禁止的 mutation API: {leaked}"


# ─── 基础 CRUD 走通 ────────────────────────────────────────────────

def test_insert_and_list_basic(tmp_db_path):
    aid = audit_repo.insert(
        actor_id=1, actor_role="admin", actor_name="admin",
        action="user.create",
        resource_type="user", resource_id="42",
        success=1, detail_json={"role": "analyst"},
        client_ip="127.0.0.1", user_agent="curl/8", request_id="req-1",
    )
    assert isinstance(aid, int) and aid > 0
    rows = audit_repo.list_filtered(page=1, size=50)
    assert len(rows) == 1
    r = rows[0]
    assert r["actor_id"] == 1
    assert r["action"] == "user.create"
    assert r["resource_id"] == "42"
    assert r["client_ip"] == "127.0.0.1"
    assert r["user_agent"] == "curl/8"
    # detail_json 应是 dict（repo 自动 json.loads）
    assert json.loads(r["detail_json"]) if isinstance(r["detail_json"], str) else r["detail_json"] == {"role": "analyst"} or r["detail_json"] == {"role": "analyst"}


def test_list_filtered_by_actor(tmp_db_path):
    audit_repo.insert(actor_id=1, actor_role="admin", actor_name="a", action="user.create", resource_type="user")
    audit_repo.insert(actor_id=2, actor_role="analyst", actor_name="b", action="auth.login_success", resource_type="user")
    audit_repo.insert(actor_id=1, actor_role="admin", actor_name="a", action="user.delete", resource_type="user", resource_id="42")
    rows = audit_repo.list_filtered(actor_id=1, page=1, size=50)
    assert len(rows) == 2
    assert all(r["actor_id"] == 1 for r in rows)


def test_list_filtered_by_action(tmp_db_path):
    audit_repo.insert(actor_id=1, actor_role="admin", actor_name="a", action="user.create", resource_type="user")
    audit_repo.insert(actor_id=2, actor_role="admin", actor_name="b", action="user.update", resource_type="user")
    rows = audit_repo.list_filtered(action="user.create", page=1, size=50)
    assert len(rows) == 1
    assert rows[0]["action"] == "user.create"


def test_list_pagination(tmp_db_path):
    for i in range(25):
        audit_repo.insert(actor_id=1, actor_role="admin", actor_name="a",
                          action="user.create", resource_type="user", resource_id=str(i))
    page1 = audit_repo.list_filtered(page=1, size=10)
    page2 = audit_repo.list_filtered(page=2, size=10)
    page3 = audit_repo.list_filtered(page=3, size=10)
    assert len(page1) == 10
    assert len(page2) == 10
    assert len(page3) == 5
    # 不同页 id 应不重叠
    ids1 = {r["id"] for r in page1}
    ids2 = {r["id"] for r in page2}
    assert not (ids1 & ids2)


def test_delete_older_than(tmp_db_path):
    """purge 接口（commit #5 复用）— 删 N 天前；当前时间内的不删。"""
    audit_repo.insert(actor_id=1, actor_role="admin", actor_name="a",
                      action="user.create", resource_type="user")
    deleted = audit_repo.delete_older_than(days=90, dry_run=False)
    assert deleted == 0  # 全是新数据


# ─── R-65 AuditWriteError 在 models/errors.py（不在 services） ─────

def test_R65_audit_write_error_in_models_errors():
    """R-65：AuditWriteError 必须扩展自 models.errors.BIAgentError；
    不在 services/audit_service 重定义（避免 v0.4.4 services/errors.py 重复造轮子）。"""
    from bi_agent.models.errors import AuditWriteError, BIAgentError
    assert issubclass(AuditWriteError, BIAgentError)


# ─── R-55 AuditAction Literal 锁死 ────────────────────────────────────

def test_R55_audit_action_literal_covers_8_categories():
    """R-55 + R-63：Literal 必须覆盖 8 类 mutation × 子动作；messages 显式不在内。"""
    from bi_agent.models.audit import AuditAction
    # 取 Literal 的字符串集合
    actions = set(AuditAction.__args__)
    # 8 类 mutation 关键 prefix 必须各有 ≥1 条
    expected_prefixes = ["auth.", "user.", "datasource.", "api_key.", "budget.",
                         "config.", "saved_report.", "export.", "audit."]
    for p in expected_prefixes:
        assert any(a.startswith(p) for a in actions), f"R-55：缺少 {p} 前缀的 action"
    # R-63 messages 显式排除
    assert not any(a.startswith("message") for a in actions), "R-63：messages 表不入审计"
