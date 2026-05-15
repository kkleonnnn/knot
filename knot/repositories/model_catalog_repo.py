"""model_catalog_repo — model_catalog_live 表 CRUD（v0.6.0.6 F-D）。

设计：
- UPSERT 语义：同 model_id 触发覆盖 + 更新 fetched_at
- list_all() 返回全部供 admin UI 展示
- 不与 MODELS dict 耦合（dict 是代码源，本表是 OR live 缓存）
"""
from __future__ import annotations

import json

from knot.repositories.base import get_conn


def upsert(*, model_id: str, context_length: int | None,
           input_price: float | None, output_price: float | None,
           raw: dict | None = None) -> None:
    """同 model_id 触发覆盖；fetched_at 由 SQLite 默认值刷新。"""
    conn = get_conn()
    conn.execute(
        "INSERT INTO model_catalog_live "
        "(model_id, context_length, input_price, output_price, raw_json, fetched_at) "
        "VALUES (?,?,?,?,?, datetime('now','localtime')) "
        "ON CONFLICT(model_id) DO UPDATE SET "
        "context_length=excluded.context_length, "
        "input_price=excluded.input_price, "
        "output_price=excluded.output_price, "
        "raw_json=excluded.raw_json, "
        "fetched_at=excluded.fetched_at",
        (model_id, context_length, input_price, output_price,
         json.dumps(raw, ensure_ascii=False) if raw else None),
    )
    conn.commit()
    conn.close()


def list_all() -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT model_id, context_length, input_price, output_price, fetched_at "
        "FROM model_catalog_live ORDER BY model_id"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def count_all() -> int:
    conn = get_conn()
    n = conn.execute("SELECT COUNT(*) FROM model_catalog_live").fetchone()[0]
    conn.close()
    return int(n or 0)
