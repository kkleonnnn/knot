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

# v0.9.7：`import os` 随 env 模式退役一并删除 —— 本适配器**不再读进程 env**（凭据一律经 source_id）
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
    # ⭐⭐ v0.9.6 硬边界：**非起源租户禁止行使「以某个身份发出网络请求」这个能力**。
    # **为什么门在这一行、而不在 `pick_http_route`**：`execute` 是**唯一**发出网络请求
    # （`requests.get/post`，本文件下方两处）**且唯一读进程 env 凭据**的函数 ⇒ 能力就在这里。
    # 门若只放决策点（`pick_http_route`），不变量就依赖「`query.py` 里一个 `if`」+「将来没人直呼
    # `run_http_step`」—— 而后者是**公开函数、自带 spec、不重新求 route** ⇒ monitor / 定时报表 /
    # LogicForm 混合路由任一条接进来都能绕过。
    #
    # ⚠️ **它代偿的是 R-T-GATE 清单的 ② 和 ③**（不只 ②）：
    #   ② 进程 env 凭据 —— 只有「无 source_id」的 env 路径读它；
    #      `source_id` 路径的凭据来自**租户自己的库**（`resolve_spec` → `get_datasource` → `get_conn`）
    #      ⇒ 那条本已是 per-tenant 凭据机制，本门对它是**过阻**；
    #   ③ **让这个过阻仍然正确**：`url_allowlist` 的 allowlist 是**进程级** ⇒ 非 owner 即便只用
    #      自己的凭据，打的也是**部署方 allowlist 里的主机** = 伸手进部署方网络（SSRF 向）。
    # ⛔ **只有 ②③ 都落地才可移除本门** —— ② 落地后最自然的动作是「现在非 owner 可以用 HTTP 了」，
    #    但那时 ③ 若还开着，过阻的正当性就没了却门也没了。**别单独摘。**
    # ⏳ **v0.9.7 进行中**：③ 已落（allowlist per-tenant 化）· ② 本 commit 落（env 模式已删，见下）
    #    ⇒ 本门在本片**末尾一并摘除**（手册 D5：摘门放最后 = 安全性单调不降）。
    #    若你读到这行而门还在、且 ②③ 都已落地 —— 那就是本片没走完，别把它当稳定状态。
    #
    # ⚠️ **消息不得含 env 名 / owner tid / 部署方表名**：`run_http_step` 把 `str(e)` 放进
    # `result["error"]`，`api/query.py` 原样 yield 给客户端 —— 那正是 #262 那条缝。
    from knot.core.tenant_context import is_owner_tenant
    if not is_owner_tenant():
        raise HTTPAuthError("该租户未启用 HTTP 数据源")

    method = spec.get("method", "GET").upper()
    url_template = spec.get("url_template")
    response_path = spec.get("response_path", "data")
    timeout_sec = int(spec.get("timeout_sec", _DEFAULT_TIMEOUT_SEC))

    # spec 完整性检查
    if not url_template:
        raise HTTPAdapterError("HTTPEndpointSpec.url_template 缺失")

    # ⭐ v0.9.7 B-3 ②：凭据**只能**来自「租户自己的数据源行」—— **env 模式已退役**。
    # `services/http_planner.resolve_spec` 用 spec 的 `source_id` 查**租户库** `data_sources`
    # （Fernet 解密 `http_config`）把 `base_url` / `auth_header` / `auth_value` 注入进 spec
    # ⇒ 凭据天然 per-tenant（那条路本来就在，本片只是把绕过它的路封死）。
    #
    # ⛔ **删掉的是「spec 自带 env 名 → 本函数读进程 env」那条路**（`base_url_env` / `auth_*_env`）：
    #    进程 env 是**租户盲**的 ⇒ 租户#2 能用租户#1 的凭据读其实时接口 = **跨租户数据出境**
    #    （R-T-GATE 清单 B-3 ②）。**零真实生产者** —— 部署方真实 `_local_catalog.py` 的 http 表
    #    全走 `source_id`（实测 `base_url_env|auth_value_env` 0 命中）⇒ 退役不打断任何真实部署。
    # 📌 **#262 的教训与守护不随这段代码消失**：全仓 AST 哨兵仍在
    #    `tests/test_no_env_value_in_messages.py`（禁「从 env 读出的值」进消息 / 日志 / 响应），
    #    其端到端测已改瞄本片新引入的 env 读点（起源租户 allowlist 回退的启动 WARN）。
    #
    # ⚠️ 本处是**硬边界**，不依赖上游是否软降级：`run_http_step` 是**公开函数、自带 spec、
    #    不重新求 route** ⇒ monitor / 定时报表 / 混合路由任何直呼者都必须在这一行被拦住。
    #    消息不含 env 名 / tid / 部署方表名（#262 那条缝：`str(e)` 会被 yield 给客户端）。
    base_url = (spec.get("base_url") or "").rstrip("/")
    if not base_url:
        raise HTTPAuthError("该 HTTP 表未绑定本租户的数据源")
    header_name = spec.get("auth_header", "")
    header_value = spec.get("auth_value", "")

    # URL 拼接 + allowlist 守护
    url = url_template.replace("{base_url}", base_url)
    check_url_allowed(url)  # ← OVERRIDE #3 安全核心

    # auth header 处理
    headers = {}
    if header_name and header_value:
        headers[header_name] = header_value

    # HTTP 调用
    # v0.6.1.4 fix: user-facing error 不露完整 URL（防内部路由泄漏）；完整 URL 留在 logger 给 admin 排查
    import logging as _log
    _logger = _log.getLogger(__name__)

    try:
        if method == "GET":
            resp = requests.get(url, params=params, headers=headers, timeout=timeout_sec)
        elif method == "POST":
            resp = requests.post(url, json=params, headers=headers, timeout=timeout_sec)
        else:
            raise HTTPAdapterError(f"不支持的 HTTP method: {method}")
    except requests.Timeout as e:
        _logger.error(f"HTTP {method} {url} 超时 ({timeout_sec}s): {e}")
        raise HTTPTimeout(f"外部 HTTP API {method} 超时 ({timeout_sec}s)") from e
    except requests.ConnectionError as e:
        _logger.error(f"HTTP {method} {url} 不可达: {e}")
        raise HTTPUnavailable(f"外部 HTTP API {method} 不可达") from e
    except requests.RequestException as e:
        _logger.error(f"HTTP {method} {url} 请求异常: {e}")
        raise HTTPAdapterError(f"外部 HTTP API {method} 请求异常") from e

    # 状态码分流
    if resp.status_code in (401, 403):
        _logger.error(f"HTTP {method} {url} auth 失败 (HTTP {resp.status_code})")
        raise HTTPAuthError(f"外部 HTTP API auth 失败 (HTTP {resp.status_code})")
    if resp.status_code == 404:
        _logger.error(f"HTTP {method} {url} 路由 404 — base_url 或 path 错误")
        raise HTTPAdapterError("外部 HTTP API 路由 404 — 请联系管理员检查配置")
    if resp.status_code >= 500:
        _logger.error(f"HTTP {method} {url} 服务异常 (HTTP {resp.status_code})")
        raise HTTPUnavailable(f"外部 HTTP API 服务异常 (HTTP {resp.status_code})")
    if resp.status_code != 200:
        _logger.error(f"HTTP {method} {url} 非预期状态码: {resp.status_code}")
        raise HTTPAdapterError(f"外部 HTTP API 非预期状态码: {resp.status_code}")

    # JSON 解析
    try:
        body = resp.json()
    except ValueError as e:
        _logger.error(f"HTTP {method} {url} response 非 JSON: {e}")
        raise HTTPAdapterError("外部 HTTP API response 非 JSON 格式") from e

    # 业务码检查（约定：code=0 表示成功；可在 spec 中重写约定）
    if isinstance(body, dict) and "code" in body and body["code"] != 0:
        _logger.error(f"HTTP {method} {url} 业务错误 code={body['code']} msg={body.get('msg')!r}")
        raise HTTPAdapterError(
            f"外部 HTTP API 业务错误 code={body['code']} msg={body.get('msg')!r}"
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
