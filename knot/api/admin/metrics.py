"""knot/api/admin/metrics.py — 指标注册表管理路由（v0.7.0 C2 语义层第一刀）。

route 前缀 `/api/admin/metrics-registry`（**避与既有 `/api/admin/metrics` 内测健康 KPI 屏撞**）。
全 require_admin（v0.7.0 metric 仅 admin 可见，继承 R-2FA enroll gate）。CRUD 经 metric_repo（OOS-1 死锁）。
审计接线：metric.create/update/delete（AuditAction）+ resource_type=metric。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from knot.api._audit_helpers import audit
from knot.api.deps import require_admin
from knot.models.errors import MetadataError
from knot.repositories import metric_repo

router = APIRouter()


class MetricCreateRequest(BaseModel):
    catalog_id: int = 1
    name: str
    caliber: str
    display: str = ""
    aliases: str = ""              # JSON list
    base_object: str = ""
    filters: str = ""              # JSON list
    dimensions: str = ""           # JSON list
    lineage: str = ""              # JSON list（inert — v0.7.1 编译校验）
    freshness_lag_days: int = 1
    enabled: int = 1


class MetricUpdateRequest(BaseModel):
    name: str | None = None
    caliber: str | None = None
    display: str | None = None
    aliases: str | None = None
    base_object: str | None = None
    filters: str | None = None
    dimensions: str | None = None
    lineage: str | None = None
    freshness_lag_days: int | None = None
    enabled: int | None = None


@router.get("/api/admin/metrics-registry")
async def admin_list_metrics(catalog_id: int | None = None, admin=Depends(require_admin)):
    return metric_repo.list_metrics(catalog_id)


@router.get("/api/admin/metrics-registry/{metric_id}")
async def admin_get_metric(metric_id: int, admin=Depends(require_admin)):
    m = metric_repo.get_metric(metric_id)
    if m is None:
        raise HTTPException(status_code=404, detail="指标不存在")
    return m


@router.post("/api/admin/metrics-registry")
async def admin_create_metric(req: MetricCreateRequest, request: Request, admin=Depends(require_admin)):
    payload = req.dict()
    catalog_id = payload.pop("catalog_id", 1)
    try:
        mid = metric_repo.create_metric(catalog_id=catalog_id, **payload)
    except MetadataError as e:
        raise HTTPException(status_code=400, detail=str(e))
    audit(request, admin, action="metric.create", resource_type="metric", resource_id=mid,
          detail={"name": req.name, "catalog_id": catalog_id})
    return {"id": mid}


@router.put("/api/admin/metrics-registry/{metric_id}")
async def admin_update_metric(metric_id: int, req: MetricUpdateRequest, request: Request, admin=Depends(require_admin)):
    fields = {k: v for k, v in req.dict().items() if v is not None}
    try:
        metric_repo.update_metric(metric_id, **fields)
    except MetadataError as e:
        raise HTTPException(status_code=400, detail=str(e))
    audit(request, admin, action="metric.update", resource_type="metric", resource_id=metric_id,
          detail={"fields": sorted(fields.keys())})
    return {"ok": True}


@router.delete("/api/admin/metrics-registry/{metric_id}")
async def admin_delete_metric(metric_id: int, request: Request, admin=Depends(require_admin)):
    metric_repo.delete_metric(metric_id)
    audit(request, admin, action="metric.delete", resource_type="metric", resource_id=metric_id)
    return {"ok": True}
