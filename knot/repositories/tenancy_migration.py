"""knot.repositories.tenancy_migration — v0.9.0 C4 存量迁移：pre-tenancy 单库 → tenant#1 库。

把旧单租户锚点 `SQLITE_DB_PATH`（data/knot.db）迁入 tenant#1 目录（data/tenants/1/knot.db）。

**铁律（守护者 Stage 4）：必先于现网 rollout** —— prod tenant#1 db_dir='tenants/1' ≠ 锚点，
裸 rollout = per-tenant init_db 起空库 + 旧数据在锚点孤儿。启动序 ❷.5（seed_default_tenant 后、
per-tenant init_db 前）调用；测试期由 KNOT_SKIP_STARTUP_MIGRATION gate 跳过（本模块由专测直调验证）。

设计（两轮对抗评审加固后 —— 执行者 4 视角 + 守护者 Stage 4 6-agent 数据安全对抗）：
- **COPY 非 move**（sqlite `.backup()`，WAL-safe，迁移期**只读**锚点）→ 强校验（非空 + 表集合 + 关键表行数
  + decrypt 烟测）→ 过才删锚点。校验不过 → 删 target 保锚点 last-good，raise 中止启动（fail-closed）。
  **锚点仅在 target 已验非空+fsync ✓ 且 `.pre-tenancy.bak` 已建 ✓（两副本俱在）之后才删。**
- **fsync 强制**（Stage 4 must#3）：删锚点前 target 文件 fsync 失败即 **ABORT**（非耐久卷 NFS/overlay/EIO
  → 不删锚点，fail-closed），不吞错续跑（否则掉电起空库）。
- **resume 保全**（Stage 4 must#2）：resume-unlink 既有 target 前先 backup → `.pre-resume[.N].bak`
  —— 回滚到 C1-C3 代码会在 target 上 serve 写入唯一数据、而 C4 的 `.c4-migrating` 标记 C1-C3 不清，
  重跑 C4 会旁路安全阀 unlink 之 → 保全使其可恢复（不再依赖「marker ⟹ target⊆锚点」这一被推翻的论证）。
- **安全阀广判据**（Stage 4 must#1）：`_target_has_real_data` 用 **denylist**（检查除 seed-baseline 外**所有**表
  + users>1 + totp 已 enroll）—— allowlist 会漏表（admin 登录一次即写 totp_recovery_codes/audit_log 而 users 仍=1）。
- **跨进程 flock**（.c4-migration.lock）串行化同节点多 worker/副本；跨节点 RWX 见 DEPLOY「先单副本迁移」。
- **`.c4-migrating` 标记**：标本迁移进行中，崩后重入按 resume 处理；完成信号 = **锚点消失**（非 marker）。
"""
from __future__ import annotations

import errno
import fcntl
import os
import sqlite3
from pathlib import Path

from knot.core.logging_setup import logger
from knot.repositories import tenant_repo

# 关键表行数校验点（点名核心业务/安全表；表不存在则跳 — 兼容早期缺表库）
_MIGRATION_KEY_TABLES = ("users", "audit_log", "data_sources", "conversations")

# fresh init_db + 启动 seed 后**恒非空**的表（经验实测基线，2026-07-22 grounded）：
# users(1 admin) / semantic_layer(1 空行) / prompt_templates(启动 seed 4) / catalogs(迁移 seed id=1) /
# app_settings(生产 TOTP-rollout/审计时间戳等系统标志)。安全阀须**排除**它们，否则全新 target 被误判有真数据 → 阻断合法迁移。
# 其余所有表在 fresh 恒空、仅用户操作才增长 → denylist 判据自动全覆盖（schema 加新用户表不漏，胜过 allowlist）。
_SEED_NONEMPTY_TABLES = frozenset({
    "users", "semantic_layer", "prompt_templates", "catalogs", "app_settings",
})

# 目录 fsync 不支持的良性 errno（部分 FS）；真耐久失败(EIO/ENOSPC/EROFS…)不在此列 → 传播中止迁移。
_FSYNC_DIR_BENIGN = frozenset(
    e for e in (getattr(errno, n, None) for n in ("EINVAL", "ENOTSUP", "EOPNOTSUPP", "ENOTTY", "EBADF"))
    if e is not None
)


