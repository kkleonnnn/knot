"""knot.api.platform_admin — 平台面的**平行认证路径**（out-of-band 共享密钥）+ 唯一只读端点。

## 为什么是平行路径，而不是「给 `require_tenant_admin` 加个角色分支」
`get_current_user` **结构性拒绝无租户身份**（v0.9.5 测绘 F2，逐字复核过）：
1. `deps.create_token` 强制 `tid = current_tenant()["id"]`（fail-closed）⇒ **签不出无 tid 的 token**；
2. `get_current_user` 无 `tid` → 401 `JWT_NO_TID`，且 `assert_tenant_context(tid)` 必须与中间件 ctx 相符；
3. 其后 `get_user_by_id` 读**租户库**。
⇒ 平台身份若硬塞进这条链路，**每个平台请求都得先「假装在某个租户里」** —— 正是 OOS-1v2 禁止的
fail-open 形状。故本模块自带认证，**与 `deps.py` 物理分开**（放一起早晚会被混用）。

## E1：平台身份 = out-of-band 共享密钥（资深 2026-07-29 拍板）
**刻意不建 `platform_admins` 表**，也**不往租户 `users.role` 加值** ——
两条放弃路径各有 CI tripwire：`test_iso4_platform_db_only_tenants_table`（建表即红）+
`test_auth_split_invariants.py::test_VALID_ROLES_pinned`（加 role 值即红）。
代价（DEPLOY.md 已写明）：**无「谁做的」身份** ⇒ 平台侧无法审计到人；
**无 `token_version` 等价物 ⇒ 完全无吊销机制**，轮换 = 改 env + 重启。

## 与租户 JWT **语法不相交**（结构不变量，非配置运气）
密钥必须 `kpa_` 前缀 + **禁含 `.`** + ≥32 字符。
JWS compact **恒含 2 个 `.`**（实测）⇒ 禁 `.` 使一枚合规平台密钥**在语法上不可能是 JWT**，
反之亦然。这封掉「运维误把一枚有效用户 JWT 配成平台密钥」这条自我破坏路径 ——
**不是靠两个值恰好不相等，而是靠语法域不相交**（chore 结论：安全性只能来自结构不变量）。

## 三条 must-fix 纪律（Stage 1' 复核）
1. **单一 predicate**：`rejection_reason()` 同时服务启动 WARN 与请求期 503 ——
   一个值两处读、两处规则就是刚在 chore 治过的「N 份清单」病。
2. **未配置不 WARN**（未配 = 有意禁用）；**只对「设了但不合规」WARN**，否则运维被训练成忽略 WARN。
3. ⭐ **任何消息都不得回显密钥值** —— #262 是本仓自己的事故（`7491090` 修的正是
   `f"{auth_value_env}={header_value!r}"` 把 env 明文插进异常 ⇒ admin 可读出
   `JWT_SECRET`/`KNOT_MASTER_KEY`）。本模块的 WARN/503 **只出现 env 名与不合规原因，不出现值**。
   守护：`tests/test_no_env_value_in_messages.py`（本片已扩到 loguru 花括号形态）。

## ⚠️ 503 的 detail **刻意保持通用**（执行者决定，理由写在此）
「不合规原因」（缺前缀 / 含 `.` / 长度不足）只进**服务端日志**，**不进 HTTP 响应**：
一个未认证的调用方若能从 503 读到「长度 < 32」，就等于被告知**本部署配了弱密钥**，
且能推出期望格式。⇒ 响应统一「平台端点未启用」，与「真的没配置」不可区分（对外一致，对内可诊断）。
"""
from __future__ import annotations

import os
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.security.utils import get_authorization_scheme_param
from pydantic import BaseModel

from knot.core.logging_setup import logger
from knot.repositories import tenant_repo

router = APIRouter()

#: env 名（**调用期读**，非 settings.py —— 同 `bi_schedule` 的 `KNOT_SCHEDULER_TOKEN` /
#: `webhook.py` R-SL-69 范式：便于 `monkeypatch.setenv` 测 + 与 K8s Secret 对齐）
PLATFORM_TOKEN_ENV = "KNOT_PLATFORM_ADMIN_TOKEN"

_PREFIX = "kpa_"
_MIN_LEN = 32

#: `rejection_reason` 对「未配置」返回本哨兵 —— 调用方据此区分「有意禁用」（不 WARN）
#: 与「设了但不合规」（要 WARN）。
UNSET = "未配置"


def rejection_reason(raw: str | None) -> str | None:
    """**单一 predicate**：`None` = 合规可用；否则返回**不含密钥值**的拒绝原因。

    启动 WARN 与请求期 503 **共用本函数**（must-fix #1）—— 否则一个值两处读、两处规则。
    ⚠️ 返回串**只描述形状**（缺前缀 / 含 `.` / 长度不足），**永不包含 `raw` 本身**（#262 形状）。
    """
    if not raw:
        return UNSET
    problems = []
    if not raw.startswith(_PREFIX):
        problems.append(f"缺 `{_PREFIX}` 前缀")
    if "." in raw:
        problems.append("含 `.`（与租户 JWT 语法域重叠 —— JWS compact 恒含 2 点）")
    if len(raw) < _MIN_LEN:
        problems.append(f"长度 < {_MIN_LEN}")
    return "；".join(problems) or None


