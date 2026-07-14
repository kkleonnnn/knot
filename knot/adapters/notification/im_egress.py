"""im_egress — v0.8.14 分享 IM 出站 host allowlist（独立 egress 边界）。

R-SL-69：与数据源读取 allowlist `KNOT_HTTP_ALLOWED_HOSTS` 物理隔离（读 vs 发两条边界不混用）。
D6（kk LOCKED）：IM host 是固定基础设施（非部署变量）→ **硬编常量**，不走 env
  （env 未设=deny-all 会静默坏功能，比 misconfig 风险更实）。
R-BI-SHARE-4：telegram/lark adapter **每个出站调用点**须在 requests.* 前过 is_im_host_allowed，否则 raise。
"""
from __future__ import annotations

from urllib.parse import urlparse

# 固定 IM 出站 host 白名单（Telegram + 飞书 + 国际 Lark）
IM_ALLOWED_HOSTS = frozenset({
    "api.telegram.org",
    "open.feishu.cn",
    "open.larksuite.com",
})


def is_im_host_allowed(url: str) -> bool:
    """url 的 host 是否在固定 IM 白名单（host-only，无 port/path）。"""
    if not url:
        return False
    try:
        host = urlparse(url).hostname
    except ValueError:
        return False
    return bool(host) and host in IM_ALLOWED_HOSTS
