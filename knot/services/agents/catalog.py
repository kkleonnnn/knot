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

import importlib
import importlib.util
import json
import pathlib

LEXICON: dict = {}
TABLES: list = []
BUSINESS_RULES: str = ""
RELATIONS: list = []  # v0.4.1.1: 多表关联元数据，list[tuple(left_t, left_c, right_t, right_c, semantics)]
_SOURCE: str = "empty"  # "db" | "real" | "example" | "empty"


def _load_from_files() -> tuple:
    """返回 (lexicon, tables, business_rules, relations, source_tag)；
    source_tag ∈ real/example/empty。
    v0.4.1.1 R-S3：老 catalog 文件无 RELATIONS 常量时 getattr 返 [] 不抛 AttributeError。"""
    try:
        m = importlib.import_module("_local_catalog")
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
    """v0.5.44 — 返回 (lexicon, tables, business_rules, relations, found_any)。

    relations 新加（4 键 → 4 字段全部走 DB 覆盖；之前 v0.4.x R-S3 仅 3 字段）。
    """
    try:
        from knot.repositories.settings_repo import get_app_setting
    except Exception:
        return {}, [], "", [], False
    try:
        raw_tables = get_app_setting("catalog.tables") or ""
        raw_lex = get_app_setting("catalog.lexicon") or ""
        rules = get_app_setting("catalog.business_rules") or ""
        raw_rel = get_app_setting("catalog.relations") or ""
    except Exception:
        return {}, [], "", [], False

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


def reload() -> str:
    """v0.5.44 — 重新加载 catalog；返回 source 标签。
    DB 4 键覆盖 file 默认（粒度：每键独立）；某键 DB 为空则继续走 file fallback。
    RELATIONS 现也走 DB 覆盖（admin UI v0.5.44 落地，根因解防 cartesian）。"""
    global LEXICON, TABLES, BUSINESS_RULES, RELATIONS, _SOURCE

    f_lex, f_tables, f_rules, f_relations, f_src = _load_from_files()
    db_lex, db_tables, db_rules, db_relations, db_found = _load_from_db()

    LEXICON = db_lex if db_lex else f_lex
    TABLES = db_tables if db_tables else f_tables
    BUSINESS_RULES = db_rules if db_rules.strip() else f_rules
    RELATIONS = db_relations if db_relations else f_relations  # v0.5.44 — DB 覆盖优先

    _SOURCE = "db" if db_found else f_src
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
