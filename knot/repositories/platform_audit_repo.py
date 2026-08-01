"""platform_audit_repo —— `platform.db` 的 `platform_audit` 表读写（v0.9.8 · R-T-GATE R7）。

## 为什么写侧在 `repositories` 而不是 `services`
`.importlinter` Contract 4 `repos-no-business` 明禁 `knot.repositories → knot.services`。
而本表的**唯一写入者**是 `tenant_repo`（同层）⇒ 写侧必须在 repositories。
既成先例正是这个形状：`audit_repo`（repositories）+ `audit_service`（services 编排）。

## 为什么读侧也在这里（不建 `platform_audit_service`）
`api/platform_admin.py` 的既有平台只读端点就是 **api → repositories 直连**
（`:48` import `tenant_repo`、`:155` 调 `list_tenants_public()`，**投影做在 SQL 层**、
response model 在 api）。照「读侧留 service」的处方做，那个 service 的全部内容会是
**一层直穿的 passthrough** —— 而本仓对「只为满足一张图而存在的东西」有明确的免疫记忆
（v0.9.5 E4「零消费者 = 死码」· chore 的「N 份清单」）。
`api → repositories` 在 `.importlinter` 的 `layers` 契约下合法（layers 只禁**下层 import 上层**，
跳过中间层的**顺向** import 不禁）—— 这也解释了 v0.9.5 为什么闸门全绿。

## ⭐⭐ `insert` 的两条承重约束（改本文件前必读）
1. **连接由调用方注入**（`conn` 是第一个位置参数）——
2. **本函数不 `commit()`**。

**为什么**：审计写入必须与**被记录的那个动作**在**同一个事务**里，单次 `commit()`。
⇒ 「审计写失败」**不再是一个独立事件** —— 它与「动作失败」是**同一件事**（一起回滚）。
⇒ **零新增失败模式**，且得到一个**比 fail-closed 更强的性质**：
   **不存在「动作发生了但没记」或「记了但没发生」。**

⛔ **反面教材（v0.9.8 草案 D5，已被守护者 §II 溶解）**：草案曾把「首启审计写失败该 raise 还是吞」
标为本片唯一影响可用性的决策并主张 raise。真实风险是：`replicas=1` 是 R10、**零强制**
⇒ 多副本 + 共享 PVC 首启并发写 `platform.db` ⇒ `database is locked` ⇒ **全副本 boot 崩循环**
⇒ 那等于把一个**未被强制的运维约束**变成**可用性单点**。
⇒ **教训（已入 CLAUDE.md v3.1-B 第 10 条）：当两个选项都需要你「定一条策略」时，
   往往说明那个失败模式本不该存在 —— 策略题是失败模式的影子。**
   而**指出它的是分层契约** ⇒ **契约冲突不是绕路的对象，它常常在告诉你结构错了。**

## ⚠️ append-only（D7-④ 哨兵强制）
本模块**只暴露** `insert` / `list_recent`。**严禁**新增 `UPDATE` / `DELETE` 路径 ——
审计是**只可追加的证据**，不是可编辑的记录。
（租户侧已有 `purge_audit_log.py` 这个合法 DELETE 先例，而平台审计的清理已登记 backlog
⇒ 那个脚本一定会来；有哨兵它就必须是一次**显式、被评审**的改动。）
"""
from __future__ import annotations

import json
import sqlite3

#: 只读端点的**显式列白名单**（禁 `SELECT *` —— 同 `tenant_repo._PUBLIC_COLS` 的理由：
#: 将来给表加列时，`SELECT *` 会**自动**把新列吐进 HTTP 响应）。
#: ⚠️ `detail_json` **在投影里**（v0.9.8 M3 裁定）——
#: 不返回它的话，事故现场读不到最有用的信息（「db_dir 从什么改成了什么」），端点会退化成死载荷。
#: ⇒ **连带后果**：D7-② 那条「凭据/env 值不得进 detail」的哨兵**由此成为本端点的承重守护**，
#:   不再只是卫生 —— 放松它的人必须知道端点也随之破防。
_PUBLIC_COLS = (
    "id", "ts", "actor", "action", "tenant_id", "tenant_slug", "success", "detail_json", "source",
)


def insert(
    conn: sqlite3.Connection,
    *,
    action: str,
    tenant_id: int | None = None,
    tenant_slug: str | None = None,
    actor: str | None = None,
    success: bool = True,
    detail: dict | None = None,
    source: str | None = None,
) -> int:
    """写一条平台审计并返回 `lastrowid`。

    ⚠️ **连接由调用方注入，且本函数不 `commit()`** —— 见模块 docstring「两条承重约束」。
    调用方必须在**同一个事务**里完成「被记录的动作 + 本次 insert」，然后**单次 commit**。

    Args:
        action: `models.platform_audit.PlatformAuditAction` 的成员（前缀守护断精确集合）。
        detail: 变更详情。⛔ **严禁写入凭据 / env 值 / allowlist 内容**（D7-② 哨兵 +
            该端点会返回本字段）。记「哪个字段变了 / 从什么到什么」即可，值本身若敏感就只记「已变更」。
        actor: `'system:boot'` / `'cli:<显式传入>'` / `None`。
            ⛔ **严禁**用容器 `whoami` 充当 actor —— `kubectl exec` 下它 = root/app user
            ⇒ 把「谁」记成 root ⇒ 本表的价值命题（「谁改了 db_dir」）当场落空。
    """
    cur = conn.execute(
        "INSERT INTO platform_audit "
        "(actor, action, tenant_id, tenant_slug, success, detail_json, source) "
        "VALUES (?,?,?,?,?,?,?)",
        (actor, action, tenant_id, tenant_slug, 1 if success else 0,
         json.dumps(detail or {}, ensure_ascii=False), source),
    )
    return cur.lastrowid


def list_recent(conn: sqlite3.Connection, *, limit: int = 50, before_id: int | None = None) -> list[dict]:
    """按 id 倒序读平台审计（**显式投影**，禁 `SELECT *`）。

    `before_id` = 游标分页（取 id 严格小于它的那些）⇒ 禁无界返回。
    ⚠️ 连接同样由调用方注入 —— 与 `insert` 一致，避免本模块自己持有连接生命周期。
    """
    sql = f"SELECT {', '.join(_PUBLIC_COLS)} FROM platform_audit"  # noqa: S608 — 列名来自本模块常量
    params: list = []
    if before_id is not None:
        sql += " WHERE id < ?"
        params.append(before_id)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(max(1, limit))
    return [dict(r) for r in conn.execute(sql, params).fetchall()]
