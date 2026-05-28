"""totp_repo — totp_recovery_codes 表 CRUD（v0.6.2.0 R-PB-B1-2/7/11）。

设计原则：
- code_hash 走 bcrypt（与 password_hash 同精神 — 单向；明文不留 DB）。
- 单次使用语义：mark_used 必检查 used_at IS NULL（防 race 重复消费）。
- 重置场景 delete_all_for_user_in_tx 走传入 conn — 与 user_repo.clear_totp_in_tx 同事务
  （R-PB-B1-9 R-46-Tx 守护 — secret + recovery_codes 同事务清除）。
- 列表查询返 (id, code_hash) 元组列表，service 层走 bcrypt.checkpw 逐条比对
  （单 user 最多 10 codes — 性能可接受；不引入索引）。
"""
from __future__ import annotations

import sqlite3
from datetime import datetime

from knot.repositories.base import get_conn


def insert_recovery_codes_in_tx(
    conn: sqlite3.Connection, user_id: int, code_hashes: list[str],
) -> None:
    """R-PB-B1-9 R-46-Tx：在传入 conn 事务中批量 INSERT recovery code hash。

    与 user_repo.set_totp_in_tx 同事务 — secret + codes 任一失败全回滚
    （防 secret 已写但 recovery codes 缺失 → 账号锁死）。
    """
    conn.executemany(
        "INSERT INTO totp_recovery_codes (user_id, code_hash) VALUES (?, ?)",
        [(user_id, h) for h in code_hashes],
    )


def get_unused_codes(user_id: int) -> list[tuple[int, str]]:
    """返 [(id, code_hash), ...] — service 层走 bcrypt.checkpw 逐条比对。

    R-PB-B1-11：consume 时调用方拿 id → mark_used_by_id。
    """
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, code_hash FROM totp_recovery_codes "
        "WHERE user_id=? AND used_at IS NULL ORDER BY id",
        (user_id,),
    ).fetchall()
    conn.close()
    return [(int(r["id"]), str(r["code_hash"])) for r in rows]


def mark_used_by_id(code_id: int) -> bool:
    """R-PB-B1-11：单次使用语义守护 — WHERE used_at IS NULL 防 race 重复消费。

    返 True = 成功标记；False = 已被使用（race 场景）或 id 不存在。
    """
    conn = get_conn()
    cur = conn.execute(
        "UPDATE totp_recovery_codes SET used_at=? "
        "WHERE id=? AND used_at IS NULL",
        (datetime.utcnow().isoformat(timespec="seconds") + "Z", code_id),
    )
    conn.commit()
    conn.close()
    return cur.rowcount == 1


def count_unused(user_id: int) -> int:
    """剩余可用 recovery codes 数量 — admin 视图 + 5 次/月警报基线用。"""
    conn = get_conn()
    row = conn.execute(
        "SELECT COUNT(*) AS c FROM totp_recovery_codes "
        "WHERE user_id=? AND used_at IS NULL",
        (user_id,),
    ).fetchone()
    conn.close()
    return int(row["c"]) if row else 0


def delete_all_for_user_in_tx(
    conn: sqlite3.Connection, user_id: int,
) -> None:
    """R-PB-B1-9 R-46-Tx：reset 场景清除所有 recovery codes（含已使用）。

    与 user_repo.clear_totp_in_tx + bump_token_version_in_tx 同事务。
    """
    conn.execute(
        "DELETE FROM totp_recovery_codes WHERE user_id=?", (user_id,),
    )
