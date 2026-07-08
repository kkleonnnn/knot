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
from knot.repositories import bi_report_tile_repo as tile_repo
from knot.services import engine_cache

_LAST_RUN_ROW_LIMIT = 10000  # v0.8.8 ②：BI 报表全量展示上限（kk）—— 真实运营日报数百行，1w = 安全顶；
                             # 超顶截断 + last_run_truncated=1。admin 自带 LIMIT 时 execute_query 尊重不覆盖。
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


# ── 仪表盘 tile 同步（②b · diff-by-id）────────────────────────────────────────────

def _sync_tiles(report_id: int, tiles: list, admin: dict) -> None:
    """把 payload tiles[] 同步到 bi_report_tiles（diff-by-id）—— report create/update 内调。

    - **B-1 id 归属**：payload tile 带 `id` 必须 ∈ 本 report 现有 tiles，否则忽略（防一个 report
      PUT 越权覆盖他报表 tile；admin-only 低危但必堵）。
    - 有合法 id → update（**保留其冻结快照**，update_tile 不碰 last_run_*）；无 id → insert；
      库内存在但不在 payload → delete。
    - 每 tile.sql_text 存前过 `_validate_sql`（D7 fail-closed → SqlNotReadOnly → api 400）。
    - tile 数上限由 api 层 `_check_tiles_size` 守（C-2 placement 同 overlay）。
    """
    existing = {t["id"] for t in tile_repo.list_by_report(report_id)}
    keep: set[int] = set()
    for i, t in enumerate(tiles or []):
        sql = (t.get("sql_text") or "").strip()
        _validate_sql(sql)
        fields = dict(
            tile_type=(t.get("tile_type") or "kpi"),
            title=t.get("title"),
            sql_text=sql,
            viz_config=_dump(t.get("viz_config")),
            sort_order=int(t.get("sort_order", i)),
            grid_span=int(t.get("grid_span", 1)),
        )
        tid = t.get("id")
        if tid is not None and tid in existing:      # B-1：合法归属 → update（保快照）
            tile_repo.update_tile(tid, **fields)
            keep.add(tid)
        elif tid is None:                            # 新 tile → insert
            tile_repo.create_tile(report_id, created_by=admin["id"], **fields)
        # else：带 id 但 ∉ existing（越权/陈旧）→ 忽略（B-1）
    for tid in existing - keep:                      # payload 里没了的 → delete
        tile_repo.delete_tile(tid)


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


def reorder_folders(ordered_ids: list[int]) -> None:
    """v0.8.8 ③：按 id 顺序赋 sort_order。缺失 id no-op；单表 UPDATE 无跨表污染。"""
    repo.reorder_folders(list(ordered_ids or []))


# ── 报表 ────────────────────────────────────────────────────────────────────────

def list_all() -> list[dict]:
    """全部 BI 报表（admin 授权、全体已认证只读）；目录树顺序。"""
    return repo.list_reports()


def get_report(report_id: int) -> dict | None:
    """单报表 + **附 tiles**（B-2a：组装在 getter，非 to_dto —— to_dto admin 早返会漏掉）。
    tiles 含 sql_text（admin builder 需要）；非 admin 由 to_dto 逐 tile 脱敏。viz_config /
    last_run_rows_json 保 JSON 串（前端 parse，同 dashboard_config 惯例）。"""
    r = repo.get_report(report_id)
    if r is None:
        return None
    r["tiles"] = tile_repo.list_by_report(report_id)
    return r


def create_report(admin: dict, *, title: str, sql_text: str,
                  data_source_id: int | None = None, folder_id: int | None = None,
                  report_type: str = "wide_table",
                  column_config=None, overlay_config=None, dashboard_config=None,
                  tiles: list | None = None) -> dict:
    """建报表。报表级 SQL + 每 tile SQL 均 **存前预校验**（D7）；失败抛 SqlNotReadOnly（api 转 400）。"""
    _validate_sql(sql_text)
    rid = repo.create_report(
        title=_default_title(title), sql_text=sql_text, created_by=admin["id"],
        report_type=report_type, folder_id=folder_id, data_source_id=data_source_id,
        column_config=_dump(column_config), overlay_config=_dump(overlay_config),
        dashboard_config=_dump(dashboard_config),
    )
    if tiles is not None:
        _sync_tiles(rid, tiles, admin)      # dashboard tiles（每 tile SQL 校验 + insert）
    return get_report(rid)


def update_report(report_id: int, *, admin: dict | None = None, title: str | None = None,
                 folder_id=_UNSET, sort_order: int | None = None, sql_text: str | None = None,
                 column_config=_UNSET, overlay_config=_UNSET, dashboard_config=_UNSET,
                 tiles=_UNSET) -> dict | None:
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
    if tiles is not _UNSET:                # 提供 tiles（含 []=全删）才 diff-by-id 同步；_UNSET=不动 tiles
        _sync_tiles(report_id, tiles or [], admin or {"id": None})
    return get_report(report_id)


def delete_report(report_id: int) -> bool:
    if repo.get_report(report_id) is None:
        return False
    tile_repo.delete_by_report(report_id)     # 先级联删 tiles（soft-FK，避免孤儿）
    repo.delete_report(report_id)
    return True


def reorder_reports(ordered_ids: list[int]) -> None:
    """v0.8.8 ③：按 id 顺序赋 sort_order（目录同文件夹内拖拽）。缺失 id no-op；单表 UPDATE 无跨表污染。"""
    repo.reorder_reports(list(ordered_ids or []))


# ── 刷新（冻结快照 · D6）────────────────────────────────────────────────────────