def _fsync_file(p: Path) -> None:
    """**严格** fsync 文件（失败即 raise）—— 删锚点前的耐久屏障必须真落盘；非耐久卷(NFS/overlay/EIO)
    须 fail-closed 中止迁移（Stage 4 must#3），绝不吞错续跑（否则掉电在「锚点已删、target 未落盘」窗口 → 起空库）。"""
    fd = os.open(p, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _fsync_dir(p: Path) -> None:
    """fsync 目录使 rename/create/unlink 目录项持久。真耐久失败(EIO/ENOSPC)raise；部分 FS 不支持目录 fsync → 容忍。"""
    try:
        fd = os.open(p, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError as e:
        if e.errno in _FSYNC_DIR_BENIGN:
            logger.warning(f"[C4] 目录 fsync 不支持(容忍): {p}: {e}")
            return
        raise


def _backup_db(src: Path, dst: Path) -> None:
    """sqlite backup API 拷一致快照 —— **WAL-safe**（含未 checkpoint 的已提交数据）+ **严格 fsync dst** 与其目录。

    - src 不存在 → raise：防 `sqlite3.connect` 把被并发进程刚删的锚点**重建为空库**（并发数据丢失向量）。
    - fsync dst（严格，失败 raise）+ fsync 目录：保证 target 落盘才可删锚点 —— 掉电后不会锚点已删而 target 未落盘。
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
    _fsync_file(dst)
    _fsync_dir(dst.parent)


def _backup_db_atomic(src: Path, dst: Path) -> None:
    """原子备份：backup 到 dst.tmp → os.replace → dst（+ 目录 fsync 持久化 rename）。

    防中途 crash 留**半成品 dst** 而 existence-gate 永不重生（Stage 4 #5/#6：备份重生按有效性、替换后须持久 rename）。
    """
    tmp = dst.with_name(dst.name + ".tmp")
    try:
        _backup_db(src, tmp)
        os.replace(tmp, dst)     # 原子
        _fsync_dir(dst.parent)   # 持久化 rename 目录项
    finally:
        try:
            Path(tmp).unlink(missing_ok=True)
        except OSError:
            pass


def _next_free_bak(data_dir: Path, stem: str) -> Path:
    """返回首个不存在的 `<stem>.bak` / `<stem>.1.bak` / … —— 保全既有 target 时绝不覆盖前次保全。"""
    cand = data_dir / f"{stem}.bak"
    n = 1
    while cand.exists():
        cand = data_dir / f"{stem}.{n}.bak"
        n += 1
    return cand


def _decrypt_smoke(dst: Path) -> None:
    """迁移库解密烟测：找 1 条**真密文**（enc_v1:）凭据解密（fernet round-trip 证 master key 未变/密文完好）。

    **只探 `is_encrypted` 为真的值**（Stage 4 修）—— legacy 明文 / 空占位不触发 key 校验：fernet.decrypt 对非
    enc_v1 值 passthrough 原样返回、对空占位返 ""，均**不动 key** → 只取首个非空值会让**错 master key 在存量库
    上 false-pass**。故遍历所有加密列的所有行、只对真密文做 round-trip。
    无真密文 → no-op（无可验，不阻断）；真密文解密抛 → 上层校验失败（master key 丢失/不一致 → 迁移期早失败）。
    （note：仅扫 data_sources；users.totp_secret / app_settings enc 列未覆盖 = key-health canary 有限，但非数据丢失
     —— byte-copy 保密文原样，错 key = 可恢复运维故障。）
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
    """强 complete-marker（非 file-exists）：**非空** + 表集合一致 + 关键表行数一致 + decrypt 烟测。任一不过 raise。

    非空 guard 是真正承重的一环（防并发 empty-vs-empty 假过 → 服务空库）；表集/行数对 byte-copy 近乎恒真，
    作 defense-in-depth（并发被别的 caller 改写等边缘才触发）。
    """
    sc, sd = sqlite3.connect(src), sqlite3.connect(dst)
    try:
        def _tables(c):
            return {
                r[0] for r in c.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                )
            }
        ts, td = _tables(sc), _tables(sd)
        if not ts or not td:   # 空库不得判为迁移成功
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
    """target 是否已有**用户产生**的业务数据 → 安全阀：拒绝覆盖（疑似 C1-C3 在 C4 前上现网/回滚期写入了新库）。

    **denylist**（Stage 4 must#1）：检查除 `_SEED_NONEMPTY_TABLES` 外**所有**表任一非空 + users>1 + 任一 user 已 enroll TOTP。
    比 allowlist 稳健 —— schema 新增用户表自动纳入判据，不会「清单漏表」（admin 登录一次即写 totp_recovery_codes/
    audit_log 而 users 仍=1，allowlist 漏之 → 覆盖 = 丢 2FA/审计）。读不出（partial/corrupt 残留）→ False（可覆盖重迁）。
    """
    try:
        c = sqlite3.connect(target)
        try:
            all_tables = {
                r[0] for r in c.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                )
            }
            for t in sorted(all_tables - _SEED_NONEMPTY_TABLES):
                try:
                    if c.execute(f'SELECT 1 FROM "{t}" LIMIT 1').fetchone():
                        return True
                except sqlite3.OperationalError:
                    continue
            try:
                if c.execute("SELECT COUNT(*) FROM users").fetchone()[0] > 1:
                    return True
                if c.execute(
                    "SELECT 1 FROM users WHERE totp_secret IS NOT NULL AND totp_secret != '' LIMIT 1"
                ).fetchone():
                    return True
            except sqlite3.OperationalError:
                pass
            return False
        finally:
            c.close()
    except sqlite3.Error:
        return False


