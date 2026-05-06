"""prompt_repo — prompt_templates 表（per-agent system prompt 覆盖）。"""
from __future__ import annotations

from bi_agent.repositories.base import get_conn


def list_prompt_templates() -> list:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM prompt_templates ORDER BY agent_name").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_prompt_template(agent_name: str) -> str:
    conn = get_conn()
    row = conn.execute(
        "SELECT content FROM prompt_templates WHERE agent_name=?", (agent_name,)
    ).fetchone()
    conn.close()
    return row["content"] if row and row["content"] else ""


def set_prompt_template(agent_name: str, content: str, updated_by: int = None):
    conn = get_conn()
    conn.execute(
        "INSERT INTO prompt_templates (agent_name, content, updated_by) VALUES (?,?,?) "
        "ON CONFLICT(agent_name) DO UPDATE SET content=?, updated_by=?, "
        "updated_at=datetime('now','localtime')",
        (agent_name, content, updated_by, content, updated_by),
    )
    conn.commit()
    conn.close()


def delete_prompt_template(agent_name: str):
    conn = get_conn()
    conn.execute("DELETE FROM prompt_templates WHERE agent_name=?", (agent_name,))
    conn.commit()
    conn.close()
