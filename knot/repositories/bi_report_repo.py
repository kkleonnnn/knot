"""bi_report_repo — v0.8.5 (②a) BI 模式 report_folders + bi_reports CRUD。

薄 SQL helper（镜像 saved_report_repo 纪律）；权限 / 只读校验 / 快照截断 / 脱敏 / 公式
求值全部由 services/bi_report_service.py 编排。

⚠️ R-BI-1：与 saved_reports（ASK 模式收藏）**严格分开** —— 全新表 + 全新命名，0 逻辑触碰。
BI 报表 admin 授权、全体已认证用户只读 → 无 per-user UNIQUE / owner gate（区别 saved_reports）。

nullable-set 语义：update 里可空字段（folder_id / parent_id / column_config / overlay_config）
用 `_UNSET` 哨兵区分「不改」vs「置 NULL（移出文件夹 / 清空配置）」。
"""
from __future__ import annotations

from knot.repositories.base import get_conn

# 「不改该字段」哨兵 —— 区别于「显式置 NULL」（如把报表移到未归档 folder_id=None）
_UNSET = object()


# ─── report_folders ──────────────────────────────────────────────────────────

def create_folder(name: str, created_by: int, parent_id: int | None = None,
                  sort_order: int = 0) -> int:
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO report_folders (name, parent_id, sort_order, created_by) "
        "VALUES (?,?,?,?)",
        (name, parent_id, sort_order, created_by),
    )
    rid = cur.lastrowid
    conn.commit()
    conn.close()
    return rid or 0


def get_folder(folder_id: int) -> dict | None:
    conn = get_conn()
    row = conn.execute("SELECT * FROM report_folders WHERE id=?", (folder_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def list_folders() -> list[dict]:
    """全部文件夹（admin 授权模型 → 不按 user 过滤）；按 (parent_id, sort_order) 排。"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM report_folders ORDER BY sort_order, id"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_folder(folder_id: int, *, name: str | None = None,
                 parent_id=_UNSET, sort_order: int | None = None) -> None:
    """改名 / 移动（parent_id，_UNSET=不改、None=移到顶层）/ 改序。"""
    sets: list[str] = []
    params: list = []
    if name is not None:
        sets.append("name=?")
        params.append(name)
    if parent_id is not _UNSET:
        sets.append("parent_id=?")
        params.append(parent_id)
    if sort_order is not None:
        sets.append("sort_order=?")
        params.append(sort_order)
    if not sets:
        return
    params.append(folder_id)
    conn = get_conn()
    conn.execute(f"UPDATE report_folders SET {', '.join(sets)} WHERE id=?", params)
    conn.commit()
    conn.close()


def delete_folder(folder_id: int) -> None:
    """删文件夹。folder_id soft ref → 内含报表 folder_id 变 dangling（service 层决定
    是否先把报表移到未归档；repo 只删本行不级联）。"""
    conn = get_conn()
    conn.execute("DELETE FROM report_folders WHERE id=?", (folder_id,))
    conn.commit()
    conn.close()


# ─── bi_reports ──────────────────────────────────────────────────────────────

def create_report(title: str, sql_text: str, created_by: int, *,
                  report_type: str = "wide_table", folder_id: int | None = None,
                  sort_order: int = 0, data_source_id: int | None = None,
                  column_config: str | None = None, overlay_config: str | None = None) -> int:
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO bi_reports "
        "(report_type, title, folder_id, sort_order, data_source_id, sql_text, "
        " column_config, overlay_config, created_by) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (report_type, title, folder_id, sort_order, data_source_id, sql_text,
         column_config, overlay_config, created_by),
    )
    rid = cur.lastrowid
    conn.commit()
    conn.close()
    return rid or 0


def get_report(report_id: int) -> dict | None:
    conn = get_conn()
    row = conn.execute("SELECT * FROM bi_reports WHERE id=?", (report_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def list_reports() -> list[dict]:
    """全部 BI 报表（admin 授权、全体只读 → 不按 user 过滤）；按 (folder_id, sort_order) 排
    供目录树渲染。"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM bi_reports ORDER BY folder_id, sort_order, id"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_report(report_id: int, *, title: str | None = None, folder_id=_UNSET,
                 sort_order: int | None = None, sql_text: str | None = None,
                 column_config=_UNSET, overlay_config=_UNSET) -> None:
    """改元数据 / 移动文件夹 / 改 SQL / 列配置 / 覆盖层。
    folder_id / column_config / overlay_config 用 _UNSET 哨兵（None = 显式置 NULL）。
    """
    sets: list[str] = []
    params: list = []
    if title is not None:
        sets.append("title=?")
        params.append(title)
    if folder_id is not _UNSET:
        sets.append("folder_id=?")
        params.append(folder_id)
    if sort_order is not None:
        sets.append("sort_order=?")
        params.append(sort_order)
    if sql_text is not None:
        sets.append("sql_text=?")
        params.append(sql_text)
    if column_config is not _UNSET:
        sets.append("column_config=?")
        params.append(column_config)
    if overlay_config is not _UNSET:
        sets.append("overlay_config=?")
        params.append(overlay_config)
    if not sets:
        return
    params.append(report_id)
    conn = get_conn()
    conn.execute(f"UPDATE bi_reports SET {', '.join(sets)} WHERE id=?", params)
    conn.commit()
    conn.close()


def update_last_run(report_id: int, rows_json: str, truncated: int, elapsed_ms: int,
                   run_at: str, last_run_by: int | None) -> None:
    """回写冻结快照 + bump refresh_seq（D6 admin 控刷新；②c 调度复用）。"""
    conn = get_conn()
    conn.execute(
        "UPDATE bi_reports SET "
        "last_run_rows_json=?, last_run_truncated=?, last_run_ms=?, last_run_at=?, "
        "last_run_by=?, refresh_seq=refresh_seq+1 WHERE id=?",
        (rows_json, truncated, elapsed_ms, run_at, last_run_by, report_id),
    )
    conn.commit()
    conn.close()


def delete_report(report_id: int) -> None:
    conn = get_conn()
    conn.execute("DELETE FROM bi_reports WHERE id=?", (report_id,))
    conn.commit()
    conn.close()
