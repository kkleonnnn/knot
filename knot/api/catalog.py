"""
catalog.py — admin 维护业务目录（v0.2.5）

三块数据：
  - tables          : list[dict]，表目录（{db, table, topics, summary}）
  - lexicon         : dict[str, list[str]]，业务词典（业务词 → 表全名优先级）
  - business_rules  : str，注入到 3 个 agent system prompt 的业务规则

存储：app_settings 三键（catalog.tables / catalog.lexicon / catalog.business_rules）
读取：catalog_loader.reload() —— DB 优先，缺失时 fallback 到 ohx_catalog(.example).py
"""
import json

from fastapi import APIRouter, Body, Depends, HTTPException, Request

from knot.api._audit_helpers import audit
from knot.api.deps import require_admin
from knot.repositories import settings_repo

# v0.3.0: import persistence → 直接 import 各 repo（保留"persistence.X"调用形态）
from knot.services.agents import catalog as catalog_loader

router = APIRouter()


def _has_setting(key: str) -> bool:
    v = settings_repo.get_app_setting(key) or ""
    return bool(v.strip())


@router.get("/api/admin/catalog")
async def get_catalog(admin=Depends(require_admin)):
    """返回当前生效的 catalog（DB 覆盖后）+ 文件默认值，供前端"恢复默认"使用。"""
    catalog_loader.reload()
    return {
        "source": catalog_loader._SOURCE,
        "current": {
            "tables": catalog_loader.TABLES,
            "lexicon": catalog_loader.LEXICON,
            "business_rules": catalog_loader.BUSINESS_RULES,
        },
        "defaults": catalog_loader.get_defaults_from_files(),
        "db_overrides": {
            "tables": _has_setting("catalog.tables"),
            "lexicon": _has_setting("catalog.lexicon"),
            "business_rules": _has_setting("catalog.business_rules"),
        },
    }


@router.put("/api/admin/catalog")
async def put_catalog(payload: dict = Body(...), request: Request = None, admin=Depends(require_admin)):
    """payload 形如 {tables?, lexicon?, business_rules?}；任一字段缺失 → 不动。
    传空字符串 / 空列表 / 空 dict 表示「清空该项 DB 覆盖」（回退默认）。
    """
    out = {"saved": []}
    if "tables" in payload:
        v = payload["tables"]
        if v in (None, "", [], {}):
            settings_repo.set_app_setting("catalog.tables", "")
        else:
            if not isinstance(v, list):
                raise HTTPException(status_code=400, detail="tables 必须是数组")
            settings_repo.set_app_setting("catalog.tables", json.dumps(v, ensure_ascii=False))
        out["saved"].append("tables")

    if "lexicon" in payload:
        v = payload["lexicon"]
        if v in (None, "", [], {}):
            settings_repo.set_app_setting("catalog.lexicon", "")
        else:
            if not isinstance(v, dict):
                raise HTTPException(status_code=400, detail="lexicon 必须是对象")
            settings_repo.set_app_setting("catalog.lexicon", json.dumps(v, ensure_ascii=False))
        out["saved"].append("lexicon")

    if "business_rules" in payload:
        v = payload["business_rules"]
        settings_repo.set_app_setting("catalog.business_rules", str(v or ""))
        out["saved"].append("business_rules")

    catalog_loader.reload()
    out["source"] = catalog_loader._SOURCE
    if out["saved"]:
        audit(request, admin, action="config.catalog_update", resource_type="catalog",
              detail={"saved": out["saved"]})
    return out


@router.post("/api/admin/catalog/reset")
async def reset_catalog(payload: dict = Body(default={}), request: Request = None, admin=Depends(require_admin)):
    """清空 DB 覆盖，回退到文件默认。
    payload.fields 可指定 ["tables", "lexicon", "business_rules"] 子集；缺省则全清。"""
    fields = payload.get("fields") or ["tables", "lexicon", "business_rules"]
    valid = {"tables", "lexicon", "business_rules"}
    cleared = []
    for f in fields:
        if f not in valid:
            continue
        settings_repo.set_app_setting(f"catalog.{f}", "")
        cleared.append(f)
    catalog_loader.reload()
    if cleared:
        audit(request, admin, action="config.catalog_update", resource_type="catalog",
              detail={"op": "reset", "cleared": cleared})
    return {"cleared": cleared, "source": catalog_loader._SOURCE}
