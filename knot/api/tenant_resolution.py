"""请求级租户解析 + tenant ctx 中间件（v0.9.4 step 3 从 main.py 抽出）。

**本 commit 行为完全不变** —— 纯搬迁（守护者 Q3 通则：旧机制还在时先重构，再切机制）。
抽出的两个理由：
1. `main.py` 已卡在 315 = check_file_sizes ACK 上限，step 5 扩写中间件（读 JWT tid + 严格类型
   + 登录/验证豁免）必破闸门；app 工厂不该承载解析策略。
2. 解析策略即将变成**安全边界**（决定「这个请求读哪个公司的库」）。放进独立文件才谈得上
   围着它写针对性的测 + 让守护者审一处而非审 app 工厂全文。

step 5 只改 `resolve_for_request` 内部（单租户解析器 → 读 JWT tid），中间件外壳不动。
"""

import jwt
from fastapi.security.utils import get_authorization_scheme_param

from knot.api.deps import JWT_ALGORITHM, _get_secret
from knot.core import tenant_context as _tenant_ctx
from knot.core.logging_setup import logger
from knot.repositories import tenant_repo

# ⚠️ **临时表 —— 每一项都写明摘除条件；不得增项，`test_R14_legacy_paths_exact` 断言精确内容。**
# 这两条路径**没有可用于决定租户的 JWT**，本步暂留旧的单租户解析器。
# 之所以敢留：R-T-GATE 仍硬锁第二租户（`assert_no_second_active_tenant_served`）⇒ 单租户下二者等价；
# 之所以必须写成**显式表而不是「解析不出就回退单租户」**：后者就是 OOS-1v2 禁的 fail-open 全局回退，
# 一旦写成通用回退，将来任何解析失败都会静默落到某个默认租户 = 跨租户供数。
# ⭐ **v0.9.17 起为空** —— 最后一条 `/api/bi/scheduler/tick` 已摘除：
#    它改为**自建 ctx 端点**（`tenant` 参数必填，见 `api/bi_schedule.scheduler_tick`）
#    ⇒ 本表连同它那处 `resolve_single_tenant()` 回退一起消失。
# ⚠️ **保留空表而不删掉这段**：它是「哪些路径无 JWT」的**唯一记录点**；
#    将来若再出现同类端点，作者会在这里看到「上一个是怎么处理的」（答案：自建 ctx，不是加回本表）。
_LEGACY_SINGLE_TENANT_PATHS: frozenset[str] = frozenset()
# v0.9.4 step 7 已兑现：`/api/auth/login` **已从本表摘除** —— 它改为端点内按 `?c=<slug>` 自建 ctx
# （`api/auth.login` + `_resolve_login_tenant`）。摘除后 login 请求若带陈旧 Authorization，
# middleware 可能据此设 ctx，但端点入口 `clear_active_tenant()` 无条件清掉（R-13）⇒ 无影响。


def _bearer_payload(request) -> dict | None:
    """从 `Authorization` 取 JWT payload（验签）；取不到 / 不可用 → None（**不抛**）。

    ⚠️ **解析必须至少与 `fastapi.security.HTTPBearer` 一样宽松**，故直接复用它的
    `get_authorization_scheme_param`：若本函数比 `get_current_user` 依赖的 HTTPBearer **更严**，
    就会出现「middleware 认为没凭证 → 不设 ctx；HTTPBearer 认为有凭证 → 鉴权通过 → 端点碰 DB
    → fail-closed **500**」的组合。更宽松无害（最坏是设了 ctx 而随后 401）；更严则制造 500。
    D9「Bearer 精确匹配」在此的正确读法是「不要 `startswith` 式糊弄」，不是「比 HTTPBearer 更严」。

    `InvalidKeyError`（我们自己的密钥有问题 = 服务端配置错）**刻意不吞** —— 那不是凭证问题。
    """
    scheme, token = get_authorization_scheme_param(request.headers.get("authorization") or "")
    if scheme.lower() != "bearer" or not token:
        return None
    try:
        return jwt.decode(token, _get_secret(), algorithms=[JWT_ALGORITHM])
    except jwt.InvalidTokenError:
        return None      # 畸形 / 过期 / 签名不符 → 不设 ctx；401 由 get_current_user 出