def warn_if_noncompliant() -> None:
    """启动期钩子：**只对「设了但不合规」告警**（未配置 = 有意禁用，静默）。

    存在理由：请求期只回通用 503（见模块 docstring），与「未配置」对外不可区分
    ⇒ 若不在启动期喊一声，**弱/畸形配置会静默 503**，运维在部署时看不见。
    ⭐ **为什么启动期这一次就结构上够**（守护者 Stage 4 §II② 强化）：不是靠「现网是 `Recreate` 部署」——
    而是 **env 变量在运行进程内不可变** ⇒ 改它**必然**经过一次进程启动 ⇒ 本 WARN **必然跑过一次**。
    「靠部署策略」会随运维改 RollingUpdate 而失效；「靠 env 不可变」不会。
    ⚠️ 只记 env 名 + 原因，**不记值**（#262）。
    """
    reason = rejection_reason(os.environ.get(PLATFORM_TOKEN_ENV))
    if reason is not None and reason != UNSET:
        logger.warning(
            "[platform] {} 已设置但不合规（{}）⇒ 平台端点将返回 503。"
            "要求：`{}` 前缀 + 不含 `.` + ≥{} 字符。",
            PLATFORM_TOKEN_ENV, reason, _PREFIX, _MIN_LEN,
        )


def require_platform_secret(request: Request) -> str:
    """平台面守护：未配置/不合规 → **503**（安全默认）· 不匹配 → **401**。

    ⚠️ **本依赖不设 tenant ctx、不触 `base.get_conn`**（R-v095-1）——
    平台请求**不属于任何租户**；碰租户库即是把「假装在某个租户里」这个 fail-open 形状请回来。
    解析用 `get_authorization_scheme_param`（**不手搓 `auth[7:]`** —— v0.9.4 S8 实测手搓比
    `HTTPBearer` 更严，会误拒 RFC 合法的双空格 / 尾 tab）。
    比对用 `secrets.compare_digest`（**常量时间**）；两侧 encode 成 bytes 以免非 ASCII 输入抛 `TypeError`。
    """
    configured = os.environ.get(PLATFORM_TOKEN_ENV)
    if rejection_reason(configured) is not None:
        # detail 刻意通用：不告诉调用方「配了但弱」，也不泄露期望格式（见模块 docstring）
        raise HTTPException(status_code=503, detail="平台端点未启用")
    scheme, presented = get_authorization_scheme_param(request.headers.get("authorization") or "")
    if scheme.lower() != "bearer" or not secrets.compare_digest(
        presented.encode("utf-8", "surrogatepass"), str(configured).encode("utf-8")
    ):
        raise HTTPException(status_code=401, detail="平台凭证无效")
    return "platform"


class TenantPublic(BaseModel):
    """平台端点的**显式响应契约**（Stage 3 R8 前半）。

    为什么强制 `response_model` 而不是 dict 直转：**B-3 已排期**给平台层加 per-tenant `http_spec`
    凭据 + per-tenant 初始口令 ⇒ 那时 `SELECT *` + dict 直转会**自动**把新列吐出去。
    这不是假设风险，是已登记的路线。⇒ 投影在 SQL 层显式（`tenant_repo.list_tenants_public`）
    **且**在响应层显式（本模型）—— 两道，任一道挡住新列。
    """

    id: int
    slug: str
    name: str
    status: str
    db_dir: str
    created_at: str | None = None


@router.get("/api/platform/tenants", response_model=list[TenantPublic])
async def list_tenants_platform(
    response: Response, _: str = Depends(require_platform_secret)
) -> list:
    """列出全部租户（**只读**）。

    ⚠️ **本端点是平台面唯一的 HTTP 表面，且刻意只读**（E2：本片零 platform 写操作）——
    `/api/platform/` 前缀下禁一切 POST/PUT/PATCH/DELETE，由
    `tests/test_tenant_isolation.py::test_iso6b_no_write_methods_under_platform_prefix` 守。

    ⚠️ **它不是运维逃生舱，别这么用**：`assert_no_second_active_tenant_served()` 是
    `tenant_resolution.resolve_for_request` 的**第一行**（在 Bearer 解析与路径判断之前）
    ⇒ 出现第二个 active 租户时**整站含本端点全部 fail-closed**。
    本端点存在的**唯一**理由是：零消费者的 dependency 无法 revert-to-bad 证明 ⇒ 违反 R-C3。
    """
    response.headers["Cache-Control"] = "no-store"
    return tenant_repo.list_tenants_public()
