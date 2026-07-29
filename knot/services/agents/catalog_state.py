"""knot.services.agents.catalog_state — v0.9.3 catalog 载体（per-tenant · **tid 单键单默认槽**）。

## 为什么单独一个文件
`catalog.py` 已 270/300（R-94 行数闸门），本片必加行 → 载体 + 访问器落此（D10'）。

## ⭐ 为什么 tid 单键、**不带 catalog_id 维**（B-2 承重，Stage 1 曾写错）
`catalog_loaders._load_from_db` **硬编 `get_catalog(1)`**（`catalog_loaders.py:68`，函数无参）⇒ reload 的 DB 源
**恒为 catalog#1**；而 `pick_http_route` **每 query 无条件 reload**（`http_planner.py:130`，调用点在 SSE
generator 内 `query.py:290-292`），此时 `catalog._active_catalog_ctx` 已被 `capture_active_catalog` 设成该用户的
active catalog **N**（`query.py:234`）。
→ 若按 catalog_id 分槽：**active catalog=7 的用户每发一次 query，就把 catalog#1 的口径写进 (tid,7) 槽**
= 租户内跨 catalog 口径污染，每 query 重复发生**且绿测**。

## ⭐ R-2 载体非对称（承重，不是可清理的重复）
- 本模块的槽 = **租户默认 catalog 内容**，唯一 writer = `catalog.reload()`。
- per-request **active** catalog = `catalog._active_catalog_ctx`（**另一个**载体，由 `query_helper` 设）。
**严禁**把两者「统一」，也严禁让 reload 写 active catalog 槽。

## ⭐ 槽 producer 必须是**完整 reload 流水线**（R-3' / D3'）
即 DB `catalog#1` **⊕ file 层 merge/fallback ⊕ source_type 推断**。
**严禁**用 `query_helper._parse_catalog_content` 造槽 —— 它是 **DB-only**（`query_helper.py:26-27` 明写
「file HTTP 虚拟表 merge 保持全局」）→ 会丢 file 层：`business_rules` 从 file 规则变 ""、`schema_filter` 丢
file lexicon、**最重的是 `http_planner` 丢 file HTTP 虚拟表 → `pick_http_route` 恒返 None → HTTP 查询静默落
SQL**（= `catalog.py:110-115` 记录的 v0.7.29b bug 类复发）。

## fail-closed
`tenant_cache_key()` 内部走 `current_tenant()` ⇒ **无 tenant ctx → raise `TenantContextError`**（不回退全局）。
这是刻意的：v0.9.3 前「无 ctx → 进程全局」正是跨租户默认供数通道。
"""
from __future__ import annotations

import threading
import time

from knot.core.logging_setup import logger
from knot.core.tenant_context import tenant_cache_key

#: ⭐ **载体注册表 —— 单一真相源**（chore D4'）：`catalog` 模块对外暴露的名字 → 本模块槽键。
#:
#: **为何落户在 `catalog_state` 而不是 `catalog`**：`catalog.py` import 本模块 ⇒ 反向 import 会循环。
#: 载体的**所有者**是槽，注册表跟着所有者走；`catalog.__getattr__` 是**消费方**。
#:
#: v0.9.3 之前这 6 个名字被抄在 **4 个地方**（本模块 `CARRIER_NAMES` + `catalog._ATTR_TO_SLOT`
#: + 两处测清单），改一漏一不会红 —— MUTANT-E 实证：加第 7 名 + `reload()` 里 `global` 它
#: → **26 测全绿逃逸**，代理对该名静默死。现全部从本注册表派生。
#: ⚠️ 但**派生只消除「抄写漂移」**：任何**没进本注册表**的新载体对所有派生 oracle 都不可见
#: （= 「登记漂移」）。完备性由 `tests/test_catalog_carrier_registry.py` 的**结构守护**承担
#: （禁 `catalog.py` 内任何 `global`），不由派生承担。
_ATTR_TO_SLOT = {
    "LEXICON": "lexicon", "TABLES": "tables", "BUSINESS_RULES": "business_rules",
    "RELATIONS": "relations", "FIELD_LABELS": "field_labels", "_SOURCE": "source",
}


def carrier_names() -> tuple:
    """载体名（**每次调用现算** —— 刻意做成函数而非常量）。

    ⚠️ **不要改成 `CARRIER_NAMES = tuple(_ATTR_TO_SLOT)`**：那会在 **import 期冻结**
    （实测：运行期往注册表注入第 7 名后，eager tuple 仍只有 6 个）⇒ 依赖它的
    MUTANT-E 回归测**按设计不可能通过**，而它会静默地绿。
    ⚠️ 也不要改成 `CARRIER_NAMES = _ATTR_TO_SLOT.keys()`：活视图能解决冻结，但
    **把活视图挂在常量样的名字下是陷阱** —— 读者当它是 tuple，下一个人「顺手改回 `tuple(...)`」
    就静默重新废掉那条回归测。**函数名把动态性写在每个调用点上**，这是刻意的。
    """
    return tuple(_ATTR_TO_SLOT)

