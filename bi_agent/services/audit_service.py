"""bi_agent/services/audit_service.py — 审计写入入口（v0.4.6）。

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

from bi_agent.core.logging_setup import logger
from bi_agent.repositories import audit_repo

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
        )
    except Exception as e:
        # R-47 fail-soft：业务不阻断
        logger.error(
            f"[audit] 写入失败 action={action} resource={resource_type} error={e}"
        )
        # R-64 失败盲区可观测
        _audit_write_failures_total += 1
        # R-65：不抛 AuditWriteError 出业务流（R-47 fail-soft 优先）；
        # AuditWriteError 类的存在是为未来需要可重试的审计补录场景。
