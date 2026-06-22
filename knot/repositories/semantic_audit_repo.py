"""semantic_audit_repo — semantic_query_audit 表 CRUD（v0.7.3 C1 · LogicForm 审计侧表）。

⚠️ OOS-1 死线 sustained：0 tenant_id / project_id —— catalog_id = 语义层水平切分（per-catalog），
   非租户隔离。R-SL-40：catalog_id = LogicForm 解析时 active catalog（messages 无 catalog_id，
   catalog 是 ContextVar 临时解析从不落 message → 审计渲染 / 修正 re-run 须存当时 catalog）。

侧表设计（守护者 Stage 3 裁定，非 messages 列）：messages 0 ALTER；仅语义路径 / near-miss 行
（多数 message 是 LLM 路径 → 本表小）。engine 标记 = 本表有无行派生（无需 messages 列）。
镜像 metric_repo（get_conn / close / `_COLS` / dict 返回）。
"""
from __future__ import annotations

from knot.repositories.base import get_conn

_COLS = (
    "id, message_id, catalog_id, logicform_json, compile_error_reason, "
    "is_corrected, parent_message_id, created_at"
)


def create_audit(message_id: int, catalog_id: int = 1, logicform_json: str = "",
                 compile_error_reason: str = "", is_corrected: int = 0,
                 parent_message_id: int | None = None) -> int:
    """写一条 LogicForm 审计行（语义命中 or near-miss）；返回新 id。

    命中：logicform_json = canonical_json，compile_error_reason = ""。
    near-miss：logicform_json = 解析出的 LF（诊断），compile_error_reason = CompileError 原因。
    """
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO semantic_query_audit "
            "(message_id, catalog_id, logicform_json, compile_error_reason, is_corrected, parent_message_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (message_id, catalog_id, logicform_json, compile_error_reason,
             is_corrected, parent_message_id),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def list_audit(catalog_id: int | None = None, limit: int = 100) -> list[dict]:
    """审计行（按 id 降序，最近优先）；catalog_id 给定则仅该 catalog（R-SL-39/40 隔离）。"""
    conn = get_conn()
    try:
        if catalog_id is None:
            rows = conn.execute(
                f"SELECT {_COLS} FROM semantic_query_audit ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        else:
            rows = conn.execute(
                f"SELECT {_COLS} FROM semantic_query_audit WHERE catalog_id=? ORDER BY id DESC LIMIT ?",
                (catalog_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_audit(audit_id: int) -> dict | None:
    """单条审计行；不存在返 None。"""
    conn = get_conn()
    try:
        row = conn.execute(
            f"SELECT {_COLS} FROM semantic_query_audit WHERE id=?", (audit_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_by_message(message_id: int) -> dict | None:
    """按 message_id 取审计行（engine 标记 / 会话历史徽标派生：有行=semantic，无=llm）。"""
    conn = get_conn()
    try:
        row = conn.execute(
            f"SELECT {_COLS} FROM semantic_query_audit WHERE message_id=? ORDER BY id DESC LIMIT 1",
            (message_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()
