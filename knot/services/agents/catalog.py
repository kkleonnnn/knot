"""catalog.py — 业务目录加载器（DB 优先 + file fallback + 热更；v0.9.3 起载体 per-tenant）

加载优先级（高 → 低，每键独立）：
  1) DB（admin 后台编辑）：`catalogs` 行（legacy 兜底 `app_settings` 4 键）
  2) `_local_catalog.py`（真实业务 .py，.gitignore，部署方放置）
  3) `_template_catalog.py`（仓库内通用模板）
其中 **file HTTP 虚拟表始终权威追加**（部署代码层配置 > admin DB 影子，见 `reload()` L79-82）。

**读法（v0.9.3）**：模块外一律 `import catalog as _cl` + `_cl.TABLES` 等 module-attr live 读 ——
现由 PEP 562 `__getattr__` 代理到**当前租户槽**（`catalog_state`），故 13 个 importer 写法不变即租户感知。
严禁 `from catalog import TABLES`（值绑快照 → reload 后陈旧；静态哨兵禁绝）。
**模块内**一律走 `catalog_state.get_state()` 显式访问器（裸名读编译成 `LOAD_GLOBAL`，永不触发代理）。
"""
from __future__ import annotations

import contextvars

from knot.services.agents import catalog_state
from knot.services.agents.catalog_loaders import (
    _infer_source_types_from_datasources,
    _load_from_db,
    _load_from_files,
    _merge_lexicons,
)

# v0.9.3：6 个原模块全局 → `catalog_state` 租户槽。这 6 名**必须不存在于本模块命名空间**，
# 否则下方代理永不触发（机制、实测与三道守护详见 `catalog_state` 模块 docstring + `assert_no_resurrected_globals`）。
# chore D4'：**载体注册表已移入 `catalog_state`（单一真相源）** —— 本模块是**消费方**，
# 不再持自己那份副本（反向落户会与 `catalog → catalog_state` 的 import 方向冲突）。


def __getattr__(name: str):
    """PEP 562 代理 —— 13 个 importer 的 `catalog.TABLES` 写法一行不改即租户感知（D2'）。仅供模块外读。"""
    slot_key = catalog_state._ATTR_TO_SLOT.get(name)
    if slot_key is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return catalog_state.get_state()[slot_key]

# ── v0.6.2.6 段 4 (A1 并发半): Connection Context 隔离 ──────────────────────────
# per-request active catalog 内容（请求作用域 ContextVar）；未 set → current_catalog() 回退模块全局
# （D1 / R-PB-A1-15 byte-equal — 非 query 路径 startup/admin/http_planner/conversations 脱敏不受影响）。
_active_catalog_ctx: contextvars.ContextVar = contextvars.ContextVar(
    "_active_catalog_ctx", default=None
)


def current_catalog() -> dict:
    """当前请求生效的 catalog 内容（ContextVar 优先 + **当前租户默认槽**回退）。

    query 链路（query_helper 入口捕获 per-user active catalog → set_active_catalog_ctx）→ 读 ContextVar；
    非 query 路径（admin reload / http_planner / conversations 脱敏）→ ContextVar 未 set →
    **v0.9.3 起回退到当前租户的默认 catalog 槽**（此前回退进程全局 = 跨租户默认供数通道）；
    无 **tenant** ctx 则 fail-closed raise。
    返回 {lexicon, tables, business_rules, relations, field_labels, catalog_id}（catalog_id 全局回退时 None）。
    """
    ctx = _active_catalog_ctx.get()
    if ctx is not None:
        return ctx
    # v0.9.3 D4'：回退目标从**进程全局**改为**当前租户的默认 catalog 槽** —— 跨租户面关闭。
    # 租户 ctx 本身仍 fail-closed（`get_state()` 内 `current_tenant()` 无 ctx 即 raise，不再静默供数）。
    # identity 保持：代理与本回退读同一槽的同一值对象 → `cur["tables"] is catalog.TABLES` 仍成立
    # （test_catalog_context.py:22-25 三条 `is` 断言）。
    state = catalog_state.get_state()
    return {
        "lexicon": state["lexicon"],
        "tables": state["tables"],
        "business_rules": state["business_rules"],
        "relations": state["relations"],
        "field_labels": state["field_labels"],
        "catalog_id": None,   # 租户默认槽无 per-user catalog_id（per-user 走 _parse_catalog_content）
    }


