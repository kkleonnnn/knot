"""knot.adapters.http.url_allowlist — URL host 出网白名单（v0.6.1.4 · **v0.9.7 per-tenant 域化**）

OVERRIDE #3 安全模型核心 — 防 admin UI 用户配置任意 endpoint 攻击内网。

⭐ **v0.9.7（B-3 ③ egress 租户域化）**：allowlist 从**进程级 env** 变成 **per-tenant**。
**为什么必须域化**：进程级 allowlist ⇒ **每个租户都继承部署方内网 API 主机的可达权**。
即便 ②（per-tenant 凭据）落地后各租户只能用自己的凭据，「把部署方真实 API 主机填进自己的
数据源、用自己的 token 去打」这件事仍然成立 —— 拿不到数据，但**探测内网**成立（若该 API 有
任何免鉴权端点则直接暴露）⇒ 正是本文件原本写的威胁模型「防 admin UI 用户配置任意 endpoint
攻击内网」在多租户下**按租户失效**。

**解析规则（三态；判据必须是 `is None` —— 见 `resolve_allowed_hosts`）**：

| 租户 | `tenants.allowed_http_hosts` | 结果 |
|---|---|---|
| 任意 | 非空串 | 该 host 集（**永不**与 env / 其他租户取交集或并集） |
| 非起源 | NULL | 空集 = 全拒绝（fail-closed） |
| 起源（`OWNER_TENANT_ID`） | NULL（**未配置**） | 回退 env `KNOT_HTTP_ALLOWED_HOSTS` + 启动期 WARN |
| 任意 | `''` / 全空白（**已配置为空**） | 空集 = 全拒绝；起源租户**也不**回退 env |

**为什么「替换」而非「与 env 取交集」**：env 是**起源租户的** allowlist ⇒ 为让客租户访问 host X
而把 X 写进 env，会**同时放宽起源租户的可达面** ⇒ 交集在这里是**反向的**。

**为什么载体是 `tenants` 的一列**（而非独立表 / resolver hook / 参数传入）：
- OOS-1v2 要求租户归属列只在平台库；门必须在**能力处**（`executor.execute`）；
  而 `.importlinter` 的 `adapters-no-business` 禁 `knot.adapters` → `knot.repositories`
  ⇒ 能力处**不能**直接读平台库。
- `tenant_repo.get_tenant` / `list_active_tenants` **都是 `SELECT *`**，而 tenant ctx **就是那一行**
  ⇒ 加列即自动进 ctx，只读 `knot.core.tenant_context` 即可（v0.9.6 owner 门已立此先例）
  ⇒ 零分层例外、零新模式、零启动 wiring、**零额外 per-request 查询**。
（四个被否决备选及理由：`docs/plans/v0.9.7-http-per-tenant-credentials-egress.md` §7）

env 格式（逗号分隔；**仅起源租户回退用**）：
    KNOT_HTTP_ALLOWED_HOSTS=api.example.com,api2.example.com

红线：
- **默认拒绝**（未配置 + 非起源租户 = 全拒绝；env 未设 = 全拒绝）= secure by default
- 部署方 admin UI 用户无权改 env（K8s ConfigMap 是运维资产），**也无权改该列** ——
  全仓零平台写端点（v0.9.5 E2）⇒ 唯一配置途径是运维直接 `UPDATE`，SQL 原文见 DEPLOY.md
- 双层守护：allowlist 控制 base URL host，catalog 控制具体 path
- **消息不得枚举 allowlist**（v0.9.7 D11）—— 见 `check_url_allowed`
- **R-PB2-3 措辞订正（v0.9.7）**：原写「env 未设 + catalog 含 `source:http` 表 → **启动** fail-fast」
  —— 全仓**无启动期 allowlist 检查**，实际是**首次查询时** `HTTPAuthError`。
  且 per-tenant 化后**启动期只解析一个租户**（`resolve_single_tenant`）⇒ 对**未被解析的租户**
  做启动校验**结构上不可能** ⇒ **实现它才是错的**。本片只修措辞，不实现。
"""
from __future__ import annotations

import logging as _log
import os

#: 起源租户 allowlist 的回退源（env **名**；env **值**绝不进消息/日志/响应 —— #262）
ENV_NAME = "KNOT_HTTP_ALLOWED_HOSTS"

#: 平台库 `tenants` 表的 per-tenant allowlist 列名（v0.9.7 B-3 ③）
COLUMN_NAME = "allowed_http_hosts"

_logger = _log.getLogger(__name__)

