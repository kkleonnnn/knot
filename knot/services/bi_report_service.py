"""bi_report_service — v0.8.5 (②a) BI 报表业务编排。

职责：
- 报表 CRUD + 文件夹 CRUD（admin 授权；权限门在 api 层 require_admin）
- SQL 只读**存前预校验**（D7 = doris.is_safe_sql，fail-closed；admin 即时见错）
- refresh：冻结快照 + admin 控刷新（D6，不实时跑；②c 调度器复用同 refresh）
- 脱敏 DTO：非 admin 读 **不下发 sql_text**（R-BI-6）

不做：
- LLM 调用（宽表是确定查询，不重新生成）
- 公式求值（客户端 formula.js — R-BI-11；后端只存 overlay_config 原样）
- 审计 emit（在 api 层 audit(request, admin, action=...) — 每 Literal ≥1 emit 守护）

⚠️ R-BI-1：与 saved_report_service（ASK 收藏）严格分开 —— 全新命名、0 逻辑触碰。
"""
from __future__ import annotations

import json
import time
from datetime import datetime

from knot.adapters.db import doris as db_connector
from knot.repositories import bi_report_repo as repo
from knot.services import engine_cache

_LAST_RUN_ROW_LIMIT = 200  # 复用 saved_report R-3 软限制
_TITLE_MAX = 120           # admin 授权、宽表名较长 → 放宽（saved_report 是 30）

_UNSET = repo._UNSET       # 复用 repo 哨兵：区分「不改」vs「显式置 NULL」


class SqlNotReadOnly(ValueError):
    """admin 直写 SQL 未过只读闸（R-BI-5 / D7）。api 层转 400。"""


# ── 内部 helper ────────────────────────────────────────────────────────────────

def _validate_sql(sql: str) -> None:
    ok, reason = db_connector.is_safe_sql(sql)     # D7 fail-closed
    if not ok:
        raise SqlNotReadOnly(reason or "SQL 未通过只读校验（仅允许 SELECT / WITH / SHOW 等只读语句）")


def _default_title(s: str | None) -> str:
    q = (s or "").strip() or "未命名报表"
    return q[:_TITLE_MAX] + ("…" if len(q) > _TITLE_MAX else "")


def _dump(v) -> str | None:
    """JSON 字段（column_config / overlay_config）落 TEXT：None 透传；str 原样；dict/list → dumps。"""
    if v is None or isinstance(v, str):
        return v
    return json.dumps(v, ensure_ascii=False, default=str)


def _now_iso() -> str:
    return datetime.now().isoformat(sep=" ", timespec="seconds")


# ── 文件夹 ──────────────────────────────────────────────────────────────────────

def list_folders() -> list[dict]:
    return repo.list_folders()


def create_folder(admin: dict, *, name: str, parent_id: int | None = None,
                  sort_order: int = 0) -> dict:
    fid = repo.create_folder(name=(name or "未命名文件夹").strip()[:_TITLE_MAX],
                             created_by=admin["id"], parent_id=parent_id, sort_order=sort_order)
    return repo.get_folder(fid)


def update_folder(folder_id: int, *, name: str | None = None,
                 parent_id=_UNSET, sort_order: int | None = None) -> dict | None:
    if repo.get_folder(folder_id) is None:
        return None
    repo.update_folder(folder_id, name=name, parent_id=parent_id, sort_order=sort_order)
    return repo.get_folder(folder_id)


def delete_folder(folder_id: int) -> bool:
    """删文件夹 —— 非破坏性 reparent：内含报表 → 未归档（folder_id=None）；子文件夹 → 顶层。"""
    if repo.get_folder(folder_id) is None:
        return False
    for r in repo.list_reports():
        if r["folder_id"] == folder_id:
            repo.update_report(r["id"], folder_id=None)
    for f in repo.list_folders():
        if f["parent_id"] == folder_id:
            repo.update_folder(f["id"], parent_id=None)
    repo.delete_folder(folder_id)
    return True


# ── 报表 ────────────────────────────────────────────────────────────────────────

def list_all() -> list[dict]:
    """全部 BI 报表（admin 授权、全体已认证只读）；目录树顺序。"""
    return repo.list_reports()