def _db_wellformed(path: Path) -> bool:
    """path 是否为完好非空 sqlite 库（有业务表 + quick_check ok）。skip:migrated 前防服务空/损坏库（Stage 4 #5）。

    用 quick_check（比 integrity_check 快，跳过索引×表交叉核）—— 抓结构损坏（含掉电 WAL-replay 损坏）足够，boot 期开销可控。
    """
    try:
        c = sqlite3.connect(path)
        try:
            tbls = c.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchone()[0]
            if tbls == 0:
                return False
            return c.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        finally:
            c.close()
    except sqlite3.Error:
        return False


def _clear_orphan_marker(target_dir: Path) -> None:
    """清孤儿 `.c4-migrating`（Stage 4 #4）—— 完成后残留的标记若不清，日后锚点被误恢复会旁路安全阀。"""
    m = target_dir / ".c4-migrating"
    if m.exists():
        try:
            m.unlink()
            logger.warning(f"[C4] 清除孤儿迁移标记: {m}")
        except OSError as e:
            logger.warning(f"[C4] 孤儿标记清除失败（不阻断）: {m}: {e}")


def _migrate_locked(anchor: Path, target: Path) -> str:
    """持锁执行状态机（重读锚点/target 存在性 → 幂等 + crash-resume + 安全阀）。见模块 / 入口 docstring 状态表。"""
    anchor_exists, target_exists = anchor.exists(), target.exists()
    bak = anchor.parent / (anchor.name + ".pre-tenancy.bak")

    if not anchor_exists:
        _clear_orphan_marker(target.parent)   # #4：完成后残留标记清理
        if target_exists:
            # #5：target 空/损坏一律 raise（不再仅在有 bak 时），绝不以空/损坏库起服务（fail-closed）
            if not _db_wellformed(target):
                raise RuntimeError(
                    f"[C4] 锚点已迁走但 target {target} 空/损坏 —— 拒绝以空/损坏库起服务。"
                    f"若存在 {bak.name} 请人工恢复；否则排查掉电/磁盘故障。"
                )
            return "skip:migrated"
        return "skip:fresh"

    # 锚点存在 = 存量待迁。marker = 本迁移「进行中」标记。
    marker = target.parent / ".c4-migrating"
    resuming = target_exists or marker.exists()

    # 安全阀：target 有用户产生数据 + 锚点仍在 + **无 in-progress 标记** → 非本迁移写的 → 疑似违反铁律先上现网。
    if target_exists and not marker.exists() and _target_has_real_data(target):
        raise RuntimeError(
            f"[C4] target {target} 已有用户业务数据但锚点 {anchor} 仍在、且无迁移进行中标记 —— "
            "疑似 C1-C3 在 C4 前上了现网（违反守护者铁律「C4 必先于 rollout」）。拒绝覆盖，人工核对后手动处置。"
        )

    target.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("in-progress", encoding="utf-8")   # 置标记 → 此后崩溃重入按 resume 处理

    # #2：resume 覆盖既有 target 前**先保全** → .pre-resume[.N].bak（防回滚期 C1-C3 在 target 写入的唯一数据丢失；
    # 不再依赖「marker ⟹ target⊆锚点」被推翻的论证）。仅当 target 含用户数据才保全（空/损坏残片无唯一数据可丢，直接清）。
    if target.exists() and _target_has_real_data(target):
        preserve = _next_free_bak(target.parent, "knot.db.pre-resume")
        _backup_db_atomic(target, preserve)
        logger.warning(f"[C4] resume 覆盖前已保全既有 target → {preserve}（防回滚期写入丢失）")
    for p in (target, target.with_name(target.name + "-wal"), target.with_name(target.name + "-shm")):
        if p.exists():
            p.unlink()
    _backup_db(anchor, target)                            # WAL-safe 一致快照 + 严格 fsync

    # v0.9.2：uploads.db relocation 已移出本函数 → 提到 migrate_anchor_db_to_tenant_once 外层无条件调
    # （MF1/R2：本函数走 skip:migrated 早返时也须迁 uploads，故不能挂在锚点-存在分支内）。

    # 强校验（不过 → 删 target 保锚点 last-good，raise 中止启动；标记保留 → 下次仍按 resume 重试）
    try:
        _verify_migrated_db(anchor, target)
    except Exception as e:
        target.unlink(missing_ok=True)
        raise RuntimeError(f"[C4] 迁移校验失败，已删 target 保锚点 last-good（不丢数据）: {e}") from e

    # 校验过 → 生成完整 .bak（WAL-safe 原子快照，绝不覆盖既有 bak）→ 删锚点及 sidecars（锚点消失 = 完成信号）→ 清标记
    if not bak.exists():
        _backup_db_atomic(anchor, bak)
    for p in (anchor, anchor.with_name(anchor.name + "-wal"), anchor.with_name(anchor.name + "-shm")):
        if p.exists():
            p.unlink()
    _fsync_dir(anchor.parent)   # #6：持久化锚点删除 + bak rename 目录项（非 ordered FS 掉电不丢 bak）
    marker.unlink(missing_ok=True)
    result = "resumed" if resuming else "migrated"
    logger.info(f"[C4] 存量迁移完成（{result}）：{anchor} → {target}；旧库备份 {bak}")
    return result


