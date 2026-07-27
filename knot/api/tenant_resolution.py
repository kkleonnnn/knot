"""请求级租户解析 + tenant ctx 中间件（v0.9.4 step 3 从 main.py 抽出）。

**本 commit 行为完全不变** —— 纯搬迁（守护者 Q3 通则：旧机制还在时先重构，再切机制）。
抽出的两个理由：
1. `main.py` 已卡在 315 = check_file_sizes ACK 上限，step 5 扩写中间件（读 JWT tid + 严格类型
   + 登录/验证豁免）必破闸门；app 工厂不该承载解析策略。
2. 解析策略即将变成**安全边界**（决定「这个请求读哪个公司的库」）。放进独立文件才谈得上
   围着它写针对性的测 + 让守护者审一处而非审 app 工厂全文。

step 5 只改 `resolve_for_request` 内部（单租户解析器 → 读 JWT tid），中间件外壳不动。
"""

from knot.core import tenant_context as _tenant_ctx
from knot.repositories import tenant_repo


def resolve_for_request(request) -> dict:
    """解析本请求所属租户 → tenant dict。

    step 3 = 原样搬迁：仍走**单租户解析器**（platform.db 恰 1 active，0/>1 → raise
    = R-T-GATE 请求侧兜底），故 `request` 形参此刻未被读取 —— 它是 step 5 的接口预留位
    （届时从 `Authorization` 里的 JWT 取 tid）。**签名先定、内部后换**，让 step 5 的 diff
    只落在本函数体内、不再触碰中间件与 app 工厂。

    fail-closed 契约（step 5 后仍守）：**解析不出租户就 raise，绝不回退到某个默认租户**
    —— 回退 = 静默跨租户供数（OOS-1v2）。
    """
    return tenant_repo.resolve_single_tenant()


async def tenant_context_middleware(request, call_next):
    """v0.9.0 C2 请求作用域 tenant ctx（set-without-reset）。

    传播机制（Starlette 1.3.1 BaseHTTPMiddleware 源码 + 20 并发实证 · 守护者 Stage 4 V1 亲验）：本函数于
    call_next 前 set → BaseHTTPMiddleware 在 set **之后** `start_soon` spawn 下游子任务 → 子任务 copy_context
    含本 tenant → endpoint + SSE `async def generate()`（AsyncIterable 非 threadpool）均继承；20 并发
    distinct-tenant = 20/20 无泄漏。get_conn 每连接读 current_tenant() → 传播断即 raise（非 fail-open）。
    **禁 reset**（executor fork 场景丢 ctx → 那 3 处走 copy_context().run 显式传播）。
    """
    _tenant_ctx.set_active_tenant(resolve_for_request(request))  # set-without-reset
    return await call_next(request)
