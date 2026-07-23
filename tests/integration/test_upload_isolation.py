"""v0.8.19a F5 上传表名唯一守护 — 同名文件不互相覆盖（uuid 表名）+ 删除清物理表。

守护者 Stage 3 must-fix #5-F5：表名绑 uuid（非文件名），同名文件跨用户/同用户均不 DROP-覆盖。
端到端经 /api/upload，但 monkeypatch uploads.get_upload_engine 到临时库避免污染真 dev uploads.db
（v0.9.2：_upload_engine 值绑已换 per-tenant resolver get_upload_engine）。
"""
import io

import pytest
import sqlalchemy


@pytest.fixture()
def temp_upload_engine(monkeypatch, tmp_path):
    from knot.adapters.db import doris
    from knot.api import uploads as uploads_mod
    eng = doris.create_sqlite_engine(str(tmp_path / "uploads_test.db"))
    monkeypatch.setattr(uploads_mod, "get_upload_engine", lambda: eng)
    yield eng
    eng.dispose()


def _csv(content: str):
    return ("data.csv", io.BytesIO(content.encode()), "text/csv")


def test_same_filename_uploads_no_overwrite(client, auth_headers, temp_upload_engine):
    """两次上传同名 data.csv → 两个不同 uuid 表名，都存在、各自行数，无覆盖。"""
    r1 = client.post("/api/upload", files={"file": _csv("a,b\n1,2\n")}, headers=auth_headers)
    r2 = client.post("/api/upload", files={"file": _csv("a,b\n3,4\n5,6\n")}, headers=auth_headers)
    assert r1.status_code == 200 and r2.status_code == 200, (r1.text, r2.text)
    t1, t2 = r1.json()["table_name"], r2.json()["table_name"]
    assert t1 != t2, "同名文件必须得到不同表名（uuid），不得覆盖"
    assert t1.startswith("t_") and len(t1) == 34, t1  # t_ + 32 hex
    with temp_upload_engine.connect() as c:
        n1 = c.execute(sqlalchemy.text(f'SELECT COUNT(*) FROM "{t1}"')).scalar()
        n2 = c.execute(sqlalchemy.text(f'SELECT COUNT(*) FROM "{t2}"')).scalar()
    assert (n1, n2) == (1, 2), (n1, n2)


def test_delete_upload_drops_physical_table(client, auth_headers, temp_upload_engine):
    """删除上传 → 物理表从 uploads.db 一并删除（不留孤儿表）。"""
    r = client.post("/api/upload", files={"file": _csv("a\n1\n")}, headers=auth_headers)
    assert r.status_code == 200, r.text
    uid, tbl = r.json()["id"], r.json()["table_name"]
    with temp_upload_engine.connect() as c:
        assert c.execute(sqlalchemy.text(
            f"SELECT 1 FROM sqlite_master WHERE name='{tbl}'")).fetchone()
    d = client.delete(f"/api/uploads/{uid}", headers=auth_headers)
    assert d.status_code == 200, d.text
    with temp_upload_engine.connect() as c:
        gone = c.execute(sqlalchemy.text(
            f"SELECT 1 FROM sqlite_master WHERE name='{tbl}'")).fetchone()
    assert gone is None, "删除后物理表应从 uploads.db 移除"
