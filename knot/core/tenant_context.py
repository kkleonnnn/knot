"""knot.core.tenant_context — 多租户 ContextVar（fail-closed · 无全局回退）。

镜像 `services/agents/catalog.py` 的请求作用域 ContextVar 三层模式（set-without-reset），
但**刻意去掉全局回退**：`current_tenant()` 未 set → raise `TenantContextError`
（吸取守护者「带全局回退的租户 ContextVar = 虚假隔离」裁定）。tenant 是安全边界 → fail-closed。

core 横切层：api/services/repositories 均可依赖；本模块**零 services 依赖**
（import-linter 9 contracts 零新增方向）。
v0.9.4 step 6：漂移已接**结构化 WARN + 进程计数器**（`assert_tenant_context` / `tenant_drift_count`）；
**LOCKED 的 audit-on-drift 仍未结清**（R-10 显式登记）—— 审计要写「哪个平台租户」，
而 **v0.9.5 鉴权拆分已落地却仍不足**：E1 选 out-of-band 共享密钥（无「谁做的」身份）+ E2 零平台写操作
⇒ **平台侧仍无审计落点**（`audit_service.log` → `get_conn` = 租户库）。
⇒ **随平台审计落点（`platform_audit`，B-3 之后）一起做**；core 层零 services 依赖也让 audit 写入不落本模块。
"""
from __future__ import annotations

import contextvars
import threading

from knot.core.logging_setup import logger

# v0.9.4 step 6 漂移告警：进程级计数器 + 锁。**刻意用 dict 而非模块级 int + `global`**
# —— v0.9.3 教训：`global X; X = ...` 会让 PEP 562 代理静默失效；此处虽无代理，但「不用 global」
# 已是本仓的既定手法（改一处不必回头查有没有代理/哨兵被绕过）。
_drift_lock = threading.Lock()
_drift_state = {"count": 0}

# 请求/启动/调度作用域 active tenant（未 set → current_tenant() raise，无全局回退 = fail-closed）
_active_tenant_ctx: contextvars.ContextVar = contextvars.ContextVar(
    "_active_tenant_ctx", default=None
)


class TenantContextError(RuntimeError):
    """无 active tenant ctx / 租户漂移 → fail-closed raise（严禁全局回退）。"""


class TenantDriftError(TenantContextError):
    """**真漂移**专用（v0.9.9）：ctx 非 None **但与调用方声明的 tid 不符**。

    ⚠️ **为什么要一个专门的类型**：调用方需要**区分**两种失败 ——
    「未 set ctx」是 v0.9.4 明写的**预期路径**（租户停用/不存在时 middleware 就不设），
    而「set 了但对不上」是**事故**。若调用方靠自己重新判断，判据就复制成了两份（N 份清单病）
    ⇒ **判断留在本模块，调用方只需 `except TenantDriftError`**。

    ⚠️⚠️ **子类化的已知风险，已靠枚举关闭**（v0.9.9 M2）：任何既有 `except TenantContextError`
    都会**连带吞掉**本异常，而它比「无 ctx」严重得多。**全仓恰 2 处**（实测）：
    - `api/deps.py` —— 本类型的**唯一**预期捕获点（先接本类记审计、再接父类只 401）；
    - `api/auth.py` —— 登录路径，**结构上到不了**：`_resolve_login_tenant` **从不调**
      `assert_tenant_context`，它接的是「按 slug 解析租户」的失败。
    ⇒ **新增第三处 `except TenantContextError` 前，先确认它不在漂移路径上。**

    携带 `expected` / `actual` 供调用方写审计（`core` 不能自己写 —— `core-no-business` 禁
    `knot.core → knot.repositories`；记录点因此必须在能到达 repositories 的那一层）。
    """

    def __init__(self, message: str, *, expected: int | None = None, actual=None):
        super().__init__(message)
        self.expected = expected
        self.actual = actual


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


