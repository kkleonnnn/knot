"""knot.repositories.tenancy_migration — v0.9.0 C4 存量迁移：pre-tenancy 单库 → tenant#1 库。

把旧单租户锚点 `SQLITE_DB_PATH`（data/knot.db）迁入 tenant#1 目录（data/tenants/1/knot.db）。

**铁律（守护者 Stage 4）：必先于现网 rollout** —— prod tenant#1 db_dir='tenants/1' ≠ 锚点，
裸 rollout = per-tenant init_db 起空库 + 旧数据在锚点孤儿。启动序 ❷.5（seed_default_tenant 后、
per-tenant init_db 前）调用；测试期由 KNOT_SKIP_STARTUP_MIGRATION gate 跳过（本模块由专测直调验证）。

设计（对抗评审加固后）：
- **COPY 非 move**（sqlite backup API，WAL-safe + fsync）→ 强校验（表集合/关键表行数/decrypt 烟测/非空）
  → 过才删锚点（备份到 .pre-tenancy.bak）。校验不过 → 删 target 保锚点 last-good，raise 中止启动（fail-closed）。
- **跨进程 flock**（数据根 .c4-migration.lock）串行化多 worker/副本（同节点）；跨节点 RWX 见 DEPLOY「先单副本迁移」。
- **广义 real-data 判据**：安全阀检查「seed 后恒空、仅用户操作才增长」的表（非仅 users/conversations），
  防 C1-C3 先上现网写入的租户库（1 用户 + 配了数据源/知识/报表）被误判残片而覆盖。
- **in-progress 标记** `.c4-migrating`：消歧「本迁移 crash 后残留的 target」vs「prod 独立写入的库」。
- **skip:migrated 前完好性校验**：防掉电致 target 未落盘就被判已迁 → 服务空库。
"""
from __future__ import annotations

import fcntl
import os
import sqlite3
from pathlib import Path

from knot.core.logging_setup import logger
from knot.repositories import tenant_repo

# 关键表行数校验点（点名核心业务/安全表；表不存在则跳 — 兼容早期缺表库）
_MIGRATION_KEY_TABLES = ("users", "audit_log", "data_sources", "conversations")

# seed 后恒为空、仅用户操作才增长的表（安全阀判据）。**排除** seed 即非空的表：
# users(1 admin) / semantic_layer(1 空行) / prompt_templates+few_shots(启动 seed) → 否则全新 target 被误判为「有真数据」。
_USER_CONTENT_TABLES = (
    "conversations", "messages", "data_sources", "user_sources",
    "knowledge_docs", "saved_reports", "bi_reports", "metrics",
)


def _fsync_path(p: Path) -> None:
    """fsync 文件或目录（best-effort；目录 fsync 使 rename/create 目录项持久 —— 掉电顺序屏障）。"""
    try:
        fd = os.open(p, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError as e:
        logger.warning(f"[C4] fsync 跳过（不阻断）: {p}: {e}")


def _backup_db(src: Path, dst: Path) -> None:
    """用 sqlite backup API 拷一致快照 —— **WAL-safe**（含未 checkpoint 的已提交数据）+ fsync dst 与其目录。

    - src 不存在 → raise：防 `sqlite3.connect` 把被并发进程刚删的锚点**重建为空库**（并发数据丢失向量）。
    - fsync dst + 目录：保证 target 数据页与目录项落盘，才可删锚点 —— 防掉电后锚点已删而 target 未落盘 → 服务空库。
    dst 已存在则其内容被覆盖。
    """
    if not src.exists():
        raise RuntimeError(f"[C4] backup 源不存在（防 connect 重建空库）: {src}")
    s = sqlite3.connect(src)
    d = sqlite3.connect(dst)
    try:
        s.backup(d)
    finally:
        d.close()
        s.close()
    _fsync_path(dst)
    _fsync_path(dst.parent)


def _backup_db_atomic(src: Path, dst: Path) -> None:
    """原子备份：backup 到 dst.tmp → os.replace → dst。防中途 crash 留**半成品 dst** 而 existence-gate 永不重生
    （对抗评审 #5：备份重生须按有效性判据而非仅存在性 → temp+replace 使 dst 只在完整时出现）。"""
    tmp = dst.with_name(dst.name + ".tmp")
    try:
        _backup_db(src, tmp)
        os.replace(tmp, dst)   # 原子
    finally:
        try:
            Path(tmp).unlink(missing_ok=True)   # 失败残留 tmp 清理（成功已 replace 走）
        except OSError:
            pass


def _decrypt_smoke(dst: Path) -> None:
    """迁移库解密烟测：找 1 条**真密文**（enc_v1:）凭据解密（fernet round-trip 证 master key 未变/密文完好）。

    **只探 `is_encrypted` 为真的值**（对抗评审修）—— legacy 明文 / 空占位不触发 key 校验：fernet.decrypt 对
    非 enc_v1 值 passthrough 原样返回、对空占位返 ""，均**不动 key** → 若只取首个非空值会让**错的 master key
    在存量库上 false-pass**。故须遍历所有加密列的所有行、只对真密文做 round-trip。
    无真密文 → no-op（无可验，不阻断）；真密文解密抛 → 上层校验失败（master key 丢失/不一致 → 迁移期早失败）。
    """
    from knot.core.crypto import decrypt, is_encrypted
    from knot.repositories.data_source_repo import _DS_ENCRYPTED_COLS

    c = sqlite3.connect(dst)
    try:
        if not c.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='data_sources'"
        ).fetchone():
            return
        cols = {r[1] for r in c.execute("PRAGMA table_info(data_sources)")}
        for col in (col for col in _DS_ENCRYPTED_COLS if col in cols):
            for (val,) in c.execute(
                f'SELECT "{col}" FROM data_sources WHERE "{col}" IS NOT NULL AND "{col}" != ""'
            ):
                if is_encrypted(val):
                    decrypt(val)   # 解密失败 → 抛（master key 不一致 / 密文损坏）
                    return
    finally:
        c.close()


