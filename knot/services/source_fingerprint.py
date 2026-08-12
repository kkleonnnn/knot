"""knot.services.source_fingerprint — 数据源连接参数指纹（v0.9.23 R10'-A）。

## 它解决什么
`engine_cache` 的缓存键此前只含 `host:port:user`（或 site 3 干脆一个 `source_id`）
⇒ 改 `db_password` / `db_database` 后**键不变** ⇒ 命中旧 engine
⇒ **多副本下，改过数据源的那个副本立刻生效，其余副本最多用旧凭据 1 小时**（`_TTL_SEC`）。

**修法不是「改的时候记得去失效」**（`invalidate_*` 只对本副本生效），
而是**让键包含真正被用来建连接的那些值** ⇒ 值变了键必然变 ⇒ **陈旧在结构上不可能**。
（本仓的修法优先级：让两者结构上不可能不同，优于在门里过滤某个 payload。）

⚠️ **为什么不用 `data_sources.updated_at`**：**那一列不存在**（`schema.sql` 只有 `created_at`）。
加列 = 加一条「每个写路径都要记得维护」的约束 = 本仓反复被烧的那种漂移源。

## ⭐ 三条承重设计（都来自 Stage 2/3 评审，各有实证）

1. **指纹覆盖「一组」的全部源行，不是 `primary` 单行**（lens A-P1-4 与 lens B-O6 独立同结论）：
   `engine_cache` 用 `primary=gsources[0]` 的凭据建连接，但 `databases` 由**组内全部源**合并
   ⇒ 组内增删一个 secondary、或 flip 它的 `is_active`，**`host:port:user` 不变**
   ⇒ 只对 primary 取指纹的话，**修完仍然陈旧**。
2. **HMAC(进程随机 salt)，不是裸 `sha256`**（lens A-P1-3）：`get_datasource` 返回的是**已解密的明文口令**
   ⇒ `sha256(明文口令)` 是一个**可离线爆破的无盐快哈希**，一旦随键进日志/内存转储即等价于泄露候选。
   缓存本来就只在进程内 ⇒ 用进程 salt **不损任何语义**（跨进程不需要可比）。
3. **规范序列化，不是 `a|b` 拼接**（同上）：`password="x|db1", database="y"` 与
   `password="x", database="db1|y"` 在拼接下**同指纹**。用 `json.dumps(sort_keys=True)` 消除边界歧义。

⚠️ **指纹只进缓存键，不得进日志 / 异常 / 响应**（#262 同族）。
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets

#: 进程随机 salt —— 见模块 docstring 第 2 条。**刻意不可配置、不落盘**：
#: 它的唯一作用是让指纹不是「明文口令的字典可查摘要」，而缓存的作用域本就是单进程。
_PROC_SALT: bytes = secrets.token_bytes(32)

#: 参与指纹的字段 —— **必须是「真正被用来建连接 / 决定查询范围」的那些**。
#: ⚠️ 刻意**不含** `name` / `description` / `created_at`：改个备注不该让所有副本重建连接池
#: （lens B-O11 点出的无谓 churn）。
#: ⚠️ 含 `is_active` 是**防御性**的，不是承重的：`engine_cache` 在分组**之前**就已按 `is_active`
#:    过滤（实施期实测）⇒ inactive 行**到不了指纹**；flip 它的效果是**组成员集合变了**，
#:    由「组内全部行的排序摘要」这个形状表达。留它是为了「将来若有 caller 传未过滤的行也正确」。
_FIELDS = ("id", "db_type", "db_host", "db_port", "db_user", "db_password", "db_database", "is_active")


def group_fingerprint(sources: list[dict]) -> str:
    """一组数据源行的连接指纹（16 hex 字符）。

    `sources` = `engine_cache` 里 `groups[gkey]` 那个列表（同一 `host:port:user` 组的全部行）。
    **顺序无关**（内部按 `id` 排序）—— 否则 `get_user_source_ids` 的返回顺序一变就白重建。

    ⚠️ 缺字段按 `None` 处理而**不是**跳过：跳过会让 `{a:1}` 与 `{a:1,b:None}` 同指纹。
    """
    canon = json.dumps(
        [[_norm(s.get(f)) for f in _FIELDS] for s in sorted(sources, key=lambda s: s.get("id") or 0)],
        sort_keys=True, ensure_ascii=False, separators=(",", ":"),
    )
    return hmac.new(_PROC_SALT, canon.encode("utf-8"), hashlib.sha256).hexdigest()[:16]


def row_fingerprint(src: dict) -> str:
    """单行版本（site 3 `get_engine_for_source` 用 —— 它按 `source_id` 取单条）。"""
    return group_fingerprint([src])


def legacy_user_fingerprint(user: dict) -> str:
    """`users` 表上遗留 `doris_*` 字段的指纹（site 2）。

    ⚠️ 该路径**不读 `data_sources`**（凭据直接在 `users` 行上）⇒ 字段名不同，单独映射。
    """
    return group_fingerprint([{
        "id": user.get("id"),
        "db_type": "doris",
        "db_host": user.get("doris_host"),
        "db_port": user.get("doris_port"),
        "db_user": user.get("doris_user"),
        "db_password": user.get("doris_password"),
        "db_database": user.get("doris_database"),
        "is_active": 1,
    }])


def _norm(v):
    """把值归一到「等价即相同」的形态。

    ⚠️ `db_port` 在 DB 里是 INTEGER 而 API 传进来可能是字符串 ⇒ `9030` 与 `"9030"`
    **必须同指纹**，否则同一份配置在两条路径上算出不同指纹 = 无谓重建（且难查）。
    """
    if v is None:
        return None
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, int | float):
        return str(v)
    return str(v)
