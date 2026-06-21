"""knot/api/admin/or_catalog.py — OpenRouter live catalog 同步/对比路由（admin.py 拆分 v0.6.5.11）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from knot import config as cfg
from knot.api.deps import require_admin

router = APIRouter()


# ── v0.6.0.6 F-D — OpenRouter live catalog 同步（admin UI 按钮触发）─────

@router.post("/api/admin/sync-or-catalog")
async def admin_sync_or_catalog(admin=Depends(require_admin)):
    """v0.6.0.6 F-D-6：admin 主动 fetch OpenRouter live API + UPSERT model_catalog_live。

    数据准确性由 OpenRouter API 保证（守护者 M-D6 数据自治原则）；
    业务路径仍读 cfg.MODELS dict 不动；本表纯参考/审计用途。

    设计：
    - 网络超时 30s
    - User-Agent 显式 "knot/X.Y.Z"
    - 失败 503（不刷写表）
    - 成功 200 + {fetched_count, upserted_count, sample}
    """
    import json as _json
    import urllib.error
    import urllib.request

    from knot.repositories import model_catalog_repo

    url = "https://openrouter.ai/api/v1/models"
    req = urllib.request.Request(url, headers={"User-Agent": "knot/0.6.0.6"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
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
async def admin_get_or_catalog(admin=Depends(require_admin)):
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
