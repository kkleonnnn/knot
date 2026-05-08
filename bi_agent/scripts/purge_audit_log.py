"""bi_agent/scripts/purge_audit_log.py — 审计 retention 清理脚本（v0.4.6 commit #5）。

执行：
    python3 -m bi_agent.scripts.purge_audit_log [--dry-run]

红线：
- R-41 (复用 v0.4.5 模式)：独立 entrypoint，不进 startup hook
- R-66：自动 timestamped `<db>.audit-purge-YYYYMMDD-HHMMSS.bak` + 每表事务（仅 audit_log 一张）+ dry-run
- R-49：retention 从 app_settings.audit.retention_days 读，缺失默认 90
- R-57：purge 真跑后入 meta-audit（action=audit.purge）

执行顺序（同 v0.4.5 migrate）：
1. 读 retention 配置
2. dry-run 模式：跳过 bak + DELETE
3. 真跑：先创建 timestamped bak，再 audit_repo.delete_older_than
4. 真跑后写一条 audit.purge meta-audit（fail-soft）
"""
from __future__ import annotations

import argparse
import shutil
import sys
import time
from pathlib import Path

from bi_agent.core.logging_setup import logger
from bi_agent.repositories import audit_repo, settings_repo
from bi_agent.repositories import base as _base_mod  # 调用时读 SQLITE_DB_PATH（兼容测试 monkeypatch）
from bi_agent.services import audit_service

_DEFAULT_RETENTION = 90


def _make_backup(db_path: Path) -> Path:
    """R-66：timestamped bak 避免覆盖前次（同 v0.4.5 模式）。

    格式：<db>.audit-purge-YYYYMMDD-HHMMSS.bak
    """
    ts = time.strftime("%Y%m%d-%H%M%S")
    bak = db_path.parent / f"{db_path.name}.audit-purge-{ts}.bak"
    if bak.exists():
        bak = db_path.parent / f"{db_path.name}.audit-purge-{ts}-{__import__('os').getpid()}.bak"
    shutil.copy2(db_path, bak)
    logger.info(f"[purge_audit] 已生成备份 {bak}")
    return bak


def purge(dry_run: bool = False, db_path: str | None = None) -> dict:
    """主清理函数；返回 stats dict 含 backup_path（dry-run 为 None）。"""
    days_str = settings_repo.get_app_setting("audit.retention_days", str(_DEFAULT_RETENTION))
    try:
        days = int(days_str)
    except ValueError:
        days = _DEFAULT_RETENTION

    path = Path(db_path or _base_mod.SQLITE_DB_PATH)
    backup_path: str | None = None
    if not dry_run:
        backup_path = str(_make_backup(path))

    deleted = audit_repo.delete_older_than(days, dry_run=dry_run)

    stats = {"days": days, "deleted": deleted, "backup_path": backup_path}

    # R-57 meta-audit：真跑后写入；dry-run 不写
    if not dry_run and deleted > 0:
        audit_service.log(
            actor=None, action="audit.purge", resource_type="audit",
            detail={"days": days, "deleted_count": deleted},
        )

    mode = "[dry-run] " if dry_run else ""
    logger.info(f"[purge_audit]{mode} 完成: {stats}")
    return stats


def _main() -> int:
    ap = argparse.ArgumentParser(description="v0.4.6 审计日志 retention 清理（独立 entrypoint）")
    ap.add_argument("--dry-run", action="store_true", help="只统计 would_delete，0 副作用")
    args = ap.parse_args()
    try:
        stats = purge(dry_run=args.dry_run)
        prefix = "[dry-run] " if args.dry_run else ""
        print(f"{prefix}清理完成: {stats}")
        return 0
    except Exception as e:
        sys.stderr.write(f"\n\033[91m[清理失败] {e}\033[0m\n")
        return 1


if __name__ == "__main__":
    sys.exit(_main())
