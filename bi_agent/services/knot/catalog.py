"""catalog_loader.py — 业务目录加载器（v0.2.5 DB 优先 + 热更）

加载优先级（高 → 低）：
  1) DB（admin 后台编辑）：app_settings 三键
       - catalog.tables          (JSON list[dict])
       - catalog.lexicon         (JSON dict[str, list[str]])
       - catalog.business_rules  (text)
     某项 DB 有值即用 DB；该项为空则继续 fallback。
  2) bi_agent/core/ohx_catalog.py        — 真实业务 .py（.gitignore，部署方按需放置）
  3) bi_agent/core/ohx_catalog.example.py — 仓库内通用模板

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
_SOURCE: str = "empty"  # "db" | "real" | "example" | "empty"


def _load_from_files() -> tuple:
    """返回 (lexicon, tables, business_rules, source_tag)；source_tag ∈ real/example/empty"""
    try:
        m = importlib.import_module("ohx_catalog")
        return (
            getattr(m, "LEXICON", {}) or {},
            getattr(m, "TABLES", []) or [],
            getattr(m, "BUSINESS_RULES", "") or "",
            "real",
        )
    except Exception:
        pass
    try:
        p = pathlib.Path(__file__).parent / "ohx_catalog.example.py"
        if p.exists():
            spec = importlib.util.spec_from_file_location("ohx_catalog_example", p)
            m = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(m)
            return (
                getattr(m, "LEXICON", {}) or {},
                getattr(m, "TABLES", []) or [],
                getattr(m, "BUSINESS_RULES", "") or "",
                "example",
            )
    except Exception:
        pass
    return {}, [], "", "empty"


def _load_from_db() -> tuple:
    """返回 (lexicon, tables, business_rules, found_any)。"""
    try:
        from bi_agent.repositories.settings_repo import get_app_setting
    except Exception:
        return {}, [], "", False
    try:
        raw_tables = get_app_setting("catalog.tables") or ""
        raw_lex = get_app_setting("catalog.lexicon") or ""
        rules = get_app_setting("catalog.business_rules") or ""
    except Exception:
        return {}, [], "", False

    tables, lex = [], {}
    if raw_tables.strip():
        try:
            t = json.loads(raw_tables)
            if isinstance(t, list):
                tables = t
        except Exception:
            pass
    if raw_lex.strip():
        try:
            l = json.loads(raw_lex)
            if isinstance(l, dict):
                lex = l
        except Exception:
            pass

    found = bool(tables or lex or rules.strip())
    return lex, tables, rules, found


def reload() -> str:
    """重新加载 catalog；返回 source 标签。
    DB 三键覆盖 file 默认（粒度：每键独立）；某键 DB 为空则继续走 file fallback。"""
    global LEXICON, TABLES, BUSINESS_RULES, _SOURCE

    f_lex, f_tables, f_rules, f_src = _load_from_files()
    db_lex, db_tables, db_rules, db_found = _load_from_db()

    LEXICON = db_lex if db_lex else f_lex
    TABLES = db_tables if db_tables else f_tables
    BUSINESS_RULES = db_rules if db_rules.strip() else f_rules

    _SOURCE = "db" if db_found else f_src
    return _SOURCE


# 启动期初始加载（DB 表不存在时 persistence.get_app_setting 返回 None，安全）
reload()


def get_defaults_from_files() -> dict:
    """admin "恢复默认"按钮预填值。"""
    f_lex, f_tables, f_rules, f_src = _load_from_files()
    return {
        "lexicon": f_lex,
        "tables": f_tables,
        "business_rules": f_rules,
        "source": f_src,
    }


def get_table_full_names() -> list:
    return [f"{t['db']}.{t['table']}" for t in TABLES]
