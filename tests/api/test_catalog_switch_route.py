"""tests/api/test_catalog_switch_route — v0.6.2.5 段 4 (A1) commit 4 守护测试。

覆盖：
- POST /api/catalog/switch：per-user active 切换 + catalog.switch audit（38→39）+ catalog_id 落库（R-PB-A1-10）
- 多 catalog 管理路由：GET/POST/PUT/DELETE /api/admin/catalogs（OOS-1：0 tenant）
- ghost catalog_id 切换 → 404（set_user_active_catalog MetadataError）
- 默认 catalog id=1 不可删 → 400
"""


def _audit_rows(action: str):
    """直读 audit_log（client fixture 已 monkeypatch base.SQLITE_DB_PATH）。"""
    from knot.repositories.base import get_conn
    conn = get_conn()
    rows = [dict(r) for r in conn.execute(
        "SELECT action, resource_id, catalog_id FROM audit_log WHERE action=?", (action,)
    ).fetchall()]
    conn.close()
    return rows


# ─── 多 catalog 管理路由 ─────────────────────────────────────────────

def test_list_catalogs_has_default(client, auth_headers):
    r = client.get("/api/admin/catalogs", headers=auth_headers)
    assert r.status_code == 200, r.text
    cats = r.json()["catalogs"]
    assert any(c["id"] == 1 and c["name"] == "默认 Catalog" for c in cats)


def test_create_update_delete_catalog(client, auth_headers):
    # create
    r = client.post("/api/admin/catalogs", json={"name": "业务方 B", "description": "B"},
                    headers=auth_headers)
    assert r.status_code == 200, r.text
    cid = r.json()["id"]
    assert cid > 1
    # update（含内容字段）
    r = client.put(f"/api/admin/catalogs/{cid}",
                   json={"name": "业务方 B2", "business_rules": "rule B"},
                   headers=auth_headers)
    assert r.status_code == 200, r.text
    assert set(r.json()["saved"]) >= {"name", "business_rules"}
    # delete
    r = client.delete(f"/api/admin/catalogs/{cid}", headers=auth_headers)
    assert r.status_code == 200 and r.json()["deleted"] == cid


def test_create_catalog_requires_name(client, auth_headers):
    r = client.post("/api/admin/catalogs", json={"description": "no name"}, headers=auth_headers)
    assert r.status_code == 400


def test_delete_default_catalog_forbidden(client, auth_headers):
    """OOS 兜底：默认 catalog id=1 不可删。"""
    r = client.delete("/api/admin/catalogs/1", headers=auth_headers)
    assert r.status_code == 400


def test_update_nonexistent_catalog_404(client, auth_headers):
    r = client.put("/api/admin/catalogs/9999", json={"name": "x"}, headers=auth_headers)
    assert r.status_code == 404


# ─── per-user switch + catalog.switch audit ─────────────────────────

def test_switch_active_catalog_and_audit(client, auth_headers):
    # 新建一个 catalog 供切换
    cid = client.post("/api/admin/catalogs", json={"name": "切换目标"},
                      headers=auth_headers).json()["id"]
    # 切换
    r = client.post("/api/catalog/switch", json={"catalog_id": cid}, headers=auth_headers)
    assert r.status_code == 200, r.text
    assert r.json()["active_catalog_id"] == cid
    # active_catalog_id 落库
    from knot.repositories import catalog_repo, user_repo
    admin = user_repo.get_user_by_username("admin")
    assert catalog_repo.get_user_active_catalog_id(admin["id"]) == cid
    # catalog.switch audit 落库 + catalog_id（R-PB-A1-10）
    rows = _audit_rows("catalog.switch")
    assert any(int(row["catalog_id"]) == cid and int(row["resource_id"]) == cid for row in rows)


def test_switch_to_ghost_catalog_404(client, auth_headers):
    r = client.post("/api/catalog/switch", json={"catalog_id": 99999}, headers=auth_headers)
    assert r.status_code == 404


def test_switch_requires_int_catalog_id(client, auth_headers):
    r = client.post("/api/catalog/switch", json={"catalog_id": "abc"}, headers=auth_headers)
    assert r.status_code == 400
