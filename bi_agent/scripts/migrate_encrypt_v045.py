"""bi_agent/scripts/migrate_encrypt_v045.py — 一次性数据加密迁移（v0.4.5 commit #3）。

执行：
    python3 -m bi_agent.scripts.migrate_encrypt_v045 [--dry-run]

红线：
- R-36 幂等：见 enc_v1: 跳过；多次运行 DB content 不变
- R-41 独立 entrypoint：不进 startup hook（grep 守护测试）
- R-46 自动 bak：写第一个 UPDATE 之前生成 `<db>.v044-<ts>.bak`；timestamp 后缀避免覆盖
- R-46-Tx 每张表一个事务：表内中断回滚，跨表已成功保留

执行顺序（守护者提示）：
1. assert_master_key_loaded() 第一行（缺失立即 fail，不创建 bak）
2. dry-run 模式：0 副作用（不写 DB / 不创建 bak）
3. 真跑：先创建 timestamped bak，再按 TARGETS 顺序逐表加密
"""
from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
import time
from pathlib import Path

from bi_agent.core.crypto import encrypt, is_encrypted
from bi_agent.core.crypto.fernet import assert_master_key_loaded
from bi_agent.core.logging_setup import logger
from bi_agent.repositories import base as _base_mod  # 按调用时读 SQLITE_DB_PATH（兼容测试 monkeypatch）

# 表 / id 列 / 敏感列 / 可选 WHERE 子句
TARGETS = [
    ("users", "id",
     ["api_key", "openrouter_api_key", "embedding_api_key", "doris_password"], None),
    ("data_sources", "id", ["db_password"], None),
    ("app_settings", "key", ["value"],
     "key IN ('openrouter_api_key', 'embedding_api_key')"),
]


def _make_backup(db_path: Path) -> Path:
    """R-46：timestamped bak 避免覆盖前次（守护者数据丢失教训）。

    格式：<db>.v044-YYYYMMDD-HHMMSS.bak
    """
    ts = time.strftime("%Y%m%d-%H%M%S")
    bak = db_path.parent / f"{db_path.name}.v044-{ts}.bak"
    # 同秒重复（极端）→ 加进程 ID 兜底
    if bak.exists():
        bak = db_path.parent / f"{db_path.name}.v044-{ts}-{__import__('os').getpid()}.bak"
    shutil.copy2(db_path, bak)
    logger.info(f"[migrate] 已生成备份 {bak}")
    return bak


def migrate(dry_run: bool = False, db_path: str | None = None) -> dict:
    """主迁移函数；返回 stats dict 含 backup_path（dry-run 为 None）。"""
    # 守护者提示 §一处提示：master key 缺失先 fail，不创建 bak
    assert_master_key_loaded()

    path = Path(db_path or _base_mod.SQLITE_DB_PATH)
    backup_path: str | None = None
    if not dry_run:
        backup_path = str(_make_backup(path))

    stats = {"scanned": 0, "encrypted": 0, "skipped": 0, "backup_path": backup_path}

    # 用独立 connection 自管事务（base.get_conn() 默认 autocommit 行为不可靠）
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    try:
        for table, id_col, cols, where in TARGETS:
            sql = f"SELECT {id_col}, {','.join(cols)} FROM {table}"
            if where:
                sql += f" WHERE {where}"
            rows = conn.execute(sql).fetchall()

            # R-46-Tx 每表一个事务：表内中断 → 整表 ROLLBACK；其他表已 COMMIT 保持
            try:
                for row in rows:
                    stats["scanned"] += 1
                    updates = {}
                    for c in cols:
                        v = row[c]
                        if v is None or v == "" or is_encrypted(v):
                            continue
                        updates[c] = encrypt(v)
                    if updates and not dry_run:
                        set_clause = ",".join(f"{c}=?" for c in updates)
                        conn.execute(
                            f"UPDATE {table} SET {set_clause} WHERE {id_col}=?",
                            (*updates.values(), row[id_col]),
                        )
                        stats["encrypted"] += 1
                    elif updates:
                        # dry-run 路径仍计入 would_encrypt
                        stats["encrypted"] += 1
                    else:
                        stats["skipped"] += 1
                if not dry_run:
                    conn.commit()
            except Exception:
                # R-46-Tx：表内异常 → 整表回滚；上抛到调用方（也撤销前已 commit 的表？否 — 已 commit 不可撤）
                if not dry_run:
                    conn.rollback()
                raise
    finally:
        conn.close()

    mode = "[dry-run] " if dry_run else ""
    logger.info(f"[migrate]{mode} 完成: {stats}")
    return stats


def _main() -> int:
    ap = argparse.ArgumentParser(
        description="v0.4.5 数据加密迁移（一次性 / 幂等）"
    )
    ap.add_argument("--dry-run", action="store_true",
                    help="只统计 would_encrypt，0 副作用（不写 DB / 不创建 bak）")
    args = ap.parse_args()
    try:
        stats = migrate(dry_run=args.dry_run)
        prefix = "[dry-run] " if args.dry_run else ""
        print(f"{prefix}迁移完成: {stats}")
        return 0
    except Exception as e:
        sys.stderr.write(f"\n\033[91m[迁移失败] {e}\033[0m\n")
        return 1


if __name__ == "__main__":
    sys.exit(_main())
