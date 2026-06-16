"""catalog_loader.py — 业务目录加载器（v0.2.5 DB 优先 + 热更）

加载优先级（高 → 低）：
  1) DB（admin 后台编辑）：app_settings 三键
       - catalog.tables          (JSON list[dict])
       - catalog.lexicon         (JSON dict[str, list[str]])
       - catalog.business_rules  (text)
     某项 DB 有值即用 DB；该项为空则继续 fallback。
  2) knot/services/agents/_local_catalog.py    — 真实业务 .py（.gitignore，部署方按需放置）
  3) knot/services/agents/_template_catalog.py — 仓库内通用模板

调用方应通过 `import catalog_loader as _cl` + `_cl.LEXICON` / `_cl.TABLES` / `_cl.BUSINESS_RULES`
动态读取（不要 `from catalog_loader import LEXICON` 一次性快照），admin 修改后调用
`catalog_loader.reload()` 即可在不重启进程的情况下生效。
"""
from __future__ import annotations  # Python 3.9 兼容 dict | None type hint

import contextvars
import importlib
import importlib.util
import json
import pathlib

LEXICON: dict = {}
TABLES: list = []
BUSINESS_RULES: str = ""
RELATIONS: list = []  # v0.4.1.1: 多表关联元数据，list[tuple(left_t, left_c, right_t, right_c, semantics)]
_SOURCE: str = "empty"  # "db" | "real" | "example" | "empty"

# ── v0.6.2.6 段 4 (A1 并发半): Connection Context 隔离 ──────────────────────────
# per-request active catalog 内容（请求作用域 ContextVar）；未 set → current_catalog() 回退模块全局
# （D1 / R-PB-A1-15 byte-equal — 非 query 路径 startup/admin/http_planner/conversations 脱敏不受影响）。
_active_catalog_ctx: contextvars.ContextVar = contextvars.ContextVar(
    "_active_catalog_ctx", default=None
)


def current_catalog() -> dict:
    """当前请求生效的 catalog 内容（ContextVar 优先 + 模块全局回退）。

    query 链路（query_helper 入口捕获 per-user active catalog → set_active_catalog_ctx）→ 读 ContextVar；
    非 query 路径（startup / admin reload / http_planner / conversations 脱敏）→ ContextVar 未 set →
    回退模块全局（D1 / R-PB-A1-15 — 与直读 LEXICON/TABLES/... 等价 byte-equal）。
    返回 {lexicon, tables, business_rules, relations, catalog_id}（catalog_id 全局回退时 None）。
    """
    ctx = _active_catalog_ctx.get()
    if ctx is not None:
        return ctx
    return {
        "lexicon": LEXICON,
        "tables": TABLES,
        "business_rules": BUSINESS_RULES,
        "relations": RELATIONS,
        "catalog_id": None,
    }


def set_active_catalog_ctx(catalog_content: dict) -> contextvars.Token:
    """query 入口设当前请求 active catalog 内容（请求作用域）；返回 Token 供出口 reset。

    catalog_content 形态须与 current_catalog 一致：{lexicon, tables, business_rules, relations, catalog_id}
    （已解析 — lexicon dict / tables list / relations list）。
    """
    return _active_catalog_ctx.set(catalog_content)


def reset_active_catalog_ctx(token: contextvars.Token) -> None:
    """请求出口 reset ContextVar（R-PB-A1-22 — 不泄漏到下一请求；与 set 的 Token 配对）。"""
    _active_catalog_ctx.reset(token)


def _load_from_files() -> tuple:
    """返回 (lexicon, tables, business_rules, relations, source_tag)；
    source_tag ∈ real/example/empty。
    v0.4.1.1 R-S3：老 catalog 文件无 RELATIONS 常量时 getattr 返 [] 不抛 AttributeError。"""
    try:
        # v0.6.1.4: 修旧 bug — top-level "_local_catalog" 永远 import 不到（不在 PYTHONPATH）
        # 用 full module path 才能命中 knot/services/agents/_local_catalog.py
        m = importlib.import_module("knot.services.agents._local_catalog")
        return (
            getattr(m, "LEXICON", {}) or {},
            getattr(m, "TABLES", []) or [],
            getattr(m, "BUSINESS_RULES", "") or "",
            list(getattr(m, "RELATIONS", []) or []),
            "real",
        )
    except Exception:
        pass
    try:
        p = pathlib.Path(__file__).parent / "_template_catalog.py"
        if p.exists():
            spec = importlib.util.spec_from_file_location("_template_catalog", p)
            m = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(m)
            return (
                getattr(m, "LEXICON", {}) or {},
                getattr(m, "TABLES", []) or [],
                getattr(m, "BUSINESS_RULES", "") or "",
                list(getattr(m, "RELATIONS", []) or []),
                "example",
            )
    except Exception:
        pass
    return {}, [], "", [], "empty"


