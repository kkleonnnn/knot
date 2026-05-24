"""knot.adapters.http.url_allowlist — env-driven URL host 白名单 (v0.6.1.4)

OVERRIDE #3 安全模型核心 — 防 admin UI 用户配置任意 endpoint 攻击内网。

工作机制：
- env `KNOT_HTTP_ALLOWED_HOSTS` 由部署方运维设置（K8s ConfigMap）
- admin UI 加 HTTP source 时 URL 的 host 必须在 allowlist 内
- 默认拒绝（env 未设 = 全拒绝）= secure by default

env 格式（逗号分隔）：
    KNOT_HTTP_ALLOWED_HOSTS=futuresadmin.0t.oh,futuresadmin.0p.oh,payment-admin.0p.oh

红线：
- R-PB2-3 sustained：env 未设时 + catalog 含 source:http 表 → 启动 fail-fast
- 部署方 admin UI 用户无权改 env（K8s ConfigMap 是运维资产）
- 双层守护：env 控制 base URL host，catalog 控制具体 path
"""
from __future__ import annotations

import os
from urllib.parse import urlparse


def get_allowed_hosts() -> set[str]:
    """读 env KNOT_HTTP_ALLOWED_HOSTS。

    Returns:
        允许的 host set；未设或空 → 空 set（=全拒绝）
    """
    raw = os.environ.get("KNOT_HTTP_ALLOWED_HOSTS", "")
    if not raw:
        return set()
    return {h.strip() for h in raw.split(",") if h.strip()}


def is_url_allowed(url: str) -> bool:
    """判断 URL 是否在 allowlist 内。

    检查 host 字面匹配（不含端口；端口未来按需扩展）。

    Args:
        url: 完整 URL（如 http://futuresadmin.0t.oh/admin/api/v1/...）

    Returns:
        True 在 allowlist；False 不在
    """
    if not url:
        return False
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    host = parsed.hostname  # 不含端口
    if not host:
        return False
    return host in get_allowed_hosts()


def check_url_allowed(url: str) -> None:
    """守护检查 — 不在 allowlist 抛 HTTPAuthError。

    用于 executor 调 HTTP 前的强制门检。
    """
    from knot.adapters.http.base import HTTPAuthError

    if not is_url_allowed(url):
        try:
            host = urlparse(url).hostname or "<unknown>"
        except ValueError:
            host = "<unparseable>"
        allowed = get_allowed_hosts()
        raise HTTPAuthError(
            f"URL host {host!r} 不在 KNOT_HTTP_ALLOWED_HOSTS 内 "
            f"(allowed: {sorted(allowed) if allowed else 'empty / 未配 env'})"
        )
