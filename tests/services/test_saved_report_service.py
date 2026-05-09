"""tests/services/test_saved_report_service.py — v0.4.1 service 5 条单测。

覆盖：
- create_from_message snapshot intent + display_hint
- R-S6 老消息 intent=None → fallback 'detail'
- R-3 软限制 200 行截断 + last_run_truncated=1
- R-12 幂等：第二次 pin 同 message 返既存对象 + already_existed=True
- R-S5 _default_title 处理 None / 空 / >30 字
"""
import json

import pytest

from knot.repositories import base as base_mod
from knot.services import saved_report_service


@pytest.fixture()
def init_db(tmp_db_path):
    """复用 repositories/conftest 的 tmp_db_path。"""
    yield tmp_db_path


_USER = {"id": 1, "role": "admin", "default_source_id": None}


def _msg(message_id, intent="metric", rows=None, question="问 X 是多少", sql="SELECT 1"):
    return {
        "id": message_id,
        "conversation_id": 1,
        "question": question,
        "sql_text": sql,
        "rows": rows or [{"x": 1}],
        "intent": intent,
        "created_at": "2026-05-07 10:00:00",
        "query_time_ms": 230,
    }


def test_create_from_message_snapshots_intent(init_db):
    sr, existed = saved_report_service.create_from_message(_USER, _msg(100, intent="metric"))
    assert existed is False
    assert sr["intent"] == "metric"
    assert sr["display_hint"] == "metric_card"
    assert sr["title"] == "问 X 是多少"
    assert sr["sql_text"] == "SELECT 1"
    assert sr["last_run_truncated"] == 0


def test_create_from_message_falls_back_to_detail_when_intent_null(init_db):
    """R-S6：老消息（v0.4.0 之前）intent=None → 'detail' + 'detail_table'。"""
    sr, _ = saved_report_service.create_from_message(_USER, _msg(101, intent=None))
    assert sr["intent"] == "detail"
    assert sr["display_hint"] == "detail_table"


def test_create_from_message_truncates_rows_at_200(init_db):
    """R-3 软限制：>200 行截断 + truncated=1；JSON 中确为 200 行。"""
    big_rows = [{"i": i} for i in range(250)]
    sr, _ = saved_report_service.create_from_message(_USER, _msg(102, rows=big_rows))
    assert sr["last_run_truncated"] == 1
    parsed = json.loads(sr["last_run_rows_json"])
    assert len(parsed) == 200


def test_create_from_message_idempotent(init_db):
    """R-12：第二次 pin 同 message → 返既存行 + already_existed=True，id 不变。"""
    msg = _msg(103, intent="metric")
    sr1, existed1 = saved_report_service.create_from_message(_USER, msg)
    sr2, existed2 = saved_report_service.create_from_message(
        _USER, msg, title="另一个标题", pin_note="备注",
    )
    assert existed1 is False
    assert existed2 is True
    assert sr1["id"] == sr2["id"]
    # 既存对象未被覆盖（title 仍是首次的）
    assert sr2["title"] == sr1["title"]
    assert sr2["pin_note"] is None  # R-12 幂等：第二次的 pin_note 不会写入


def test_default_title_handles_empty_and_long_question(init_db):
    """R-S5：空 → '未命名报表'；>30 字 → 截断 + '…'；strip 空白。"""
    assert saved_report_service._default_title(None) == "未命名报表"
    assert saved_report_service._default_title("") == "未命名报表"
    assert saved_report_service._default_title("   ") == "未命名报表"
    long = "A" * 50
    truncated = saved_report_service._default_title(long)
    assert len(truncated) == 31  # 30 字 + '…'
    assert truncated.endswith("…")
    assert saved_report_service._default_title("  hello  ") == "hello"
