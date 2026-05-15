"""frontend_error_repo — frontend_errors 表 CRUD（v0.6.0.4 F-B）。

设计：
- 仅 insert + list_admin（无 update / delete — 错误是审计现实）
- M-B2 PII 防御链由上层 api/frontend_errors.py 在 insert 前应用
- R-61 cap 200 sustained
"""
from __future__ import annotations

from knot.repositories.base import get_conn

_MAX_MESSAGE_LEN = 2000  # 防 attacker stuff huge payload
_MAX_STACK_LEN = 10000
_MAX_URL_LEN = 500
_MAX_UA_LEN = 500


def insert(
    *,
    user_id: int | None,
    message: str,
    stack: str = "",
    url: str = "",
    user_agent: str = "",
    error_hash: str | None = None,
) -> int:
    """单行 INSERT；返回 lastrowid。长度硬截断防巨型 payload 攻击。"""
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO frontend_errors "
        "(user_id, message, stack, url, user_agent, error_hash) "
        "VALUES (?,?,?,?,?,?)",
        (user_id,
         (message or "")[:_MAX_MESSAGE_LEN],
         (stack or "")[:_MAX_STACK_LEN],
         (url or "")[:_MAX_URL_LEN],
         (user_agent or "")[:_MAX_UA_LEN],
         (error_hash or "")[:64]),
    )
    rid = cur.lastrowid
    conn.commit()
    conn.close()
    return rid


def list_admin(*, limit: int = 100, offset: int = 0) -> list[dict]:
    """admin 全局错误列表（含 username 冗余便于审阅）。R-61 cap 200。"""
    limit = max(1, min(int(limit), 200))
    offset = max(0, int(offset))
    conn = get_conn()
    rows = conn.execute(
        "SELECT fe.*, u.username AS username, u.display_name AS display_name "
        "FROM frontend_errors fe "
        "LEFT JOIN users u ON u.id = fe.user_id "
        "ORDER BY fe.created_at DESC LIMIT ? OFFSET ?",
        (limit, offset),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def count_admin() -> int:
    conn = get_conn()
    n = conn.execute("SELECT COUNT(*) FROM frontend_errors").fetchone()[0]
    conn.close()
    return int(n or 0)


def top_hashes(*, limit: int = 10) -> list[dict]:
    """admin 看高频错误聚合（hash + count + 最近一次）。"""
    limit = max(1, min(int(limit), 100))
    conn = get_conn()
    rows = conn.execute(
        "SELECT error_hash, COUNT(*) AS cnt, MAX(created_at) AS last_at, "
        "       (SELECT message FROM frontend_errors fe2 "
        "        WHERE fe2.error_hash = fe.error_hash ORDER BY id DESC LIMIT 1) AS last_message "
        "FROM frontend_errors fe "
        "WHERE error_hash IS NOT NULL AND error_hash != '' "
        "GROUP BY error_hash ORDER BY cnt DESC, last_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
