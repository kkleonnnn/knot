"""bi_schedule_service — v0.8.17 (②c) 定时刷新编排。

K8s CronJob → POST /api/bi/scheduler/tick → run_due()：
  扫到期 schedule → **原子认领**（sched_repo.claim，防重叠 tick 双打）→ refresh(report_id, sentinel) →
  记 fire 台账 + emit `bi_report.refresh` 审计（detail.trigger=scheduled；service 直调 audit_service.log = headless）。
刷新纯重跑冻结只读 SQL，**0 LLM / 0 budget**（bi_report_service 不触 cost）。
时区：Asia/Shanghai（time_resolver._TZ；守护者 B-2 — _TZ None 兜底 naive 本地钟，不崩）。
"""
from __future__ import annotations

from datetime import datetime, timedelta

from knot.core import time_resolver
from knot.repositories import bi_report_schedule_repo as sched_repo
from knot.services import audit_service, bi_report_service

_SENTINEL = {"id": None}          # headless actor：refresh wide_table 用 admin["id"]→None→last_run_by NULL（schema 允许）
_FMT = "%Y-%m-%d %H:%M:%S"        # 与 schema next_run_at 串一致（字典序 = 时间序，list_due/claim 直接比串）
CADENCES = ("daily", "hourly", "every_n_hours")


def _now() -> datetime:
    """当前时刻。守护者 B-2：time_resolver._TZ 为 None（zoneinfo 不可用）时兜底 naive 本地钟，绝不崩。"""
    tz = time_resolver._TZ
    return datetime.now(tz) if tz else datetime.now()


def compute_next_run(cadence: str, interval_hours=None, run_at_hhmm=None, from_dt: datetime | None = None) -> str:
    """算下次触发（Asia/Shanghai 墙钟串）：
    - daily → 下一个 run_at_hhmm（今日该时刻已过→明天；默认 08:00，落在上游 D-1 ETL 之后）
    - every_n_hours → +N 小时（N≥1）
    - hourly / 未知 → +1 小时
    """
    base = from_dt or _now()
    if cadence == "daily":
        hh, mm = 8, 0
        if run_at_hhmm and ":" in str(run_at_hhmm):
            try:
                hh, mm = (int(x) for x in str(run_at_hhmm).split(":", 1))
            except Exception:
                hh, mm = 8, 0
        cand = base.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if cand <= base:
            cand = cand + timedelta(days=1)
        nxt = cand
    elif cadence == "every_n_hours":
        n = max(1, int(interval_hours or 1))
        nxt = base + timedelta(hours=n)
    else:  # hourly / fallback
        nxt = base + timedelta(hours=1)
    return nxt.strftime(_FMT)


def _classify(out: dict | None) -> tuple[str, str, int | None]:
    """refresh() 返回值 → (status, error, refresh_seq)。"""
    if out is None:
        return "skipped", "报表不存在", None
    err = out.get("error") or ""
    seq = out.get("refresh_seq")
    if not err:
        return "ok", "", seq
    if err == bi_report_service._NO_ENGINE:
        return "no_engine", err, seq
    return "error", err, seq


def run_due() -> dict:
    """CronJob tick 主编排。返 {checked, fired, results:[{schedule_id, report_id, status, error}]}。"""
    now = _now()
    now_str = now.strftime(_FMT)
    due = sched_repo.list_due(now_str)
    results, fired = [], 0
    for s in due:
        new_next = compute_next_run(s["cadence"], s.get("interval_hours"), s.get("run_at_hhmm"), now)
        if sched_repo.claim(s["id"], now_str, new_next) != 1:
            continue                       # 被别的 tick 抢 / 未到期 → 原子去重跳过
        fired += 1
        rid = s["report_id"]
        try:
            out = bi_report_service.refresh(rid, _SENTINEL)
        except Exception as e:             # refresh 不应抛，但自主运行防御性兜底
            out = {"error": f"refresh 异常：{type(e).__name__}"}
        status, err, seq = _classify(out)
        sched_repo.record_fire(s["id"], rid, status, error=err[:500], refresh_seq=seq)
        # headless 审计（service 直调 log；R-BI-8：定时刷新有留痕，复用现成 bi_report.refresh Literal）
        audit_service.log(
            actor=None, action="bi_report.refresh", resource_type="bi_report",
            resource_id=rid, success=(status == "ok"),
            detail={"trigger": "scheduled", "schedule_id": s["id"], "status": status},
            catalog_id=s.get("catalog_id"),
        )
        results.append({"schedule_id": s["id"], "report_id": rid, "status": status, "error": err})
    return {"checked": len(due), "fired": fired, "results": results}
