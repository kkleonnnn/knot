"""message_repo — messages 表 + semantic_layer。"""
from __future__ import annotations

import json

from knot.repositories.base import get_conn

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
                 recovery_attempt: int = 0,
                 # v0.6.1.0：端到端响应延迟（毫秒），admin 内测指标屏 P95 计算用；
                 # None 允许（老消息 / 不需要追踪的写入路径），P95 query 时 WHERE latency_ms IS NOT NULL
                 latency_ms: int | None = None) -> int:
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
        " recovery_attempt, latency_ms) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (conv_id, question, sql, explanation, confidence,
         rows_json, db_error, cost_usd, input_tokens, output_tokens, retry_count, intent,
         agent_kind, clarifier_cost, sql_planner_cost, fix_sql_cost, presenter_cost,
         clarifier_tokens, sql_planner_tokens, fix_sql_tokens, presenter_tokens,
         recovery_attempt, latency_ms),
    )
    mid = cur.lastrowid
    conn.execute(
        "UPDATE conversations SET updated_at=datetime('now','localtime') WHERE id=?",
        (conv_id,),
    )
    conn.commit()
    conn.close()
    return mid


def get_messages(conv_id: int, viewer_user_id: int | None = None) -> list:
    """获取会话消息；v0.6.0.3 F-A：可选 LEFT JOIN viewer 的 feedback 用于前端回显态度。

    viewer_user_id=None → 不查 feedback（向后兼容）；
    传入 → 每行附加 user_feedback_score (+1/-1/None)。
    """
    conn = get_conn()
    if viewer_user_id is None:
        rows = conn.execute(
            "SELECT * FROM messages WHERE conversation_id=? ORDER BY created_at",
            (conv_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT m.*, mf.score AS user_feedback_score "
            "FROM messages m "
            "LEFT JOIN message_feedback mf ON mf.message_id = m.id AND mf.user_id = ? "
            "WHERE m.conversation_id = ? "
            "ORDER BY m.created_at",
            (viewer_user_id, conv_id),
        ).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        d["rows"] = json.loads(d.get("rows_json") or "[]")
        result.append(d)
    return result


def list_messages_for_admin(
    period_days: int = 7,
    user_id: int | None = None,
    agent_kind: str | None = None,
    has_error: bool | None = None,
    page: int = 1,
    size: int = 50,
) -> dict:
    """v0.6.0.18 — admin 用户查询历史屏数据源（跨用户聚合）。

    返回结构：
      {"items": [...], "total": int, "page": int, "size": int}

    items 每条含 message 字段 + actor info：
      - id / question / agent_kind / cost_usd / latency_ms / db_error
        / created_at / recovery_attempt / intent / confidence
        / sql_text / explanation
      - actor_id / actor_username / actor_display_name / actor_role
      - conversation_id / conversation_title
    """
    size = min(size, 200)
    if size < 1:
        size = 50
    page = max(page, 1)

    conn = get_conn()
    where = ["m.created_at >= datetime('now', '-' || ? || ' days', 'localtime')",
             "m.agent_kind != 'legacy'"]
    params: list = [period_days]
    if user_id is not None:
        where.append("c.user_id = ?")
        params.append(user_id)
    if agent_kind:
        where.append("m.agent_kind = ?")
        params.append(agent_kind)
    if has_error is True:
        where.append("(m.db_error IS NOT NULL AND m.db_error != '')")
    elif has_error is False:
        where.append("(m.db_error IS NULL OR m.db_error = '')")
    where_clause = " AND ".join(where)

    total = conn.execute(
        f"SELECT COUNT(*) FROM messages m "
        f"JOIN conversations c ON c.id = m.conversation_id "
        f"WHERE {where_clause}",
        params,
    ).fetchone()[0] or 0

    offset = (page - 1) * size
    rows = conn.execute(
        f"SELECT m.id, m.question, m.agent_kind, m.cost_usd, m.latency_ms, "
        f"m.db_error, m.created_at, m.recovery_attempt, m.intent, m.confidence, "
        f"m.sql_text, m.explanation, m.conversation_id, "
        f"c.title AS conversation_title, "
        f"c.user_id AS actor_id, "
        f"u.username AS actor_username, u.display_name AS actor_display_name, "
        f"u.role AS actor_role "
        f"FROM messages m "
        f"JOIN conversations c ON c.id = m.conversation_id "
        f"LEFT JOIN users u ON u.id = c.user_id "
        f"WHERE {where_clause} "
        f"ORDER BY m.created_at DESC "
        f"LIMIT ? OFFSET ?",
        params + [size, offset],
    ).fetchall()
    conn.close()
    items = [dict(r) for r in rows]
    return {"items": items, "total": total, "page": page, "size": size}


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


def get_cost_breakdown(period_days: int = 7) -> dict:
    """v0.4.2 admin 看板：按 agent_kind 分桶 + 按 user 分组的 cost 汇总。

    返回结构：
        {
            "period_days": 7,
            "total_cost_usd": 1.234,
            "total_messages": 234,
            "by_agent_kind": {clarifier: 0.1, sql_planner: 0.5, fix_sql: 0.05, presenter: 0.3, legacy: 0.0},
            "by_user": [{user_id, username, cost_usd, message_count}, ...],
            "recovery_attempt_total": 12,  # 累计自纠正次数（fan-out + fix_sql）
        }
    """
    conn = get_conn()
    cutoff_clause = f"created_at >= datetime('now', '-{int(period_days)} days', 'localtime')"
    # 总览 + 按 agent_kind 分桶
    by_kind_rows = conn.execute(
        f"""
        SELECT
            COALESCE(SUM(clarifier_cost), 0)   AS clarifier,
            COALESCE(SUM(sql_planner_cost), 0) AS sql_planner,
            COALESCE(SUM(fix_sql_cost), 0)     AS fix_sql,
            COALESCE(SUM(presenter_cost), 0)   AS presenter,
            COALESCE(SUM(cost_usd), 0)         AS total_cost,
            COUNT(*)                           AS msg_count,
            COALESCE(SUM(recovery_attempt), 0) AS recovery_total
        FROM messages
        WHERE {cutoff_clause}
        """
    ).fetchone()
    # 'legacy' 桶（老消息只有 cost_usd 没有分桶字段）单独算
    legacy_row = conn.execute(
        f"""
        SELECT COALESCE(SUM(cost_usd), 0) AS legacy_cost
        FROM messages
        WHERE agent_kind='legacy' AND {cutoff_clause}
        """
    ).fetchone()
    # 按 user 分组（需要 user 表 join）
    by_user_rows = conn.execute(
        f"""
        SELECT
            c.user_id           AS user_id,
            u.username          AS username,
            COALESCE(SUM(m.cost_usd), 0) AS cost_usd,
            COUNT(m.id)         AS message_count
        FROM messages m
        JOIN conversations c ON m.conversation_id = c.id
        JOIN users u         ON c.user_id = u.id
        WHERE m.{cutoff_clause}
        GROUP BY c.user_id, u.username
        ORDER BY cost_usd DESC
        """
    ).fetchall()
    conn.close()
    return {
        "period_days": period_days,
        "total_cost_usd": float(by_kind_rows["total_cost"] or 0),
        "total_messages": int(by_kind_rows["msg_count"] or 0),
        "by_agent_kind": {
            "clarifier":   float(by_kind_rows["clarifier"] or 0),
            "sql_planner": float(by_kind_rows["sql_planner"] or 0),
            "fix_sql":     float(by_kind_rows["fix_sql"] or 0),
            "presenter":   float(by_kind_rows["presenter"] or 0),
            "legacy":      float(legacy_row["legacy_cost"] or 0),
        },
        "by_user": [
            {
                "user_id": int(r["user_id"]),
                "username": r["username"],
                "cost_usd": float(r["cost_usd"] or 0),
                "message_count": int(r["message_count"] or 0),
            }
            for r in by_user_rows
        ],
        "recovery_attempt_total": int(by_kind_rows["recovery_total"] or 0),
    }


def get_recovery_trend(period_days: int = 30, since_date: str | None = None) -> dict:
    """v0.4.3 System_Recovery 维度（R-19 过滤 legacy）。

    返回结构：
        {
            "period_days": 30,
            "total_recovery_attempts": 42,
            "total_messages": 234,
            "by_day": [{"date": "2026-05-08", "count": 5, "msg_count": 30}, ...],
            "top_users": [{"user_id": 1, "username": "admin", "count": 12, "msg_count": 50}, ...],
        }

    R-19：WHERE agent_kind != 'legacy' AND created_at >= since_date（默认 v0.4.2 上线日）。
    避免 v0.4.2 之前历史数据（recovery_attempt 一律 NULL/0）污染趋势曲线。
    """
    conn = get_conn()
    cutoff_clause = f"created_at >= datetime('now', '-{int(period_days)} days', 'localtime')"
    extra_filter = ""
    params: list = []
    if since_date:
        extra_filter = " AND created_at >= ?"
        params.append(since_date)

    # 总览
    overview = conn.execute(
        f"""
        SELECT
            COALESCE(SUM(recovery_attempt), 0) AS total_recovery,
            COUNT(*) AS msg_count
        FROM messages
        WHERE agent_kind != 'legacy' AND {cutoff_clause}{extra_filter}
        """,
        params,
    ).fetchone()

    # 按日分桶
    by_day_rows = conn.execute(
        f"""
        SELECT
            DATE(created_at) AS day,
            COALESCE(SUM(recovery_attempt), 0) AS count,
            COUNT(*) AS msg_count
        FROM messages
        WHERE agent_kind != 'legacy' AND {cutoff_clause}{extra_filter}
        GROUP BY DATE(created_at)
        ORDER BY day
        """,
        params,
    ).fetchall()

    # Top 10 高频自纠正 user
    top_users_rows = conn.execute(
        f"""
        SELECT
            c.user_id  AS user_id,
            u.username AS username,
            COALESCE(SUM(m.recovery_attempt), 0) AS count,
            COUNT(m.id) AS msg_count
        FROM messages m
        JOIN conversations c ON m.conversation_id = c.id
        JOIN users u         ON c.user_id = u.id
        WHERE m.agent_kind != 'legacy' AND m.{cutoff_clause}{extra_filter.replace('created_at', 'm.created_at')}
        GROUP BY c.user_id, u.username
        HAVING SUM(m.recovery_attempt) > 0
        ORDER BY count DESC
        LIMIT 10
        """,
        params,
    ).fetchall()
    conn.close()

    return {
        "period_days": period_days,
        "total_recovery_attempts": int(overview["total_recovery"] or 0),
        "total_messages": int(overview["msg_count"] or 0),
        "by_day": [
            {"date": r["day"], "count": int(r["count"] or 0), "msg_count": int(r["msg_count"] or 0)}
            for r in by_day_rows
        ],
        "top_users": [
            {
                "user_id": int(r["user_id"]),
                "username": r["username"],
                "count": int(r["count"] or 0),
                "msg_count": int(r["msg_count"] or 0),
            }
            for r in top_users_rows
        ],
    }


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
