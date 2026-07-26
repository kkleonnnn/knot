"""knot.repositories.uploads_relocation — v0.9.2 uploads.db 存量物理迁移（数据根 → per-tenant）。

C4（knot.db 迁移）的姊妹：把 data-root `uploads.db` 移到 `tenants/<id>/uploads.db`。**独立状态机**，由
`tenancy_migration.migrate_anchor_db_to_tenant_once` 在持 flock 内、`_migrate_locked` 成功返回后**无条件调**
（MF1/R2：真实 v0.9.0→v0.9.2 升级 knot.db 已在 v0.9.0 迁走 → `_migrate_locked` 走 skip:migrated 早返，
若把 relocation 挂在 anchor-存在分支就永不跑 = uploads 孤儿）。

复用 tenancy_migration 的 **C4 Stage-4 硬化** `_backup_db`（严格 fsync 失败即 raise，非弱 copy2；G2/MF3）。
**空 uploads.db 合法**（租户从未上传）→ 不复用 C4 的「零表即 raise」`_verify_migrated_db`（MF4/R4）；
但**损坏**一律 fail-closed（守护者 Stage 4 §II：skip:relocated 前补 quick_check 健康探针 `_uploads_wellformed`，
补齐与 C4 `_migrate_locked` #5 的不对称 —— 空合法 ≠ 损坏可放行）。
"""
from __future__ import annotations

import os
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


def _uploads_unhealthy_reason(path: Path) -> str | None:
    """None = 完好（**0 表仍合法**）；否则返回不健康原因**原文**（供运维分辨「锁竞争/权限」与「真损坏」）。

    守护者 Stage 4 §II（C4-parity）：skip:relocated 前的健康探针。relocation 完成后 target 若被掉电 /
    WAL-replay 损坏，仅凭 `target.exists()` 返 skip → `get_upload_engine` 建引擎于损坏库 → 运行时查询失败
    且**无 fail-closed halt**（C4 姊妹路径 `_migrate_locked` #5 是 enforce 的，此处曾不对称）。
    不复用 C4 `_db_wellformed`：它「零表即 False」，而空 uploads 合法（MF4）。
    实证：0-byte 与 `.backup()` 空库 quick_check 均为 ok；页内破坏（头完好）返非 ok 长串；垃圾字节 raise。

    **返回原因而非裸 bool 的理由**（Stage 4 对抗 AV-A/AV-C/AV-D 三方独立复现）：`sqlite3.Error` 同时覆盖
    `OperationalError: database is locked`（锁竞争 —— 库其实完好）与 `DatabaseError: file is not a database`
    （真损坏）。控制流**故意不区分**（narrow 到 DatabaseError 只会让 OperationalError 裸 traceback 逃出启动期，
    更糟；实测 4 并发上传 / 1993 MiB 库 / 33 次启动探针 0 误判，最坏 1.8s « 5s busy timeout），改为把原文带进
    错误信息 + 由「重启是否复现」区分：锁竞争/权限所致的 halt 重启即恢复，真损坏才持续复现。
    """
    try:
        c = sqlite3.connect(path)
        try:
            r = c.execute("PRAGMA quick_check").fetchone()[0]
            return None if r == "ok" else f"quick_check={str(r)[:200]}"
        finally:
            c.close()
    except sqlite3.Error as e:
        return f"{type(e).__name__}: {e}"


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
      src 无 + target 有(完好，0 表亦算)            → skip:relocated（已迁）
      src 无 + target 有(损坏)                      → raise（Stage 4 §II C4-parity：拒以损坏库起服务）
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
        if not target_exists:
            return "skip:fresh"
        # Stage 4 §II（C4-parity，镜像 `_migrate_locked` #5）：已迁 target 不健康 → fail-closed halt，
        # 绝不以损坏 uploads 库起服务。**0 表仍合法**（`_uploads_unhealthy_reason` 非 C4 `_db_wellformed`）。
        reason = _uploads_unhealthy_reason(target)
        if reason is not None:
            bak = data_root / "uploads.db.pre-v0.9.2-relocation.bak"
            raise RuntimeError(
                f"[uploads-reloc] uploads 库 {target} 已迁走 data-root 源但探针不健康（{reason}）—— 拒绝以损坏库起服务。\n"
                f"  ① 先判性质：锁竞争 / 权限（OperationalError）所致的 halt **重启即恢复**；真损坏才会持续复现。\n"
                f"  ② 确为损坏且有备份 → 把备份还原到 **{target}** 本身"
                f"（若存在 {bak.name}；勿还原到 data-root —— 那会触发下一轮「源与 target 并存」安全阀 halt）。\n"
                f"  ③ 确为损坏且无备份 / 无需保留历史上传 → 删除 {target.name} 后重启（走 skip:fresh，用户重新上传）。"
            )
        return "skip:relocated"

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
        if _uploads_unhealthy_reason(target) is None:
            _backup_db_atomic(target, preserve)   # 可读 → WAL-safe sqlite 备份（含未 checkpoint 的 -wal）
            logger.warning(f"[uploads-reloc] resume 覆盖前保全既有 target → {preserve}")
        else:
            # ⭐ Stage 4 对抗（AV-B/AV-D + critic 三方独立命中）：`_uploads_has_real_data` 读不出即 True（保守），
            # 于是**半写/损坏的 target 也会走到这里** —— 而 sqlite `.backup()` 读不出它 → 抛 DatabaseError 裸逃出
            # `main.py:90`（无 try/except）→ **永久 boot crash-loop**，且 C4 姊妹在同态下会自愈（其
            # `_target_has_real_data` 读不出返 False）。改为整字节 rename 留证（原子、不需 sqlite 可读），
            # 随后由仍在的 src 重做 relocation 自愈 —— 数据不丢（src 是 last-good），启动不卡死。
            os.replace(target, preserve)
            _fsync_dir(tenant_dir)
            logger.warning(f"[uploads-reloc] 既有 target 读不出（{_uploads_unhealthy_reason(preserve)}）"
                           f"→ 整字节移存 {preserve} 留证，由 data-root 源重做 relocation")
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
