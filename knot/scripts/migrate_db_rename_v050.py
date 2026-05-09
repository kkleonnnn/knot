"""knot/scripts/migrate_db_rename_v050.py — v0.5.0 DB rename startup hook + 独立 entrypoint。

执行（独立 entrypoint 双轨）：
    python3 -m knot.scripts.migrate_db_rename_v050 [--dry-run] [--data-dir <path>]

红线：
- R-69 幂等：4 场景（仅老 / 仅新 / 都无 / 都有）；timestamped backup 不覆盖前次
- R-76 原子性：shutil.copy2 + Path.rename try/except；rename 失败 → 删 bak 保老 DB
- R-77 跨平台：Python io 实现，不依赖 sed/shell

设计：
- 性质 ≠ v0.4.5 R-41 加密迁移（重写每条记录）；DB rename 是文件层操作，可作 startup hook
- 函数独立可单测；--dry-run 仅打印检测结果不动文件
- 模式：copy + rename（写 bak 后 rename 主文件）；rename 失败时 bak 删（避免误导用户已迁移）
"""
from __future__ import annotations

import argparse
import shutil
import sys
import time
from pathlib import Path

from knot.core.logging_setup import logger


def migrate_db_rename(data_dir: Path | str, dry_run: bool = False) -> dict:
    """检测 bi_agent.db → 备份 + rename 为 knot.db。幂等。

    场景矩阵：
      (a) 仅 bi_agent.db 存在 → backup + rename → knot.db
      (b) 仅 knot.db 存在 → 跳过（已迁移）
      (c) 都不存在 → 跳过（首次启动 / 无 DB）
      (d) 都存在 → fail-fast（人工介入；绝不静默 drop）

    R-76 atomic：shutil.copy2 + Path.rename 必须 try/except；rename 失败 → 删 bak 保老 DB。
    """
    data_dir = Path(data_dir)
    old = data_dir / "bi_agent.db"
    new = data_dir / "knot.db"

    if not old.exists() and not new.exists():
        return {"status": "no_db_yet"}
    if not old.exists() and new.exists():
        return {"status": "already_migrated"}
    if old.exists() and new.exists():
        msg = (
            f"[migrate-db-rename] 检测到 {old} 和 {new} 同时存在 — "
            "请人工确认数据归属（保留更新的一份），删除另一份后重启。"
        )
        logger.error(msg)
        raise RuntimeError(msg)

    # 场景 (a)：仅老 db → backup + rename
    ts = time.strftime("%Y%m%d-%H%M%S")
    bak = old.parent / f"{old.name}.v044-{ts}.bak"
    # 同秒重复（极端）→ 加 PID 兜底
    if bak.exists():
        import os
        bak = old.parent / f"{old.name}.v044-{ts}-{os.getpid()}.bak"

    if dry_run:
        return {
            "status": "would_migrate",
            "old": str(old),
            "new": str(new),
            "backup": str(bak),
        }

    # R-76 原子性：try/except 包裹；rename 失败 → 删 bak 保老 DB
    try:
        shutil.copy2(old, bak)
        old.rename(new)
    except OSError:
        # 绝不允许 DB 消失：bak 已建但 rename 失败 → 删 bak 避免误导
        if bak.exists() and not new.exists():
            try:
                bak.unlink()
            except OSError:
                pass  # bak 删失败 fallthrough，原异常优先
        logger.error(f"[migrate-db-rename] FAILED — old DB preserved: {old}")
        raise

    logger.info(f"[migrate-db-rename] {old} → {new}（备份保留 {bak}）")
    return {
        "status": "migrated",
        "backup": str(bak),
        "new_db": str(new),
    }


def _main() -> int:
    ap = argparse.ArgumentParser(
        description="v0.5.0 DB rename migration（一次性 / 幂等 / atomic）"
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="只打印检测结果，0 副作用（不写 DB / 不创建 bak）",
    )
    ap.add_argument(
        "--data-dir",
        default=None,
        help="data 目录路径（默认 <repo>/knot/data/）",
    )
    args = ap.parse_args()

    if args.data_dir:
        data_dir = Path(args.data_dir)
    else:
        # 默认 repo_root/knot/data/
        repo_root = Path(__file__).resolve().parents[2]
        data_dir = repo_root / "knot" / "data"
        data_dir.mkdir(parents=True, exist_ok=True)

    try:
        result = migrate_db_rename(data_dir, dry_run=args.dry_run)
        prefix = "[dry-run] " if args.dry_run else ""
        print(f"{prefix}migrate-db-rename: {result}")
        return 0
    except Exception as e:
        sys.stderr.write(f"\n\033[91m[migrate-db-rename FAILED] {e}\033[0m\n")
        return 1


if __name__ == "__main__":
    sys.exit(_main())