#: {tenant_cache_key("catalog"): {6 slot 键}} —— 进程内，按租户分槽
_state: dict = {}
#: lazy miss load 与发布共用；**RLock**（reentrant）—— get_state 持锁调 reload，reload 内再调 publish。
#: 注意职责边界：本锁只防**冷槽重复加载**；「读者永不见半成品」由 `publish()` 的**整槽替换**（GIL）提供，与锁无关。
_lock = threading.RLock()


def _key():
    """当前租户的槽键（fail-closed：无 tenant ctx → `tenant_cache_key` 内 `current_tenant()` raise）。"""
    return tenant_cache_key("catalog")


def publish(
    *, lexicon: dict, tables: list, business_rules: str, relations: list,
    field_labels: dict, source: str,
) -> dict:
    """**原子发布**当前租户的槽（`catalog.reload()` 是唯一调用方 · D2'/D3'）。

    整槽一次性替换（dict 赋值在 GIL 下原子）→ 读者永不看到半成品态（Codex R9 / Stage 4 看点 5）。
    keyword-only：防位置参数错位把 lexicon 灌进 tables 这类静默错。
    """
    slot = {
        "lexicon": lexicon, "tables": tables, "business_rules": business_rules,
        "relations": relations, "field_labels": field_labels, "source": source,
    }
    k = _key()
    with _lock:
        _state[k] = slot
    # F-3' 观测：**每次发布**记 DEBUG（`pick_http_route` 每 query 都 reload → INFO 会变日志噪音；
    # 冷槽那条才是 INFO）。同样只记规模与来源，严禁记内容。
    logger.debug(
        "[catalog] 槽发布 tenant={} source={} tables={} http_tables={} lexicon_keys={} relations={}",
        k[0], source, len(tables),
        sum(1 for t in tables if t.get("source_type") == "http"), len(lexicon), len(relations),
    )
    return slot


def get_state() -> dict:
    """当前租户的槽；**miss → lazy 完整 reload 流水线加载后发布**（D5' 强制项）。

    冷槽在「每租户第一次 query 的 clarifier」时**保证发生**（时序：clarifier `query.py:242` 早于
    reload `query.py:290`）—— 故 lazy loader 不是边角优化，是 F-1'「删 warm-up」的前提。
    双检 + RLock 只保证**并发首访不重复加载**（实测 4/24 线程各自 barrier 冷访 → reload 恰 1 次、无死锁）。
    「读者不见半成品」**不是**锁提供的 —— 是 `publish()` 整槽替换 + reload 内部构造完才发布提供的
    （对抗自核纠：删双检 / 锁换 no-op 后 26 测全绿 ⇒ 锁不承担正确性，仅省一次重复加载）。
    """
    k = _key()
    slot = _state.get(k)
    if slot is not None:
        return slot
    with _lock:
        slot = _state.get(k)          # 双检：可能在等锁期间已被别的线程填好
        if slot is not None:
            return slot
        # lazy import 破环（catalog 在模块级 import 本模块拿访问器）—— 沿用本仓 R-106 方案 1
        from knot.services.agents import catalog as _cat
        t0 = time.perf_counter()
        _cat.reload(strict=False)     # 唯一 writer，内部 publish 到本槽
        slot = _state[k]              # reload 必 publish；未 publish 属契约破坏，KeyError 即暴露
        # F-3' 观测：**冷槽加载**记 INFO（每租户进程内仅首次，信息量高）。只记规模与来源，
        # **严禁记 catalog 内容**（business_rules / lexicon 含业务口径 = 敏感）。
        logger.info(
            "[catalog] 冷槽加载 tenant={} source={} tables={} lexicon_keys={} relations={} ms={:.1f}",
            k[0], slot["source"], len(slot["tables"]), len(slot["lexicon"]),
            len(slot["relations"]), (time.perf_counter() - t0) * 1000,
        )
        return slot


def invalidate_all() -> None:
    """清所有租户槽（**测试 / conftest reset 用**；生产不调 —— 生产靠 reload 覆盖当前租户槽）。"""
    with _lock:
        _state.clear()


def assert_no_resurrected_globals() -> None:
    """⭐ B-1 运行期断言：`catalog` 模块命名空间内**不得**出现那 6 名（Stage 4 看点 1）。

    实测过的失效机制：PEP 562 模块 `__getattr__` **只在常规属性查找失败时**触发。一旦模块内
    `global TABLES; TABLES = ...` 把名字复活进 `__dict__`，代理就**静默死亡**（不报错）、租户槽闲置、
    跨租户串供照旧。**时序真相**：`reload()` 在启动期与每 query 都跑 ⇒ 一旦复活就永久落在静默支
    （NameError 那支只存在于首次 reload 之前，反而是幸运情况）→ 静态哨兵之外必须再有运行期断言。
    """
    from knot.services.agents import catalog as _cat
    resurrected = sorted(set(carrier_names()) & set(vars(_cat)))
    if resurrected:
        raise AssertionError(
            f"catalog 模块命名空间出现载体名 {resurrected} —— PEP 562 代理已被静默旁路"
            "（reload 须用局部变量构造 + publish，禁 `global`）；per-tenant 槽将闲置、跨租户串供复发。"
        )
