"""export_service — v0.4.0 detail intent 触发的 CSV 导出。

设计选择（手册 §4.1）：内存 BytesIO 模式。
- MAX_RESULT_ROWS=500 锁死单次结果集 → CSV ≤ 200KB，无需 streaming
- BytesIO 既不落盘也不流式，FastAPI StreamingResponse 一行包装
- 中文 utf-8-sig（带 BOM）保证 Excel 直接打开不乱码
- v0.4.1 升级 xlsx 时换 openpyxl 写入同一 BytesIO，调用方契约不变
"""
from __future__ import annotations

import csv
import json
from io import StringIO


def rows_to_csv_bytes(rows: list[dict], cols: list[str] | None = None) -> bytes:
    """把 [{col: val}, ...] 转成 CSV 字节流（utf-8-sig，带 BOM）。

    cols=None 时从首行 keys 推断字段顺序。
    复杂值（dict / list）使用 JSON 序列化（中文不转义）。
    空 rows 返回空 bytes。
    """
    if not rows:
        return b""
    cols = cols or list(rows[0].keys())
    sio = StringIO()
    writer = csv.DictWriter(sio, fieldnames=cols, extrasaction="ignore")
    writer.writeheader()
    for r in rows:
        writer.writerow({c: _stringify(r.get(c)) for c in cols})
    return sio.getvalue().encode("utf-8-sig")


def _stringify(v) -> str:
    if v is None:
        return ""
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False, default=str)
    return str(v)
