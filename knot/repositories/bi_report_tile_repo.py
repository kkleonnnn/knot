"""bi_report_tile_repo — v0.8.6 (②b) 仪表盘 tile CRUD。

薄 SQL helper（镜像 bi_report_repo 纪律）；per-tile SQL 只读校验 / diff-by-id 归属 / 脱敏 /
整表原子刷新编排全部由 services/bi_report_service.py 负责。

⚠️ R-BI-1：与 saved_reports（ASK 收藏）严格分开 —— 全新表 + 全新命名，0 逻辑触碰。
tile.report_id soft ref bi_reports（无硬 FK）；删报表由 service 先调 delete_by_report 级联。
D2 整表原子刷新 → tile **无自己的 refresh_seq**（报表级 bump，见 bi_report_repo.touch_refresh_seq）。

nullable-set 语义：update 里可空字段（title / viz_config）用 `_UNSET` 哨兵区分「不改」vs「置 NULL」。
"""
from __future__ import annotations

from knot.repositories.base import get_conn
from knot.repositories.bi_report_repo import _UNSET  # 复用同一「不改」哨兵


def list_by_report(report_id: int) -> list[dict]:
    """某报表全部 tile，按 (sort_order, id) 排（渲染 + diff-by-id 归属基准）。"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM bi_report_tiles WHERE report_id=? ORDER BY sort_order, id",
        (report_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_tile(tile_id: int) -> dict | None:
    conn = get_conn()
    row = conn.execute("SELECT * FROM bi_report_tiles WHERE id=?", (tile_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def create_tile(report_id: int, *, tile_type: str, sql_text: str, created_by: int,
                title: str | None = None, viz_config: str | None = None,
                sort_order: int = 0, grid_span: int = 1) -> int:
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO bi_report_tiles "
        "(report_id, tile_type, title, sql_text, viz_config, sort_order, grid_span, created_by) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (report_id, tile_type, title, sql_text, viz_config, sort_order, grid_span, created_by),
    )
    tid = cur.lastrowid
    conn.commit()
    conn.close()
    return tid or 0


def update_tile(tile_id: int, *, tile_type: str | None = None, title=_UNSET,
                sql_text: str | None = None, viz_config=_UNSET,
                sort_order: int | None = None, grid_span: int | None = None) -> None:
    """改 tile 配置 / 排序 / 跨度。**绝不碰 last_run_***（快照独立走 update_tile_last_run）
    → 编辑配置/reorder/resize 不 wipe 未改 tile 的冻结快照（②b §5#7 correctness）。
    title / viz_config 用 _UNSET 哨兵（None = 显式置 NULL）。"""
    sets: list[str] = []
    params: list = []
    if tile_type is not None:
        sets.append("tile_type=?")
        params.append(tile_type)
    if title is not _UNSET:
        sets.append("title=?")
        params.append(title)
    if sql_text is not None:
        sets.append("sql_text=?")
        params.append(sql_text)
    if viz_config is not _UNSET:
        sets.append("viz_config=?")
        params.append(viz_config)
    if sort_order is not None:
        sets.append("sort_order=?")
        params.append(sort_order)
    if grid_span is not None:
        sets.append("grid_span=?")
        params.append(grid_span)
    if not sets:
        return
    params.append(tile_id)
    conn = get_conn()
    conn.execute(f"UPDATE bi_report_tiles SET {', '.join(sets)} WHERE id=?", params)
    conn.commit()
    conn.close()


def update_tile_last_run(tile_id: int, *, rows_json: str, truncated: int, elapsed_ms: int,
                        run_at: str, error: str | None) -> None:
    """回写 per-tile 冻结快照（整表原子刷新循环内逐 tile 调；报表级 refresh_seq 另 bump）。
    per-tile error 独立 → 一 tile SQL 挂不连累其余 tile 展示（②b §5#5）。"""
    conn = get_conn()
    conn.execute(
        "UPDATE bi_report_tiles SET "
        "last_run_rows_json=?, last_run_truncated=?, last_run_ms=?, last_run_at=?, last_run_error=? "
        "WHERE id=?",
        (rows_json, truncated, elapsed_ms, run_at, error, tile_id),
    )
    conn.commit()
    conn.close()


def update_tile_error(tile_id: int, *, error: str, run_at: str, elapsed_ms: int = 0) -> None:
    """v0.8.17 守护者 B-1：tile SQL 失败时只更 error + 时戳，**不动 last_run_rows_json**（保留上次 good 快照）。
    自主定时刷新下「一次瞬时 SQL 错把该 tile good 数据抹空」不可接受 → SQL 错走本函数而非 update_tile_last_run。"""
    conn = get_conn()
    conn.execute(
        "UPDATE bi_report_tiles SET last_run_error=?, last_run_at=?, last_run_ms=? WHERE id=?",
        (error, run_at, elapsed_ms, tile_id),
    )
    conn.commit()
    conn.close()


def delete_tile(tile_id: int) -> None:
    conn = get_conn()
    conn.execute("DELETE FROM bi_report_tiles WHERE id=?", (tile_id,))
    conn.commit()
    conn.close()


def delete_by_report(report_id: int) -> None:
    """级联删某报表全部 tile（service delete_report 先调，避免孤儿 soft-FK）。"""
    conn = get_conn()
    conn.execute("DELETE FROM bi_report_tiles WHERE report_id=?", (report_id,))
    conn.commit()
    conn.close()