def _load_from_db() -> tuple:
    """v0.6.2.5 段 4 — 改读 catalogs 表默认行（id=1）；app_settings 4-key 降级 legacy 兜底。

    源切换（资深 A 拍板 / R-PB-A1-8）：catalogs id=1（commit 1 seed 自 app_settings → byte-equal）
    为主源；catalog id=1 行缺失（迁移前 / 被清空）→ app_settings 4-key legacy 兜底。
    兜底熔断（Stage 2 修订 3 / ε2 fail-fast 精神）：catalogs id=1 缺失 + app_settings 也无法读
      （异常）→ 真空期 → raise MetadataError（strict 与否由 reload 决定 — 沿用既有 ε2 模式）。
    返回 (lexicon, tables, business_rules, relations, found_any)。
    relations 4 键全走 DB 覆盖（v0.5.44；之前 v0.4.x R-S3 仅 3 字段）。
    """
    raw_tables = raw_lex = rules = raw_rel = ""
    got = False
    try:
        from knot.repositories import catalog_repo
        cat = catalog_repo.get_catalog(1)
        if cat is not None:
            raw_tables = cat.get("tables") or ""
            raw_lex = cat.get("lexicon") or ""
            rules = cat.get("business_rules") or ""
            raw_rel = cat.get("relations") or ""
            got = True
    except Exception:
        pass  # catalogs 表访问失败 → 落 app_settings legacy 兜底
    if not got:
        try:
            from knot.repositories.settings_repo import get_app_setting
            raw_tables = get_app_setting("catalog.tables") or ""
            raw_lex = get_app_setting("catalog.lexicon") or ""
            rules = get_app_setting("catalog.business_rules") or ""
            raw_rel = get_app_setting("catalog.relations") or ""
        except Exception as e:
            from knot.models.errors import MetadataError
            raise MetadataError(
                "catalog 双源不可用（catalogs id=1 缺失 + app_settings legacy 无法读）— 真空期熔断",
            ) from e

    tables, lex, relations = [], {}, []
    if raw_tables.strip():
        try:
            t = json.loads(raw_tables)
            if isinstance(t, list):
                tables = t
        except Exception:
            pass
    if raw_lex.strip():
        try:
            parsed = json.loads(raw_lex)
            if isinstance(parsed, dict):
                lex = parsed
        except Exception:
            pass
    # v0.5.44 — relations JSON 解析（list of [left_t, left_c, right_t, right_c, semantics]）
    if raw_rel.strip():
        try:
            parsed_rel = json.loads(raw_rel)
            if isinstance(parsed_rel, list):
                # 兼容 tuple 长度 ≥4（semantics 可省略）；过滤无效条目
                relations = [tuple(r) for r in parsed_rel if isinstance(r, (list, tuple)) and len(r) >= 4]
        except Exception:
            pass

    found = bool(tables or lex or rules.strip() or relations)
    return lex, tables, rules, relations, found


