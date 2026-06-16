"""query_helper.py — v0.6.2.6 段 4 (A1 并发半): query 入口 per-user active catalog 捕获。

隔离三层第①层（应用层捕获）：query 入口读 user.active_catalog_id → catalog_repo.get_active_catalog
→ 解析 catalogs 行 JSON 字段 → set_active_catalog_ctx（请求作用域 ContextVar）→ 下游 schema_filter /
_business_rules / get_relations 经 current_catalog() 读 per-user active catalog（D2 helper 注入层）。

R-PB-A1-19 query.py Extract Method：捕获逻辑剥离至此（query.py 仅 2 行调用，保 SSE 样板 byte-equal）。
**0 yield**（R-109 / Stage 2 Q3 — ContextVar 不提前失效/泄漏）。
reset：commit 2 仅 capture（set）；task 隔离防跨请求泄漏；正式 reset + 出口不泄漏断言由 commit 4 中间件统一（R-PB-A1-22）。
"""
from __future__ import annotations

import json
import logging

from knot.services.agents import catalog as catalog_loader

logger = logging.getLogger("knot.catalog")


def _parse_catalog_content(row: dict) -> dict:
    """catalogs 行（tables/lexicon/business_rules/relations JSON 串）→ current_catalog() 形态
    {lexicon dict, tables list, business_rules str, relations list, catalog_id int}（与 _load_from_db 解析一致）。

    注：per-user catalog = DB SQL 内容（catalog id=N 的 4 字段）；file HTTP 虚拟表 merge 保持全局
    （HTTP 表非 per-catalog — OOS；部署级 file 配置）。
    """
    raw_tables = row.get("tables") or ""
    raw_lex = row.get("lexicon") or ""
    rules = row.get("business_rules") or ""
    raw_rel = row.get("relations") or ""
    tables, lex, relations = [], {}, []
    if raw_tables.strip():
        try:
            t = json.loads(raw_tables)
            if isinstance(t, list):
                tables = t
        except Exception:
            pass
    if raw_lex.strip():
        try:
            p = json.loads(raw_lex)
            if isinstance(p, dict):
                lex = p
        except Exception:
            pass
    if raw_rel.strip():
        try:
            pr = json.loads(raw_rel)
            if isinstance(pr, list):
                relations = [tuple(r) for r in pr if isinstance(r, (list, tuple)) and len(r) >= 4]
        except Exception:
            pass
    return {
        "lexicon": lex, "tables": tables, "business_rules": rules,
        "relations": relations, "catalog_id": row.get("id"),
    }


def capture_active_catalog(user: dict):
    """query 入口捕获 per-user active catalog → set ContextVar；返回捕获的 catalog_id（fail-soft 失败回退全局返 None）。

    fail-soft：active catalog 解析失败（真空期 / DB 错）→ 不 set ContextVar → current_catalog() 回退全局
    （query 不阻断 — 可用性优先；隔离一致性由第②层 assert_catalog_context 兜底）。
    返回 catalog_id（expected）供第②层 assert（SSE generate() 内验 ContextVar 传播 + Q4 race 漂移）。
    """
    try:
        from knot.repositories import catalog_repo
        content = _parse_catalog_content(catalog_repo.get_active_catalog(user["id"]))
        catalog_loader.set_active_catalog_ctx(content)  # Token 弃 — reset 由 commit 4 中间件
        return content["catalog_id"]
    except Exception:
        logger.warning("per-user active catalog 捕获失败 — query 降级回退全局 catalog", exc_info=False)
        return None


def assert_catalog_context(expected_catalog_id, user: dict) -> None:
    """隔离三层第②层（SQL 执行前 assert）+ 第③层（失败 audit + raise）。

    验当前 ContextVar 的 active catalog_id == 入口捕获的 expected（防 async race 漂移 / ContextVar 未传播）。
    漂移 → catalog.context_violation audit（attempted/expected 落库 R-PB-A1-23）+ raise CatalogContextException
    （error_translator → 「查询上下文发生安全冲突，请重试」D4）。
    当前 async 单 Task（Q4 实证 0 create_task）→ ContextVar 不漂移 → assert 通过；SSE generate() 内验传播；
    expected None（capture fail-soft 回退全局）→ 跳过 assert（已降级全局，无 per-user 一致性可验）。
    """
    if expected_catalog_id is None:
        return
    current = catalog_loader.current_catalog()["catalog_id"]
    if current != expected_catalog_id:
        from knot.models.errors import CatalogContextException
        from knot.services import audit_service
        audit_service.log(
            actor=user, action="catalog.context_violation", resource_type="catalog",
            resource_id=expected_catalog_id, success=False,
            detail={"attempted_catalog_id": current, "expected_catalog_id": expected_catalog_id},
            catalog_id=expected_catalog_id,
        )
        raise CatalogContextException(attempted_catalog_id=current, expected_catalog_id=expected_catalog_id)


def release(token) -> None:
    """请求出口 reset ContextVar（与 capture 的 Token 配对；token None 跳过）。

    commit 2 query 入口仅 capture（set）+ task 隔离防跨请求泄漏；正式 reset + 出口不泄漏断言
    由 commit 4 中间件统一（R-PB-A1-22）。本 release 供 commit 4 / sync finally 显式配对。
    """
    if token is not None:
        catalog_loader.reset_active_catalog_ctx(token)