#: 已告警过的**坏 allowlist 条目**（`_parse` 每次调用都重跑 ⇒ 不去重会每请求刷一条）。
_BAD_ENTRY_WARNED: set[str] = set()


def _parse(raw: str | None) -> set[str]:
    """逗号分隔 → host 集；空白项丢弃 ⇒ `''` / `' '` / `' , '` 全部 → 空集（= 全拒绝）。

    ⭐ **v0.9.21：条目也过 `url_canon` 的同一口径**（Stage 2 B-P1-1）。
    不这么做的话，等值的两边只规范化一边 = 拿**两种产出方式**比对（v3.1-C 六问⑤）：
    实测运维写的 `例え.jp` 会与请求侧的 `xn--r8jz45g.jp` **永不匹配**、`::1` 与 `[::1]` 同理
    —— fail-closed，但**与 bug 不可区分**（v0.9.7 M5 同族）。
    ⚠️ 顺带修一个**既有缺陷**（不是本片引入的）：原实现只 `strip()` **不小写化**，
    而 `urlparse().hostname` **今天也返回小写** ⇒ 运维写 `Allowed.Corp` **今天就已经两个方向全拒**。

    ⚠️ **不可规范化的条目丢弃 + WARN，绝不静默保留** —— 保留会得到一个**永不匹配**的串，
    那与「写错了一个字母」不可区分（DEPLOY「多租户运维门」已写明这条行为）。
    """
    from knot.adapters.http.url_canon import canonical_host_of_entry

    out: set[str] = set()
    for item in (raw or "").split(","):
        e = item.strip()
        if not e:
            continue
        host = canonical_host_of_entry(e)
        if host is None:
            # ⚠️ **去重**：`_parse` 在**每次** `is_url_allowed` / `check_url_allowed` 里都会重跑
            #    ⇒ 不去重的话一个坏条目会**每请求刷一条 WARN**（自验时实测刷了 7 次）。
            #    与端口告警同理：这是**配置问题**，说一次就够。
            if e not in _BAD_ENTRY_WARNED:
                _BAD_ENTRY_WARNED.add(e)
                _logger.warning(            # 只记条目本身（运维自己配的，不是新信息）
                    f"egress allowlist 条目无法解析成主机名，**已丢弃**: {e!r}"
                )
            continue
        out.add(host)
    return out


def resolve_allowed_hosts() -> tuple[set[str], str]:
    """→ `(host 集, 来源标签)`。**来源标签仅供日志/诊断，不得进客户端消息。**

    ⚠️ **无 tenant ctx ⇒ 抛 `TenantContextError`**（`current_tenant()` 既有行为，与 `get_conn` 同形）。
    **刻意不 catch**：v0.9.4 MF3 的教训是「fail-soft 吞 `TenantContextError` = 安全信号静默丢失」。
    这里吞掉虽然是 fail-**closed**（空集 = 拒绝），但会**掩盖 ctx 缺失这个事实**；让它响。
    """
    from knot.core.tenant_context import current_tenant, is_owner_tenant

    # ⚠️ **必须 `.get()`，不得下标**：ctx 契约（`set_active_tenant` docstring）**只保证 `id` / `db_dir`**；
    # 测侧有 15 处手工构造 ctx（多数只有 `{"id":…, "db_dir":…}`），**无一带本列** ⇒ 下标会 KeyError 15 处。
    # `.get()` → None → 非起源租户拒 / 起源租户回退 env，**两个方向都安全**（守护者 must-fix M2）。
    raw = current_tenant().get(COLUMN_NAME)

    # ⚠️⚠️ **判据必须是 `is None`；严禁 `if raw:` 或 `if raw and raw.strip():`** ——
    # 那样 `''` / `'  '`（部署方**明确表达的「禁」**）会落回 env ⇒ 静默变成「按 env 放行」。
    # **这是本片唯一一个能把 fail-closed 写成 fail-open 的地方**（守护者 must-fix M1）。
    if raw is None:                                          # 未配置
        if not is_owner_tenant():
            return set(), "unconfigured"                     # 非起源租户 ⇒ 全拒绝
        return _parse(os.environ.get(ENV_NAME, "")), "env-fallback"
    return _parse(raw), "column"                             # 已配置（可能为空 ⇒ 拒绝，且不回退）


def get_allowed_hosts() -> set[str]:
    """当前租户允许出网的 host 集。

    ⭐ **本函数签名仍不变**（v0.9.7 起）—— 它经 `resolve_allowed_hosts()` 自动 per-tenant 化。
    ⚠️ **但 v0.9.21 起 `check_url_allowed` 的签名变了**（改为**回传规范化后的 URL**）：
    调用方**必须发那个返回值**，否则「门校验的」与「真正被发的」又是两个东西。
    ⇒ 原先那句「三个生产调用点零改动跟随」**已作废**，别再照它推断。
    ⚠️ 契约变化：v0.9.7 起本函数**可能抛** `TenantContextError`（无 tenant ctx 时）。
    """
    return resolve_allowed_hosts()[0]


