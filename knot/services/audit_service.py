"""knot/services/audit_service.py — 审计写入入口（v0.4.6）。

红线落点：
- R-47 fail-soft：repo.insert 失败 → logger.error 不阻断业务
- R-48 PII 严禁入 detail_json：字段名命中 _PII_BLACKLIST → ••••redacted••••
- R-51 actor 必从 Depends(get_current_user) 取，严禁信 client body
- R-55 action 必走 AuditAction Literal（type-check + 运行时 audit_repo 校验）
- R-59 密文也不入：字段名命中即 redact，enc_v1: 前缀也不漏
- R-62 _PII_BLACKLIST 必含 v0.4.5 全 6 类敏感字段（与 settings_repo._SENSITIVE_KEYS / user_repo._USER_ENCRYPTED_COLS / data_source_repo._DS_ENCRYPTED_COLS 同步）
- R-64 失败盲区可观测：模块级 _audit_write_failures_total 计数器（prometheus hook 预埋）
- R-65 errors 树复用：本模块**严禁**重定义 Exception 子类；写入失败用 models.errors.AuditWriteError
- D7 PII scrub 递归深度上限 3（防恶意嵌套栈溢出）

设计：
- service 层**只** PII scrub + actor 解析 + fail-soft，**不**做业务字段校验
- 业务字段含义靠 action 字符串自带，不靠 service 强制
"""
from __future__ import annotations

from typing import Any

from knot.core.logging_setup import logger
from knot.repositories import audit_repo

# R-62：与 v0.4.5 锁定的敏感字段名一致 — 任意一处更新另两处必须同步（CLAUDE.md 流程红线）
# - user_repo._USER_ENCRYPTED_COLS
# - data_source_repo._DS_ENCRYPTED_COLS
# - settings_repo._SENSITIVE_KEYS
_PII_BLACKLIST = frozenset({
    # v0.4.5 加密的 5 类（去重后）
    "api_key", "openrouter_api_key", "embedding_api_key",
    "doris_password", "db_password",
    # bcrypt hash 与原始密码（与 v0.4.5 user_repo 一致）
    "password", "password_hash",
    # v0.6.3.0 B2 R-PB-B2-补2：R-62 同步偿还 — v0.6.2.0 给 user_repo._USER_ENCRYPTED_COLS
    # 加 totp_secret 时漏同步本黑名单（破 R-62）。补 totp_secret + recovery_code（兜底资产）+ secret（通用）。
    # 守护测试断言 _PII_BLACKLIST ⊇ _USER_ENCRYPTED_COLS 防未来再漏。
    "totp_secret", "recovery_code", "secret",
    # v0.8.14 分享 IM 凭据（R-BI-SHARE-2）：加进 settings_repo._SENSITIVE_KEYS 必同步此处。
    # ⚠️ _scrub 精确键匹配 → 通用 "secret" 不 substring 命中 "lark_app_secret"，须显式列出。
    # superset CI test_R62_pii_superset_of_sensitive_keys 强制（漏一即红）。
    "lark_app_secret", "telegram_bot_token",
})

_REDACTED = "••••redacted••••"
_MAX_DEPTH = 3  # D7：递归深度上限

# R-64：失败盲区可观测 — 模块级计数器（prometheus 接入前的 hook 预埋）
_audit_write_failures_total: int = 0


def get_failure_count() -> int:
    """R-64 hook：返回当前进程内 audit 写入失败累计数（admin metrics 路由可读取）。"""
    return _audit_write_failures_total


def _reset_failure_count_for_tests() -> None:
    """仅供测试 fixture 调用；生产路径不应使用。"""
    global _audit_write_failures_total
    _audit_write_failures_total = 0


def _scrub(obj: Any, depth: int = 0) -> Any:
    """递归脱敏：字段名命中 _PII_BLACKLIST → _REDACTED；超 _MAX_DEPTH 整体 redact。

    R-48 + R-59 + R-62 + D7 综合落点。
    """
    if depth >= _MAX_DEPTH:
        return _REDACTED
    if isinstance(obj, dict):
        return {
            k: (_REDACTED if k in _PII_BLACKLIST else _scrub(v, depth + 1))
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_scrub(x, depth + 1) for x in obj]
    return obj


