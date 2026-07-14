"""bi_schedule 路由（v0.8.17 ②c）— BI 报表定时刷新配置 CRUD + CronJob tick 端点。

触发架构：**K8s CronJob → POST /api/bi/scheduler/tick**（单外部触发经 K8s Service 只打一个 pod
→ 应用内零常驻 loop → 无多副本重复 fire）。tick 由 `KNOT_SCHEDULER_TOKEN` bearer 守（守护者 B-3
secrets.compare_digest 常量时间比对；未配 token → 503 disabled = 安全默认）。

配置 CRUD 走 `require_report_perm("schedule")`（激活此前 dormant 的 can_schedule 权限位）。
审计（R-BI-8）：配置 CRUD emit `bi_report.schedule`；fire 事件在 service 层 emit `bi_report.refresh`(trigger=scheduled)。
R-BI-1：与 saved_reports/Chat 0 触。
"""
from __future__ import annotations

import asyncio
import os
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from knot.api._audit_helpers import audit
from knot.api.bi_reports import require_report_perm
from knot.repositories import bi_report_schedule_repo as sched_repo
from knot.services import bi_schedule_service as sched_svc

router = APIRouter()


@router.post("/api/bi/scheduler/tick")
async def scheduler_tick(request: Request):
    """CronJob 敲钟：扫到期 schedule → 原子认领 → 刷新。token 门（无 token→503 / 错→401）。

    独立 egress/security env `KNOT_SCHEDULER_TOKEN` **调用期读**（同 webhook.py R-SL-69 范式，
    非 settings.py — 便于 monkeypatch.setenv 测 + 与 CronJob Header 对齐）。未设 = disabled（安全默认）。"""
    token = os.environ.get("KNOT_SCHEDULER_TOKEN", "")
    if not token:
        raise HTTPException(status_code=503, detail="调度器未启用（未配置 KNOT_SCHEDULER_TOKEN）")
    auth = request.headers.get("authorization", "")
    presented = auth[7:] if auth[:7].lower() == "bearer " else ""
    if not secrets.compare_digest(presented, token):   # 守护者 B-3：常量时间比对
        raise HTTPException(status_code=401, detail="无效调度 token")
    loop = asyncio.get_event_loop()                     # 卸 sync SQLAlchemy 刷新到线程池
    return await loop.run_in_executor(None, sched_svc.run_due)


class ScheduleRequest(BaseModel):
    enabled: bool = True
    cadence: str = "daily"                # daily | hourly | every_n_hours
    interval_hours: int | None = None     # every_n_hours 用
    run_at_hhmm: str | None = None        # daily 触发时刻 'HH:MM'（Asia/Shanghai）


@router.get("/api/bi/reports/{report_id}/schedule")
async def get_schedule(report_id: int, user=Depends(require_report_perm("schedule"))):
    """报表当前 schedule（无则 null）。含 next_run_at / last_fired_at 回显。"""
    return sched_repo.get_by_report(report_id)


@router.put("/api/bi/reports/{report_id}/schedule")
async def set_schedule(report_id: int, req: ScheduleRequest, request: Request,
                       user=Depends(require_report_perm("schedule"))):
    if req.cadence not in sched_svc.CADENCES:
        raise HTTPException(status_code=400, detail=f"cadence 非法（须 {sched_svc.CADENCES}）")
    if req.cadence == "every_n_hours" and not (req.interval_hours and req.interval_hours >= 1):
        raise HTTPException(status_code=400, detail="every_n_hours 须 interval_hours>=1")
    # enabled 才算 next_run_at；停用则清空（list_due 只取 next_run_at 非空）
    next_run = (sched_svc.compute_next_run(req.cadence, req.interval_hours, req.run_at_hhmm)
                if req.enabled else None)
    sched_repo.upsert_schedule(
        report_id, catalog_id=1, created_by=user["id"],
        enabled=1 if req.enabled else 0, cadence=req.cadence,
        interval_hours=req.interval_hours, run_at_hhmm=req.run_at_hhmm, next_run_at=next_run,
    )
    audit(request, user, action="bi_report.schedule", resource_type="bi_report",
          resource_id=report_id, detail={"enabled": req.enabled, "cadence": req.cadence})
    return sched_repo.get_by_report(report_id)


@router.delete("/api/bi/reports/{report_id}/schedule")
async def delete_schedule(report_id: int, request: Request,
                          user=Depends(require_report_perm("schedule"))):
    sched_repo.delete_by_report(report_id)
    audit(request, user, action="bi_report.schedule", resource_type="bi_report",
          resource_id=report_id, detail={"deleted": True})
    return {"ok": True}


@router.get("/api/bi/reports/{report_id}/schedule/fires")
async def get_schedule_fires(report_id: int, user=Depends(require_report_perm("schedule"))):
    """fire 历史台账（最近优先，≤50）—— ScheduleModal 可观测（避 monitors 孤儿 triggers 教训）。"""
    return sched_repo.list_fires(report_id, limit=50)
