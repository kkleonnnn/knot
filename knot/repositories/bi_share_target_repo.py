"""bi_share_target_repo — v0.8.14 分享投递目标白名单 CRUD（admin 策展）。

用户分享时提交 target_id 引本表行；服务端校验 target_id ∈ 本表（chat_id 禁用户自填 — R-BI-SHARE-1）。
chat_id 非机密（明文存）；OOS-1：绑 data_source_id（可空=全局），严禁 tenant_id。
IM 凭据（lark_app_secret/telegram_bot_token）不在本表 —— 走 settings_repo 加密 app_settings。
"""
from __future__ import annotations

from knot.repositories.base import get_conn

PLATFORMS = ("lark", "tg")
_COLS = "id, name, platform, chat_id, region, data_source_id, created_at, created_by"


def list_targets() -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        f"SELECT {_COLS} FROM bi_share_targets ORDER BY id"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_targets_by_ids(ids: list[int]) -> list[dict]:
    """按 id 批量取（用于分享时逐 target_id 校验 ∈ 白名单）。去重后查。"""
    uniq = list(dict.fromkeys(int(i) for i in ids))
    if not uniq:
        return []
    ph = ",".join("?" * len(uniq))
    conn = get_conn()
    rows = conn.execute(
        f"SELECT {_COLS} FROM bi_share_targets WHERE id IN ({ph})", tuple(uniq)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def create_target(*, name: str, platform: str, chat_id: str, region: str | None,
                   data_source_id: int | None, created_by: int) -> int:
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO bi_share_targets (name, platform, chat_id, region, data_source_id, created_by) "
        "VALUES (?,?,?,?,?,?)",
        (name, platform, chat_id, region, data_source_id, created_by),
    )
    conn.commit()
    tid = cur.lastrowid
    conn.close()
    return tid


def delete_target(target_id: int) -> None:
    conn = get_conn()
    conn.execute("DELETE FROM bi_share_targets WHERE id=?", (target_id,))
    conn.commit()
    conn.close()