def set_active_catalog_ctx(catalog_content: dict) -> contextvars.Token:
    """query 入口设当前请求 active catalog 内容（请求作用域）；返回 Token。

    catalog_content 形态须与 current_catalog 一致：{lexicon, tables, business_rules, relations, catalog_id}
    （已解析 — lexicon dict / tables list / relations list）。
    生产靠 asyncio task 隔离（copy_context per-request）不显式 reset —— 中间件 reset 方案（R-PB-A1-22）
    已于 v0.6.2.6 撤回；返回的 Token 仅测试用（v0.7.47 死码清扫删公开 reset 包装）。
    """
    return _active_catalog_ctx.set(catalog_content)


def reload(strict: bool = False) -> str:
    """v0.5.44 — 重新加载 catalog；返回 source 标签。
    DB 4 键覆盖 file 默认（粒度：每键独立）；某键 DB 为空则继续走 file fallback。
    RELATIONS 现也走 DB 覆盖（admin UI v0.5.44 落地，根因解防 cartesian）。

    v0.6.1.4: HTTP 虚拟表（source_type=http）从 file merge 进 DB catalog。
    理由：HTTP 表是部署方代码层配置（OSS 模式），不应被 admin DB 编辑覆盖；
          SQL 表仍由 DB 主导（admin 后台编辑）。

    v0.6.2.1 ε2 fail-fast：
      - strict=False（默认 — 模块 import / startup 时）：source_type 推断异常 → log warning 不阻塞
      - strict=True（admin reload / pick_http_route 触发时）：推断异常 → MetadataError 上抛
      防 BI 全盘瘫痪：业务条件触发 fail-fast；startup 期降级为 warning。

    v0.9.3 D2'/D3'：**全程局部变量构造 → 末尾一次性原子发布到当前租户槽**（`catalog_state.publish`）。
      - **禁 `global`**：`global X; X = ...` 会把载体名复活进模块 `__dict__` → PEP 562 代理静默死亡、
        租户槽闲置、跨租户串供照旧且无异常（B-1 实测）。静态哨兵 + 末尾运行期断言双守。
      - 本函数是租户槽的**唯一 writer**，且输出**只落租户默认槽**（R-2 非对称：per-request active catalog
        走 `_active_catalog_ctx` 那个另一载体 —— 因 `_load_from_db` 硬编 `get_catalog(1)`，若按 active
        catalog_id 分槽会把 catalog#1 口径写进 (tid,N) 槽 = 租户内跨 catalog 污染）。
    """
    from knot.models.errors import MetadataError

    f_lex, f_tables, f_rules, f_relations, f_src = _load_from_files()
    # v0.6.2.5 兜底熔断（Stage 2 修订 3）：catalogs id=1 缺失 + app_settings 无法读 → 真空期。
    # 沿用 ε2 strict 模式：strict=True（admin/query）→ fail-fast 上抛；strict=False（startup）→ 降级。
    try:
        db_lex, db_tables, db_rules, db_relations, db_field_labels, db_found = _load_from_db()  # v0.7.27 6-tuple
    except MetadataError:
        if strict:
            raise
        # startup 期常见为 DB 表未就绪（init_db 前模块级 reload / 全新部署首启）— 一行降级提示，
        # 不打 traceback（避免吓到运维；干净首启）；strict=True（admin/query）仍 fail-fast 上抛全栈。
        import logging
        logging.getLogger("knot.catalog").warning(
            "catalog 双源暂不可达（DB 表未就绪/未配置）— startup 降级空覆盖，init_db / admin reload 后生效",
        )
        db_lex, db_tables, db_rules, db_relations, db_field_labels, db_found = {}, [], "", [], {}, False  # v0.7.27 6-tuple（R-SL-189.1 承重：+6th {} 防 db_field_labels NameError）

    # v0.6.1.4: TABLES — DB 主导 SQL 表，file 始终追加 HTTP 虚拟表
    base_tables = list(db_tables) if db_tables else list(f_tables)
    if db_tables:  # DB 主导 SQL 表；file HTTP 表始终【权威覆盖】同名 DB 条目（v0.7.29 b merge 权威）
        # HTTP 表 = 部署代码层配置（file _local/_template_catalog，L80-82 架构铁律）> admin 手灌 DB 影子。
        # 旧逻辑 `if full not in existing_names` 让手灌 DB 同名条目（常缺 source_type=http →
        #   is_http_table False → pick_http_route 漏 = problem 1 静默落 SQL bug 类）**遮蔽**权威 file http。
        # 修：先剔除 base_tables 中与 file http 同名的影子条目，再追加 file http（权威）。
        # no-collision 路径 byte-equal（DB SQL 表不与 file http 同名 → 过滤 0 剔除 + 追加同旧）。
        http_from_file = [
            t for t in (f_tables or [])
            if t.get("source_type") == "http"
        ]
        http_names = {f"{t.get('db')}.{t.get('table')}" for t in http_from_file}
        base_tables = [t for t in base_tables if f"{t.get('db')}.{t.get('table')}" not in http_names]
        base_tables.extend(http_from_file)

    # v0.6.2.1 R-PB-C1-1 + ε2：source_type 推断兜底 + fail-fast 熔断
    # strict=True（admin reload / pick_http_route 触发）→ MetadataError 上抛
    # strict=False（startup module import）→ log warning + 不阻塞（避免 BI 启动失败）
    # 仅在 DB 主导（admin UI 编辑场景）时启用 — file-only 模式跳过
    if db_tables and db_found:
        from knot.models.errors import MetadataError
        try:
            base_tables = _infer_source_types_from_datasources(base_tables)
        except MetadataError:
            if strict:
                raise  # 业务条件触发（admin/query）→ fail-fast 上抛
            import logging
            logging.getLogger("knot.catalog").warning(
                "catalog source_type 推断兜底失败（startup 期降级；admin reload 时重试）",
                exc_info=True,
            )
    tables = base_tables

    # v0.6.1.4: LEXICON — 智能合并（不简单覆盖）
    # 同一关键词在 file 和 DB 都存在时 → value list 合并（保留两边的表）
    # 由 pick_http_route entity-aware ranking 决定优先级
    lexicon = _merge_lexicons(f_lex, db_lex)

    business_rules = db_rules if db_rules.strip() else f_rules
    relations = db_relations if db_relations else f_relations  # v0.5.44 — DB 覆盖优先
    field_labels = db_field_labels  # v0.7.27 维度中文标签 — DB-only（file 载体不提供 → 无 file fallback；空 → merge no-op byte-equal）

    source = "db+file_http" if (db_found and any(t.get("source_type") == "http" for t in tables)) else ("db" if db_found else f_src)

    # ⭐ 原子发布：整槽一次性替换（GIL 下原子）→ 并发读者永不见半成品态
    catalog_state.publish(
        lexicon=lexicon, tables=tables, business_rules=business_rules,
        relations=relations, field_labels=field_labels, source=source,
    )
    # ⭐ B-1 第二道守护（静态哨兵之外的运行期断言）：本函数绝不能把载体名复活进模块命名空间。
    catalog_state.assert_no_resurrected_globals()
    return source


