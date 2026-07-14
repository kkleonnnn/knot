"""tests/services/test_bi_schedule_service.py — v0.8.17 (②c) 定时刷新编排。

覆盖：compute_next_run 各 cadence + 坏 hhmm 回退 + _TZ None 兜底(守护者 B-2) /
run_due 分类(ok/no_engine/skipped) + fire 台账 + headless 审计 emit(trigger=scheduled) +
原子认领去重(重叠 tick 只 fire 一次)。
"""
from datetime import datetime

from knot.repositories import bi_report_schedule_repo as sr
from knot.services import bi_schedule_service as S


def test_compute_next_run_cadences():
    d = datetime(2026, 7, 14, 9, 0, 0)
    assert S.compute_next_run("daily", None, "08:00", d) == "2026-07-15 08:00:00"      # 已过→明天
    assert S.compute_next_run("daily", None, "20:00", d) == "2026-07-14 20:00:00"      # 未过→今天
    # hourly 锚 :MM（kk：可配分钟，稳态每小时于 :MM 触发，不卡点）
    assert S.compute_next_run("hourly", None, "08:30", d) == "2026-07-14 09:30:00"     # :30 → 下个 09:30
    assert S.compute_next_run("hourly", None, "08:00", d) == "2026-07-14 10:00:00"     # :00 → 下个 10:00
    # every_n_hours 锚 HH:MM 起步：02:00 起每 6h = 02/08/14/20 → base 09:00 后下个 14:00
    assert S.compute_next_run("every_n_hours", 6, "02:00", d) == "2026-07-14 14:00:00"
    assert S.compute_next_run("daily", None, "bad", d) == "2026-07-15 08:00:00"        # 坏 hhmm→默认 08:00


def test_compute_next_run_tz_none_fallback(monkeypatch):
    """守护者 B-2：_TZ None（zoneinfo 不可用）不崩，兜底本地钟。"""
    monkeypatch.setattr(S.time_resolver, "_TZ", None)
    out = S.compute_next_run("hourly", None, None)                # from_dt=None → 走 _now() → _TZ None 分支
    assert len(out) == 19 and out[4] == "-"                       # 'YYYY-MM-DD HH:MM:SS'


def test_run_due_classifies_records_audits(tmp_db_path, monkeypatch):
    outcomes = {}
    monkeypatch.setattr(S.bi_report_service, "refresh", lambda rid, admin: outcomes.get(rid))
    audits = []
    monkeypatch.setattr(S.audit_service, "log", lambda **k: audits.append(k))
    for rid, cad in ((101, "daily"), (102, "hourly"), (103, "hourly")):
        sr.upsert_schedule(report_id=rid, created_by=1, cadence=cad, run_at_hhmm="08:00",
                           next_run_at="2020-01-01 08:00:00")
    outcomes.update({101: {"error": "", "refresh_seq": 7},
                     102: {"error": S.bi_report_service._NO_ENGINE, "refresh_seq": 3},
                     103: None})
    res = S.run_due()
    assert res["checked"] == 3 and res["fired"] == 3
    assert {r["report_id"]: r["status"] for r in res["results"]} == {101: "ok", 102: "no_engine", 103: "skipped"}
    assert len(audits) == 3 and all(a["detail"]["trigger"] == "scheduled" for a in audits)
    assert audits[0]["action"] == "bi_report.refresh" and audits[0]["resource_type"] == "bi_report"
    assert [f["status"] for f in sr.list_fires(101)] == ["ok"]


def test_run_due_atomic_dedup_second_tick_noop(tmp_db_path, monkeypatch):
    """重叠 tick：认领后 next_run 已推进未来 → 第二次 tick 该 schedule 不再 fire（原子去重）。"""
    monkeypatch.setattr(S.bi_report_service, "refresh", lambda rid, admin: {"error": "", "refresh_seq": 1})
    monkeypatch.setattr(S.audit_service, "log", lambda **k: None)
    sr.upsert_schedule(report_id=201, created_by=1, cadence="hourly", next_run_at="2020-01-01 08:00:00")
    assert S.run_due()["fired"] == 1
    assert S.run_due()["fired"] == 0
