"""knot/scripts/scan_secrets_at_rest.py — **只读**巡检：库里还有没有明文敏感值。

执行：
    python3 -m knot.scripts.scan_secrets_at_rest [--tenant N | --all-tenants] [--verify-key]

**退出码**：0 = 干净 · 1 = 有发现 · 2 = 跑不起来（配置/库问题）。⇒ 可直接进运维巡检脚本。

═══ 为什么需要这条命令（它补的是一个**验收方法上的**缺口）═══
Codex R10 正确地禁止「在真实库里注入明文来验证扫描器好用」—— 那是往生产库写明文凭据。
但这样一来，「真实库报 0 明文」就**只剩一半验证**：能证明*当前没有*，**不能证明扫描器没坏**
（一个恒返空的扫描器给出同样的 0）。⇒ 三者合起来才闭合：
  ① 本命令在真实库上**只读**跑 ⇒ 可信的「现在有没有」；
  ② 扫描器自身的正对照在**临时库**里做（`tests/repositories/test_secret_at_rest.py`）；
  ③ 出事后运维有**一条可跑的命令**，而不是只能重启服务看日志。

═══ `--verify-key` = **完整判据**（默认关）═══
不带该参数 = **廉价判据**（无 `enc_v1:` 前缀 ⇒ 明文），与启动期扫描同口径。
带上则**额外**对每个密文做真解密，回答「当前 key 是不是这库的 key」——
**混 key 库里所有值都是「某把 key 的合法密文」，廉价判据看不出 key 错了。**
⚠️ 完整判据**刻意不进启动期**（成本随租户数线性；理由见 `repositories/secret_at_rest` 模块头）。
"""
from __future__ import annotations

import argparse
import sys

from knot.core.crypto import decrypt, is_encrypted
from knot.repositories import secret_at_rest


def _scan_one(tenant: dict, verify_key: bool) -> tuple[int, int, list[str]]:
    """返回 (明文数, 验过的密文数, 解不开的落点描述)。⛔ 描述里永不含值。"""
    from knot.repositories.base import get_conn

    conn = get_conn()
    try:
        findings = secret_at_rest.scan_plaintext_secrets(conn)
        undecryptable: list[str] = []
        checked = 0
        if verify_key:
            for spot in secret_at_rest.landing_spots():
                try:
                    sql = f"SELECT {spot.pk_col}, {spot.col} FROM {spot.table}"
                    params: tuple = ()
                    if spot.key_filter is not None:
                        sql += f" WHERE {spot.pk_col}=?"
                        params = (spot.key_filter,)
                    rows = conn.execute(sql, params).fetchall()
                except Exception:
                    continue
                for pk, value in rows:
                    if not is_encrypted(value):
                        continue
                    try:
                        decrypt(value)
                        checked += 1
                    except Exception:
                        undecryptable.append(f"{spot.table}.{spot.col}(pk={pk!r})")
    finally:
        conn.close()

    label = f"tenant#{tenant['id']}({tenant.get('slug')})"
    print(f"  {label}: 明文 {secret_at_rest.format_findings(findings)}"
          + (f" · 当前 key 解得开 {checked} 个密文" if verify_key else "")
          + (f" · ⛔ 解不开 {len(undecryptable)} 个：{'、'.join(undecryptable[:5])}"
             if undecryptable else ""))
    return len(findings), checked, undecryptable


def _main() -> int:
    ap = argparse.ArgumentParser(description="只读巡检：静态明文敏感值")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--tenant", type=int, default=None, help="租户 id（默认 = 单租户解析）")
    g.add_argument("--all-tenants", action="store_true", help="全部租户（含 suspended）")
    ap.add_argument("--verify-key", action="store_true",
                    help="额外用当前 key 试解每个密文（完整判据；成本随行数增长）")
    args = ap.parse_args()

    from knot.core import tenant_context as _tc
    from knot.repositories import tenant_repo as _tr

    try:
        if args.all_tenants:
            tenants = _tr.list_tenants()
        elif args.tenant:
            t = _tr.get_tenant(args.tenant)
            if not t:
                sys.stderr.write(f"租户 {args.tenant} 不存在\n")
                return 2
            tenants = [t]
        else:
            tenants = [_tr.resolve_single_tenant()]
    except Exception as e:
        sys.stderr.write(f"跑不起来（租户解析失败）：{e}\n")
        return 2

    print(f"扫描 {len(tenants)} 个租户库（⛔ 只读，不改任何数据）：")
    total_plain = 0
    total_bad_key = 0
    for t in tenants:
        tok = _tc.set_active_tenant(t)
        try:
            n_plain, _checked, bad = _scan_one(t, args.verify_key)
        except Exception as e:
            sys.stderr.write(f"  tenant#{t['id']}: 扫描失败 —— {type(e).__name__}: {e}\n")
            return 2
        finally:
            _tc.reset_active_tenant(tok)
        total_plain += n_plain
        total_bad_key += len(bad)

    if total_plain or total_bad_key:
        print(f"\n❌ 共 {total_plain} 处明文" + (f" + {total_bad_key} 处当前 key 解不开" if total_bad_key else ""))
        if total_plain:
            print("   修：python3 -m knot.scripts.migrate_encrypt_v045 [--all-tenants]")
        if total_bad_key:
            print("   ⛔ 解不开 = **KNOT_MASTER_KEY 与该库不匹配**。**先别跑迁移** ——"
                  " 那会造成双 key 混库且不可逆（迁移脚本自带 preflight 会拦，但请先查清 key）。")
        return 1
    print("\n✅ 0 处明文")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
