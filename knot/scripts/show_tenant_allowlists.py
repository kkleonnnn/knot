"""knot/scripts/show_tenant_allowlists.py — **只读**复核：每个租户的出网 allowlist 三态（v0.9.19 C0'''）。

用法（**只读，无任何写入**）：
    python3 -m knot.scripts.show_tenant_allowlists            # 全部租户
    python3 -m knot.scripts.show_tenant_allowlists --tenant 2 # 指定租户

═══ 为什么需要它（而不是让运维自己敲 sqlite3）═══

⛔ **`sqlite3` CLI 此前不在镜像里**（实测 `docker run --rm python:3.11-slim which sqlite3` → 无）
⇒ DEPLOY 里所有 `sqlite3 …` 指令**自 v0.9.7 写下之日起就跑不了**。
v0.9.19 已在 Dockerfile 装上它，但那只是让**既有文档不再撒谎** ——
本脚本解决的是另一半：**判读**。

⚠️ **三态里最容易看错的是 `NULL` 与 `''`，而它们语义相反**：
| 值 | 起源租户 | 其他租户 |
|---|---|---|
| `NULL`（未配置） | 回退 env（+ 启动 WARN） | **全部拒绝** |
| `''`（部署方明确的「禁」） | **全部拒绝**（不回退） | **全部拒绝** |
| 非空 | 就是该集合（永不与 env 或别家取并集） |

裸 `SELECT` 把两者都显示成空白；`quote()` 能分但要人**记得加**、且输出要人**逐字判读**。
⇒ 本脚本直接打印**语义**（`未配置` / `明确禁止` / `N 项`），不让判读这一步存在。

═══ 只读保证 ═══
全文**只有 SELECT**，无 `UPDATE`/`INSERT`/`DELETE`/`ALTER`
（由 `tests/scripts/test_show_tenant_allowlists.py` 的 AST 断言守 ——
它是「破坏性 CLI 必须有显式目标」那条规矩的另一面：**只读工具才可以没有目标**）。
"""
from __future__ import annotations

import argparse
import sys

#: 要复核的列 —— **从写口派生**，不硬编（与 `tests/test_allowlist_column_registration.py` 同源）。
#: ⇒ 第三份 allowlist 落地时，本脚本**自动**开始复核它，不需要有人记得回来加一行。


def _managed_columns() -> tuple[str, ...]:
    from knot.repositories import tenant_repo
    return tuple(f for f in tenant_repo._MUTABLE_TENANT_FIELDS if f.startswith("allowed_"))


def _describe(raw: str | None) -> str:
    """把一列的原始值翻成**语义**（这一步就是本脚本存在的理由）。"""
    if raw is None:
        return "未配置（NULL）→ 起源租户回退 env；其他租户全部拒绝"
    if raw.strip() == "":
        return "明确禁止（空串）→ 全部拒绝，且**不回退 env**"
    hosts = [h.strip() for h in raw.split(",") if h.strip()]
    return f"{len(hosts)} 项：{', '.join(hosts)}"


def _main() -> int:
    ap = argparse.ArgumentParser(description="只读复核：租户出网 allowlist 三态")
    ap.add_argument("--tenant", type=int, default=None,
                    help="只看这一个租户 id（默认：全部）")
    args = ap.parse_args()

    from knot.repositories import tenant_repo

    cols = _managed_columns()
    if not cols:
        print("⚠️ 写口里没有任何 allowlist 列 —— 要么写口被改坏了，要么本脚本的前缀约定过期了")
        return 2

    rows = tenant_repo.list_tenants()
    if args.tenant is not None:
        rows = [r for r in rows if r["id"] == args.tenant]
        if not rows:
            print(f"⛔ 没有 id={args.tenant} 的租户")
            return 2

    for r in rows:
        print(f"\n── 租户 #{r['id']}  slug={r['slug']!r}  status={r['status']}")
        for c in cols:
            # ⚠️ `.get()` 不得下标：将来新增的列可能还没进这一行（同 resolver 侧的 M2 理由）
            print(f"   {c:24} = {_describe(r.get(c))}")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(_main())
