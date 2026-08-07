"""catalog_loaders — catalog 纯加载器（v0.6.5.12 收官③ 从 catalog.py 抽出）。

⚠️ **v0.9.6 起本模块不再是「纯 loader」**：`load_file_layer()` **读租户策略**
（`core.tenant_context.is_owner_tenant`）—— file 层只归起源租户。改动本模块前先读那个函数的 docstring。
（Contract 8 `catalog-loaders-pure` 守的是「不得 import 有状态 catalog」，与本条不冲突。）

4 个**纯函数**（无状态；不读/写 catalog 的载体）：从配置文件 / DB / DataSource 推断 / lexicon 合并，
计算并返 tuple。**v0.9.3 起**返值由 `catalog.reload()` 经 `catalog_state.publish()` **原子发布到当前租户槽**
（此前是 `global` reassign 塞回 catalog.py 的模块全局 —— 该形态已物理删除，并有静态哨兵禁 `global`）。

⚠️ R-CS-2/R-CS-7 + Contract 8（catalog-loaders-pure）：本模块**严禁 import catalog**
（保 catalog → catalog_loaders 单向；防 facade-freeze 环 + 防未来反向读 global）。
knot 依赖（repositories / models.errors / logging）保**函数体内延迟 import**（防 import-time 环）。
"""
from __future__ import annotations

import importlib
import importlib.util
import json
import pathlib


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


def load_file_layer() -> tuple:
    """⭐ **file 层的唯一 choke point**（v0.9.6 D1）—— `catalog.reload()` 与
    `get_defaults_from_files()` **都必须经本函数**，不得直呼 `_load_from_files()`。

    **决定**：file 层（= 部署方写的 `_local_catalog.py` / 仓内 `_template_catalog.py`）**只归起源租户**。
    非起源租户返**完整 empty 五元组** —— **禁半空**：实读 `catalog.reload()` 的五种合并策略里
    `business_rules = db_rules if db_rules.strip() else f_rules` ⇒ 只清 tables 而留 `f_rules`，
    **空-DB 的非 owner 仍会拿到部署方业务口径**；`lexicon` 更是**无条件合并**。
    ⇒ 这条闸闭合的是「空-DB 租户被**零动作**注入部署方表/词典/口径」这条路径。

    ⚠️ **为什么是外层 wrapper 而不是把判据写进 `_load_from_files` 内部**：全仓有 **4 处**测
    用 `monkeypatch.setattr(<facade>, "_load_from_files", …)` **整个替换**那个函数
    （`test_catalog_loaders.py:220` / `test_knot_catalog.py:104` /
    `test_catalog_tenant_isolation.py:241,262`）⇒ 判据若在函数内部，那 4 处**绕过判据**
    ⇒ owner 路径**零覆盖**。放外层后它们改 patch 源模块，即**升级为判据的 owner 路径守护**。
    """
    from knot.core.tenant_context import is_owner_tenant
    if not is_owner_tenant():
        return {}, [], "", [], "empty"
    return _load_from_files()


def warn_if_private_catalog_missing() -> None:
    """未挂载私有 catalog ⇒ 响亮告警（v0.9.16）。

    **它是排除动作的前提条件，不是装饰**：排掉 `_local_catalog.py` 后 file 层落模板
    ⇒ HTTP 虚拟表消失 ⇒ **查询静默落 SQL**（v0.7.29b），而 R-v096-4 明禁静默。
    只在起源租户 + 文件缺失时响（非 owner 本就该空）；消息不含表名/路径（#262）。
    """
    from knot.core.logging_setup import logger
    from knot.core.tenant_context import OWNER_TENANT_ID
    from knot.repositories import tenant_repo
    try:
        served = tenant_repo.resolve_single_tenant()
    except Exception:
        return
    if served.get("id") != OWNER_TENANT_ID:
        return                       # 非起源租户：file 层本就该空，由 owner-gate 负责
    if (pathlib.Path(__file__).parent / "_local_catalog.py").exists():
        return                       # 已挂载 ⇒ 静默（正常情形不出声）
    logger.warning(
        "[catalog] 私有 catalog 未挂载 ⇒ file 层退回内置模板："
        "HTTP 虚拟表消失、实时接口查询会**静默落 SQL**（v0.7.29b 失败模式）。"
        "若本部署确实使用 HTTP 数据源，请按 DEPLOY「私有 catalog」段 bind-mount 该文件；"
        "若本部署只用 SQL 数据源，可忽略本条。"
    )


