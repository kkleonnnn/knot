"""收官② admin.py 拆分契约哨兵（v0.6.5.11 R-AS-1/2/3）。

admin.py 908 行拆 knot/api/admin/ 7 域包后，守护三契约：
- R-AS-1：admin.router 聚合 = 35 路由（30 + v0.7.0 C2 metric registry 5 端点；main.py `admin.router` byte-equal）。
- R-AS-2：admin._DS_STATS_CACHE re-export 同对象（3 隔离测试 in-place 突变可见的命门）。
- R-AS-3：7 域 + __init__ 全 born-clean（from __future__ AST-position 容忍 docstring + 0 Optional[）。
"""
from __future__ import annotations

import ast
from pathlib import Path

_ADMIN_DIR = Path(__file__).resolve().parents[2] / "knot" / "api" / "admin"
_DOMAINS = ["users", "datasources", "models", "api_keys", "budgets", "stats", "or_catalog", "metrics", "logicform", "monitors"]


def test_admin_router_aggregates_46_routes():
    """R-AS-1：admin.router 聚合 10 域 = 46 路由（40 + v0.7.7 monitors list/create/update/delete/triggers/check-now 6；穿透 FastAPI 0.137 懒包装）。"""
    from fastapi import APIRouter, FastAPI

    from knot.api import admin
    from tests._route_count import flatten_app_routes

    assert isinstance(admin.router, APIRouter)
    # FastAPI 0.137 include_router 懒包装：admin.router.routes 仅 7 个 _IncludedRouter（每 sub 一个），
    # 30 条叶子路由须经 original_router.routes flatten 还原（复用 tests/_route_count helper；
    # 数 route 对象非 path 集 — GET+POST 同 path 会去重致 <30）。
    app = FastAPI()
    app.include_router(admin.router)
    admin_routes = [
        r for r in flatten_app_routes(app)
        if getattr(r, "path", "").startswith("/api/admin/")
    ]
    assert len(admin_routes) == 46, f"admin 应聚合 46 路由（40 + monitors 6: list/create/update/delete/triggers/check-now）；实际 {len(admin_routes)}"


def test_ds_stats_cache_reexport_same_object():
    """R-AS-2：admin._DS_STATS_CACHE 与 datasources._DS_STATS_CACHE 是同一对象（id 锁）。

    re-export 绑定同 dict → 3 隔离测试 in-place 突变（`["data"]=`）跨绑定可见 datasources 路由读的同对象。
    若拆分误用 reassign / 各持副本，此断言红（守护命门）。
    """
    from knot.api import admin
    from knot.api.admin import datasources

    assert admin._DS_STATS_CACHE is datasources._DS_STATS_CACHE


def test_born_clean_ast_position_and_no_optional():
    """R-AS-3：7 域 + __init__ 全 from __future__ AST-position（首个 import，容忍 docstring）+ 0 Optional[。"""
    for name in [*_DOMAINS, "__init__"]:
        src = (_ADMIN_DIR / f"{name}.py").read_text(encoding="utf-8")
        assert "Optional[" not in src, f"admin/{name}.py 残留 Optional[（born-clean 须 0）"
        body = ast.parse(src).body
        # 容忍前导 module docstring
        idx = 1 if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ) else 0
        first = body[idx]
        assert (
            isinstance(first, ast.ImportFrom)
            and first.module == "__future__"
            and any(a.name == "annotations" for a in first.names)
        ), f"admin/{name}.py：from __future__ import annotations 须为首个 import（AST-position 非字面 L1）"
