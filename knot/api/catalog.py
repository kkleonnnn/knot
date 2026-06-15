"""
catalog.py — admin 维护业务目录（v0.2.5）

三块数据：
  - tables          : list[dict]，表目录（{db, table, topics, summary}）
  - lexicon         : dict[str, list[str]]，业务词典（业务词 → 表全名优先级）
  - business_rules  : str，注入到 3 个 agent system prompt 的业务规则

存储：app_settings 三键（catalog.tables / catalog.lexicon / catalog.business_rules）
读取：catalog_loader.reload(strict=True) —— DB 优先，缺失时 fallback 到 _local_catalog / _template_catalog.py
"""
import json

from fastapi import APIRouter, Body, Depends, HTTPException, Request

from knot.api._audit_helpers import audit
from knot.api.deps import require_admin
from knot.repositories import catalog_repo

# v0.3.0: import persistence → 直接 import 各 repo（保留"persistence.X"调用形态）
from knot.services.agents import catalog as catalog_loader

router = APIRouter()


def _has_override(field: str) -> bool:
    """v0.6.2.5：db_overrides 反映 catalogs 表默认行 id=1 该字段是否非空（替代旧 app_settings）。"""
    cat = catalog_repo.get_catalog(1) or {}
    return bool((cat.get(field) or "").strip())


@router.get("/api/admin/catalog")
async def get_catalog(admin=Depends(require_admin)):
    """v0.5.44 — 加 relations 字段返回；4 键全部可走 DB 覆盖。"""
    catalog_loader.reload(strict=True)
    return {
        "source": catalog_loader._SOURCE,
        "current": {
            "tables": catalog_loader.TABLES,
            "lexicon": catalog_loader.LEXICON,
            "business_rules": catalog_loader.BUSINESS_RULES,
            "relations": [list(r) for r in catalog_loader.RELATIONS],
        },
        "defaults": catalog_loader.get_defaults_from_files(),
        "db_overrides": {
            "tables": _has_override("tables"),
            "lexicon": _has_override("lexicon"),
            "business_rules": _has_override("business_rules"),
            "relations": _has_override("relations"),
        },
    }


@router.put("/api/admin/catalog")
async def put_catalog(payload: dict = Body(...), request: Request = None, admin=Depends(require_admin)):
    """payload 形如 {tables?, lexicon?, business_rules?}；任一字段缺失 → 不动。
    传空字符串 / 空列表 / 空 dict 表示「清空该项 DB 覆盖」（回退默认）。
    """
    # v0.6.2.5：批量收集 → 写 catalogs 表默认行 id=1（替代旧 app_settings 4-key；
    # 校验全过后一次性 update，relations 400 不留半写 — 比旧逐键写更原子）
    out = {"saved": []}
    updates: dict = {}
    if "tables" in payload:
        v = payload["tables"]
        if v in (None, "", [], {}):
            updates["tables"] = ""
        else:
            if not isinstance(v, list):
                raise HTTPException(status_code=400, detail="tables 必须是数组")
            updates["tables"] = json.dumps(v, ensure_ascii=False)
        out["saved"].append("tables")

    if "lexicon" in payload:
        v = payload["lexicon"]
        if v in (None, "", [], {}):
            updates["lexicon"] = ""
        else:
            if not isinstance(v, dict):
                raise HTTPException(status_code=400, detail="lexicon 必须是对象")
            updates["lexicon"] = json.dumps(v, ensure_ascii=False)
        out["saved"].append("lexicon")

    if "business_rules" in payload:
        v = payload["business_rules"]
        updates["business_rules"] = str(v or "")
        out["saved"].append("business_rules")

    # v0.5.44 — relations 字段（JSON list of [left_t, left_c, right_t, right_c, semantics]）
    if "relations" in payload:
        v = payload["relations"]
        if v in (None, "", [], {}):
            updates["relations"] = ""
        else:
            if not isinstance(v, list):
                raise HTTPException(status_code=400, detail="relations 必须是数组（list of tuples）")
            for r in v:
                if not isinstance(r, (list, tuple)) or len(r) < 4:
                    raise HTTPException(status_code=400, detail="relations 每项必须 ≥4 元组 [left_t, left_c, right_t, right_c, semantics?]")
            updates["relations"] = json.dumps(v, ensure_ascii=False)
        out["saved"].append("relations")

    if updates:
        catalog_repo.update_catalog(1, **updates)

    catalog_loader.reload(strict=True)
    out["source"] = catalog_loader._SOURCE
    if out["saved"]:
        audit(request, admin, action="config.catalog_update", resource_type="catalog",
              detail={"saved": out["saved"]})
    return out


@router.post("/api/admin/catalog/reset")
async def reset_catalog(payload: dict = Body(default={}), request: Request = None, admin=Depends(require_admin)):
    """清空 DB 覆盖，回退到文件默认。
    payload.fields 可指定 ["tables", "lexicon", "business_rules"] 子集；缺省则全清。"""
    fields = payload.get("fields") or ["tables", "lexicon", "business_rules", "relations"]
    valid = {"tables", "lexicon", "business_rules", "relations"}  # v0.5.44 — relations 加入
    cleared = [f for f in fields if f in valid]
    # v0.6.2.5：清 catalogs 表默认行 id=1 字段（替代旧 app_settings 4-key）
    if cleared:
        catalog_repo.update_catalog(1, **{f: "" for f in cleared})
    catalog_loader.reload(strict=True)
    if cleared:
        audit(request, admin, action="config.catalog_update", resource_type="catalog",
              detail={"op": "reset", "cleared": cleared})
    return {"cleared": cleared, "source": catalog_loader._SOURCE}