# v0.9.3 D6'：**删除 import 期无条件 `reload()`** —— 它原在无 tenant ctx 下跑，双源皆不可达 → 静默降级加载
# `_template_catalog` demo 表（实测 `_SOURCE='example'`）；per-tenant 后更会在 import 期 raise。
# 冷槽由 `catalog_state.get_state()` 的 lazy miss loader 兜（D5' 强制项）。


def get_defaults_from_files() -> dict:
    """⚠️ **v0.9.5 起生产零调用者**（原唯一调用点 = `/api/admin/catalog` 的 `defaults`，已删）。

    ⛔ **不得未过评审就重新接到 HTTP 响应** —— 它返**部署级** `_local_catalog` 全文、绕过 per-tenant 槽
    （详 `docs/plans/v0.9.5-auth-split-platform-tenant-admin.md` D4'）。本片不删它，已登记 backlog。
    """
    f_lex, f_tables, f_rules, f_relations, f_src = _load_from_files()
    return {
        "lexicon": f_lex,
        "tables": f_tables,
        "business_rules": f_rules,
        "relations": [list(r) for r in f_relations],  # tuple → list (JSON-friendly)
        "field_labels": {},   # v0.7.27 DB-only（file 载体无 → "恢复默认" = 清空 field_labels）
        "source": f_src,
    }


def get_table_full_names() -> list:
    """v0.9.3 §II：转显式载体访问器（原裸名读 `TABLES`）。`knot/` 内 0 生产调用者但
    `tests/services/test_knot_catalog.py:67` 是活调用者 → 不随死码删（`_template_catalog.py:106` 同名物不动）。"""
    return [f"{t['db']}.{t['table']}" for t in catalog_state.get_state()["tables"]]


