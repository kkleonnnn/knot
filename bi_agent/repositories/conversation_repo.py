"""conversation_repo — conversations 表 CRUD。"""
from __future__ import annotations

from bi_agent.repositories.base import get_conn


def create_conversation(user_id: int, title: str = "新对话") -> int:
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO conversations (user_id, title) VALUES (?,?)", (user_id, title)
    )
    cid = cur.lastrowid
    conn.commit()
    conn.close()
    return cid


def list_conversations(user_id: int) -> list:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM conversations WHERE user_id=? ORDER BY updated_at DESC",
        (user_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_conversation_title(conv_id: int, title: str):
    conn = get_conn()
    conn.execute(
        "UPDATE conversations SET title=?, updated_at=datetime('now','localtime') WHERE id=?",
        (title, conv_id),
    )
    conn.commit()
    conn.close()


def delete_conversation(conv_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM messages WHERE conversation_id=?", (conv_id,))
    conn.execute("DELETE FROM conversations WHERE id=?", (conv_id,))
    conn.commit()
    conn.close()


def get_conversation_owner(conv_id: int) -> int | None:
    """返回 conversation 的 user_id；不存在则 None。导出路由权限校验用。"""
    conn = get_conn()
    row = conn.execute(
        "SELECT user_id FROM conversations WHERE id=?", (conv_id,),
    ).fetchone()
    conn.close()
    return row["user_id"] if row else None
