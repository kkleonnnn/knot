"""knot/api/admin/or_catalog.py — OpenRouter live catalog 同步/对比路由（admin.py 拆分 v0.6.5.11）。"""

from __future__ import annotations

import urllib.request

from fastapi import APIRouter, Depends, HTTPException

from knot import config as cfg
from knot.api.deps import require_tenant_admin


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """⭐ v0.9.22：**不跟随重定向**的 handler。

    ## 为什么需要它
    出网 allowlist **只管第一跳** —— 目标回一个 302 就能把请求引到名单外的主机。
    本仓其余 6 个出网点都是 `requests` 形态、已带 `allow_redirects=False`（v0.9.21）；
    **只有这一处是 `urlopen`**，而它**默认跟随** ⇒ 它之所以在上一片被漏掉，
    正因为**形态不同**（按「找 `allow_redirects`」的扫描面结构上找不到它）。

    ## 机理（实测）
    `redirect_request` 返 `None` ⇒ `http_error_302` 直接 return
    ⇒ 落到 `http_error_default` ⇒ **抛 `HTTPError(code=302)`**、第二跳零发生。
    ⭐ **这正是选它而非换 `requests` 的理由**：3xx 变成 `HTTPError`
    ⇒ 与 4xx/5xx **共用调用处那条既有 `except`** ⇒ 上游异常一律 **503、不写表**（fail-closed 保住）。
    ⚠️ 换 `requests` 反而会引入 **4 处 fail-open**（4xx/5xx/**以及 302 的响应体**都不抛
    ⇒ 那个体会被当模型目录 upsert）+ 一个**不可关闭的 `.netrc` 凭据出境面**（实测）。

    ⚠️ **诚实边界**：`urlopen` 与 `requests` **同样**走 `HTTP_PROXY`
    ⇒ 代理面**今天就存在**，不是本片引入的，也不由本片解决（启动期 WARN 提示）。
    """

    def redirect_request(self, *a):          # noqa: D102
        return None


#: 全仓**唯一**允许的 `urlopen` 替代品（哨兵会禁掉直调 `urllib.request.urlopen`）。
_OPENER = urllib.request.build_opener(_NoRedirect())


router = APIRouter()


# ── v0.6.0.6 F-D — OpenRouter live catalog 同步（admin UI 按钮触发）─────

@router.post("/api/admin/sync-or-catalog")
async def admin_sync_or_catalog(admin=Depends(require_tenant_admin)):
    """v0.6.0.6 F-D-6：admin 主动 fetch OpenRouter live API + UPSERT model_catalog_live。

    数据准确性由 OpenRouter API 保证（守护者 M-D6 数据自治原则）；
    业务路径仍读 cfg.MODELS dict 不动；本表纯参考/审计用途。

    设计：
    - 网络超时 30s
    - User-Agent = `knot`（**不带版本** —— v0.9.22 去掉，理由见下方注释）
    - **不跟随重定向**（走 `_OPENER`）⇒ 3xx 与 4xx/5xx 同路 503、不写表
    - 失败 503（不刷写表）
    - 成功 200 + {fetched_count, upserted_count, sample}
    """
    import json as _json
    import urllib.error
    import urllib.request

    from knot.repositories import model_catalog_repo

    url = "https://openrouter.ai/api/v1/models"
    # ⭐ UA **不带版本**（v0.9.22）：原写死 `knot/0.6.0.6`，那个字面**漂了 30+ PATCH**。
    # ⚠️ 修法刻意不是「从真相源读版本」而是**把版本从 UA 里去掉** ——
    #    UA 里的版本在这里**零功能价值**，而「两个地方要同步」这件事本身就是漂移的来源。
    #    （本仓的修法优先级：**让两者结构上不可能不同** 优于「记得同步」。）
    # ⚠️ 顺带发现（**不在本片修**）：`pyproject.toml` 的 `version` 是 `0.3.0`，
    #    比实际漂了约 60 个 PATCH，且**不在 4 源点里** ⇒ 已登记 backlog。
    req = urllib.request.Request(url, headers={"User-Agent": "knot"})
    try:
        # ⭐ v0.9.22：走 `_OPENER`（**不跟随重定向**）而非 `urllib.request.urlopen`。
        #    ⇒ 3xx 会抛 `HTTPError`，与 4xx/5xx **共用下面那条 except** ⇒ 照旧 503、不写表。
        with _OPENER.open(req, timeout=30) as resp:
            payload = _json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, _json.JSONDecodeError, TimeoutError) as e:
        raise HTTPException(status_code=503, detail=f"OpenRouter API 拉取失败: {type(e).__name__}")

    data = payload.get("data") or []
    upserted = 0
    sample = []
    for m in data:
        mid = m.get("id")
        if not mid:
            continue
        ctx = m.get("context_length")
        p = m.get("pricing") or {}
        try:
            in_price = float(p.get("prompt") or 0) * 1_000_000
            out_price = float(p.get("completion") or 0) * 1_000_000
        except (ValueError, TypeError):
            in_price, out_price = None, None
        model_catalog_repo.upsert(
            model_id=mid,
            context_length=int(ctx) if ctx else None,
            input_price=round(in_price, 4) if in_price else None,
            output_price=round(out_price, 4) if out_price else None,
            raw={"id": mid, "context_length": ctx, "pricing": p},
        )
        upserted += 1
        if len(sample) < 3:
            sample.append({"id": mid, "ctx": ctx,
                           "in": round(in_price, 4) if in_price else None,
                           "out": round(out_price, 4) if out_price else None})

    return {
        "ok": True,
        "fetched_count": len(data),
        "upserted_count": upserted,
        "sample": sample,
    }


@router.get("/api/admin/or-catalog")
async def admin_get_or_catalog(admin=Depends(require_tenant_admin)):
    """v0.6.0.6 F-D-6：读 model_catalog_live 缓存表 + 与 cfg.MODELS dict 对比标 drift。

    前端可见：
    - in_dict: model_id 是否在 cfg.MODELS（dict 内已配置）
    - dict_input_price / dict_output_price / dict_max_context: dict 当前值（对比 OR live）
    - drift: True/False (任一字段差异)
    """
    from knot.repositories import model_catalog_repo
    live = model_catalog_repo.list_all()
    out = []
    for r in live:
        mid = r["model_id"]
        d = cfg.MODELS.get(mid)
        drift = False
        if d:
            if r.get("input_price") is not None and abs(float(r["input_price"]) - float(d.get("input_price", 0))) > 0.001:
                drift = True
            if r.get("output_price") is not None and abs(float(r["output_price"]) - float(d.get("output_price", 0))) > 0.001:
                drift = True
            if r.get("context_length") is not None and int(r["context_length"]) != int(d.get("max_context") or 0):
                drift = True
        out.append({
            **r,
            "in_dict": d is not None,
            "dict_input_price": d.get("input_price") if d else None,
            "dict_output_price": d.get("output_price") if d else None,
            "dict_max_context": d.get("max_context") if d else None,
            "drift": drift,
        })
    return {"items": out, "total": len(out)}
