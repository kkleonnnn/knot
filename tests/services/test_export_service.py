"""tests/services/test_export_service.py — v0.4.0 CSV 导出 service 单测。

覆盖：utf-8-sig BOM / 字段顺序 / 复杂值 JSON 序列化 / 空 rows / 中文字符。
"""
from __future__ import annotations

import csv
from io import StringIO

from bi_agent.services.export_service import rows_to_csv_bytes


def _decode(b: bytes) -> str:
    """utf-8-sig 解码会自动剥掉 BOM；用 utf-8 解码可以验证 BOM 字节存在。"""
    return b.decode("utf-8-sig")


def test_empty_rows_returns_empty_bytes():
    assert rows_to_csv_bytes([]) == b""


def test_bom_byte_order_mark_present():
    """utf-8-sig 必须以 BOM (\xef\xbb\xbf) 起手，否则 Excel 中文乱码。"""
    out = rows_to_csv_bytes([{"a": 1}])
    assert out.startswith(b"\xef\xbb\xbf")


def test_basic_csv_roundtrip():
    rows = [{"name": "alice", "age": 30}, {"name": "bob", "age": 25}]
    out = rows_to_csv_bytes(rows)
    text = _decode(out)
    parsed = list(csv.DictReader(StringIO(text)))
    assert parsed == [{"name": "alice", "age": "30"}, {"name": "bob", "age": "25"}]


def test_chinese_chars_round_trip():
    rows = [{"用户": "张三", "金额": "¥100"}]
    out = rows_to_csv_bytes(rows)
    text = _decode(out)
    assert "用户" in text and "张三" in text and "¥100" in text


def test_explicit_cols_controls_order_and_subset():
    rows = [{"a": 1, "b": 2, "c": 3}]
    out = rows_to_csv_bytes(rows, cols=["c", "a"])
    text = _decode(out)
    header = text.splitlines()[0]
    assert header == "c,a"  # 顺序锁住，b 被丢弃


def test_complex_value_json_serialized():
    rows = [{"id": 1, "extra": {"nested": "中文"}}]
    out = rows_to_csv_bytes(rows)
    text = _decode(out)
    # dict 应被 JSON 序列化；csv writer 会把内层 " 双引号化（""..."")
    # 关键点：(1) 中文不被 ensure_ascii 转义；(2) JSON key/value 都进得去
    assert "中文" in text
    assert "nested" in text
    # 通过 csv.DictReader 反解，验证整个值是合法 JSON
    parsed = list(csv.DictReader(StringIO(text)))
    import json as _json
    assert _json.loads(parsed[0]["extra"]) == {"nested": "中文"}


def test_list_value_json_serialized():
    rows = [{"id": 1, "tags": ["a", "b", "c"]}]
    out = rows_to_csv_bytes(rows)
    text = _decode(out)
    assert "[" in text and "a" in text and "b" in text and "c" in text


def test_none_value_renders_empty():
    rows = [{"a": 1, "b": None}]
    out = rows_to_csv_bytes(rows)
    text = _decode(out)
    # CSV: "1," 表示 a=1, b=空
    data_line = text.splitlines()[1]
    assert data_line.endswith(",")  # b 字段值为空字符串
