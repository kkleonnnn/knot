"""tests/api/test_metrics_admin.py — v0.7.0 C2 指标注册表 admin 路由不变量 carrier。

§4.5 不变量 API 层守护（C2 同址而生）：
- gate 鉴权 + R-2FA：metric 端点全 require_admin（→ get_current_user 链含 2FA enroll gate
  → R-2FA 透传继承，metrics.py 无独立鉴权代码路径）；无 token 401/403 + 非 admin 403。
- 审计接线：create/update/delete 各落对应 AuditAction Literal（metric.create/update/delete）。
- OOS-1 死线（API 层）：MetricCreate/Update Pydantic 模型结构性 0 tenant_id/project_id 字段
  （+ repo 层 `_reject_forbidden` 死锁双层；见 test_metric_repo）。
"""
from knot.repositories import audit_repo


def _last_action(prefix: str):
    for r in audit_repo.list_filtered(page=1, size=200):
        if r["action"].startswith(prefix):
            return r
    return None


# ─── gate 鉴权 + R-2FA enroll gate（继承）────────────────────────────

def test_metric_endpoint_requires_auth(client):
    """无 token → 401/403（HTTPBearer）；证 metric 端点强制鉴权。"""
    r = client.get("/api/admin/metrics-registry")
    assert r.status_code in (401, 403)


def test_metric_endpoint_rejects_non_admin(client, auth_headers):
    """非 admin（analyst）→ 403（require_admin）。

    R-2FA：require_admin → get_current_user 含 2FA enroll gate，metric 端点无独立鉴权
    代码路径 → 2FA 不变量透传继承（无需单独 carrier 测试）。
    """
    create = client.post(
        "/api/admin/users",
        json={"username": "metric_analyst", "password": "p", "role": "analyst"},
        headers=auth_headers,
    )
    assert create.status_code == 200
    login = client.post("/api/auth/login", json={"username": "metric_analyst", "password": "p"})
    assert login.status_code == 200
    tok = login.json()["token"]

    r = client.get("/api/admin/metrics-registry", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 403


# ─── CRUD + 审计接线（每 Literal emit）────────────────────────────────

def test_metric_crud_and_audit(client, auth_headers):
    """admin CRUD 闭环 + create/update/delete 各落对应审计 Literal。"""
    # create
    r = client.post("/api/admin/metrics-registry", headers=auth_headers, json={
        "name": "gmv", "display": "成交额 GMV", "caliber": "SUM(o.pay_amount)",
        "aliases": '["成交额","gmv"]', "dimensions": '["date","city"]',
    })
    assert r.status_code == 200, f"create 应 200；实际 {r.status_code}: {r.text}"
    mid = r.json()["id"]
    assert _last_action("metric.create") is not None, "create 须落 metric.create 审计"
    assert _last_action("metric.create")["resource_type"] == "metric"

    # get
    g = client.get(f"/api/admin/metrics-registry/{mid}", headers=auth_headers)
    assert g.status_code == 200 and g.json()["name"] == "gmv"
    assert g.json()["catalog_id"] == 1  # OOS-1 默认归属

    # list
    lst = client.get("/api/admin/metrics-registry", headers=auth_headers)
    assert lst.status_code == 200 and any(m["id"] == mid for m in lst.json())

    # update
    u = client.put(f"/api/admin/metrics-registry/{mid}", headers=auth_headers,
                   json={"caliber": "SUM(o.amt)", "display": "GMV"})
    assert u.status_code == 200
    assert _last_action("metric.update") is not None, "update 须落 metric.update 审计"
    assert client.get(f"/api/admin/metrics-registry/{mid}", headers=auth_headers).json()["caliber"] == "SUM(o.amt)"

    # delete
    d = client.delete(f"/api/admin/metrics-registry/{mid}", headers=auth_headers)
    assert d.status_code == 200
    assert _last_action("metric.delete") is not None, "delete 须落 metric.delete 审计"
    assert client.get(f"/api/admin/metrics-registry/{mid}", headers=auth_headers).status_code == 404


def test_get_missing_metric_404(client, auth_headers):
    r = client.get("/api/admin/metrics-registry/99999", headers=auth_headers)
    assert r.status_code == 404


# ─── OOS-1 死线（API 层结构性）──────────────────────────────────────

def test_request_schemas_have_no_tenant_fields():
    """MetricCreate/Update Pydantic 模型结构性 0 tenant_id/project_id（API 层不可注入）。"""
    from knot.api.admin.metrics import MetricCreateRequest, MetricUpdateRequest
    for model in (MetricCreateRequest, MetricUpdateRequest):
        fields = set(model.model_fields)
        assert "tenant_id" not in fields and "project_id" not in fields, (
            f"OOS-1 死线：{model.__name__} 严禁 tenant_id/project_id 字段"
        )


def test_route_path_avoids_internal_metrics_collision():
    """metric 注册表路由用 /api/admin/metrics-registry（避与既有 /api/admin/metrics 内测 KPI 撞）。"""
    from knot.api.admin.metrics import router
    paths = {r.path for r in router.routes}
    assert "/api/admin/metrics-registry" in paths
    assert "/api/admin/metrics" not in paths, "严禁占用既有内测 KPI 屏 /api/admin/metrics"
