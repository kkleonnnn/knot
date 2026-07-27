"""knot.core.tenant_context — 多租户 ContextVar（fail-closed · 无全局回退）。

镜像 `services/agents/catalog.py` 的请求作用域 ContextVar 三层模式（set-without-reset），
但**刻意去掉全局回退**：`current_tenant()` 未 set → raise `TenantContextError`
（吸取守护者「带全局回退的租户 ContextVar = 虚假隔离」裁定）。tenant 是安全边界 → fail-closed。

core 横切层：api/services/repositories 均可依赖；本模块**零 services 依赖**
（import-linter 9 contracts 零新增方向）。audit-on-drift 随 0.1 多租户接线补（那时 drift 才是真威胁）。
"""
from __future__ import annotations

import contextvars

# 请求/启动/调度作用域 active tenant（未 set → current_tenant() raise，无全局回退 = fail-closed）
_active_tenant_ctx: contextvars.ContextVar = contextvars.ContextVar(
    "_active_tenant_ctx", default=None
)


class TenantContextError(RuntimeError):
    """无 active tenant ctx / 租户漂移 → fail-closed raise（严禁全局回退）。"""


def set_active_tenant(tenant_row: dict) -> contextvars.Token:
    """设当前作用域 active tenant（返回 Token 供 finally reset）。

    tenant_row 须含 `id` / `db_dir`（get_conn 双层解析用）。
    请求路径 middleware **set-without-reset**（靠 uvicorn per-request asyncio task 隔离，镜像 catalog ctx）；
    启动序 / 调度器 / 后台 task set 后**必须 finally reset**（防 ctx 泄进 serving 使 fail-closed 虚化）。
    """
    return _active_tenant_ctx.set(tenant_row)


def reset_active_tenant(token: contextvars.Token) -> None:
    """reset ctx（启动序 / 调度器 / 后台 task 的 finally 必调）。"""
    _active_tenant_ctx.reset(token)


def current_tenant() -> dict:
    """当前 active tenant（**fail-closed**：未 set → raise TenantContextError，无全局回退）。"""
    t = _active_tenant_ctx.get()
    if t is None:
        raise TenantContextError(
            "无 active tenant context（fail-closed）—— 请求经 middleware set，启动/调度/脚本须显式 set_active_tenant"
        )
    return t


def tenant_cache_key(*parts):
    """进程内缓存的统一租户键（v0.9.1 MF4 单一 choke point）：`(current_tenant()["id"], *parts)`。

    所有「按 per-tenant AUTOINCREMENT id 键」的模块级缓存（engine / DS-status / DS-stats / token）都经此 —
    防四处分散手改漏一处 = 仍跨租户串（守护者 MF4）。未 set ctx → `current_tenant()` raise（fail-closed，符合预期）。
    （rate-limit 桶是字符串键，用 `current_tenant()["id"]` 直接前缀同源，不经本 tuple helper。）
    """
    return (current_tenant()["id"], *parts)


def assert_tenant_context(expected_tenant_id: int) -> None:
    """执行前租户漂移 tripwire（镜像 `assert_catalog_context`）：current tenant id != expected → raise。

    tenant 是安全边界 → runtime tripwire 兜底（catalog ctx assert 之外的独立防线）。
    v0.9.0 单租户下恒 tenant#1；多租户 async race 漂移检测在此。未 set 亦 raise（current_tenant fail-closed）。
    audit-on-drift 随 0.1（core 保持无 services 依赖 → audit 落 services 层调用点，见 query 执行前）。
    """
    current = current_tenant()  # 未 set 即 raise
    if current.get("id") != expected_tenant_id:
        raise TenantContextError(
            f"tenant context 漂移：expected={expected_tenant_id} actual={current.get('id')}"
        )


def reraise_if_tenant_error(e: BaseException) -> None:
    """v0.9.3 D8'：catalog 读的 fail-soft handler 里调用 —— e 是 `TenantContextError` 则**重抛**（fail-closed），
    否则原样返回、让调用方走它既有的降级。

    作用 = 把「**缺 tenant ctx**」从「其他异常」里分离：前者绝不能被降级吞掉（降级后果按站点不同 ——
    脱敏静默 no-op / RELATIONS 段空致错数 / 把部署级 file catalog 当成该租户内容），后者保持既有可用性优先。
    收成单一 helper 而非各站点 inline，因此 revert harness 也是单点（改此处即可验全部站点）。
    """
    if isinstance(e, TenantContextError):
        raise e
