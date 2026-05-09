"""export_service — v0.4.0 CSV / v0.4.2 xlsx 导出。

设计选择（手册 §4.1 + §3.5）：内存 BytesIO 模式。
- MAX_RESULT_ROWS=500 锁死单次 CSV 结果集 → ≤ 200KB
- xlsx：5000 行硬限（资深 R-15）；超出截断 + 守护者 R-S7 metadata 暴露给前端
- 中文 utf-8-sig（带 BOM）保证 Excel 直接打开不乱码（CSV 模式）
- xlsx 模式下 openpyxl 自动 utf-8 + 数字格式保留
"""
from __future__ import annotations

import csv
import json
from io import BytesIO, StringIO

# v0.4.2 R-15 + R-S7：xlsx 单文件硬限 5000 行
XLSX_MAX_ROWS: int = 5000


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


def rows_to_xlsx_bytes(
    rows: list[dict],
    cols: list[str] | None = None,
    sheet_name: str = "Data",
) -> tuple[bytes, dict]:
    """v0.4.2：rows → xlsx bytes + R-S7 metadata。

    返回 (xlsx_bytes, metadata)：
      metadata = {
          "truncated": bool,        # rows 是否被截断
          "total": int,             # 原始行数
          "exported": int,          # 实际写入 xlsx 的行数（≤ XLSX_MAX_ROWS）
      }

    资深 R-15：5000 行硬限防 OOM。
    守护者 R-S7：metadata 由 API 层放 response header（X-Export-*），前端 toast 提示。

    数字保留为 number 类型（Excel 自动右对齐 + 公式可用）；
    复杂值（dict/list）JSON 序列化为字符串。
    """
    from openpyxl import Workbook  # 延迟 import，避免不用 xlsx 时也加载
    truncated = len(rows) > XLSX_MAX_ROWS
    actual_rows = rows[:XLSX_MAX_ROWS] if truncated else rows
    cols = cols or (list(actual_rows[0].keys()) if actual_rows else [])

    wb = Workbook()
    ws = wb.active
    ws.title = sheet_name
    if cols:
        ws.append(cols)
    for r in actual_rows:
        ws.append([_xlsx_value(r.get(c)) for c in cols])

    bio = BytesIO()
    wb.save(bio)
    return bio.getvalue(), {
        "truncated": truncated,
        "total": len(rows),
        "exported": len(actual_rows),
    }


def _stringify(v) -> str:
    if v is None:
        return ""
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False, default=str)
    return str(v)


def _xlsx_value(v):
    """xlsx 写入值的类型转换。
    - None → '' （空 cell）
    - int/float → 保留为 number（Excel 自动识别）
    - bool → True/False（openpyxl 原生支持）
    - dict/list → JSON 字符串
    - 其他 → str()"""
    if v is None:
        return ""
    if isinstance(v, (int, float, bool)):
        return v
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False, default=str)
    return str(v)
