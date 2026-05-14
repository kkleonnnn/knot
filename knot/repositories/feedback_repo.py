"""feedback_repo — message_feedback 表 CRUD（v0.6.0.3 F-A）。

设计原则：
- 同 user × 同 message UNIQUE → upsert 语义（INSERT OR REPLACE）保幂等
- admin GET 分页 + 可选过滤 score
- 无 update / delete 路径（feedback 一旦提交是审计现实）；admin 想看反悔记录走 audit_log

守护：M-A5 — submit 操作必须 audit_log（由上层 api/conversations.py 调用 audit_service）
"""
from __future__ import annotations

from knot.repositories.base import get_conn


def upsert(*, message_id: int, user_id: int, score: int, comment: str = "") -> int:
    """同 (message_id, user_id) UNIQUE 触发覆盖；返回 lastrowid。"""
    if score not in (-1, 1):
        raise ValueError(f"score 必须 +1 或 -1，收到 {score}")
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO message_feedback (message_id, user_id, score, comment) "
        "VALUES (?,?,?,?) "
        "ON CONFLICT(message_id, user_id) DO UPDATE SET "
        "score=excluded.score, comment=excluded.comment, "
        "created_at=datetime('now','localtime')",
        (message_id, user_id, score, comment or ""),
    )
    rid = cur.lastrowid
    conn.commit()
    conn.close()
    return rid


def get_by_message_user(message_id: int, user_id: int) -> dict | None:
    """查特定用户对特定消息的反馈（用户回到历史对话显示自己之前的态度）。"""
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM message_feedback WHERE message_id=? AND user_id=?",
        (message_id, user_id),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def list_admin(*, score: int | None = None, limit: int = 100, offset: int = 0) -> list[dict]:
    """admin 全局反馈列表（含 user.username + message.question 冗余便于审阅）。

    R-61: limit cap 200 sustained。
    """
    limit = max(1, min(int(limit), 200))
    offset = max(0, int(offset))
    sql = (
        "SELECT mf.*, u.username as username, u.display_name as display_name, "
        "       m.question as question, c.id as conversation_id "
        "FROM message_feedback mf "
        "JOIN users u ON u.id = mf.user_id "
        "JOIN messages m ON m.id = mf.message_id "
        "JOIN conversations c ON c.id = m.conversation_id "
    )
    params: list = []
    if score is not None:
        sql += "WHERE mf.score=? "
        params.append(int(score))
    sql += "ORDER BY mf.created_at DESC LIMIT ? OFFSET ?"
    params += [limit, offset]
    conn = get_conn()
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def count_admin(score: int | None = None) -> int:
    """对应 list_admin 的总数（用于前端分页 total）。"""
    conn = get_conn()
    if score is None:
        n = conn.execute("SELECT COUNT(*) FROM message_feedback").fetchone()[0]
    else:
        n = conn.execute("SELECT COUNT(*) FROM message_feedback WHERE score=?", (int(score),)).fetchone()[0]
    conn.close()
    return int(n or 0)