# ── v0.4.1.1: RELATIONS 元数据访问 + 按需渲染 ─────────────────────────────────
def get_relations() -> list:
    """返当前 RELATIONS 全量。R-S3：老 catalog 无此常量时上面 _load_from_files
    已经 fallback 成 []，本函数永不 KeyError / AttributeError。

    v0.6.2.6 段 4 (A1 并发半) D2：经 current_catalog() 读 per-request active catalog 的 relations
    （ContextVar 优先 + 全局回退）→ get_relations_for_tables / _relations_for_schema 全链 per-catalog；
    非 query 路径 ContextVar 未 set → 回退全局 RELATIONS byte-equal（R-PB-A1-15）。"""
    return list(current_catalog()["relations"])


# ── v0.6.1.4: HTTP 虚拟表支持（OVERRIDE #3 — catalog-driven endpoint metadata）──
def is_http_table(table_full_name: str) -> bool:
    """检查 table_full_name 是否为 source_type=http 的虚拟表。

    Args:
        table_full_name: 格式 "db.table" (与 get_table_full_names 一致)

    Returns:
        True 是 HTTP 虚拟表，False 是 SQL 表或未注册
    """
    t = _find_table(table_full_name)   # 单次解析（§6-5 同理，勿写成两次 _find_table 调用）
    return t is not None and t.get("source_type", "db") == "http"


def _find_table(table_full_name: str) -> dict | None:
    """在**当前租户槽**里按 "db.table" 找表条目（v0.9.3：替代 5 处裸名读 `TABLES` 的公共实现）。

    注意读的是租户槽而**不是** `current_catalog()`：ctx 载体由 `_parse_catalog_content` 生成、
    **永不含 file HTTP 虚拟表**（`query_helper.py:26-27`）→ 若 HTTP helper 改走 ctx，
    query 路径内 `is_http_table()` 恒 False → `pick_http_route` 永返 None → **HTTP 查询静默落 SQL**
    （v0.7.29b bug 类复发）。故 HTTP 三件必须读经完整 reload 流水线（含 file merge）的租户槽。
    """
    if "." not in table_full_name:
        return None
    db, table = table_full_name.split(".", 1)
    for t in catalog_state.get_state()["tables"]:
        if t.get("db") == db and t.get("table") == table:
            return t
    return None


def get_http_spec(table_full_name: str) -> dict | None:
    """取 HTTP 虚拟表的 endpoint spec（喂给 knot.adapters.http.executor.execute）。

    Args:
        table_full_name: 格式 "db.table"

    Returns:
        dict (HTTPEndpointSpec 形态) 或 None（非 HTTP 表或未配 http_spec）

    v0.9.3 §6-5：**单次解析**载体。原实现先经 `is_http_table()` 扫一遍、再自己扫一遍 ——
    而两次扫之间夹着 `pick_http_route` 的每-query `reload()`，可能出现 `is_http_table=True`
    但取 spec 时命中新内容返 None → **静默落 SQL**。现取一次条目本地复用，消除该窗口。
    """
    t = _find_table(table_full_name)
    if t is None or t.get("source_type", "db") != "http":
        return None
    return t.get("http_spec")


def get_http_tables() -> list:
    """返所有 source_type=http 的表的全名 list。

    用途：query.py 路由层启动期可检查"含 HTTP 表 → 必须设 KNOT_HTTP_ALLOWED_HOSTS env"。
    """
    return [
        f"{t['db']}.{t['table']}" for t in catalog_state.get_state()["tables"]
        if t.get("source_type", "db") == "http"
    ]


def get_relations_for_tables(selected: list) -> str:
    """R-S4 按需渲染：仅返 selected 表涉及的关联，避免 prompt token 挤压。

    selected: 形如 ['demo_dwd.dwd_user_reg', 'demo_dwd.dwd_order'] 的全名 list
              （schema_filter 选完 12 表后传入）

    返回 markdown 字符串供 prompt 注入；当无匹配关联时返空字符串。
    格式：
        ## 表关系 RELATIONS（多表查询必须按此 ON 条件 JOIN）
        - `demo_dwd.dwd_order.user_id` = `demo_dwd.dwd_user_reg.user_id` — 订单与注册用户
    """
    rels = get_relations()
    if not rels or not selected:
        return ""
    sel = set(selected)
    matched = [r for r in rels if len(r) >= 5 and r[0] in sel and r[2] in sel]
    if not matched:
        return ""
    lines = ["## 表关系 RELATIONS（多表查询必须按此 ON 条件 JOIN）"]
    for left_t, left_c, right_t, right_c, sem in matched:
        lines.append(f"- `{left_t}.{left_c}` = `{right_t}.{right_c}` — {sem}")
    return "\n".join(lines)