def is_url_allowed(url: str) -> bool:
    """判断 URL 是否在**当前租户的** allowlist 内。

    检查 host 字面匹配（**仍不含端口** —— v0.9.21 只给端口加**可诊断告警**，不改放行语义；
    改成 `host:port` 精确匹配会让**所有现存纯 host 配置立刻全拒**，那要单独一片 + 迁移）。
    ⚠️ 「端口/子域/IP 字面校验缺失」这个既有弱点**按租户放大**（每个租户各自的列都带同一弱点，
    且各租户互不知情）—— 端口那半已由 `check_url_allowed` 的 WARN 变得**可诊断**，其余仍是 backlog。

    ⭐ **v0.9.21：host 改由 `url_canon.canonicalize()` 算**（与 `requests` 将要施加的规范化同一套）。
    此前用 `urlparse().hostname`，而实际连接由 urllib3 解析 ⇒ 同一串两者可给出**不同 host**
    （`http://127.0.0.1:9999\\@allowed.corp/x`：门看到 `allowed.corp` 放行、实连 `127.0.0.1`）。
    ⚠️ **本函数只答「能不能去」，不回传规范化串** —— 写侧（`admin/datasources`）只需要 yes/no，
    且**不得**把规范化串落进存储（规范化会给裸 host 补 `/` ⇒ `{base_url}` 拼接会得 `//`）。

    Args:
        url: 完整 URL（如 https://api.example.com/v1/...）

    Returns:
        True 在 allowlist；False 不在（**含无法规范化** ⇒ fail-closed）
    """
    if not url:
        return False
    from knot.adapters.http.url_canon import UrlCanonError, canonicalize

    try:
        _, host = canonicalize(url)
    except UrlCanonError:
        return False                        # 无法规范化 ⇒ 不放行（fail-closed）
    return host in get_allowed_hosts()


#: 已告警过的 `host:port` —— 端口告警是**配置问题**，每请求刷一条会淹掉日志。
#: ⚠️ 进程内去重 ⇒ 多副本/多 worker 下每个进程各告警一次（可接受：它是诊断不是审计）。
_PORT_WARNED: set[str] = set()


def _warn_if_unusual_port(normalized: str, host: str) -> None:
    """host 命中 allowlist 但端口非 80/443 ⇒ **告警一次**（不改放行/拒绝语义）。

    ⚠️ **为什么只告警不拦**：allowlist 现存值全是**纯 host 字面**
    ⇒ 改成 `host:port` 精确匹配会让所有现存配置**立刻全拒**（要单独一片 + 迁移）。
    ⇒ 本片只让它**可诊断**：allowlist 内主机的任意端口仍放行（内网端口仍可扫），
      但至少运维能在日志里看见「有人在往一个不寻常的端口打」。
    ⚠️ **诚实收窄**：这不是「端口受控」，只是「端口可见」。
    """
    from urllib3.util import parse_url

    port = parse_url(normalized).port
    if port is None or port in (80, 443):
        return
    key = f"{host}:{port}"
    if key in _PORT_WARNED:
        return
    _PORT_WARNED.add(key)
    _logger.warning(
        f"egress 目标端口非 80/443: host={host!r} port={port} —— "
        "allowlist **只比对主机名、不含端口** ⇒ 该主机的任意端口都会放行。"
        "若这不是预期，请复核该数据源/告警地址的配置。"
    )


