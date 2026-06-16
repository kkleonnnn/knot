"""tests/_route_count — 路由计数动态展平 helper（v0.6.2.5 commit 7 / P-1/P-5 治本）。

背景：FastAPI 0.137 起 `app.include_router(r)` 不再把子路由展平进 `app.routes`，
而是追加一个 `_IncludedRouter`（fastapi.routing 的 dataclass，BaseRoute 子类，**无 .path**；
子路由在 `.original_router.routes`，可嵌套）。于是 `len(app.routes)` 从 ~80 降到 ~24（17 router
各成 1 个 _IncludedRouter 包装器 + FastAPI 默认 + mount），且 `{r.path for r in app.routes}`
会撞 `_IncludedRouter` 无 `.path`。

本 helper 递归经 `original_router.routes` 下钻还原叶子路由集，**兼容**：
- FastAPI <0.137（Starlette 0.x）：app.routes 本就扁平（Route/Mount 直接含 .path）→ 原样返回
- FastAPI 0.137+：穿透 _IncludedRouter 懒包装 → 还原叶子 Route

这是 v0.6.0.4 P-1/P-5 决议「动态计数治本」的兑现 —— 路由计数守护不再依赖 app.routes 扁平结构，
对上游 FastAPI/Starlette include_router 内部实现变更鲁棒。
"""
from __future__ import annotations


def _flatten(routes) -> list:
    out = []
    for r in routes:
        # FastAPI 0.137+ _IncludedRouter：无 .path，经 original_router.routes 下钻（可嵌套）
        orig = getattr(r, "original_router", None)
        if orig is not None and hasattr(orig, "routes"):
            out.extend(_flatten(orig.routes))
        else:
            # 叶子 Route / Mount / spa catch-all（含 .path）— 不下钻 Mount 内部静态文件
            out.append(r)
    return out


def flatten_app_routes(app) -> list:
    """还原 app 的叶子路由列表（穿透 FastAPI 0.137+ _IncludedRouter 懒包装）。"""
    return _flatten(app.routes)


def app_route_paths(app) -> set:
    """所有叶子路由的 path 集合（防 _IncludedRouter 无 .path 崩溃）。"""
    return {r.path for r in flatten_app_routes(app) if hasattr(r, "path")}
