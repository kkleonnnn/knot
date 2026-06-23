"""tests/services/test_catalog_context — v0.6.2.6 段 4 (A1 并发半) commit 1 守护测试。

覆盖（ContextVar 基础设施）：
- current_catalog() ContextVar 未 set → 回退模块全局（R-PB-A1-15 byte-equal）
- set_active_catalog_ctx → current_catalog() 读 ContextVar；reset → 回退全局
- ContextVar 请求作用域（默认 None；token 配对 reset 不泄漏 — R-PB-A1-14/22）
- AuditAction Literal +catalog.context_violation（39→40）
- CatalogContextException 在 errors 树（attempted/expected meta — R-PB-A1-16/23）
"""
import contextvars

from knot.models.audit import AuditAction
from knot.models.errors import BIAgentError, CatalogContextException
from knot.services.agents import catalog as catalog_loader


# ─── current_catalog() ContextVar 优先 + 全局回退（R-PB-A1-15）─────────

def test_current_catalog_falls_back_to_globals_when_unset():
    """ContextVar 未 set → current_catalog() 回退模块全局（与直读等价 byte-equal）。"""
    cur = catalog_loader.current_catalog()
    assert cur["lexicon"] is catalog_loader.LEXICON
    assert cur["tables"] is catalog_loader.TABLES
    assert cur["business_rules"] is catalog_loader.BUSINESS_RULES
    assert cur["relations"] is catalog_loader.RELATIONS
    assert cur["catalog_id"] is None  # 全局回退无 per-user catalog_id


def test_set_active_catalog_ctx_overrides_globals():
    """set_active_catalog_ctx → current_catalog() 读 ContextVar；reset → 回退全局。"""
    content = {"lexicon": {"GMV": ["t"]}, "tables": [{"db": "x"}],
               "business_rules": "rule B", "relations": [], "catalog_id": 7}
    token = catalog_loader.set_active_catalog_ctx(content)
    try:
        cur = catalog_loader.current_catalog()
        assert cur["catalog_id"] == 7
        assert cur["business_rules"] == "rule B"
        assert cur is content
    finally:
        catalog_loader.reset_active_catalog_ctx(token)
    # reset 后回退全局（不泄漏 — R-PB-A1-22）
    assert catalog_loader.current_catalog()["catalog_id"] is None


def test_contextvar_request_scope_isolated_across_contexts():
    """ContextVar 请求作用域：copy_context 内 set 不泄漏到外层（async 上下文隔离基础）。"""
    def _inner():
        token = catalog_loader.set_active_catalog_ctx(
            {"lexicon": {}, "tables": [], "business_rules": "", "relations": [], "catalog_id": 99}
        )
        assert catalog_loader.current_catalog()["catalog_id"] == 99
        # 注：不 reset，验 copy_context 隔离（独立上下文副本）

    ctx = contextvars.copy_context()
    ctx.run(_inner)
    # 外层上下文不受 copy_context 内 set 影响（请求作用域隔离）
    assert catalog_loader.current_catalog()["catalog_id"] is None


# ─── AuditAction 40 + CatalogContextException ─────────────────────────

def test_auditaction_has_context_violation():
    """AuditAction Literal +catalog.context_violation（39→40）。"""
    actions = AuditAction.__args__
    assert "catalog.context_violation" in actions
    assert "catalog.switch" in actions  # 结构半 sustained
    assert "config.budget_update" in actions  # v0.6.5.9 修 budget-config 审计崩溃新增
    assert len(actions) == 51, (
        f"AuditAction 应 51 条（47 + v0.7.7 C1 monitor.create/update/delete/trigger）；实际 {len(actions)}"
    )


def test_catalog_context_exception_in_errors_tree():
    """CatalogContextException 是 BIAgentError 子类 + attempted/expected meta（R-PB-A1-16/23）。"""
    assert issubclass(CatalogContextException, BIAgentError)
    exc = CatalogContextException(attempted_catalog_id=3, expected_catalog_id=1)
    assert exc.attempted_catalog_id == 3
    assert exc.expected_catalog_id == 1
    assert "attempted=3" in str(exc) and "expected=1" in str(exc)