def clear_active_tenant() -> contextvars.Token:
    """**显式清空**当前作用域 ctx（返回 Token 供 finally reset）—— v0.9.4 R-13 入口不变量。

    用途：**自建-ctx 端点**（login / totp-verify —— 它们必须从请求内容而非 Authorization 决定租户）
    在入口无条件调用，把「可能是别的租户的 ctx」清掉，再从请求内容解析并 set 自己的。

    为何不写 `set_active_tenant(None)`：那个函数签名收 `dict`，塞 None 是滥用；更重要的是
    **本函数名就是 R-13 的标记** —— 「哪些端点自建 ctx」由调用本函数的地方**自证**，
    不需要第二份会漂移的端点清单（正是 #258 刻意避开的东西）。

    清掉之后 ctx 为 None ⇒ `current_tenant()` fail-closed raise ⇒ 「入口到 set-ctx 之间误调任何
    依赖 ctx 的东西」会**当场响亮崩掉**，而不是静默串到别的租户。R-13 因此是**运行期自执行**的，
    不靠静态清单去猜「哪些调用依赖 ctx」（那是个传递闭包，静态判不准）。
    """
    return _active_tenant_ctx.set(None)


def current_tenant() -> dict:
    """当前 active tenant（**fail-closed**：未 set → raise TenantContextError，无全局回退）。"""
    t = _active_tenant_ctx.get()
    if t is None:
        raise TenantContextError(
            "无 active tenant context（fail-closed）—— 请求经 middleware set，启动/调度/脚本须显式 set_active_tenant"
        )
    return t


#: ⭐ **起源租户 id**（v0.9.6）—— 「多租户之前就存在的那一个」。
#: **不是任意选的**：`tenant_repo.seed_default_tenant` **硬编 `id=1`** 且只在 `tenants` 空时 seed；
#: `tenancy_migration` 把 pre-tenancy 的 `knot.db` 搬进 tenant#1 ⇒ 它就是部署方本人。
#: ⚠️ **`db_dir` 不可用作标识**（生产 `tenants/1` / 测试 `.` = 环境相关）；`slug` 语义上可改名。
#: ⚠️ 本模块只持「**谁是起源租户**」这个**租户身份事实**；「**file catalog / HTTP 出网归起源租户**」
#: 是**决定**，写在三个调用点的 docstring 里（`catalog_loaders.load_file_layer` /
#: `http_planner.pick_http_route` / `adapters/http/executor.execute`）。
OWNER_TENANT_ID = 1


