import csv
import io
import re
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

import db_connector
import persistence
from ..dependencies import get_current_user
from ..engine_cache import _upload_engine

router = APIRouter()


def _parse_csv_bytes(data: bytes) -> tuple:
    for enc in ("utf-8-sig", "utf-8", "gbk", "gb2312"):
        try:
            text = data.decode(enc)
            reader = csv.reader(io.StringIO(text))
            all_rows = list(reader)
            if not all_rows:
                return [], []
            return all_rows[0], all_rows[1:]
        except (UnicodeDecodeError, Exception):
            continue
    return [], []


def _parse_excel_bytes(data: bytes) -> tuple:
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    ws = wb.active
    all_rows = [[str(cell.value) if cell.value is not None else "" for cell in row] for row in ws.iter_rows()]
    wb.close()
    if not all_rows:
        return [], []
    return all_rows[0], all_rows[1:]


@router.post("/api/upload")
async def upload_file(file: UploadFile = File(...), user=Depends(get_current_user)):
    fname = file.filename or "upload"
    ext = Path(fname).suffix.lower()
    if ext not in (".csv", ".xlsx", ".xls"):
        raise HTTPException(status_code=400, detail="仅支持 CSV 和 Excel 文件")

    data = await file.read()
    if len(data) > 20 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="文件不超过 20 MB")

    if ext == ".csv":
        headers, rows = _parse_csv_bytes(data)
    else:
        try:
            headers, rows = _parse_excel_bytes(data)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Excel 解析失败: {str(e)[:200]}")

    if not headers:
        raise HTTPException(status_code=400, detail="文件为空或格式错误")

    table_name = "t_" + re.sub(r"[^\w]", "_", Path(fname).stem)[:32]
    ok, err = db_connector.load_rows_to_sqlite(_upload_engine, table_name, headers, rows)
    if not ok:
        raise HTTPException(status_code=500, detail=f"写入失败: {err}")

    upload_id = persistence.create_file_upload(
        user_id=user["id"], filename=fname,
        table_name=table_name, row_count=len(rows), columns=headers,
    )
    return {"id": upload_id, "filename": fname, "table_name": table_name,
            "row_count": len(rows), "columns": headers}


@router.get("/api/uploads")
async def list_uploads(user=Depends(get_current_user)):
    return persistence.list_file_uploads(user["id"])


@router.delete("/api/uploads/{upload_id}")
async def delete_upload(upload_id: int, user=Depends(get_current_user)):
    rec = persistence.get_file_upload(upload_id)
    if not rec or rec["user_id"] != user["id"]:
        raise HTTPException(status_code=404)
    persistence.delete_file_upload(upload_id)
    return {"ok": True}
