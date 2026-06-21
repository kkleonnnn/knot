"""catalog_loaders — catalog 纯加载器（v0.6.5.12 收官③ 从 catalog.py 抽出）。

4 个**纯函数**（无状态；不读/写 catalog.py 的 5 mutable globals）：从配置文件 / DB / DataSource
推断 / lexicon 合并，计算并返 tuple，由 `catalog.reload()` 把返值经 `global` reassign 塞回
catalog.py 自己的 globals（live-read 契约 = globals/reload 留 catalog.py 同模块，本模块只算不存）。

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