def _infer_source_types_from_datasources(tables: list) -> list:
    """v0.6.2.1 R-PB-C1-1 + ε2 — fail-fast 熔断 + source_type 推断兜底。

    生产 bug 链路（e38de5e76703）：admin UI 01 表目录编辑器只支持
    {db, table, topics, summary} 4 字段，灌入 DB catalog.tables 时
    source_type 字段被吃掉 → is_http_table() fallback 默认 "db" →
    pick_http_route() 永返 None → 静默落 sql_planner。

    修复策略（ε2 fail-fast + 业务条件触发）：
      1. DataSource 表查询失败 → MetadataError 熔断
         （防 BI 全盘瘫痪 — 既有 doris/mysql 不被误推断为 http）
      2. DataSource 表查询成功但为空 → MetadataError 熔断（同上）
      3. DataSource 表正常非空 → 对 catalog tables 中 db_name 匹配
         db_type='http' DataSource 的表，强制 source_type='http'

    设计哲学协同：
      - 与 v0.4.5 R-37 master_key fail-fast 同精神
      - 与 v0.5.0 R-74 双 key 探针"业务条件触发"同精神
      - 内存态推断（passthrough mutation），不持久化回 DB
        admin UI 字段持久化由 F1.2/F1.3 独立路径解决
    """
    from knot.models.errors import MetadataError
    from knot.repositories import data_source_repo
    try:
        ds_list = data_source_repo.list_datasources()
    except Exception as e:
        raise MetadataError(
            f"DataSource 表查询失败 — catalog source_type 推断兜底中止 "
            f"(ε2 fail-fast — 防误推断既有 doris/mysql 为 http): {e}",
        ) from e

    if not ds_list:
        # DataSource 表为空 — 异常状态（任何有效部署应至少有 1 个数据源）
        # 不静默 fallback；不推断 — 防 BI 全盘瘫痪
        raise MetadataError(
            "DataSource 表为空 — catalog source_type 推断兜底中止 "
            "(ε2 fail-fast — 防误推断既有 doris/mysql 为 http)",
        )

    # 业务条件触发：db_type='http' 的 DataSource db_name 集合
    http_db_names = {
        ds.get("db_database", "").strip()
        for ds in ds_list
        if ds.get("db_type") == "http" and ds.get("db_database")
    }
    if not http_db_names:
        return tables  # 无 HTTP DataSource — 不推断

    # 推断：catalog 表 db 字段匹配 http_db_names + 未显式 source_type → 标 http
    inferred_count = 0
    for t in tables:
        if t.get("source_type"):
            continue  # 已显式（来自 _local_catalog.py 等）→ 不动
        if t.get("db") in http_db_names:
            t["source_type"] = "http"
            inferred_count += 1

    if inferred_count > 0:
        # 元数据 audit log（admin 可观察推断生效）
        import logging
        logging.getLogger("knot.catalog").info(
            f"catalog source_type 推断兜底：{inferred_count} 表标记为 http "
            f"(http DataSource db_names={sorted(http_db_names)})",
        )

    return tables