_NO_ENGINE = "无可用数据库引擎（检查报表数据源配置）"


def _exec_one(engine, sql: str):
    """跑一条 SQL → (snap, truncated, elapsed_ms, error)；截断 _LAST_RUN_ROW_LIMIT。engine 非空由调用方保证。"""
    t0 = time.time()
    try:
        rows, db_error = db_connector.execute_query(engine, sql, max_rows=_LAST_RUN_ROW_LIMIT)
    except Exception as e:
        rows, db_error = [], str(e)[:200]
    elapsed_ms = int((time.time() - t0) * 1000)
    truncated = len(rows) > _LAST_RUN_ROW_LIMIT
    snap = rows[:_LAST_RUN_ROW_LIMIT] if truncated else rows
    return snap, truncated, elapsed_ms, (db_error or "")


def refresh(report_id: int, admin: dict) -> dict | None:
    """重执行报表冻结 SQL 回写快照 + bump refresh_seq。返 None = 报表不存在（api 转 404）。

    - **dashboard**：循环每 tile 各自 SQL → 写各自冻结快照（per-tile error 隔离）→ 报表级
      refresh_seq **bump-only**（D2 整表原子 · B-3，不写报表级 rows）。
    - **wide_table**：单 SQL 写报表级快照（②a 路径不变）。
    引擎解析：报表绑 data_source_id → engine_cache.get_engine_for_source（无 source/engine → 记错）。
    ②c 调度器复用本函数（admin=sentinel；service 不 emit 审计，在 api 层）。
    """
    r = repo.get_report(report_id)
    if not r:
        return None
    sid = r.get("data_source_id")
    engine = engine_cache.get_engine_for_source(sid) if sid else None
    if r["report_type"] in ("dashboard", "tabbed"):     # 两者均 tile 承载 → 同 tile-loop 刷新
        return _refresh_tiled(report_id, engine, r["report_type"])
    # wide_table（②a 单 SQL 路径）
    if engine is None:
        return {"rows": [], "truncated": False, "last_run_ms": 0, "last_run_at": _now_iso(),
                "error": _NO_ENGINE, "refresh_seq": r["refresh_seq"]}
    snap, truncated, elapsed_ms, err = _exec_one(engine, r["sql_text"])
    run_at = _now_iso()
    repo.update_last_run(
        report_id, rows_json=json.dumps(snap, ensure_ascii=False, default=str),
        truncated=1 if truncated else 0, elapsed_ms=elapsed_ms, run_at=run_at,
        last_run_by=admin["id"],
    )
    return {"rows": snap, "truncated": truncated, "last_run_ms": elapsed_ms,
            "last_run_at": run_at, "error": err,
            "refresh_seq": repo.get_report(report_id)["refresh_seq"]}


def _refresh_tiled(report_id: int, engine, report_type: str) -> dict:
    """tile 承载报表（dashboard 网格 / tabbed 页签）整表原子刷新（②b D2/B-3；v0.8.7 tabbed 复用）。

    engine None（数据源缺失 / test_connection 瞬时失败）→ **不触任何 tile 快照、不 bump**，直接返错
    （镜像 wide_table engine-None 早返，保留各 tile 上次 good 快照 —— 复核 correctness：避免一次 DB blip
    把整盘 good 快照抹成空）。engine 在但某 tile SQL 失败 → 该 tile 写 [] + error（与 wide_table 查询错一致）。
    """
    if engine is None:
        return {"report_type": report_type, "tiles": [], "tile_count": 0, "error_count": 0,
                "error": _NO_ENGINE, "refresh_seq": repo.get_report(report_id)["refresh_seq"]}
    run_at = _now_iso()
    summaries = []
    for t in tile_repo.list_by_report(report_id):
        snap, truncated, elapsed_ms, err = _exec_one(engine, t["sql_text"])
        tile_repo.update_tile_last_run(
            t["id"], rows_json=json.dumps(snap, ensure_ascii=False, default=str),
            truncated=1 if truncated else 0, elapsed_ms=elapsed_ms, run_at=run_at,
            error=(err or None),
        )
        summaries.append({"tile_id": t["id"], "rows_count": len(snap), "error": err})
    repo.touch_refresh_seq(report_id)      # B-3 报表级 bump-only（不写报表级 rows_json）
    error_count = sum(1 for s in summaries if s["error"])
    return {"report_type": report_type, "tiles": summaries,
            "tile_count": len(summaries), "error_count": error_count,
            "error": (f"{error_count} 个板块刷新出错" if error_count else ""),
            "refresh_seq": repo.get_report(report_id)["refresh_seq"]}


# ── 脱敏 DTO（R-BI-6）────────────────────────────────────────────────────────────

def to_dto(report: dict, is_admin: bool) -> dict:
    """非 admin **不下发 sql_text**（R-BI-6）—— 报表级 + **每 tile**。列配置 / 覆盖层 / viz_config（展示层）保留。

    B-2b：`{**report}` 是浅拷 → `tiles` 是共享引用；若 in-place pop 会 mutate repo 返回的 tile dict
    污染同进程 admin 路径 → 必须**深拷每个 tile dict 再 pop**（新 list + 新 dict，剔 sql_text）。
    B-2a：tiles 由 getter（get_report）附上，此处仅脱敏 —— to_dto admin 早返，组装绝不能放这里。
    """
    if is_admin:
        return report
    d = {**report}
    d.pop("sql_text", None)
    tiles = d.get("tiles")
    if isinstance(tiles, list):
        d["tiles"] = [{k: v for k, v in t.items() if k != "sql_text"} for t in tiles]
    return d