def resolve_for_request(request) -> dict | None:
    """解析本请求所属租户 → tenant dict，**无法解析则返回 None（中间件届时不设 ctx）**。

    ⭐ **本步的核心设计选择（偏离草案 D9 的字面，理由如下）：中间件永不 401。**
    草案写「缺失/畸形一律 401」。若真由中间件出 401，就必须让它知道「哪些路径本来就没 token」
    —— SPA / 静态挂载 / docs / OPTIONS 预检 / login —— 那是**一份会漂移的路径清单**，正是 #258
    刻意避开的东西（漏一条 = 打断跨域前端或把用户锁在登录页外）。
    → 改为：**中间件只在「凭证可用且租户可服务」时设 ctx，否则什么都不做**；401 的责任回到
    `get_current_user`（鉴权本来就该在那），它对 tid 缺失/畸形/租户不可服务一律 401。
    效果等价、且**不需要任何「无 token 端点」清单**。
    ⚠️ 不设 ctx **不等于**放行：下游任何碰 DB 的代码都会撞 fail-closed（`current_tenant()` raise）
    ⇒ 漏网只会**响亮崩掉**，不会静默跨租户供数。

    ⭐ **v0.9.20（P-c）已 lift R-T-GATE** —— 原本这里的第一行是
    `tenant_repo.assert_no_second_active_tenant_served()`，它在出现 **>1 个 active 租户**时 raise，
    使**整站（含 `/api/platform/*`）全部 fail-closed**。该门连同函数本体已**物理删除**。

    ⇒ **现在起，「当前是哪家公司」完全由 JWT 的 `tid` 决定**，本函数不再关心一共有几家。
    ⚠️ **正因如此，本函数不得有任何回退**：解析不出 tid、或 tid 指向的租户不可服务 ⇒ 返 `None`
    （不设 ctx ⇒ 下游 `get_current_user` 401），**绝不能挑一个租户顶上** ——
    那是 OOS-1v2 禁的 fail-open 全局回退，且在多租户下等于**跨租户供数**。
    守护：`test_R15_no_generic_fallback`（AST 静态封死回退）+ `test_unusable_credential_leaves_ctx_unset`。

    0 active 的语义**未变**：受保护 API 因无可解析租户自然 401；login 返回统一的
    「账号或密码错误」而不是 500。
    """
    payload = _bearer_payload(request)
    if payload is None:
        return None

    tid = payload.get("tid")
    # R-10 D9 严格化：`type(tid) is int and tid > 0`。实测 sqlite3 INTEGER affinity 会把
    # `'1'` / `1.0` / `True` 三者都匹配到整型 id=1 ⇒ 松了就是可伪造的租户选择。
    if type(tid) is not int or tid <= 0:
        return None

    # 停用 / 不存在 → None（**绝不回退**到任何默认租户 —— 回退 = 静默跨租户供数，OOS-1v2）
    tenant = tenant_repo.resolve_tenant_by_id(tid)
    if tenant is None:
        # v0.9.4 step 6：记一行 INFO —— 运维要能把「租户停用/已删」与「坏 token」分开。
        # 只记 tid，不记 token / 路径 / 业务内容。**不是 WARN**：这是预期的 fail-closed 路径
        #（真·漂移才 WARN，见 core/tenant_context.assert_tenant_context）。
        # 触发前提是**已验签**的 token + 正整数 tid ⇒ 只有真实（或曾经真实）用户会走到，无扫描噪音。
        logger.info(f"[tenant-resolve] 不可服务的租户 tid={tid}（停用或不存在）→ 不设 ctx")
    return tenant


async def tenant_context_middleware(request, call_next):
    """v0.9.0 C2 请求作用域 tenant ctx（set-without-reset）。

    传播机制（Starlette 1.3.1 BaseHTTPMiddleware 源码 + 20 并发实证 · 守护者 Stage 4 V1 亲验）：本函数于
    call_next 前 set → BaseHTTPMiddleware 在 set **之后** `start_soon` spawn 下游子任务 → 子任务 copy_context
    含本 tenant → endpoint + SSE `async def generate()`（AsyncIterable 非 threadpool）均继承；20 并发
    distinct-tenant = 20/20 无泄漏。get_conn 每连接读 current_tenant() → 传播断即 raise（非 fail-open）。
    **禁 reset**（executor fork 场景丢 ctx → 那 3 处走 copy_context().run 显式传播）。

    v0.9.4 step 5：`resolve_for_request` 可能返 **None**（无可用凭证 / 租户不可服务）⇒ 此时
    **不设 ctx**，让 fail-closed 接管（见 resolve_for_request docstring：中间件永不 401）。
    """
    tenant = resolve_for_request(request)
    if tenant is not None:
        _tenant_ctx.set_active_tenant(tenant)   # set-without-reset
    return await call_next(request)
