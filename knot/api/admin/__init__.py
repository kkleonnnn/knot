"""knot/api/admin/ — admin 路由包（v0.6.5.11 收官② admin.py 908 行拆 7 域）。

聚合 7 域子 router → `admin.router`（main.py `from knot.api import admin` + `admin.router` byte-equal）。
re-export `_DS_STATS_CACHE`（R-AS-2：3 测试 in-place 突变同对象 — datasources-stats 5min 缓存）。
"""
from __future__ import annotations

from fastapi import APIRouter

from . import api_keys, budgets, datasources, logicform, metrics, models, or_catalog, stats, users

# R-AS-2 re-export：同一 mutable dict 对象（from-import 绑定）；3 测试 in-place 突变（["data"]=）
# 跨此绑定可见 datasources.py 的同对象（dict 可变；仅 reassign 会破 — 测试 0 reassign）。
from .datasources import _DS_STATS_CACHE  # noqa: F401

router = APIRouter()
for _sub in (users, datasources, models, api_keys, budgets, stats, or_catalog, metrics, logicform):
    router.include_router(_sub.router)
