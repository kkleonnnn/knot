"""
catalog.py — admin 维护业务目录 + 多 catalog 切换（v0.2.5 / v0.6.2.5 段 4 A1）

四块数据（单个 catalog 内）：
  - tables          : list[dict]，表目录（{db, table, topics, summary}）
  - lexicon         : dict[str, list[str]]，业务词典（业务词 → 表全名优先级）
  - business_rules  : str，注入到 3 个 agent system prompt 的业务规则
  - relations       : list[tuple]，多表关联元数据（v0.5.44）

存储（v0.6.2.5 段 4 起）：catalogs 表默认行 id=1（替代旧 app_settings 4-key；
  catalog id=1 缺失时 app_settings legacy 兜底；详 catalog_loader._load_from_db）。
读取：catalog_loader.reload(strict=True) —— catalogs id=1 优先，缺失 fallback _local/_template_catalog.py。
多 catalog（v0.6.2.5 A1）：catalogs 表多行 + per-user users.active_catalog_id 切换；
  ⚠️ OOS-1 死线 R-PB-A1-1：0 tenant_id — catalog_id = 语义层水平切分 ≠ 租户隔离。
"""
import json

from fastapi import APIRouter, Body, Depends, HTTPException, Request

from knot.api._audit_helpers import audit
from knot.api.deps import get_current_user, require_admin
from knot.models.errors import MetadataError
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


# ── v0.6.2.5 段 4 (A1): 多 catalog 管理 + per-user 切换 ──────────────────────


def _serialize_catalog_payload(payload: dict) -> dict:
    """校验 + 序列化 catalog 元字段（name/description）+ 内容 4 字段
    （tables/lexicon/business_rules/relations）→ catalog_repo create/update kwargs。
    空值（None/""/[]/{}）→ 清空该字段。复用 PUT /api/admin/catalog 同校验语义/文案。
    """
    out: dict = {}
    if "description" in payload:
        out["description"] = str(payload["description"] or "")
    if "tables" in payload:
        v = payload["tables"]
        if v in (None, "", [], {}):
            out["tables"] = ""
        elif isinstance(v, list):
            out["tables"] = json.dumps(v, ensure_ascii=False)
        else:
            raise HTTPException(status_code=400, detail="tables 必须是数组")
    if "lexicon" in payload:
        v = payload["lexicon"]
        if v in (None, "", [], {}):
            out["lexicon"] = ""
        elif isinstance(v, dict):
            out["lexicon"] = json.dumps(v, ensure_ascii=False)
        else:
            raise HTTPException(status_code=400, detail="lexicon 必须是对象")
    if "business_rules" in payload:
        out["business_rules"] = str(payload["business_rules"] or "")
    if "relations" in payload:
        v = payload["relations"]
        if v in (None, "", [], {}):
            out["relations"] = ""
        elif isinstance(v, list):
            for r in v:
                if not isinstance(r, (list, tuple)) or len(r) < 4:
                    raise HTTPException(status_code=400, detail="relations 每项必须 ≥4 元组 [left_t, left_c, right_t, right_c, semantics?]")
            out["relations"] = json.dumps(v, ensure_ascii=False)
        else:
            raise HTTPException(status_code=400, detail="relations 必须是数组（list of tuples）")
    return out


@router.get("/api/admin/catalogs")
async def list_all_catalogs(admin=Depends(require_admin)):
    """所有 catalog 元信息（id/name/description）— admin 多 catalog 选择器用（不返重内容字段）。"""
    return {
        "catalogs": [
            {"id": c["id"], "name": c["name"], "description": c["description"],
             "created_at": c["created_at"], "updated_at": c["updated_at"]}
            for c in catalog_repo.list_catalogs()
        ],
    }


@router.post("/api/admin/catalogs")
async def create_new_catalog(payload: dict = Body(...), request: Request = None, admin=Depends(require_admin)):
    """新建 catalog（name 必填）。⚠️ OOS-1 死线：0 tenant — 仅 catalog_id 语义切分。"""
    name = str(payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name 必填")
    fields = _serialize_catalog_payload(payload)
    cid = catalog_repo.create_catalog(name=name, **fields)
    audit(request, admin, action="config.catalog_update", resource_type="catalog",
          resource_id=cid, detail={"op": "create", "name": name}, catalog_id=cid)
    return {"id": cid, "name": name}


@router.put("/api/admin/catalogs/{cid}")
async def update_catalog_by_id(cid: int, payload: dict = Body(...), request: Request = None, admin=Depends(require_admin)):
    """更新指定 catalog（元字段 name/description + 内容 4 字段）。id=1 改动即时 reload。"""
    if catalog_repo.get_catalog(cid) is None:
        raise HTTPException(status_code=404, detail=f"catalog id={cid} 不存在")
    updates = _serialize_catalog_payload(payload)
    if "name" in payload:
        nm = str(payload["name"] or "").strip()
        if not nm:
            raise HTTPException(status_code=400, detail="name 不能为空")
        updates["name"] = nm
    if updates:
        catalog_repo.update_catalog(cid, **updates)
    if cid == 1:
        catalog_loader.reload(strict=True)  # 默认 catalog 改动即时生效
    audit(request, admin, action="config.catalog_update", resource_type="catalog",
          resource_id=cid, detail={"op": "update", "fields": sorted(updates.keys())}, catalog_id=cid)
    return {"id": cid, "saved": sorted(updates.keys())}


@router.delete("/api/admin/catalogs/{cid}")
async def delete_catalog_by_id(cid: int, request: Request = None, admin=Depends(require_admin)):
    """删除 catalog。⚠️ 默认 catalog id=1 不可删（兜底基线）。"""
    if cid == 1:
        raise HTTPException(status_code=400, detail="默认 catalog (id=1) 不可删除")
    if catalog_repo.get_catalog(cid) is None:
        raise HTTPException(status_code=404, detail=f"catalog id={cid} 不存在")
    catalog_repo.delete_catalog(cid)
    audit(request, admin, action="config.catalog_update", resource_type="catalog",
          resource_id=cid, detail={"op": "delete"}, catalog_id=cid)
    return {"deleted": cid}


@router.post("/api/catalog/switch")
async def switch_active_catalog(payload: dict = Body(...), request: Request = None, user=Depends(get_current_user)):
    """per-user 切换 active catalog（D5 server 解析 users.active_catalog_id）。
    OOS-2：无 catalog 级 RBAC（哪个用户能用哪个 catalog 留 v0.7+）— 任意登录用户切自己的 active。
    """
    catalog_id = payload.get("catalog_id")
    if not isinstance(catalog_id, int) or isinstance(catalog_id, bool):
        raise HTTPException(status_code=400, detail="catalog_id 必须是整数")
    try:
        catalog_repo.set_user_active_catalog(user["id"], catalog_id)
    except MetadataError as e:
        raise HTTPException(status_code=404, detail=str(e))
    audit(request, user, action="catalog.switch", resource_type="catalog",
          resource_id=catalog_id, catalog_id=catalog_id)
    return {"active_catalog_id": catalog_id}