def migrate_anchor_db_to_tenant_once() -> str:
    """C4 存量迁移入口（幂等 · 抗 crash 续跑 · 跨进程串行）。返回状态串供启动日志。

    状态机（见 `_migrate_locked`）：
      db_dir='.'（target==锚点，测试）              → skip:same-path
      锚点无 + target 无                             → skip:fresh
      锚点无 + target 有(完好)                       → skip:migrated（顺清孤儿标记）
      锚点无 + target 有(空/损坏)                    → raise（拒服务空/损坏库；有 .bak 则人工恢复）
      锚点有 + target 无                             → migrated（首迁）
      锚点有 + target 有(残片/空 或 有标记)          → resumed（先保全既有 target→.pre-resume.bak 再覆盖重迁）
      锚点有 + target 有(用户数据 且 无标记)         → raise（疑似违反铁律先上现网 → 拒覆盖）
    """
    t1 = tenant_repo.resolve_single_tenant()
    anchor = Path(tenant_repo.SQLITE_DB_PATH)
    target = anchor.parent / t1["db_dir"] / "knot.db"

    # ⭐ Stage 4 对抗（critic 命中 · 4 lens 全漏）：db_dir 含容校验 —— **写侧（会 unlink 源）此前无校验**，
    # 而读侧 resolver 有（`upload_engine._tenant_uploads_path` + 其 escape 测）。db_dir='../evil' 会把 knot.db /
    # uploads.db 搬到数据根**外**并删源，随后读侧 resolver 拒绝服务它自己刚建的文件 = OOS-1v2 文件边界逃逸。
    # 放在此处（而非 `relocate_uploads_once` 内）是因为 C4 与 uploads 的 target 同源于本行 —— 一处守两条路径，
    # 不制造「uploads 有守卫、C4 没有」的新不对称。db_dir 当前仅 seed 写（0 个 API 写点）→ 本条为纵深防御；
    # 根治 = v0.9.5 provisioning 期 db_dir 格式约束 + UNIQUE（backlog 已登记）。
    _root = anchor.parent.resolve()
    _tdir = (_root / t1["db_dir"]).resolve()
    if _root != _tdir and _root not in _tdir.parents:
        raise RuntimeError(
            f"[C4] tenant#{t1['id']} db_dir 逃出数据根：{_tdir} 不在 {_root} 内"
            f"（db_dir={t1['db_dir']!r} 非法）—— 拒绝迁移，防把租户库写到边界外并删源。"
        )

    if target.resolve() == anchor.resolve():
        return "skip:same-path"                          # db_dir='.'（测试；uploads 亦 same-path 无需迁）

    # 跨进程独占锁（数据根 .c4-migration.lock）：串行化同节点多 worker/副本启动的一次性迁移。
    # 落后进程拿锁后由 `_migrate_locked` 重读状态 → 见锚点已迁走 → 走 skip 分支。
    # 跨节点 RWX（NFS）flock 不保证 → DEPLOY「首次 v0.9 升级先以单副本/init-container 迁移，再扩容」。
    # v0.9.2 lazy import 避 tenancy_migration ↔ uploads_relocation 循环（后者 top-level import 本模块 helper）。
    from knot.repositories import uploads_relocation
    anchor.parent.mkdir(parents=True, exist_ok=True)
    lock_fd = os.open(anchor.parent / ".c4-migration.lock", os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        knot_result = _migrate_locked(anchor, target)   # knot 迁移抛错 → propagate 中止（relocation 不跑）
        # ⭐ MF1/R2：uploads relocation 独立、knot 成功返回后**无条件**跑（skip:migrated/skip:fresh/migrated 皆跑）
        # —— 真实 v0.9.0→v0.9.2 升级 knot.db 已在 v0.9.0 迁走、knot_result=skip:migrated，uploads 仍须迁。
        uploads_result = uploads_relocation.relocate_uploads_once(anchor.parent, target.parent)
        logger.info(f"[uploads-reloc] tenant#{t1['id']} uploads: {uploads_result}")
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)
    return knot_result
