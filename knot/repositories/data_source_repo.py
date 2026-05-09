"""data_source_repo — data_sources + user_sources 表 CRUD。

v0.4.5：db_password 透明加解密（守 R-38）。
"""
from __future__ import annotations

from knot.core.crypto import decrypt, encrypt
from knot.core.crypto.fernet import CryptoConfigError
from knot.models.errors import ConfigMissingError
from knot.repositories.base import get_conn

_DS_ENCRYPTED_COLS = ("db_password",)


def _decrypt_ds_row(row) -> dict | None:
    if row is None:
        return None
    out = dict(row)
    for col in _DS_ENCRYPTED_COLS:
        if col in out and out[col]:
            try:
                out[col] = decrypt(out[col])
            except CryptoConfigError as e:
                raise ConfigMissingError(str(e)) from e
    return out


def list_datasources() -> list:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM data_sources ORDER BY id").fetchall()
    conn.close()
    return [_decrypt_ds_row(r) for r in rows]


def get_datasource(source_id: int) -> dict | None:
    conn = get_conn()
    row = conn.execute("SELECT * FROM data_sources WHERE id=?", (source_id,)).fetchone()
    conn.close()
    return _decrypt_ds_row(row)


def create_datasource(user_id, name, description, db_host, db_port,
                      db_user, db_password, db_database, db_type="doris") -> int:
    enc_pw = encrypt(db_password) if db_password else db_password
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO data_sources "
        "(user_id, name, description, db_host, db_port, db_user, db_password, db_database, db_type) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (user_id, name, description, db_host, db_port, db_user, enc_pw, db_database, db_type),
    )
    sid = cur.lastrowid
    conn.commit()
    conn.close()
    return sid


def update_datasource(source_id: int, **kwargs):
    if not kwargs:
        return
    for col in _DS_ENCRYPTED_COLS:
        if col in kwargs and kwargs[col]:
            kwargs[col] = encrypt(kwargs[col])
    fields = ", ".join(f"{k}=?" for k in kwargs)
    values = list(kwargs.values()) + [source_id]
    conn = get_conn()
    conn.execute(f"UPDATE data_sources SET {fields} WHERE id=?", values)
    conn.commit()
    conn.close()


def delete_datasource(source_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM data_sources WHERE id=?", (source_id,))
    conn.commit()
    conn.close()


# ── user ↔ data source 关联 ────────────────────────────────────────────

def set_user_sources(user_id: int, source_ids: list):
    conn = get_conn()
    conn.execute("DELETE FROM user_sources WHERE user_id=?", (user_id,))
    if source_ids:
        conn.executemany(
            "INSERT OR IGNORE INTO user_sources (user_id, source_id) VALUES (?,?)",
            [(user_id, sid) for sid in source_ids],
        )
    conn.commit()
    conn.close()


def get_user_source_ids(user_id: int) -> list:
    conn = get_conn()
    rows = conn.execute("SELECT source_id FROM user_sources WHERE user_id=?", (user_id,)).fetchall()
    conn.close()
    return [r[0] for r in rows]


def get_all_user_source_ids() -> dict:
    conn = get_conn()
    rows = conn.execute("SELECT user_id, source_id FROM user_sources").fetchall()
    conn.close()
    result: dict = {}
    for user_id, source_id in rows:
        result.setdefault(user_id, []).append(source_id)
    return result
