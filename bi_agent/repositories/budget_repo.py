"""budget_repo — budgets 表 CRUD（v0.4.3）。

R-18 幂等：upsert() 用 INSERT OR REPLACE 处理 UNIQUE 冲突；
service 层先 SELECT 判断 already_existed 后调用，给 API 返回标记。

R-23 不缓存：所有读路径都直接 conn.execute；service 层禁止再加 LRU/TTL。
admin 改完预算后下次查询立即生效。
"""
from __future__ import annotations

from bi_agent.repositories.base import get_conn


def upsert(scope_type: str, scope_value: str, budget_type: str,
           threshold: float, action: str = "warn", enabled: int = 1) -> int:
    """R-18 INSERT OR REPLACE 幂等：UNIQUE (scope_type, scope_value, budget_type) 冲突时
    覆盖现有 threshold/action/enabled；返 lastrowid（既存或新建都是 INSERT OR REPLACE 后的 id）。

    service 层调用前应先用 get_by_unique() 判断 already_existed。
    """
    conn = get_conn()
    cur = conn.execute(
        "INSERT OR REPLACE INTO budgets "
        "(scope_type, scope_value, budget_type, threshold, action, enabled, updated_at) "
        "VALUES (?,?,?,?,?,?, datetime('now','localtime'))",
        (scope_type, scope_value, budget_type, threshold, action, enabled),
    )
    rid = cur.lastrowid
    conn.commit()
    conn.close()
    return rid or 0


def get(budget_id: int) -> dict | None:
    conn = get_conn()
    row = conn.execute("SELECT * FROM budgets WHERE id=?", (budget_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_by_unique(scope_type: str, scope_value: str, budget_type: str) -> dict | None:
    """R-18 配套：UNIQUE 三元组查找；service 层判断 already_existed 用。"""
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM budgets WHERE scope_type=? AND scope_value=? AND budget_type=?",
        (scope_type, scope_value, budget_type),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def list_all() -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM budgets ORDER BY scope_type, scope_value, budget_type"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def list_by_scope(scope_type: str, scope_value: str) -> list[dict]:
    """R-23 实时查（无缓存）。仅返 enabled=1 的预算。"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM budgets WHERE scope_type=? AND scope_value=? AND enabled=1",
        (scope_type, scope_value),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update(budget_id: int, threshold: float | None = None,
           action: str | None = None, enabled: int | None = None) -> None:
    """改 threshold / action / enabled；None 表示不动。"""
    sets: list[str] = []
    params: list = []
    if threshold is not None:
        sets.append("threshold=?")
        params.append(threshold)
    if action is not None:
        sets.append("action=?")
        params.append(action)
    if enabled is not None:
        sets.append("enabled=?")
        params.append(int(enabled))
    if not sets:
        return
    sets.append("updated_at=datetime('now','localtime')")
    params.append(budget_id)
    conn = get_conn()
    conn.execute(f"UPDATE budgets SET {', '.join(sets)} WHERE id=?", params)
    conn.commit()
    conn.close()


def delete(budget_id: int) -> None:
    conn = get_conn()
    conn.execute("DELETE FROM budgets WHERE id=?", (budget_id,))
    conn.commit()
    conn.close()
