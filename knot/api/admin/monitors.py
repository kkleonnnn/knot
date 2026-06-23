"""knot/api/admin/monitors.py — 事件/规则/动作监控路由（v0.7.7 C4 语义层第八刀）。

route `/api/admin/monitors`（避撞既有 admin 屏）。全 require_admin（继承 R-2FA enroll gate R-SL-65）。
CRUD 经 monitor_repo（OOS-1 死锁）+ monitor.create/update/delete audit（R-SL-66）。

⭐ check-now（手动「立即检查」，D1 绕调度器卡点）：
- **R-SL-77 flag-gate**：fire 路径受 `KNOT_SEMANTIC_LAYER`（flag off → 不 fire，守零生产风险不变量）。
- D3：admin 自己 `get_user_engine` 取值（engine None → 该 monitor skip 优雅 R-SL-71）。
- eval（monitor_eval 0 LLM R-SL-70）→ 命中 fire webhook（独立 allowlist R-SL-69）+ monitor.trigger audit
  + 每 check 留痕侧表（R-SL-75 re-fire：每命中确实外发，非 0 累积）。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from knot.api._audit_helpers import audit
from knot.api.deps import require_admin
from knot.models.errors import MetadataError
from knot.repositories import monitor_repo

router = APIRouter()


class MonitorCreateRequest(BaseModel):
    catalog_id: int = 1
    name: str
    metric_name: str
    comparator: str                  # gt|lt|gte|lte|eq | pct_change_gt|pct_change_lt
    threshold: float
    baseline_period: str = ""        # 环比基准期 time_resolver 枚举（阈值类空）
    time_window: str = ""            # 当期 time_resolver 枚举
    action_type: str = "webhook"
    action_target: str = ""          # webhook URL（KNOT_WEBHOOK_ALLOWED_HOSTS 守护）
    enabled: int = 1


class MonitorUpdateRequest(BaseModel):
    name: str | None = None
    metric_name: str | None = None
    comparator: str | None = None
    threshold: float | None = None
    baseline_period: str | None = None
    time_window: str | None = None
    action_type: str | None = None
    action_target: str | None = None
    enabled: int | None = None


@router.get("/api/admin/monitors")
async def admin_list_monitors(catalog_id: int | None = None, admin=Depends(require_admin)):
    return monitor_repo.list_monitors(catalog_id)


@router.post("/api/admin/monitors")
async def admin_create_monitor(req: MonitorCreateRequest, request: Request, admin=Depends(require_admin)):
    payload = req.dict()
    catalog_id = payload.pop("catalog_id", 1)
    try:
        mid = monitor_repo.create_monitor(catalog_id=catalog_id, **payload)
    except MetadataError as e:
        raise HTTPException(status_code=400, detail=str(e))
    audit(request, admin, action="monitor.create", resource_type="monitor", resource_id=mid,
          detail={"name": req.name, "metric_name": req.metric_name, "catalog_id": catalog_id})
    return {"id": mid}


@router.put("/api/admin/monitors/{monitor_id}")
async def admin_update_monitor(monitor_id: int, req: MonitorUpdateRequest, request: Request,
                               admin=Depends(require_admin)):
    fields = {k: v for k, v in req.dict().items() if v is not None}
    try:
        monitor_repo.update_monitor(monitor_id, **fields)
    except MetadataError as e:
        raise HTTPException(status_code=400, detail=str(e))
    audit(request, admin, action="monitor.update", resource_type="monitor", resource_id=monitor_id,
          detail={"fields": sorted(fields.keys())})
    return {"ok": True}


@router.delete("/api/admin/monitors/{monitor_id}")
async def admin_delete_monitor(monitor_id: int, request: Request, admin=Depends(require_admin)):
    monitor_repo.delete_monitor(monitor_id)
    audit(request, admin, action="monitor.delete", resource_type="monitor", resource_id=monitor_id)
    return {"ok": True}


@router.get("/api/admin/monitors/{monitor_id}/triggers")
async def admin_monitor_triggers(monitor_id: int, admin=Depends(require_admin)):
    return monitor_repo.list_triggers(monitor_id)


@router.post("/api/admin/monitors/check-now")
async def admin_monitors_check_now(request: Request, admin=Depends(require_admin)):
    """手动「立即检查」所有 enabled monitor（D1）。R-SL-77 flag-gate：flag off → 不 fire。"""
    import os

    # R-SL-77：fire 路径受 KNOT_SEMANTIC_LAYER（守零生产风险不变量于副作用最重处）
    if os.getenv("KNOT_SEMANTIC_LAYER", "false").strip().lower() != "true":
        return {"ok": False, "detail": "语义层未启用（KNOT_SEMANTIC_LAYER off）—— check/fire 不执行", "results": []}

    from knot.adapters.notification.base import Notification
    from knot.adapters.notification.webhook import WebhookError, WebhookNotificationAdapter
    from knot.core import time_resolver
    from knot.repositories import catalog_repo
    from knot.services import query_helper
    from knot.services.engine_cache import get_user_engine
    from knot.services.semantic import monitor_eval

    engine, _schema = get_user_engine(admin)                  # D3：admin 自己 engine
    time_ctx = time_resolver.resolve_time_context()
    adapter = WebhookNotificationAdapter()
    results = []
    for m in monitor_repo.list_monitors(enabled_only=True):
        row = catalog_repo.get_catalog(m["catalog_id"])       # R-SL-72 原 catalog 编译口径
        catalog = (query_helper._parse_catalog_content(row) if row
                   else {"catalog_id": m["catalog_id"], "tables": [], "relations": []})
        res = monitor_eval.evaluate_monitor(m, catalog, engine, time_ctx)   # 0 LLM R-SL-70 / fail-soft R-SL-71
        detail = res["detail"]
        if res["hit"] and m["action_type"] == "webhook":
            try:
                adapter.send(Notification(title=f"[监控] {m['name']}", body=detail, level="warn",
                                          target=m["action_target"]))    # R-SL-69 独立 allowlist
                detail += " | webhook 已发送"
                audit(request, admin, action="monitor.trigger", resource_type="monitor", resource_id=m["id"],
                      detail={"name": m["name"], "metric_value": res["metric_value"]})
            except WebhookError as e:
                res["status"] = "skipped"
                detail += f" | webhook 失败: {e}"
        # R-SL-75 留痕：每 check 一行（hit/no_hit/skipped）；re-fire = 每命中确实外发
        monitor_repo.create_trigger(m["id"], catalog_id=m["catalog_id"], metric_value=res["metric_value"],
                                    hit=1 if res["hit"] else 0, status=res["status"], detail=detail)
        results.append({"monitor_id": m["id"], "name": m["name"], "status": res["status"],
                        "hit": res["hit"], "metric_value": res["metric_value"], "detail": detail})
    return {"ok": True, "evaluated": len(results),
            "fired": sum(1 for r in results if r["status"] == "fired"), "results": results}
