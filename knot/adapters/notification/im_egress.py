"""im_egress — v0.8.14 分享 IM 出站 host allowlist（独立 egress 边界）。

R-SL-69：与数据源读取 allowlist `KNOT_HTTP_ALLOWED_HOSTS` 物理隔离（读 vs 发两条边界不混用）。
D6（kk LOCKED）：IM host 是固定基础设施（非部署变量）→ **硬编常量**，不走 env
  （env 未设=deny-all 会静默坏功能，比 misconfig 风险更实）。
R-BI-SHARE-4：telegram/lark adapter **每个出站调用点**须在 requests.* 前过 is_im_host_allowed，否则 raise。

⭐ **v0.9.21：host 提取改走 `url_canon`（与另两处门同一口径）。**
此前用 `urlparse().hostname`，而实际连接由 urllib3 解析 ⇒ 同一串两者可给出**不同 host**
⇒ 门校验的与真正被用的不是同一个值。三处门此前各写了一遍同一个错，现在收成一处。
⚠️ 本表**已是规范化形态**（全小写 ASCII），故不需要像另两处那样在读取时过 `canonical_host_of_entry`
—— 但**下方有断言守住这一点**：改成非规范化字面（如 `API.Telegram.org`）会当场炸，
而不是静默变成「永不匹配」（v0.9.7 M5 那类「fail-closed 但与 bug 不可区分」）。
"""
from __future__ import annotations

# 固定 IM 出站 host 白名单（Telegram + 飞书 + 国际 Lark）
IM_ALLOWED_HOSTS = frozenset({
    "api.telegram.org",
    "open.feishu.cn",
    "open.larksuite.com",
})


def _assert_entries_are_canonical() -> None:
    """⭐ 导入期断言：本表每一项都**已是规范化形态**。

    ⚠️ 为什么是断言而不是「读取时规范化」：本表是**硬编常量**（D6 kk LOCKED），
    不是运维配置 ⇒ 它出错是**代码错误**，应当**当场炸**，而不是在运行期悄悄丢弃条目。
    ⚠️ 若不守：有人把某项写成 `API.Telegram.org`，而请求侧的 host 恒小写
    ⇒ 该条目**永不匹配** ⇒ IM 分享静默全坏，且**与「功能本来就没配」不可区分**。
    """
    from knot.adapters.http.url_canon import canonical_host_of_entry

    bad = {h: canonical_host_of_entry(h) for h in IM_ALLOWED_HOSTS
           if canonical_host_of_entry(h) != h}
    if bad:
        raise AssertionError(
            f"IM_ALLOWED_HOSTS 含**非规范化**条目 {bad} —— 它们永不匹配请求侧的 host。"
            "请直接写成规范化形态（全小写、IDN 用 punycode、IPv6 带方括号）。"
        )


_assert_entries_are_canonical()


def is_im_host_allowed(url: str) -> bool:
    """url 的 host 是否在固定 IM 白名单（host-only，无 port/path）。

    ⭐ v0.9.21：host 由 `url_canon.canonicalize()` 算 —— 与实际发请求的规范化**同一套**。
    无法规范化（含非 http/https）⇒ `False`（fail-closed）。
    """
    if not url:
        return False
    from knot.adapters.http.url_canon import UrlCanonError, canonicalize

    try:
        _, host = canonicalize(url)
    except UrlCanonError:
        return False
    return host in IM_ALLOWED_HOSTS