def warn_if_owner_tenant_not_served() -> None:
    """启动期钩子：**被服务的租户不是起源租户**时响亮告警（G14 的静默失败）。

    ⚠️ **为什么需要它**：`tenant_repo.resolve_single_tenant()` 只要求 **恰 1 个 active**、
    **不要求 `id == OWNER_TENANT_ID`**（实读）⇒ 停用 tenant#1 + active tenant#2 ⇒ **boot 成功**，
    而 owner-gate 下 **file 层对被服务的那个租户静默消失**（表/词典/口径/relations 全空）
    ⇒ 部署方自己的 catalog 没了却**没有任何声音**。
    ⇒ 照 v0.9.5 `platform_admin.warn_if_noncompliant` 的范式：**只在异常情形告警**，正常静默。

    ⚠️ 无 active 租户 / >1 active（R-T-GATE）时 `resolve_single_tenant()` 自己 raise ——
    本函数**吞掉**那种情况（不是本函数要诊断的事，且启动序另有处理）。
    ⚠️ 消息只含租户 id 与后果，**不含**部署方表名 / env 名（#262 纪律）。
    """
    from knot.core.logging_setup import logger
    from knot.core.tenant_context import OWNER_TENANT_ID
    from knot.repositories import tenant_repo
    try:
        served = tenant_repo.resolve_single_tenant()
    except Exception:
        return                      # 0 / >1 active：启动序另有处理，不是本函数的诊断面
    tid = served.get("id")
    if tid != OWNER_TENANT_ID:
        logger.warning(
            f"[catalog] 被服务的租户 id={tid} **不是起源租户**（{OWNER_TENANT_ID}）⇒ "
            f"file 层 catalog 对它为空（表/词典/业务口径/relations 全空）、HTTP 路由被门挡住。"
            f"若这不是预期：起源租户可能被停用/删除 —— 见 CLAUDE.md R-T-GATE 就绪清单。"
        )


def _load_from_db() -> tuple:
    """v0.6.2.5 段 4 — 改读 catalogs 表默认行（id=1）；app_settings 4-key 降级 legacy 兜底。

    源切换（资深 A 拍板 / R-PB-A1-8）：catalogs id=1（commit 1 seed 自 app_settings → byte-equal）
    为主源；catalog id=1 行缺失（迁移前 / 被清空）→ app_settings 4-key legacy 兜底。
    兜底熔断（Stage 2 修订 3 / ε2 fail-fast 精神）：catalogs id=1 缺失 + app_settings 也无法读
      （异常）→ 真空期 → raise MetadataError（strict 与否由 reload 决定 — 沿用既有 ε2 模式）。
    返回 (lexicon, tables, business_rules, relations, found_any)。
    relations 4 键全走 DB 覆盖（v0.5.44；之前 v0.4.x R-S3 仅 3 字段）。
    """
    raw_tables = raw_lex = rules = raw_rel = raw_field_labels = ""   # v0.7.27 +field_labels（DB-only；legacy 无）
    got = False
    try:
        from knot.repositories import catalog_repo
        cat = catalog_repo.get_catalog(1)
        if cat is not None:
            raw_tables = cat.get("tables") or ""
            raw_lex = cat.get("lexicon") or ""
            rules = cat.get("business_rules") or ""
            raw_rel = cat.get("relations") or ""
            raw_field_labels = cat.get("field_labels") or ""   # v0.7.27（app_settings legacy 路径无此键 → 留 ""）
            got = True
    except Exception as e:
        # D8'：漏 tenant ctx **不得**降级 —— 那会把「部署级 file/legacy catalog」当成该租户内容
        # （全体租户共用一份，含部署方真实业务规则与库表清单）。
        from knot.core.tenant_context import reraise_if_tenant_error as _rt
        _rt(e)   # 非缺-ctx 的失败 → 落 app_settings legacy 兜底
    if not got:
        try:
            from knot.repositories.settings_repo import get_app_setting
            raw_tables = get_app_setting("catalog.tables") or ""
            raw_lex = get_app_setting("catalog.lexicon") or ""
            rules = get_app_setting("catalog.business_rules") or ""
            raw_rel = get_app_setting("catalog.relations") or ""
        except Exception as e:
            # v0.9.3 对抗自核：此处**不放** TenantContextError 守卫 —— 上面第一处守卫（本函数 DB 分支）
            # 已把缺-ctx 抛出（traceback 坐实），走到这里的必然不是 TenantContextError ⇒ 放守卫是死代码
            # （同我在 sql_planner_prompts 删死守卫的标准）。
            from knot.models.errors import MetadataError
            raise MetadataError(
                "catalog 双源不可用（catalogs id=1 缺失 + app_settings legacy 无法读）— 真空期熔断。"
                "若日志同期有 TenantContextError，真因是缺 tenant ctx 而非 catalogs 行缺失。",
            ) from e

    tables, lex, relations = [], {}, []
    if raw_tables.strip():
        try:
            t = json.loads(raw_tables)
            if isinstance(t, list):
                # v0.9.3 对抗自核：只收 dict 元素 —— `PUT /api/admin/catalog` 只校 `isinstance(v, list)`
                # 不校元素类型（api/catalog.py），传 ["db.t"] 这种字符串元素会先持久污染 DB，
                # 随后每次 reload 都在 `t.get(...)` 撞 AttributeError；而 v0.9.3 删了 import 期 reload
                # 与 warm-up ⇒ 进程内不再有 last-good ⇒ 读侧每次重试每次抛（脱敏等 fail-soft 点会静默降级）。
                tables = [x for x in t if isinstance(x, dict)]
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

    # v0.7.27 field_labels JSON 解析（{列名:中文} dict；镜像 lexicon — 非 dict/坏 JSON → {} fail-open）
    field_labels: dict = {}
    if raw_field_labels.strip():
        try:
            parsed_fl = json.loads(raw_field_labels)
            if isinstance(parsed_fl, dict):
                field_labels = parsed_fl
        except Exception:
            pass

    found = bool(tables or lex or rules.strip() or relations)   # field_labels 不入 found（独立元数据，不构成"catalog 有内容"）
    return lex, tables, rules, relations, field_labels, found


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