def is_owner_tenant() -> bool:
    """当前租户是否 = 起源租户（**fail-closed**：无 ctx → `current_tenant()` raise）。

    ⭐ **为什么谓词住在 `core`**：`.importlinter` 的 `adapters-no-business` **禁 `knot.services`**
    ⇒ 若把它放 `services` 层（如 `catalog_loaders`），`adapters/http/executor` **根本 import 不到**
    ⇒ `core` 是唯一合法的共享住所（**结构性唯一解，不是取舍**）。
    ⭐ **严格 int 判定**：`type(tid) is int` —— 接 v0.9.4 的 tid 严格化教训
    （`True == 1` 且 `1.0 == 1`，宽松比较会把 `True`/`1.0` 当成 owner）。
    """
    tid = current_tenant().get("id")
    return type(tid) is int and tid == OWNER_TENANT_ID


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
    v0.9.4 step 5 起有真实生产调用点（`api/deps.get_current_user`，此前 0 处）：它比对 **JWT 声明的 tid**
    与 **middleware 设进 ctx 的租户**，挡的是 B-4「**ctx 非 None 但是错的租户**」—— `get_conn` 只判
    ctx 是否为 None，对该模式**免疫**（按错 tid 建槽也会命中并返 200）。

    **两种失败刻意分开**（v0.9.4 step 6）：
    - **未 set**（ctx is None）→ 不是漂移，**不告警不计数**。step 5 起这是**预期路径**：token 声明的租户
      已停用/不存在时 middleware 就不设 ctx ⇒ 若把它算成漂移，每个这类请求都会刷一条 WARN（噪音淹没真信号）。
    - **set 了但对不上** → **真漂移**：结构化 WARN + 进程计数器。单租户下**不应发生**（同源同 token）；
      发生即代表 ctx 被别处污染 / async 传播串了 / 有第二条设 ctx 的路径。

    ✅ **R-10 audit-on-drift 已于 v0.9.9 兑现**（自 v0.9.4 登记、连续 5 片未兑现后）：
    真漂移抛 `TenantDriftError`，由**调用方**（`api/deps.get_current_user`）写**平台审计**。
    ⚠️ **写平台表而非租户表是承重决定**：漂移那一刻「当前是哪家公司」这个信息**本身就是坏的**
    ⇒ 写租户库就是写进**两个互斥声明中可能错的那一个** ——
    后果不止「要相信坏信息」，而是**把安全事件披露给错误那家公司的 admin、
    同时对该知道的那家隐藏它** = 一次跨租户信息披露。平台表 ctx-free ⇒ 唯一可信落点。
    ⚠️ 记录**不能落在本模块**：`core-no-business` 禁 `knot.core → knot.repositories`。
    """
    current = _active_tenant_ctx.get()
    if current is None:
        raise TenantContextError(
            "无 active tenant context（fail-closed）—— 请求经 middleware set，"
            "启动/调度/脚本须显式 set_active_tenant"
        )
    actual = current.get("id")
    if actual != expected_tenant_id:
        with _drift_lock:
            _drift_state["count"] += 1
            seq = _drift_state["count"]
        # 结构化：固定事件名便于运维 grep / 告警规则挂钩。**只记 id，不记 db_dir/路径/业务内容**
        #（同 v0.9.3 F-3' 观测纪律：日志只记规模/来源，严禁记内容）。
        logger.warning(
            f"[tenant-drift] tenant_ctx_drift expected={expected_tenant_id} "
            f"actual={actual} seq={seq}"
        )
        # v0.9.9：抛**专门的子类** —— 调用方据此区分「事故」与「预期路径」，并写平台审计。
        # ⚠️ 计数器与 WARN 都在**本行之前**（`core` 先跑再抛，调用方才可能写审计）
        # ⇒ 「审计写故障时两个信号一起消失」在结构上不可能发生（M5 自验）。
        raise TenantDriftError(
            f"tenant context 漂移：expected={expected_tenant_id} actual={actual}",
            expected=expected_tenant_id, actual=actual,
        )


def tenant_drift_count() -> int:
    """进程内漂移计数（**诊断用，非租户数据**）—— 只增不减，无 reset API。

    刻意**不按租户分键**：漂移正意味着「当前 ctx 不可信」，用它去构造键就是用坏的东西当键
    （且 `tenant_cache_key` 会 raise）。这是运维告警计数器，不是业务数据 ⇒ 进程全局正确。
    测试用**前后差值**断言（无 reset 是刻意的：能 reset 的计数器会被误当成可清账的状态）。
    """
    with _drift_lock:
        return _drift_state["count"]


def reraise_if_tenant_error(e: BaseException) -> None:
    """v0.9.3 D8'：catalog 读的 fail-soft handler 里调用 —— e 是 `TenantContextError` 则**重抛**（fail-closed），
    否则原样返回、让调用方走它既有的降级。

    作用 = 把「**缺 tenant ctx**」从「其他异常」里分离：前者绝不能被降级吞掉（降级后果按站点不同 ——
    脱敏静默 no-op / RELATIONS 段空致错数 / 把部署级 file catalog 当成该租户内容），后者保持既有可用性优先。
    收成单一 helper 而非各站点 inline，因此 revert harness 也是单点（改此处即可验全部站点）。
    """
    if isinstance(e, TenantContextError):
        raise e