def check_url_allowed(url: str) -> str:
    """守护检查 — 不在**本租户** allowlist 则抛 `HTTPAuthError`；**返回规范化后的 URL**。

    ⭐⭐ **v0.9.21：签名从 `-> None` 改为 `-> str`，调用方必须发这个返回值。**
    否则门校验的串与真正被发的串**不是同一个** —— 而那正是本片要修的缺陷本身。

    ⭐ **端口告警在这一行**（出网前），不在写入时：写入时校验会被 `url_template` **结构性击穿**
    （`PUT /api/admin/catalog` 的 `url_template` 零校验 + `executor` 是 `str.replace`
    ⇒ `{base_url}:9402` 让**出网那一刻**的端口不是写入时校验的那个）。
    ⇒ 「校验的 X 必须是被用的 X」这条对端口同样适用。

    ⭐ **v0.9.7 D11：消息不得枚举 allowlist**（守护者 must-fix M4 —— 实读坐实原实现**不干净**）。
    原写法 `f"(allowed: {sorted(allowed)})"` 把**整份白名单**插进异常，而这条异常经
    `http_planner.run_http_step` 的 `except Exception` → `result["error"]` → `api/query.py`
    **原样 yield 给客户端** ⇒ 租户 admin 就能把部署方**整份 egress allowlist** 读出来
    = **与 #262 完全同类**（#262 泄的是 `JWT_SECRET` / `KNOT_MASTER_KEY`，本处泄的是
    `KNOT_HTTP_ALLOWED_HOSTS` 的**值**）。原消息还点名了 env ⇒ 告诉租户「这机制叫什么、去猜什么」。

    ⇒ 客户端消息只回显**调用方自己给的 host**（他自己配的，不是新信息）；诊断进**日志**，
    且只记**来源机制**（`env-fallback` / `column` / `unconfigured`），**不记内容、不记条目数**
    —— #262 的规则是 env **值**不得进消息 / **日志** / 响应，而「条目数」在污点传播上仍是 env 派生
    （实测被 `test_SEC_no_env_value_interpolated_into_messages` 拦下，详见手册 D11）。
    """
    from knot.adapters.http.base import HTTPAuthError
    from knot.adapters.http.url_canon import UrlCanonError, canonicalize

    try:
        normalized, host = canonicalize(url)
    except UrlCanonError as e:
        # ⚠️ `UrlCanonError` 的消息**不含 URL**（它有活链路到客户端）⇒ 可直接外露
        raise HTTPAuthError(str(e)) from None

    if host in get_allowed_hosts():
        _warn_if_unusual_port(normalized, host)
        return normalized

    from knot.core.tenant_context import current_tenant
    _logger.warning(                                    # 日志 ≠ 响应：来源机制可记，内容不可
        f"egress 拒绝: host={host!r} tenant={current_tenant().get('id')} "
        f"allowlist 来源={resolve_allowed_hosts()[1]}"
    )
    raise HTTPAuthError(f"目标主机 {host!r} 不在本租户的出网白名单内")


def warn_if_owner_using_env_fallback(owner_row: dict | None) -> None:
    """启动期 WARN：起源租户仍在用 **env 回退**（未迁移到 `tenants.allowed_http_hosts`）。

    **为什么不做启动期自动 seed**（把 env 值写进列）：那会制造**漂移** —— 运维改 ConfigMap 重启后
    列不跟随，形成「改了没反应」的静默 no-op。回退 + WARN 让 env 在迁移完成前**保持权威**。

    ⚠️ **为什么 `owner_row` 由调用方传入**（`knot/main.py` 启动钩子）：`adapters` 不得 import
    `repositories`（`.importlinter` `adapters-no-business`）⇒ 本函数拿不到平台库。
    这与**被否决的备选 D**（「把 allowed hosts 当参数传进 `execute`」）**不同类**：
    那里传的是**门的判据** ⇒ 门变 caller-trusted；这里传的是**一条诊断日志的输入** ⇒ 传错只会
    少打/多打一条 WARN，**不影响任何授权判定**。**判据：这个参数会不会决定「放不放行」。**

    ⚠️ **只报 env 名，绝不报 env 值，且不枚举 host**（#262）。
    """
    if owner_row is None:
        _logger.warning("[egress] 起源租户不存在 —— 无法判断 allowlist 配置状态（平台库异常？）")
        return
    if owner_row.get(COLUMN_NAME) is not None:
        return                                          # 已迁移到列 ⇒ 静默
    # ⚠️ **连「条目数」都不打**（Stage 1' 的 D11 原写「记条目数」，被 #262 AST 哨兵拦下 —— 它对
    # 「从 env 读出的值」做污点传播，而 `len(...)` 仍是 env 派生 ⇒ 哨兵分不清计数与内容，**这是对的**）。
    # 两条路里选了「不打」而非「加 `_ALLOWED` 例外」：例外是按 (文件, **变量名**) 放行 ⇒ 本文件将来
    # 任何同名变量都会静默获得豁免 = 弱化哨兵。而计数本就可有可无 —— 「来源=env 回退」已足够指路，
    # 且 env 是运维自己的 ConfigMap，他自己读得到。
    _logger.warning(
        f"[egress] 起源租户的 {COLUMN_NAME} 未配置 → 回退 env {ENV_NAME}。"
        f"建议迁移到 tenants.{COLUMN_NAME}（per-tenant）—— SQL 见 DEPLOY.md「多租户运维门」。"
    )
