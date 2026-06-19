"""v0.6.5.4 OR-only 孤儿 migration 守护（base.py init_db）.

migration 三行为：① fresh/test DB → model_settings 仍空（兜底 c==0 不触发，守 v0.6.5.3 测试隔离）
② DELETE 清孤儿直连 key ③ 有配置但无默认时兜底设 OR 默认。幂等（同步 DML，非 create_task）。
"""
from __future__ import annotations

from knot.repositories import base


def test_fresh_db_model_settings_empty(tmp_db_path):
    """① fresh DB init_db 后 model_settings 仍空 —— 兜底（c==0）确定性不触发，绝不给 test DB 加行。"""
    conn = base.get_conn()
    n = conn.execute("SELECT COUNT(*) FROM model_settings").fetchone()[0]
    conn.close()
    assert n == 0, f"fresh DB model_settings 必空（兜底不触发，守测试隔离）；实际 {n} 行"


def test_migration_deletes_orphan_direct_keys(tmp_db_path):
    """② 现存孤儿直连 key 被 migration DELETE（admin 曾启用直连模型）。"""
    conn = base.get_conn()
    conn.execute("INSERT INTO model_settings(model_key,enabled,is_default) VALUES('claude-haiku-4-5-20251001',1,1)")
    conn.execute("INSERT INTO model_settings(model_key,enabled,is_default) VALUES('gpt-4o',1,0)")
    conn.commit()
    conn.close()

    base.init_db()  # 幂等 migration 再跑

    conn = base.get_conn()
    rows = [r[0] for r in conn.execute("SELECT model_key FROM model_settings").fetchall()]
    conn.close()
    assert "claude-haiku-4-5-20251001" not in rows, "孤儿直连 key 应被 DELETE"
    assert "gpt-4o" not in rows, "孤儿直连 key 应被 DELETE"
    # 两孤儿是仅有的行 → 删后 c==0 → 兜底不触发 → model_settings 空
    assert rows == [], f"删孤儿后应空（c==0 兜底跳）；实际 {rows}"


def test_migration_backfills_or_default_when_configured(tmp_db_path):
    """③ admin 配过 OR 模型 + 直连默认（孤儿）→ 删孤儿后 c>0 无默认 → 兜底设 OR 默认。"""
    conn = base.get_conn()
    conn.execute("INSERT INTO model_settings(model_key,enabled,is_default) VALUES('anthropic/claude-sonnet-4',1,0)")
    conn.execute("INSERT INTO model_settings(model_key,enabled,is_default) VALUES('claude-haiku-4-5-20251001',1,1)")  # 孤儿默认
    conn.commit()
    conn.close()

    base.init_db()  # 幂等 migration 再跑

    conn = base.get_conn()
    rows = {r[0]: r[1] for r in conn.execute("SELECT model_key, is_default FROM model_settings").fetchall()}
    conn.close()
    assert "claude-haiku-4-5-20251001" not in rows, "孤儿删"
    assert rows.get("anthropic/claude-sonnet-4") == 0, "OR 配置行保留"
    assert rows.get("anthropic/claude-haiku-4.5") == 1, "兜底设 OR 默认（c>0 且无 is_default）"