def get_report(report_id: int) -> dict | None:
    return repo.get_report(report_id)


def create_report(admin: dict, *, title: str, sql_text: str,
                  data_source_id: int | None = None, folder_id: int | None = None,
                  report_type: str = "wide_table",
                  column_config=None, overlay_config=None, dashboard_config=None) -> dict:
    """建报表。SQL **存前预校验**（D7）；失败抛 SqlNotReadOnly（api 转 400）。"""
    _validate_sql(sql_text)
    rid = repo.create_report(
        title=_default_title(title), sql_text=sql_text, created_by=admin["id"],
        report_type=report_type, folder_id=folder_id, data_source_id=data_source_id,
        column_config=_dump(column_config), overlay_config=_dump(overlay_config),
        dashboard_config=_dump(dashboard_config),
    )
    return repo.get_report(rid)


def update_report(report_id: int, *, title: str | None = None, folder_id=_UNSET,
                 sort_order: int | None = None, sql_text: str | None = None,
                 column_config=_UNSET, overlay_config=_UNSET, dashboard_config=_UNSET) -> dict | None:
    if repo.get_report(report_id) is None:
        return None
    if sql_text is not None:
        _validate_sql(sql_text)                                   # 改 SQL 也过存前闸
    repo.update_report(
        report_id,
        title=(_default_title(title) if title is not None else None),
        folder_id=folder_id, sort_order=sort_order, sql_text=sql_text,
        column_config=(_UNSET if column_config is _UNSET else _dump(column_config)),
        overlay_config=(_UNSET if overlay_config is _UNSET else _dump(overlay_config)),
        dashboard_config=(_UNSET if dashboard_config is _UNSET else _dump(dashboard_config)),
    )
    return repo.get_report(report_id)


def delete_report(report_id: int) -> bool:
    if repo.get_report(report_id) is None:
        return False
    repo.delete_report(report_id)
    return True


# ── 刷新（冻结快照 · D6）────────────────────────────────────────────────────────

def refresh(report_id: int, admin: dict) -> dict | None:
    """重执行报表冻结 SQL 回写快照 + bump refresh_seq。返 None = 报表不存在（api 转 404）。

    引擎解析：报表绑 data_source_id（admin 建时选）→ engine_cache.get_engine_for_source。
    无 source / engine 不可用 → 返 error（不写快照）。②c 调度器复用本函数（admin=sentinel）。
    """
    r = repo.get_report(report_id)
    if not r:
        return None
    sid = r.get("data_source_id")
    engine = engine_cache.get_engine_for_source(sid) if sid else None
    if engine is None:
        return {"rows": [], "truncated": False, "last_run_ms": 0, "last_run_at": _now_iso(),
                "error": "无可用数据库引擎（检查报表数据源配置）", "refresh_seq": r["refresh_seq"]}

    t0 = time.time()
    try:
        rows, db_error = db_connector.execute_query(engine, r["sql_text"])
    except Exception as e:
        rows, db_error = [], str(e)[:200]
    elapsed_ms = int((time.time() - t0) * 1000)

    truncated = len(rows) > _LAST_RUN_ROW_LIMIT
    snap = rows[:_LAST_RUN_ROW_LIMIT] if truncated else rows
    run_at = _now_iso()
    repo.update_last_run(
        report_id, rows_json=json.dumps(snap, ensure_ascii=False, default=str),
        truncated=1 if truncated else 0, elapsed_ms=elapsed_ms, run_at=run_at,
        last_run_by=admin["id"],
    )
    return {"rows": snap, "truncated": truncated, "last_run_ms": elapsed_ms,
            "last_run_at": run_at, "error": db_error or "",
            "refresh_seq": repo.get_report(report_id)["refresh_seq"]}


# ── 脱敏 DTO（R-BI-6）────────────────────────────────────────────────────────────

def to_dto(report: dict, is_admin: bool) -> dict:
    """非 admin **不下发 sql_text**（R-BI-6）。列配置 / 覆盖层（展示层）保留。"""
    if is_admin:
        return report
    d = {**report}
    d.pop("sql_text", None)
    return d