def _merge_lexicons(file_lex: dict, db_lex: dict) -> dict:
    """v0.6.1.4: 智能合并 file + DB lexicon。

    同一关键词存在两边时，合并 value list（保留两边表）；
    由 pick_http_route entity-aware 决定优先级。
    """
    if not file_lex and not db_lex:
        return {}
    if not file_lex:
        return dict(db_lex)
    if not db_lex:
        return dict(file_lex)
    merged: dict = dict(db_lex)
    for key, file_val in file_lex.items():
        if not isinstance(file_val, list):
            file_val = [file_val] if file_val else []
        existing = merged.get(key)
        if existing is None:
            merged[key] = list(file_val)
            continue
        if not isinstance(existing, list):
            existing = [existing] if existing else []
        for t in file_val:
            if t not in existing:
                existing.append(t)
        merged[key] = existing
    return merged


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
    """
    global LEXICON, TABLES, BUSINESS_RULES, RELATIONS, _SOURCE

    from knot.models.errors import MetadataError

    f_lex, f_tables, f_rules, f_relations, f_src = _load_from_files()
    # v0.6.2.5 兜底熔断（Stage 2 修订 3）：catalogs id=1 缺失 + app_settings 无法读 → 真空期。
    # 沿用 ε2 strict 模式：strict=True（admin/query）→ fail-fast 上抛；strict=False（startup）→ 降级。
    try:
        db_lex, db_tables, db_rules, db_relations, db_found = _load_from_db()
    except MetadataError:
        if strict:
            raise
        # startup 期常见为 DB 表未就绪（init_db 前模块级 reload / 全新部署首启）— 一行降级提示，
        # 不打 traceback（避免吓到运维；干净首启）；strict=True（admin/query）仍 fail-fast 上抛全栈。
        import logging
        logging.getLogger("knot.catalog").warning(
            "catalog 双源暂不可达（DB 表未就绪/未配置）— startup 降级空覆盖，init_db / admin reload 后生效",
        )
        db_lex, db_tables, db_rules, db_relations, db_found = {}, [], "", [], False

    # v0.6.1.4: TABLES — DB 主导 SQL 表，file 始终追加 HTTP 虚拟表
    base_tables = list(db_tables) if db_tables else list(f_tables)
    if db_tables:  # DB 已主导 SQL 表时，单独 merge file 中 HTTP 表
        http_from_file = [
            t for t in (f_tables or [])
            if t.get("source_type") == "http"
        ]
        existing_names = {f"{t.get('db')}.{t.get('table')}" for t in base_tables}
        for t in http_from_file:
            full = f"{t.get('db')}.{t.get('table')}"
            if full not in existing_names:
                base_tables.append(t)

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
    TABLES = base_tables

    # v0.6.1.4: LEXICON — 智能合并（不简单覆盖）
    # 同一关键词在 file 和 DB 都存在时 → value list 合并（保留两边的表）
    # 由 pick_http_route entity-aware ranking 决定优先级
    LEXICON = _merge_lexicons(f_lex, db_lex)

    BUSINESS_RULES = db_rules if db_rules.strip() else f_rules
    RELATIONS = db_relations if db_relations else f_relations  # v0.5.44 — DB 覆盖优先

    _SOURCE = "db+file_http" if (db_found and any(t.get("source_type") == "http" for t in TABLES)) else ("db" if db_found else f_src)
    return _SOURCE


# 启动期初始加载（DB 表不存在时 persistence.get_app_setting 返回 None，安全）
reload()


def get_defaults_from_files() -> dict:
    """admin "恢复默认"按钮预填值。v0.5.44 加 relations。"""
    f_lex, f_tables, f_rules, f_relations, f_src = _load_from_files()
    return {
        "lexicon": f_lex,
        "tables": f_tables,
        "business_rules": f_rules,
        "relations": [list(r) for r in f_relations],  # tuple → list (JSON-friendly)
        "source": f_src,
    }


def get_table_full_names() -> list:
    return [f"{t['db']}.{t['table']}" for t in TABLES]


# ── v0.4.1.1: RELATIONS 元数据访问 + 按需渲染 ─────────────────────────────────
def get_relations() -> list:
    """返当前 RELATIONS 全量。R-S3：老 catalog 无此常量时上面 _load_from_files
    已经 fallback 成 []，本函数永不 KeyError / AttributeError。"""
    return list(RELATIONS)


# ── v0.6.1.4: HTTP 虚拟表支持（OVERRIDE #3 — catalog-driven endpoint metadata）──
def is_http_table(table_full_name: str) -> bool:
    """检查 table_full_name 是否为 source_type=http 的虚拟表。

    Args:
        table_full_name: 格式 "db.table" (与 get_table_full_names 一致)

    Returns:
        True 是 HTTP 虚拟表，False 是 SQL 表或未注册
    """
    if "." not in table_full_name:
        return False
    db, table = table_full_name.split(".", 1)
    for t in TABLES:
        if t.get("db") == db and t.get("table") == table:
            return t.get("source_type", "db") == "http"
    return False


def get_http_spec(table_full_name: str) -> dict | None:
    """取 HTTP 虚拟表的 endpoint spec（喂给 knot.adapters.http.executor.execute）。

    Args:
        table_full_name: 格式 "db.table"

    Returns:
        dict (HTTPEndpointSpec 形态) 或 None（非 HTTP 表或未配 http_spec）
    """
    if not is_http_table(table_full_name):
        return None
    db, table = table_full_name.split(".", 1)
    for t in TABLES:
        if t.get("db") == db and t.get("table") == table:
            return t.get("http_spec")
    return None


def get_field_mapping(table_full_name: str) -> dict:
    """取虚拟表的 field_mapping（API 字段 → 业务字段重映射）。

    Returns: dict 或空 dict（未配映射）
    """
    if "." not in table_full_name:
        return {}
    db, table = table_full_name.split(".", 1)
    for t in TABLES:
        if t.get("db") == db and t.get("table") == table:
            return t.get("field_mapping", {}) or {}
    return {}


def get_http_tables() -> list:
    """返所有 source_type=http 的表的全名 list。

    用途：query.py 路由层启动期可检查"含 HTTP 表 → 必须设 KNOT_HTTP_ALLOWED_HOSTS env"。
    """
    return [
        f"{t['db']}.{t['table']}" for t in TABLES
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
