"""tests/api/test_audit_purge.py — v0.6.0.5 F-C audit 自动清理守护。

覆盖（v0.5 守护者 M-C1~M-C5）：
- POST /api/admin/audit/purge 立即清理 + meta-audit
- GET /api/admin/audit/purge-status 返回 last_purge_at
- audit_repo.delete_older_than chunk 模式（默认 chunk_size=1000）
- retention 边界 7~3650 后端 422 (R-49 sustained)
- meta-audit detail trigger 字段（auto / manual / cli）
"""
from __future__ import annotations


def _seed_old_audit_rows(n: int = 50, days_ago: int = 100):
    """fixture 辅助：直接 SQL 插入 n 行 created_at = N 天前的 audit_log。"""
    from knot.repositories.base import get_conn
    conn = get_conn()
    for i in range(n):
        conn.execute(
            "INSERT INTO audit_log (action, resource_type, success, "
            "                       detail_json, created_at) "
            "VALUES (?,?,?,?, datetime('now','localtime', ?))",
            ("auth.login_success", "user", 1, "{}", f"-{days_ago} days"),
        )
    conn.commit()
    conn.close()


def test_purge_status_endpoint_returns_last_purge_at(client, auth_headers):
    """POST /api/admin/audit/purge 后 last_purge_at 字段更新（注意：startup auto-hook
    可能已在 client fixture 启动时跑过 → 初始值可能已存在，本测试只断言 manual
    触发后字段非空 + trigger=manual）。"""
    # 触发清理（即使 0 行也应更新 last_purge_at）
    r2 = client.post("/api/admin/audit/purge", headers=auth_headers)
    assert r2.status_code == 200
    assert r2.json()["ok"] is True
    assert r2.json()["trigger"] == "manual"

    r3 = client.get("/api/admin/audit/purge-status", headers=auth_headers)
    assert r3.status_code == 200
    assert r3.json()["last_purge_at"] is not None


def test_purge_deletes_old_rows_and_writes_meta_audit(client, auth_headers):
    """purge 真删 + R-57 meta-audit 写入 action=audit.purge + trigger=manual。"""
    _seed_old_audit_rows(n=30, days_ago=100)  # 100 天前 30 行（默认 retention 90 → 全删）
    r = client.post("/api/admin/audit/purge", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["deleted"] == 30
    assert r.json()["trigger"] == "manual"

    # 检查 meta-audit
    from knot.repositories.base import get_conn
    conn = get_conn()
    row = conn.execute(
        "SELECT detail_json FROM audit_log "
        "WHERE action='audit.purge' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    assert row is not None, "audit.purge meta-audit 必须写入"
    import json as _j
    detail = _j.loads(row[0])
    assert detail.get("trigger") == "manual"
    assert detail.get("deleted_count") == 30


def test_chunk_delete_handles_large_batches(client, auth_headers):
    """M-C1 chunk DELETE 默认 1000 — 插 2500 行验证多批次处理。"""
    _seed_old_audit_rows(n=2500, days_ago=100)
    r = client.post("/api/admin/audit/purge", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["deleted"] == 2500


def test_purge_requires_admin(client):
    r = client.post("/api/admin/audit/purge")
    assert r.status_code in (401, 403)


def test_retention_boundary_7_to_3650(client, auth_headers):
    """R-49 retention 7~3650 边界 — < 7 或 > 3650 → 400。"""
    r1 = client.put("/api/admin/audit-config",
                    json={"retention_days": 6}, headers=auth_headers)
    assert r1.status_code == 400
    r2 = client.put("/api/admin/audit-config",
                    json={"retention_days": 3651}, headers=auth_headers)
    assert r2.status_code == 400
    # 边界内
    r3 = client.put("/api/admin/audit-config",
                    json={"retention_days": 30}, headers=auth_headers)
    assert r3.status_code == 200