def _verify_migrated_db(src: Path, dst: Path) -> None:
    """强 complete-marker（非 file-exists）：**非空** + 表集合一致 + 关键表行数一致 + decrypt 烟测。任一不过 raise。"""
    sc, sd = sqlite3.connect(src), sqlite3.connect(dst)
    try:
        def _tables(c):
            return {
                r[0] for r in c.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                )
            }
        ts, td = _tables(sc), _tables(sd)
        if not ts or not td:   # 空库不得判为迁移成功（防并发 empty-vs-empty 假过 → 服务空库）
            raise RuntimeError(f"迁移库无表 src={len(ts)} dst={len(td)}")
        if ts != td:
            raise RuntimeError(f"表集合不一致 src−dst={ts - td} dst−src={td - ts}")
        for t in _MIGRATION_KEY_TABLES:
            if t not in td:
                continue
            ns = sc.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
            nd = sd.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
            if ns != nd:
                raise RuntimeError(f"关键表 {t} 行数不符 src={ns} dst={nd}")
    finally:
        sc.close()
        sd.close()
    _decrypt_smoke(dst)


def _target_has_real_data(target: Path) -> bool:
    """target 是否已有**用户产生**的业务数据 → 安全阀：拒绝覆盖（疑似 C1-C3 在 C4 前上现网写入了新库）。

    检查 seed 后恒空、仅用户操作才增长的表（`_USER_CONTENT_TABLES`）+ users 超过 seed admin（1）。
    **排除** seed 即非空的表（semantic_layer / prompt_templates / few_shots）—— 否则全新 target 被误判。
    任一非空 → True。读不出（partial/corrupt 残留）→ False（视作待重迁残片，可覆盖）。
    """
    try:
        c = sqlite3.connect(target)
        try:
            for t in _USER_CONTENT_TABLES:
                try:
                    if c.execute(f'SELECT 1 FROM "{t}" LIMIT 1').fetchone():
                        return True
                except sqlite3.OperationalError:
                    continue   # 表不存在（早期库）→ 跳
            try:
                if c.execute("SELECT COUNT(*) FROM users").fetchone()[0] > 1:
                    return True
            except sqlite3.OperationalError:
                pass
            return False
        finally:
            c.close()
    except sqlite3.Error:
        return False


def _db_wellformed(path: Path) -> bool:
    """path 是否为完好非空 sqlite 库（有业务表 + integrity_check ok）。skip:migrated 前防服务空/损坏库。"""
    try:
        c = sqlite3.connect(path)
        try:
            tbls = c.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchone()[0]
            if tbls == 0:
                return False
            return c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        finally:
            c.close()
    except sqlite3.Error:
        return False


def _backup_uploads(data_dir: Path) -> None:
    """uploads.db 一并备份（§7 备份/回滚；**不迁** —— engine_cache._upload_engine import 期绑数据根，relocation=v0.9.1）。

    temp + os.replace 原子落地 → 防中途 crash 留半成品 .bak 而 existence-gate 永不重生。
    """
    up = data_dir / "uploads.db"
    up_bak = data_dir / "uploads.db.pre-tenancy.bak"
    if not up.exists() or up_bak.exists():
        return
    try:
        _backup_db_atomic(up, up_bak)
    except (sqlite3.Error, OSError, RuntimeError) as e:
        logger.warning(f"[C4] uploads.db 备份跳过（不阻断；uploads 不迁不改）: {e}")