def log(
    *,
    actor: dict | None,
    action: str,            # 类型应为 AuditAction（Literal），运行时不强制验
    resource_type: str,
    resource_id: str | int | None = None,
    success: bool = True,
    detail: dict | None = None,
    client_ip: str | None = None,
    user_agent: str | None = None,
    request_id: str | None = None,
    catalog_id: int | None = None,  # v0.6.2.5 R-PB-A1-10：末位可选 — 33+ 既有调用 byte-equal
) -> None:
    """fire-and-log（R-47）：业务路径必须 try-free 调用。

    R-51：actor 来自 token-resolved Depends(get_current_user)；
    detail 中任何 actor_id / actor_name 字段都被忽略（只走顶层 actor 参数）。
    """
    global _audit_write_failures_total
    try:
        scrubbed_detail = _scrub(detail) if detail else {}
        audit_repo.insert(
            actor_id=actor["id"] if actor else None,
            actor_role=actor.get("role") if actor else None,
            actor_name=actor.get("username") if actor else None,  # R-54 冗余快照
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id is not None else None,
            success=1 if success else 0,
            detail_json=scrubbed_detail,
            client_ip=client_ip,
            user_agent=user_agent,
            request_id=request_id,
            catalog_id=catalog_id,
        )
    except Exception as e:
        # ⭐ v0.9.4 MF3（守护者 Stage 4）：**缺 tenant ctx 必须重抛，不得 fail-soft 吞掉**。
        # 这是 v0.9.3 D8' 立的范式（`query_helper` / `desensitize` / `llm_prompt_builder` /
        # `catalog_loaders` 已各用一处），本处是**第 5 个**站点 —— 守护者在 Stage 3 逮过同一个
        # fail-soft，v0.9.4 又咬第二次：
        #   我在 Q1 声称「middleware 不 set ctx ⇒ 下游碰 DB 会**响亮崩掉**」，
        #   但 audit 这条路径上**不成立** —— 无 ctx 时 `audit_repo.insert` 抛 `TenantContextError`，
        #   被本处 R-47 fail-soft 吞成一行 `logger.error` ⇒ 调用方拿到**正常的 401**，
        #   而那条**安全审计记录静默丢失**（登录失败/越权尝试查无此事）。
        # ⇒ 「审计写不进去」与「缺租户上下文」必须分开：前者可 fail-soft（业务不阻断，R-47 原意），
        #    后者是**隔离边界失效**，绝不能降级（v0.9.3 同款判断：降级后果按站点不同，
        #    此处后果 = 安全记录丢失且无人知情）。
        from knot.core.tenant_context import reraise_if_tenant_error as _rt
        _rt(e)
        # R-47 fail-soft：业务不阻断
        logger.error(
            f"[audit] 写入失败 action={action} resource={resource_type} error={e}"
        )
        # R-64 失败盲区可观测
        _audit_write_failures_total += 1
        # R-65：不抛 AuditWriteError 出业务流（R-47 fail-soft 优先）；
        # AuditWriteError 类的存在是为未来需要可重试的审计补录场景。


def claim_auto_purge(days: int = 7) -> bool:
    """启动期 audit 自动清理的**原子认领**（v0.9.23 R10'-C）。返回「本副本是否该跑」。

    ## 为什么需要认领
    原实现是 read-then-write（读 `audit.last_purge_at` → 判 7 天 → 跑 → 成功后写回）
    ⇒ **N 个副本同时启动会同时读到同一个旧时间戳、同时判「该跑」**
    ⇒ N 个并发 chunk DELETE 打同一个租户库，而异常被调用方的 `except` 吞成一条 WARN。
    （「读-判断-写回」这个形状在 4 进程下**实测丢 74% 的更新** —— 见 R10' Stage 1 §0.5。）

    ## ⭐⭐ 为什么用**独立标记**而不是把 `last_purge_at` 提前 stamp（Stage 3 MF7）
    `last_purge_at` 的语义是「**上次成功清理**的时间」，`purge_audit_log` 在**成功之后**才写它。
    若认领时就把它推到 now：purge 抛错（会被调用方吞成 WARN）之后，
    **7 天内不再重试** ⇒ 审计表无限增长，而唯一线索是一条 WARN。
    ⇒ 认领用 `audit.purge_claimed_at`，与「完成」标记**分开**：
    认领失败只说明「这一轮有别人接了」，不说明「已经清过了」。

    ⚠️ **认领窗口 = 同一个 `days`**：认领标记推进 `days` 天 ⇒ 该窗口内其余副本认领失败；
    若那次 purge 失败，**下一个窗口**仍会有人重试（而不是等到 `last_purge_at` 过期）。
    """
    import datetime as _dt

    from knot.repositories import settings_repo

    last_done = settings_repo.get_app_setting("audit.last_purge_at", "")
    if last_done:
        try:
            if (_dt.datetime.now() - _dt.datetime.fromisoformat(last_done)).days < days:
                return False          # 确实刚清过 ⇒ 无需认领（也不推进认领标记）
        except ValueError:
            pass                      # 坏数据 → 当作没清过，走认领
    # ⚠️ 认领标记写的是「**下一次允许认领的时间**」= now + days
    #    ⇒ 单调递增、字典序可比，且与 `last_purge_at` 的语义不冲突。
    horizon = (_dt.datetime.now() + _dt.timedelta(days=days)).isoformat(timespec="seconds")
    return settings_repo.claim_if_newer("audit.purge_claimed_at", horizon)
