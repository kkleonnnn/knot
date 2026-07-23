"""knot.repositories.uploads_relocation — v0.9.2 uploads.db 存量物理迁移（数据根 → per-tenant）。

C4（knot.db 迁移）的姊妹：把 data-root `uploads.db` 移到 `tenants/<id>/uploads.db`。**独立状态机**，由
`tenancy_migration.migrate_anchor_db_to_tenant_once` 在持 flock 内、`_migrate_locked` 成功返回后**无条件调**
（MF1/R2：真实 v0.9.0→v0.9.2 升级 knot.db 已在 v0.9.0 迁走 → `_migrate_locked` 走 skip:migrated 早返，
若把 relocation 挂在 anchor-存在分支就永不跑 = uploads 孤儿）。

复用 tenancy_migration 的 **C4 Stage-4 硬化** `_backup_db`（严格 fsync 失败即 raise，非弱 copy2；G2/MF3）。
**空 uploads.db 合法**（租户从未上传）→ 不复用 C4 的「零表即 raise」`_verify_migrated_db`（MF4/R4）。
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from knot.core.logging_setup import logger
from knot.repositories.tenancy_migration import (
    _backup_db,
    _backup_db_atomic,
    _fsync_dir,
    _next_free_bak,
)

_MARKER = ".uploads-relocating"


def _uploads_tables(path: Path) -> set:
    """uploads.db 的用户表集合（t_* 上传表；排除 sqlite 内部表）。读不出 → 空集。"""
    try:
        c = sqlite3.connect(path)
        try:
            return {
                r[0] for r in c.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                )
            }
        finally:
            c.close()
    except sqlite3.Error:
        return set()


def _uploads_has_real_data(path: Path) -> bool:
    """有用户上传表 → True。**读不出(corrupt/locked) → True**（对抗 #4 保守：不静默覆盖未知内容 → 触发 valve
    halt 或 preserve，非当作空可覆盖）。0 表可读 → False（合法空，可覆盖残片）。"""
    try:
        c = sqlite3.connect(path)
        try:
            return bool({
                r[0] for r in c.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                )
            })
        finally:
            c.close()
    except sqlite3.Error:
        return True


def _clear_orphan_marker(tenant_dir: Path) -> None:
    """清孤儿 `.uploads-relocating`（对抗 #1，镜像 C4 `_clear_orphan_marker`）—— 完成后残留标记不清 → 日后
    data-root 被恢复会旁路安全阀（marker 在 → resume 覆盖 live target 而非 halt）。"""
    m = tenant_dir / _MARKER
    if m.exists():
        try:
            m.unlink()
            _fsync_dir(tenant_dir)
            logger.warning(f"[uploads-reloc] 清除孤儿标记: {m}")
        except OSError as e:
            logger.warning(f"[uploads-reloc] 孤儿标记清除失败（不阻断）: {m}: {e}")


def _verify_relocated_uploads(src: Path, dst: Path) -> None:
    """校验 relocation copy 完整（**空 uploads 合法** — 不要求 ≥1 表，区别 C4 `_verify_migrated_db`）：
    src+dst quick_check ok + 精确表集一致 + 逐表行数一致。任一不过 raise → 上层保 last-good。"""
    sc, sd = sqlite3.connect(src), sqlite3.connect(dst)
    try:
        for tag, c in (("src", sc), ("dst", sd)):
            if c.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise RuntimeError(f"[uploads-reloc] {tag} quick_check 不过（损坏）")
        ts = _uploads_tables(src)
        td = _uploads_tables(dst)
        if ts != td:
            raise RuntimeError(f"[uploads-reloc] 表集合不一致 src−dst={ts - td} dst−src={td - ts}")
        for t in sorted(ts):
            ns = sc.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
            nd = sd.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
            if ns != nd:
                raise RuntimeError(f"[uploads-reloc] 表 {t} 行数不符 src={ns} dst={nd}")
    finally:
        sc.close()
        sd.close()


def relocate_uploads_once(data_root: Path, tenant_dir: Path) -> str:
    """data-root uploads.db → tenant_dir/uploads.db 的独立 crash-safe 状态机（6 态）。持锁由调用方保证。

      db_dir='.'（target==src，测试）              → skip:same-path
      src 无 + target 无                            → skip:fresh（租户从未上传 · 合法空）
      src 无 + target 有                            → skip:relocated（已迁）
      src 有 + target 无                            → relocated（首迁）
      src 有 + target 有(残片/空 或 有标记)         → resumed（覆盖重迁；真数据 target 先保全 .pre-resume.N.bak）
      src 有 + target 有(有 t_* 真数据 且 无标记)   → raise（疑似违反铁律先上现网 → 拒覆盖）
    """
    src = data_root / "uploads.db"
    target = tenant_dir / "uploads.db"

    if target.resolve() == src.resolve():
        return "skip:same-path"
    src_exists, target_exists = src.exists(), target.exists()
    if not src_exists:
        _clear_orphan_marker(tenant_dir)   # 对抗 #1：清完成后残留的孤儿标记（防日后 data-root 恢复旁路安全阀）
        return "skip:relocated" if target_exists else "skip:fresh"

    marker = tenant_dir / _MARKER
    resuming = target_exists or marker.exists()
    if target_exists and not marker.exists() and _uploads_has_real_data(target):
        raise RuntimeError(
            f"[uploads-reloc] target {target} 已有上传表但 data-root {src} 仍在、无进行中标记 —— "
            "疑似 C1-C3 在 relocation 前上了现网写入。拒绝覆盖，人工核对后手动处置。"
        )

    tenant_dir.mkdir(parents=True, exist_ok=True)
    marker.write_text("in-progress", encoding="utf-8")
    _fsync_dir(tenant_dir)   # 对抗 #7：marker 落盘再动 target（fsync 重排下防 target 已改而 marker 未持久）

    # resume 保全含真数据的既有 target（防回滚期写入丢失，镜像 C4 must#2）
    if target.exists() and _uploads_has_real_data(target):
        preserve = _next_free_bak(tenant_dir, "uploads.db.pre-resume")
        _backup_db_atomic(target, preserve)
        logger.warning(f"[uploads-reloc] resume 覆盖前保全既有 target → {preserve}")
    for p in (target, target.with_name(target.name + "-wal"), target.with_name(target.name + "-shm")):
        if p.exists():
            p.unlink()
    _backup_db(src, target)                    # 硬化 WAL-safe + 严格 fsync

    try:
        _verify_relocated_uploads(src, target)
    except Exception as e:
        target.unlink(missing_ok=True)
        raise RuntimeError(f"[uploads-reloc] 校验失败，已删 target 保 data-root 源 last-good: {e}") from e

    # 当场新建 relocation 备份（硬化，不依赖 stale .pre-tenancy.bak；R5）→ 删源 + sidecars → fsync 目录 → 清标记
    bak = data_root / "uploads.db.pre-v0.9.2-relocation.bak"
    if not bak.exists():
        _backup_db_atomic(src, bak)
    for p in (src, src.with_name(src.name + "-wal"), src.with_name(src.name + "-shm")):
        if p.exists():
            p.unlink()
    _fsync_dir(data_root)
    marker.unlink(missing_ok=True)
    _fsync_dir(tenant_dir)   # 对抗 #7：marker 删除持久化（否则掉电后孤儿 marker 残留）
    result = "resumed" if resuming else "relocated"
    logger.info(f"[uploads-reloc] 完成（{result}）：{src} → {target}；源备份 {bak}")
    return result
