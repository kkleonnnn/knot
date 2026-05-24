"""knot.adapters.http.base — Generic HTTP executor Protocol + types (v0.6.1.4)

OVERRIDE #3 (2026-05-24)：撤回守护者 §IV P2-2「不做通用 HTTP 配置化框架」红线。
理由：KNOT 是 OSS 项目，PR review 作为安全闸门在 OSS 上下文失效。

替代安全模型（多层防御）：
- URL allowlist 走 env (KNOT_HTTP_ALLOWED_HOSTS) — 部署方 K8s ConfigMap 控制
- admin role + 2FA (v0.6.2.0) + audit log (R-PB2-12)
- rate limit per endpoint pattern (R-PB2-11)
- catalog endpoint metadata 改动必经 audit (P2-2''')

设计：
- generic `executor.execute(spec, params)` — endpoint metadata 全部从 catalog 传入
- adapter 文件不再 hardcode 业务 endpoint paths
- OSS 用户部署 KNOT 后，通过 admin UI catalog + env 配置接任何 HTTP API

红线（v0.6.1.4 LOCKED §3 修订版）：
- R-PB2-1：HTTPEndpointSpec 签名 byte-equal（catalog 结构稳定性）
- R-PB2-3：必需 env 缺失 fail-fast (URL allowlist / per-endpoint env)
- R-PB2-5：fail-soft — HTTP 失败不阻塞业务
- R-PB2-6：scope 极简 — generic executor 仅做参数填充 + HTTP + JSON 解析
"""
from __future__ import annotations

from typing import Any, TypedDict


class HTTPEndpointSpec(TypedDict, total=False):
    """Catalog 中 source_type=http 表的 endpoint 元数据规范。

    存于 catalog.tables.<name>.http_spec，由 admin UI 配置或 catalog 字典 seed。
    """
    method: str               # "GET" / "POST"
    url_template: str         # "{base_url}/admin/api/v1/position/list"
    base_url_env: str         # 引用 env 名（如 "KNOT_FUTURES_ADMIN_BASE_URL"）
    auth_header_env: str      # env 名 — auth header 字段名（如 KNOT_..._AUTH_HEADER）
    auth_value_env: str       # env 名 — auth header value（如 KNOT_..._AUTH_VALUE）
    response_path: str        # JSON dot path 解析 rows: "data.records" 或 "data"
    param_schema: dict[str, Any]  # 参数 schema 描述（required / type / values）
    timeout_sec: int          # 默认 5


# ─── Error 类型 ─────────────────────────────────────────────────────────


class HTTPAdapterError(Exception):
    """HTTP adapter 通用错误（route 不存在 / response shape 异常 / 业务码非 0）。

    query.py 层捕获后走 error_translator → ErrorBanner kind="http_unavailable"
    （R-PB2-14）。
    """


class HTTPAuthError(HTTPAdapterError):
    """认证失败（env 缺失 / API 401 / URL 不在 allowlist）。

    启动期 env 缺失时抛此异常 → query.py 层 fail-fast（R-PB2-3）。
    """


class HTTPTimeout(HTTPAdapterError):
    """请求超时（R-PB2-15 默认 5s，spec.timeout_sec 可调）。

    error_translator kind="http_timeout"（v0.6.1.5 followup 落地）。
    """


class HTTPUnavailable(HTTPAdapterError):
    """上游不可达（5xx / connection refused / DNS 失败）。

    error_translator kind="http_unavailable"（R-PB2-14）。
    """
