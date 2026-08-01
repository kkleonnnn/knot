"""knot/scripts/migrate_encrypt_v045.py — 敏感列静态加密迁移（一次性 / 幂等 / 可重跑）。

执行：
    python3 -m knot.scripts.migrate_encrypt_v045 [--dry-run] [--tenant N | --all-tenants]

红线（v0.4.5 立）：
- R-36 幂等：见 enc_v1: 跳过；多次运行 DB content 不变
- R-41 独立 entrypoint：不进 startup hook（grep 守护测试）
- R-46 自动 bak：写第一个 UPDATE 之前生成 `<db>.v044-<ts>.bak`；timestamp 后缀避免覆盖
- R-46-Tx 每张表一个事务：表内中断回滚，跨表已成功保留

═══ v0.9.11 硬化 —— **执行顺序本身是承重的，别重排** ═══
  ① master key fail-fast ② schema 就绪校验 ③ **全量 decrypt preflight**
  ④ 建备份（WAL-safe / 0600）⑤ 逐表加密（每表一事务）⑥ **同连接**后置校验

四条不变量（各由 `tests/scripts/test_migrate_encrypt_v045.py::test_Sa1..Sa6` 守，
事故叙事与实测证据见 CHANGELOG v0.9.11 + `docs/plans/v0.9.10-secret-at-rest-guard.md`）：

- **a1 备份必须 WAL-safe**：租户库是 `journal_mode=WAL`（`base.py:46`）⇒ `shutil.copy2` 只拷主文件，
  未 checkpoint 的**已提交数据全丢**，而 `quick_check` 仍报 `ok` ⇒ 无法察觉。走 sqlite backup API。
- **a2 preflight 必须在 ③ 而不是 ④ 之后**：错 key 时若先建备份，那份备份就是**磁盘上一份新的
  明文凭据副本**。且缺 preflight ⇒ 旧密文被前缀跳过、新值用新 key 加密 ⇒ **双 key 混库，不可逆**。
- **a3 ⑥ 必须与 ⑤ 同一次运行、同一个连接**：「声称完成」与「核实完成」分开，正是 2026-05-09
  那次「建了备份、一个字节没写、返回成功」三个月无人察觉的根因。
- **a5 缺列只报错、不代跑 schema 迁移**：两个不可逆操作共用一份备份会让回滚路径失效
  （schema 成功 + 加密失败 ⇒ 恢复出一个 schema 比代码旧的库）。R-41 同精神。
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import time
from pathlib import Path

from knot.core.crypto import decrypt, encrypt, is_encrypted
from knot.core.crypto.fernet import assert_master_key_loaded
from knot.core.logging_setup import logger
from knot.repositories import base as _base_mod  # 按调用时读 SQLITE_DB_PATH（兼容测试 monkeypatch）

# 跨包引下划线名：本脚本已有先例（`_base_mod._tenant_db_path()`），`knot/scripts` 亦不在分层契约内。
# 刻意**不**改名为 public —— 那会牵动 tenancy_migration（承重）+ 3 调用点 + 1 处测 docstring。
from knot.repositories.tenancy_migration import _backup_db_atomic


def _derive_targets() -> list[tuple[str, str, list[str], str | None]]:
    """敏感落点从**三个既有真相源**派生（不造第 4 份清单）+ **确定性排序**。

    返回 (表, 主键列, 敏感列有序表, 可选 WHERE)。表顺序与列顺序都固定 ⇒
    失败注入点相同则失败位置相同 ⇒ **事故可复现**（R6 + 守护者强化：
    `settings_repo._SENSITIVE_KEYS` 实测是 `frozenset`，无序已坐实）。
    """
    from knot.repositories.data_source_repo import _DS_ENCRYPTED_COLS
    from knot.repositories.settings_repo import _SENSITIVE_KEYS
    from knot.repositories.user_repo import _USER_ENCRYPTED_COLS

    keys = sorted(_SENSITIVE_KEYS)
    in_list = ", ".join(f"'{k}'" for k in keys)
    return [
        ("users", "id", sorted(_USER_ENCRYPTED_COLS), None),
        ("data_sources", "id", sorted(_DS_ENCRYPTED_COLS), None),
        ("app_settings", "key", ["value"], f"key IN ({in_list})"),
    ]


# 兼容既有引用；**每次读都重新派生**，避免 import 期快照与真相源脱钩。
def __getattr__(name):  # PEP 562
    if name == "TARGETS":
        return _derive_targets()
    raise AttributeError(name)


def _assert_schema_ready(conn: sqlite3.Connection, targets) -> None:
    """a5：目标列必须都存在，否则**显式报错**（绝不静默跳过 —— 那会让「11/11 覆盖」变成谎言）。

    ⭐ 刻意**不**代跑 schema 迁移：两个不可逆操作共用一份备份会让回滚路径失效
    （schema 成功 + 加密失败 ⇒ 按备份恢复得到 schema 比代码旧的库 ⇒ 恢复本身产出坏状态）。
    """
    missing = []
    for table, _id, cols, _w in targets:
        have = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
        if not have:
            missing.append(f"{table}（表不存在）")
            continue
        missing += [f"{table}.{c}" for c in cols if c not in have]
    if missing:
        raise RuntimeError(
            "库的 schema 比代码旧，以下敏感落点不存在：" + "、".join(missing) + "\n"
            "  本脚本**不代跑 schema 迁移**（两个不可逆操作共用一份备份会让回滚路径失效）。\n"
            "  修：先用当前版本**启动一次应用**（启动期逐租户 init_db 会补齐 schema），再重跑本脚本。"
        )


def _iter_landing_values(conn: sqlite3.Connection, targets):
    """遍历全部敏感落点，yield (表, 主键值, 列名, 原始值)。空值跳过。"""
    for table, id_col, cols, where in targets:
        sql = f"SELECT {id_col}, {','.join(cols)} FROM {table}"
        if where:
            sql += f" WHERE {where}"
        for row in conn.execute(sql).fetchall():
            for c in cols:
                v = row[c]
                if v is None or v == "":
                    continue
                yield table, row[id_col], c, v


def _preflight_decrypt_all(conn: sqlite3.Connection, targets) -> int:
    """a2 —— **写任何东西之前**（含建备份之前）验证：当前 key 能解开**每一个**现存密文。

    任一失败 ⇒ raise ⇒ **零写入、零备份**。这封掉「双 key 混库」这条**不可逆**路径：
    否则错 key 下旧密文被前缀跳过、新明文用新 key 加密，脚本 exit 0，
    而**没有任何一把 key 能解全库**。

    ⚠️ 只探 `is_encrypted` 为真的值 —— legacy 明文本来就是本脚本要处理的对象，不是 key 错的证据。
    返回验过的密文个数（用于日志与「preflight 真的跑过」的可观测性）。
    """
    checked = 0
    for table, pk, col, v in _iter_landing_values(conn, targets):
        if not is_encrypted(v):
            continue
        try:
            decrypt(v)
        except Exception as e:
            raise RuntimeError(
                f"preflight 失败：当前 KNOT_MASTER_KEY 解不开已有密文 {table}.{col}（主键 {pk!r}）—— {type(e).__name__}。\n"
                "  ⛔ **零写入、零备份**（错 key 下建备份 = 磁盘上多一份明文凭据副本）。\n"
                "  这多半是 master key 被换过。**继续跑会造成双 key 混库，且不可逆**：\n"
                "  旧密文会被前缀跳过、新明文用新 key 加密 ⇒ 没有任何一把 key 能解全库。\n"
                "  请先确认 KNOT_MASTER_KEY 是否与该库当初加密时一致。"
            ) from e
        checked += 1
    return checked


def _make_backup(db_path: Path) -> Path:
    """R-46：timestamped bak 避免覆盖前次（守护者数据丢失教训）。

    a1：**WAL-safe** —— 走 `_backup_db_atomic`（sqlite backup API + 严格 fsync + 原子 replace），
    不是 `shutil.copy2`（后者只拷主文件，未 checkpoint 的已提交数据全丢，而 quick_check 仍报 ok）。
    a1' 权限收窄 `0600`：备份里是**未加密之前的明文凭据**，不该跟随源文件的宽权限。
    a1'' sidecar：`.backup()` 的目标连接关闭时会 checkpoint，正常不留 `-wal`/`-shm`；
         保险起见显式清理，避免旁文件被误当成「备份的一部分」而在恢复时漏拷。
    """
    ts = time.strftime("%Y%m%d-%H%M%S")
    bak = db_path.parent / f"{db_path.name}.v044-{ts}.bak"
    if bak.exists():
        bak = db_path.parent / f"{db_path.name}.v044-{ts}-{os.getpid()}.bak"
    _backup_db_atomic(db_path, bak)
    os.chmod(bak, 0o600)
    for side in (f"{bak.name}-wal", f"{bak.name}-shm"):
        Path(bak.parent / side).unlink(missing_ok=True)
    logger.info(f"[migrate] 已生成备份（WAL-safe, 0600） {bak}")
    return bak


def migrate(dry_run: bool = False, db_path: str | None = None) -> dict:
    """单租户迁移；返回 stats dict。

    a6 —— 统计口径改名（原 `scanned`/`encrypted`/`skipped` 行/字段混淆）：
      `rows_scanned` 扫过的行数 · `rows_updated` 至少改了一个字段的行数 ·
      `fields_encrypted` 真正加密的**字段**数 · `rows_unchanged` 一个字段都没动的行数 ·
      `preflight_checked` preflight 验过的现存密文数。
    dry-run 时 `rows_updated`/`fields_encrypted` = **would-** 语义，且 `backup_path is None`。

    执行顺序（**顺序本身是承重的**）：
      ① master key fail-fast ② schema 就绪校验 ③ **preflight 全量解密**
      ④ 建备份（WAL-safe/0600）⑤ 逐表加密（每表一事务）⑥ **同连接**后置校验
    """
    assert_master_key_loaded()

    path = Path(db_path) if db_path else _base_mod._tenant_db_path()
    targets = _derive_targets()
    stats = {"rows_scanned": 0, "rows_updated": 0, "fields_encrypted": 0,
             "rows_unchanged": 0, "preflight_checked": 0, "backup_path": None}

    # a3：**全程一个 connection** —— 加密与后置校验同源，杜绝「校验的是另一个库」（R5）。
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    try:
        _assert_schema_ready(conn, targets)
        stats["preflight_checked"] = _preflight_decrypt_all(conn, targets)

        if not dry_run:
            stats["backup_path"] = str(_make_backup(path))

        for table, id_col, cols, where in targets:
            sql = f"SELECT {id_col}, {','.join(cols)} FROM {table}"
            if where:
                sql += f" WHERE {where}"
            rows = conn.execute(sql).fetchall()
            # R-46-Tx 每表一个事务：表内中断 → 整表 ROLLBACK；其他表已 COMMIT 保持
            try:
                for row in rows:
                    stats["rows_scanned"] += 1
                    updates = {}
                    for c in cols:
                        v = row[c]
                        if v is None or v == "" or is_encrypted(v):
                            continue
                        updates[c] = encrypt(v)
                    if not updates:
                        stats["rows_unchanged"] += 1
                        continue
                    stats["rows_updated"] += 1
                    stats["fields_encrypted"] += len(updates)
                    if not dry_run:
                        set_clause = ",".join(f"{c}=?" for c in updates)
                        conn.execute(
                            f"UPDATE {table} SET {set_clause} WHERE {id_col}=?",
                            (*updates.values(), row[id_col]),
                        )
                if not dry_run:
                    conn.commit()
            except Exception:
                if not dry_run:
                    conn.rollback()
                raise

        if not dry_run:
            _verify_no_plaintext_left(conn, targets)
    finally:
        conn.close()

    mode = "[dry-run] " if dry_run else ""
    logger.info(f"[migrate]{mode} 完成: {stats}")
    return stats


def _verify_no_plaintext_left(conn: sqlite3.Connection, targets) -> None:
    """跑完**在同一次运行内**核实不变量已建立 —— 否则**不许声称成功**。

    ⭐ 这正是 2026-05-09 那次事故的根因：脚本「声称完成」与「核实完成」是**分开的**
    ⇒ 它建了备份、一个字节没写、返回成功，三个月无人察觉。
    a3：复用调用方的 `conn`（不另开、不依赖 ambient ctx）。
    """
    left = [f"{t}.{c}（主键 {pk!r}）" for t, pk, c, v in _iter_landing_values(conn, targets)
            if not is_encrypted(v)]
    if left:
        raise RuntimeError(
            "迁移跑完但仍有明文敏感值，**拒绝声称成功**：" + "、".join(left) + "\n"
            "  （备份已生成，可据其回滚；请排查后重跑）"
        )


def _main() -> int:
    ap = argparse.ArgumentParser(description="敏感列静态加密迁移（一次性 / 幂等）")
    ap.add_argument("--dry-run", action="store_true",
                    help="只统计 would-encrypt，0 副作用（不写 DB / 不建 bak）")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--tenant", type=int, default=None, help="租户 id（默认 = 单租户解析）")
    g.add_argument("--all-tenants", action="store_true",
                   help="遍历平台库全部租户（**含 suspended** —— 其库文件里的明文同样在磁盘上）")
    args = ap.parse_args()

    from knot.core import tenant_context as _tc
    from knot.repositories import tenant_repo as _tr

    if args.all_tenants:
        tenants = _tr.list_tenants()
    elif args.tenant:
        t = _tr.get_tenant(args.tenant)
        if not t:
            sys.stderr.write(f"\n\033[91m[迁移失败] 租户 {args.tenant} 不存在\033[0m\n")
            return 1
        tenants = [t]
    else:
        tenants = [_tr.resolve_single_tenant()]

    prefix = "[dry-run] " if args.dry_run else ""
    done: list[str] = []
    for t in tenants:
        label = f"tenant#{t['id']}({t.get('slug')})"
        tok = _tc.set_active_tenant(t)
        try:
            stats = migrate(dry_run=args.dry_run)
            print(f"{prefix}{label} 迁移完成: {stats}")
            done.append(label)
        except Exception as e:
            # a6' 部分迁移的错误语义：**明确说清哪些已完成、哪些没跑** —— 多租户下这是恢复的前提。
            #     （本租户既没进 done 也不算未处理：它是**失败的那个**，已在首行点名。）
            remaining = [f"tenant#{x['id']}" for x in tenants[len(done) + 1:]]
            sys.stderr.write(
                f"\n\033[91m[迁移失败] {label}: {e}\033[0m\n"
                f"\033[91m  已完成：{'、'.join(done) or '（无）'}\033[0m\n"
                f"\033[91m  未处理：{'、'.join(remaining) or '（无）'}\033[0m\n"
            )
            return 1
        finally:
            _tc.reset_active_tenant(tok)
    return 0


if __name__ == "__main__":
    sys.exit(_main())