def _migrate_locked(anchor: Path, target: Path) -> str:
    """持锁执行状态机（重读锚点/target 存在性 → 幂等 + crash-resume + 安全阀）。见模块 docstring 状态表。"""
    anchor_exists, target_exists = anchor.exists(), target.exists()
    bak = anchor.parent / (anchor.name + ".pre-tenancy.bak")

    if not anchor_exists:
        # 锚点已迁走（或全新）。target 存在 + 空/损坏 + 有 .bak → 疑似掉电致 target 未落盘 → 拒以空库起服务。
        if target_exists:
            if not _db_wellformed(target) and bak.exists():
                raise RuntimeError(
                    f"[C4] 锚点已迁走但 target {target} 空/损坏、且存在 {bak.name} —— "
                    "疑似掉电致 target 未落盘。拒绝以空库起服务，请从 .pre-tenancy.bak 人工恢复。"
                )
            return "skip:migrated"
        return "skip:fresh"

    # 锚点存在 = 存量待迁。marker = 本迁移「进行中」标记（崩后重入的凭据；完成时清除）。
    marker = target.parent / ".c4-migrating"
    resuming = target_exists or marker.exists()

    # 安全阀：target 有用户产生数据 + 锚点仍在 + **无 in-progress 标记** → 非本迁移写的 → 疑似违反铁律先上现网。
    # （有标记 = 本迁移崩在 copy 后 finalize 前 → 合法 resume，不触发本阀，走覆盖重迁。）
    if target_exists and not marker.exists() and _target_has_real_data(target):
        raise RuntimeError(
            f"[C4] target {target} 已有用户业务数据但锚点 {anchor} 仍在、且无迁移进行中标记 —— "
            "疑似 C1-C3 在 C4 前上了现网（违反守护者铁律「C4 必先于 rollout」）。拒绝覆盖，人工核对后手动处置。"
        )

    target.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("in-progress", encoding="utf-8")   # 置标记 → 此后崩溃重入按 resume 处理

    # 清残 target（+ 其 -wal/-shm）后重 backup，保干净快照
    for p in (target, target.with_name(target.name + "-wal"), target.with_name(target.name + "-shm")):
        if p.exists():
            p.unlink()
    _backup_db(anchor, target)                            # WAL-safe 一致快照 + fsync

    _backup_uploads(anchor.parent)

    # 强校验（不过 → 删 target 保锚点 last-good，raise 中止启动；标记保留 → 下次仍按 resume 重试）
    try:
        _verify_migrated_db(anchor, target)
    except Exception as e:
        target.unlink(missing_ok=True)
        raise RuntimeError(f"[C4] 迁移校验失败，已删 target 保锚点 last-good（不丢数据）: {e}") from e

    # 校验过 → 生成完整 .bak（WAL-safe 原子快照，绝不覆盖既有 .bak）→ 删锚点及 sidecars（锚点消失 = 完成信号）→ 清标记
    if not bak.exists():
        _backup_db_atomic(anchor, bak)
    for p in (anchor, anchor.with_name(anchor.name + "-wal"), anchor.with_name(anchor.name + "-shm")):
        if p.exists():
            p.unlink()
    marker.unlink(missing_ok=True)
    result = "resumed" if resuming else "migrated"
    logger.info(f"[C4] 存量迁移完成（{result}）：{anchor} → {target}；旧库备份 {bak}")
    return result


def migrate_anchor_db_to_tenant_once() -> str:
    """C4 存量迁移入口（幂等 · 抗 crash 续跑 · 跨进程串行）。返回状态串供启动日志。

    状态机（见 `_migrate_locked`）：
      db_dir='.'（target==锚点，测试）              → skip:same-path
      锚点无 + target 无                             → skip:fresh
      锚点无 + target 有(完好)                       → skip:migrated
      锚点无 + target 有(空/损坏) + 有 .bak          → raise（掉电未落盘 → 拒服务空库，人工恢复）
      锚点有 + target 无                             → migrated（首迁）
      锚点有 + target 有(残片/空 或 有标记)          → resumed（本迁移残留 → 覆盖重迁）
      锚点有 + target 有(用户数据 且 无标记)         → raise（疑似违反铁律先上现网 → 拒覆盖）
    """
    t1 = tenant_repo.resolve_single_tenant()
    anchor = Path(tenant_repo.SQLITE_DB_PATH)
    target = anchor.parent / t1["db_dir"] / "knot.db"

    if target.resolve() == anchor.resolve():
        return "skip:same-path"                          # db_dir='.'（测试 / 无需迁）

    # 跨进程独占锁（数据根 .c4-migration.lock）：串行化同节点多 worker/副本启动的一次性迁移。
    # 落后进程拿锁后由 `_migrate_locked` 重读状态 → 见锚点已迁走 → 走 skip 分支。
    # 跨节点 RWX（NFS）flock 不保证 → DEPLOY「首次 v0.9 升级先以单副本/init-container 迁移，再扩容」。
    anchor.parent.mkdir(parents=True, exist_ok=True)
    lock_fd = os.open(anchor.parent / ".c4-migration.lock", os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        return _migrate_locked(anchor, target)
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)
