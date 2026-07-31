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
    source_id: int            # ⭐ v0.9.7 B-3 ②：**必填** — 指向**本租户库**的 data_sources 行
    #                           （`resolve_spec` 由它注入 base_url / auth_*；凭据天然 per-tenant）
    # ⛔ v0.9.7 删除：`base_url_env` / `auth_header_env` / `auth_value_env`
    #    —— 那条路让本适配器读**进程 env** = 租户盲 ⇒ 租户#2 可用租户#1 的凭据读其实时接口
    #    = 跨租户数据出境（R-T-GATE B-3 ②）。零真实生产者，退役无兼容代价。
    #    `base_url` / `auth_header` / `auth_value` **不在本 TypedDict 声明** —— 它们不是「存进
    #    catalog 的字段」，而是 `resolve_spec` 运行期注入的**已解析值**（存进来的会被无条件覆盖）。
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
