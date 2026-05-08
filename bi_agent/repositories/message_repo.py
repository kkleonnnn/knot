"""message_repo — messages 表 + semantic_layer。"""
from __future__ import annotations

import json

from bi_agent.repositories.base import get_conn

_VALID_AGENT_KINDS_NEW = ("clarifier", "sql_planner", "fix_sql", "presenter")


def save_message(conv_id, question, sql, explanation, confidence,
                 rows, db_error, cost_usd, input_tokens, output_tokens, retry_count,
                 intent: str | None = None,
                 # v0.4.2 成本归因分桶 + recovery_attempt
                 agent_kind: str = "sql_planner",
                 clarifier_cost: float = 0.0,
                 sql_planner_cost: float = 0.0,
                 fix_sql_cost: float = 0.0,
                 presenter_cost: float = 0.0,
                 clarifier_tokens: int = 0,
                 sql_planner_tokens: int = 0,
                 fix_sql_tokens: int = 0,
                 presenter_tokens: int = 0,
                 recovery_attempt: int = 0) -> int:
    """v0.4.2 新增成本分桶参数。
    - 默认 agent_kind='sql_planner'（v0.4.0+ 主路径），强制非 'legacy'（Stage 3-A 守护）
    - 'legacy' 是不变量：仅供老消息持有，新写入禁止
    """
    if agent_kind == "legacy":
        raise ValueError(
            "'legacy' is reserved for pre-v0.4.2 records (Stage 3-A 守护者要求)。"
            "新消息必须显式指定 agent_kind ∈ {clarifier, sql_planner, fix_sql, presenter}。"
        )
    if agent_kind not in _VALID_AGENT_KINDS_NEW:
        raise ValueError(
            f"Invalid agent_kind {agent_kind!r}; "
            f"必须是 {_VALID_AGENT_KINDS_NEW} 之一（'legacy' 仅供老消息）"
        )

    rows_json = json.dumps(rows, ensure_ascii=False, default=str)
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO messages "
        "(conversation_id, question, sql_text, explanation, confidence, "
        " rows_json, db_error, cost_usd, input_tokens, output_tokens, retry_count, intent, "
        " agent_kind, clarifier_cost, sql_planner_cost, fix_sql_cost, presenter_cost, "
        " clarifier_tokens, sql_planner_tokens, fix_sql_tokens, presenter_tokens, "
        " recovery_attempt) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (conv_id, question, sql, explanation, confidence,
         rows_json, db_error, cost_usd, input_tokens, output_tokens, retry_count, intent,
         agent_kind, clarifier_cost, sql_planner_cost, fix_sql_cost, presenter_cost,
         clarifier_tokens, sql_planner_tokens, fix_sql_tokens, presenter_tokens,
         recovery_attempt),
    )
    mid = cur.lastrowid
    conn.execute(
        "UPDATE conversations SET updated_at=datetime('now','localtime') WHERE id=?",
        (conv_id,),
    )
    conn.commit()
    conn.close()
    return mid


def get_messages(conv_id: int) -> list:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM messages WHERE conversation_id=? ORDER BY created_at",
        (conv_id,),
    ).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        d["rows"] = json.loads(d.get("rows_json") or "[]")
        result.append(d)
    return result


def get_message(message_id: int) -> dict | None:
    """单条 message 查询（含 rows 解码）。

    用于 v0.4.0 导出路由按 message_id 取数据；调用方负责权限校验。
    返回 None 表示不存在。
    """
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM messages WHERE id=?", (message_id,),
    ).fetchone()
    conn.close()
    if row is None:
        return None
    d = dict(row)
    d["rows"] = json.loads(d.get("rows_json") or "[]")
    return d


def get_semantic_layer() -> str:
    conn = get_conn()
    row = conn.execute("SELECT content FROM semantic_layer LIMIT 1").fetchone()
    conn.close()
    return row["content"] if row else ""


def save_semantic_layer(content: str, updated_by: int):
    conn = get_conn()
    row = conn.execute("SELECT id FROM semantic_layer LIMIT 1").fetchone()
    if row:
        conn.execute(
            "UPDATE semantic_layer SET content=?, updated_by=?, updated_at=datetime('now','localtime') WHERE id=?",
            (content, updated_by, row["id"]),
        )
    else:
        conn.execute("INSERT INTO semantic_layer (content, updated_by) VALUES (?,?)",
                     (content, updated_by))
    conn.commit()
    conn.close()
