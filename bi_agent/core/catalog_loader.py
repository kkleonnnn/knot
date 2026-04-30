"""catalog_loader.py — 优先加载真实业务目录 ohx_catalog，缺失时 fallback 到 ohx_catalog.example。

业务隐私分层（v0.2.4）：
  - bi_agent/core/ohx_catalog.py          — 真实业务（.gitignore，部署时由用户填写）
  - bi_agent/core/ohx_catalog.example.py  — 通用模板（仓库内提交，不含真实数据）

调用方仅需：
    from catalog_loader import LEXICON, TABLES, BUSINESS_RULES
"""

import importlib
import importlib.util
import pathlib

LEXICON: dict = {}
TABLES: list = []
BUSINESS_RULES: str = ""


def _load():
    global LEXICON, TABLES, BUSINESS_RULES
    # 1) 尝试真实文件 ohx_catalog
    try:
        m = importlib.import_module("ohx_catalog")
        LEXICON = getattr(m, "LEXICON", {}) or {}
        TABLES = getattr(m, "TABLES", []) or []
        BUSINESS_RULES = getattr(m, "BUSINESS_RULES", "") or ""
        return "real"
    except Exception:
        pass

    # 2) Fallback：通过 importlib 动态加载 ohx_catalog.example.py
    try:
        p = pathlib.Path(__file__).parent / "ohx_catalog.example.py"
        if p.exists():
            spec = importlib.util.spec_from_file_location("ohx_catalog_example", p)
            m = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(m)
            LEXICON = getattr(m, "LEXICON", {}) or {}
            TABLES = getattr(m, "TABLES", []) or []
            BUSINESS_RULES = getattr(m, "BUSINESS_RULES", "") or ""
            return "example"
    except Exception:
        pass

    return "empty"


_SOURCE = _load()
