"""knot.adapters.http.executor — Generic HTTP executor (v0.6.1.4 OSS-friendly)

OVERRIDE #3：替代守护者 §IV P2-2 hardcoded adapter 文件方案。
endpoint metadata 完全从 catalog 传入（HTTPEndpointSpec），不写死路径。

执行流程：
1. URL host allowlist 校验（env KNOT_HTTP_ALLOWED_HOSTS）
2. env 解 base_url / auth / timeout
3. URL template 渲染 + params 拼接
4. requests.get/post 调用
5. 状态码分流 → typed errors
6. JSON 解析
7. response_path dot path 提取 rows

红线遵守：
- R-PB2-1：HTTPEndpointSpec TypedDict 签名 byte-equal
- R-PB2-3：env / URL allowlist 缺失 → fail-fast (HTTPAuthError)
- R-PB2-5：fail-soft — typed error 抛出供 query.py 转 ErrorBanner
- R-PB2-6：scope 极简 — 不复用 sql_planner 防御
- R-PB2-15：timeout 默认 5s（spec.timeout_sec 可调）
"""
from __future__ import annotations

import os
from typing import Any

import requests

from knot.adapters.http.base import (
    HTTPAdapterError,
    HTTPAuthError,
    HTTPEndpointSpec,
    HTTPTimeout,
    HTTPUnavailable,
)
from knot.adapters.http.url_allowlist import check_url_allowed

_DEFAULT_TIMEOUT_SEC = 5


def execute(spec: HTTPEndpointSpec, params: dict[str, Any]) -> list[dict[str, Any]]:
    """执行 HTTP endpoint 调用，返 normalized rows。

    Args:
        spec: catalog 中 source_type=http 表的 http_spec 段（HTTPEndpointSpec 形态）
        params: 调用参数 dict（如 {market, side, page, page_size}）

    Returns:
        list of row dicts（即使 API 返单条也包成 1-elem list）

    Raises:
        HTTPAuthError:    env 缺失 / 401 / URL 不在 allowlist
        HTTPTimeout:      超时
        HTTPUnavailable:  5xx / connection error
        HTTPAdapterError: spec 字段缺失 / response shape 异常 / 业务码非 0
    """
    method = spec.get("method", "GET").upper()
    url_template = spec.get("url_template")
    response_path = spec.get("response_path", "data")
    timeout_sec = int(spec.get("timeout_sec", _DEFAULT_TIMEOUT_SEC))

    # spec 完整性检查
    if not url_template:
        raise HTTPAdapterError("HTTPEndpointSpec.url_template 缺失")

    # v0.6.1.4 OVERRIDE #4: 双模式 — 直填值 vs env 引用
    # 模式 A (直填): spec 含 "base_url" / "auth_header" / "auth_value" — admin UI / DB 注入
    # 模式 B (env): spec 含 "base_url_env" / "auth_*_env" — v0.6.1.4 backward compat
    direct_base_url = spec.get("base_url")
    if direct_base_url:
        base_url = direct_base_url.rstrip("/")
        header_name = spec.get("auth_header", "")
        header_value = spec.get("auth_value", "")
    else:
        base_url_env = spec.get("base_url_env")
        if not base_url_env:
            raise HTTPAdapterError(
                "HTTPEndpointSpec 必须含 base_url（直填）或 base_url_env（env 引用）"
            )
        base_url = os.environ.get(base_url_env, "").rstrip("/")
        if not base_url:
            raise HTTPAuthError(
                f"env {base_url_env} 未设置 — catalog 含 source:http 表必须配置 (R-PB2-3)"
            )
        auth_header_env = spec.get("auth_header_env", "")
        auth_value_env = spec.get("auth_value_env", "")
        header_name = os.environ.get(auth_header_env, "") if auth_header_env else ""
        header_value = os.environ.get(auth_value_env, "") if auth_value_env else ""
        if (auth_header_env or auth_value_env) and (not header_name or not header_value):
            raise HTTPAuthError(
                f"auth env 缺失: {auth_header_env}={header_name!r} "
                f"{auth_value_env}={header_value!r} (R-PB2-3)"
            )

    # URL 拼接 + allowlist 守护
    url = url_template.replace("{base_url}", base_url)
    check_url_allowed(url)  # ← OVERRIDE #3 安全核心

    # auth header 处理
    headers = {}
    if header_name and header_value:
        headers[header_name] = header_value

    # HTTP 调用
    try:
        if method == "GET":
            resp = requests.get(url, params=params, headers=headers, timeout=timeout_sec)
        elif method == "POST":
            resp = requests.post(url, json=params, headers=headers, timeout=timeout_sec)
        else:
            raise HTTPAdapterError(f"不支持的 HTTP method: {method}")
    except requests.Timeout as e:
        raise HTTPTimeout(f"HTTP {method} {url} 超时 ({timeout_sec}s): {e}") from e
    except requests.ConnectionError as e:
        raise HTTPUnavailable(f"HTTP {method} {url} 不可达: {e}") from e
    except requests.RequestException as e:
        raise HTTPAdapterError(f"HTTP {method} {url} 请求异常: {e}") from e

    # 状态码分流
    if resp.status_code in (401, 403):
        raise HTTPAuthError(
            f"HTTP {method} {url} auth 失败 (HTTP {resp.status_code})"
        )
    if resp.status_code == 404:
        raise HTTPAdapterError(
            f"HTTP {method} {url} 路由 404 — base_url 或 path 错误"
        )
    if resp.status_code >= 500:
        raise HTTPUnavailable(
            f"HTTP {method} {url} 服务异常 (HTTP {resp.status_code})"
        )
    if resp.status_code != 200:
        raise HTTPAdapterError(
            f"HTTP {method} {url} 非预期状态码: {resp.status_code}"
        )

    # JSON 解析
    try:
        body = resp.json()
    except ValueError as e:
        raise HTTPAdapterError(f"HTTP {method} {url} response 非 JSON: {e}") from e

    # 业务码检查（约定：code=0 表示成功；可在 spec 中重写约定）
    if isinstance(body, dict) and "code" in body and body["code"] != 0:
        raise HTTPAdapterError(
            f"HTTP {method} {url} 业务错误 code={body['code']} msg={body.get('msg')!r}"
        )

    # response_path dot path 提取 rows
    return _extract_rows(body, response_path)


def _extract_rows(body: Any, dot_path: str) -> list[dict]:
    """按 dot path 提取 rows list。

    dot_path 形态：
      "data.records"   → body["data"]["records"]
      "data"           → body["data"]
      ""               → body 直接
    """
    if not dot_path:
        target = body
    else:
        target = body
        for segment in dot_path.split("."):
            if isinstance(target, dict):
                target = target.get(segment)
                if target is None:
                    return []
            else:
                raise HTTPAdapterError(
                    f"response_path {dot_path!r} 在 {segment!r} 处不能解 dict"
                )

    if target is None:
        return []
    if isinstance(target, list):
        return target
    if isinstance(target, dict):
        # 兜底：dict 单条包成 1-elem list
        return [target]
    raise HTTPAdapterError(
        f"response_path {dot_path!r} 解出非 list/dict: {type(target)}"
    )
