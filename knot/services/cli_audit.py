"""knot/services/cli_audit.py — 破坏性 CLI 的审计写口（**唯一一处**，`BL-v0915-3`）。

## 为什么存在（一次真实事件）
v0.9.15 那次 `reset_admin_password` 重置在系统里**查无此事**：审计表里有 5 次
`auth.login_fail`、有端点侧的 `user.password_reset`，唯独没有脚本那一次
⇒ 「口令什么时候被谁改的」事后**无从对账**，而当时恰好就需要对账。
⇒ **同一件事经端点做有痕、经 CLI 做无痕**，这处不对称就是本模块要消掉的东西。

## 三条设计（都不是风格选择）

### ① ⛔ 刻意**不**走 `audit_service.log`
那条路 ① 自开连接 ⇒ 与被记录的动作**两个事务**；② R-47 **fail-soft 吞异常**
⇒ 「口令改了、审计没写、还打印 ✓」原样保留 = **没修成**。
R-47 的原意是「请求路径业务不阻断」；CLI 没有这个需求，其正确行为恰恰相反 ——
**破坏性动作宁可做不了，也不要做了查不到。**

### ② 能同事务的就同事务，不能的就把话说清
- `record_password_reset(conn=…)`：与 `UPDATE users` **同连接、同事务、单次 commit**
  ⇒ 「做了但没记」/「记了但没做」**结构上不存在**（v0.9.8 platform_audit 那条承重设计的租户侧等价物）。
- `record_migration()`：**做不到同事务** —— `migrate()` 是**逐表 commit**，没有覆盖全程的事务；
  要有就得重构一个**凭据迁移**的事务边界，风险不该压在这一片。
  ⇒ 保证较弱但明确：**审计写失败不吞、异常上抛 ⇒ 脚本退 0 ⇒ 审计行一定存在。**

### ③ detail 里放什么、⛔ 不放什么
放：`via/script/tenant_id/tenant_slug` + 计数。
⛔ **不放**：口令、哈希片段、`backup_path`（它由 `SQLITE_DB_PATH` 派生 = **env 派生值**，
进审计即 #262 家族 —— v0.9.7 那条 egress 拒绝消息就是这么泄出部署方内网主机清单的）。
⇒ 故 `record_migration` 用**具名白名单** `_MIGRATION_STAT_KEYS` 而不是把 `stats` 整个塞进去。

### ④ dry-run 一律不写
规则放这里而不是各脚本里 —— 三处各写一遍就是三份会漂的判断。

⚠️ **诚实边界**：本模块只管**代码路径**。运维直接 `sqlite3 UPDATE` 仍无痕
（同 v0.9.8 的诚实边界）。也**不给** `scan_secrets_at_rest` 加审计 —— 它是只读 CLI。
"""
from __future__ import annotations

import sqlite3

from knot.repositories import audit_repo

#: `record_migration` 允许进 detail 的 stats 键（**白名单**）。
#: ⛔ 刻意排除 `backup_path`（env 派生的文件路径，#262 家族）与 `preflight_checked`（无追溯价值）。
_MIGRATION_STAT_KEYS = ("rows_scanned", "rows_updated", "fields_encrypted")


def _record(
    *,
    action: str,
    resource_type: str,
    resource_id: str | int,
    script: str,
    tenant: dict,
    detail: dict | None = None,
    conn: sqlite3.Connection | None = None,
) -> None:
    """写一行 CLI 审计。`conn` 给了就进调用方的事务（不 commit / 不 close）。

    `actor_*` 恒 `None`：CLI 由运维在库外执行，**没有租户内身份**——
    编一个 actor 比留空更糟（会把运维动作伪装成某个用户干的）。
    """
    audit_repo.insert(
        conn=conn,
        actor_id=None, actor_role=None, actor_name=None,
        action=action, resource_type=resource_type,
        resource_id=str(resource_id), success=1,
        detail_json={
            "via": "cli", "script": script,
            "tenant_id": tenant["id"], "tenant_slug": tenant.get("slug"),
            **(detail or {}),
        },
    )


def record_password_reset(conn: sqlite3.Connection, *, tenant: dict, user_id: int) -> None:
    """admin 口令重置（`reset_admin_password`）—— **与 UPDATE 同事务**（见模块 §②）。

    ⛔ 不接受任何口令/哈希参数：本函数**在结构上**不可能把凭据写进 detail。
    """
    _record(conn=conn, action="user.password_reset", resource_type="user",
            resource_id=user_id, script="reset_admin_password", tenant=tenant)


def record_migration(tenant: dict, stats: dict, *, dry_run: bool) -> None:
    """凭据列静态加密迁移（`migrate_encrypt_v045`）。dry-run 一律不写（模块 §④）。

    ⚠️ **非同事务**（模块 §②）；detail 走白名单 `_MIGRATION_STAT_KEYS`（模块 §③）。
    """
    if dry_run:
        return
    _record(action="crypto.migrate_encrypt", resource_type="crypto",
            resource_id=tenant["id"], script="migrate_encrypt_v045", tenant=tenant,
            detail={k: stats.get(k) for k in _MIGRATION_STAT_KEYS})
