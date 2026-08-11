"""出网 URL 的**单一规范化口径**（v0.9.21）—— 三处出网门共用。

═══ 它解决的问题 ═══

三处门（数据源 / webhook / IM）此前各自用 `urlparse(url).hostname` 取 host，
而随后发请求的是 `requests`（内部 urllib3 解析）。**同一个串两者可以给出不同的 host**：

    http://127.0.0.1:9999\\@allowed.corp/x
      urlparse().hostname   → 'allowed.corp'   ← 门看到这个，放行
      urllib3 → 实际连接    → '127.0.0.1'      ← 请求带着凭据去了这里

⇒ 门校验的 X 与真正被用的 X **不是同一个值** —— 这正是 CLAUDE.md 那条判据点名的形状。
⚠️ 分歧是**双向**的：除了上面这种**绕过**，还有**误拒**
（`http://allowed.corp\\@127.0.0.1/x` 门看到 `127.0.0.1` 而实连 `allowed.corp`）。
⇒ 判据是「**两者必须一致**」，不是「门够不够严」。

═══ 修法：让门算 host 用的，就是 `requests` 将要施加的那套规范化 ═══

`requests.Request(...).prepare()` 会把有歧义的部分**百分号编码进 path**
（`\\@` → `/%5C@…`）⇒ 规范化后的 URL **只有一种读法**。
本模块用它算 host，并返回规范化串；**调用方发规范化串**。

⚠️⚠️ **诚实边界（Stage 3 M1）**：本模块**不**声称「门与客户端用同一个对象」。
调用方拿到的是**字符串**，交给 `requests` 时会**再规范化一次** ⇒ 实际是「同一套规范化跑两次」。
它之所以站得住，是因为所需不变量从「两个解析器对**任意敌手输入**给出相同 host」
**弱化成「这一套规范化对 host **自身幂等**」—— 而后者由下方 `_assert_fixed_point` **运行期守护**。
⇒ 上游 `requests`/urllib3 升级若破坏该不变量（`requirements.txt` 是 `requests>=2.34,<3`，浮动 minor），
   **当场 fail-closed**，而不是静默分叉。

⚠️ 自检保的是「**本片的假设是否仍成立**」，**不是**「host 一定正确」——
若上游把规范化改成幂等但**语义不同**的算法，自检不会响；那种情形靠依赖升级时的显式复核
（本仓已有 `requirements.lock` + locked runtime lane 两道）。

═══ 本模块**不做**什么（承重）═══

⛔ **不碰 allowlist** —— 「能不能去」由三处门各自决定（它们的名单方向相反、三态语义不同，
   v0.9.18 立过「严禁混用」）。本模块只答「这个 URL 规范化后是什么、host 是谁」。
⛔ **不收 `params`** —— 实测调用方若再传一次会**重复**（`?a=1&a=1`）、字典值会**丢失**
   （`{"f":{"city":"SH"}}` → `?f=city`），且 `executor` 的 POST 走 `json=`（body）
   ⇒ 收 `params` 会把 body 参数编进 query。**今天门看到的就是 requests 收到的位置参数，零分歧**
   —— 收 `params` 是**引入**一个今天不存在的问题。
"""
from __future__ import annotations

import requests
from requests.exceptions import (
    InvalidSchema,
    InvalidURL,
    MissingSchema,
    URLRequired,
)
from urllib3.exceptions import LocationParseError
from urllib3.util import parse_url

#: 允许出网的 scheme。⚠️ **必须硬断** —— `PreparedRequest.prepare_url` 对某些形态是
#: **pass-through**（如 `ftp://allowed.corp:21/x` 一个字节都不规范化），
#: 而 `urllib3.parse_url` 仍会给出一个 host ⇒ 门会放行一个**从未被规范化**的串。
#: 今天不可利用只因 `get_adapter` 要求 `http://` 前缀、与 pass-through 条件**碰巧互补**
#: —— 那是巧合，不是结构保证。
_ALLOWED_SCHEMES = ("http", "https")

#: 规范化/解析失败时抛的类型。
#: ⚠️ **继承 `ValueError`** 是刻意的：三处门的现有 `except ValueError` 分支要接得住
#: （实测 `MissingSchema`/`InvalidURL`/`InvalidSchema` 都是 `ValueError` 子类，
#: 而 `URLRequired` **不是** ⇒ 若不统一成本类型，那一支会漏网）。
class UrlCanonError(ValueError):
    """URL 无法被规范化 ⇒ 拒绝出网。

    ⚠️ **消息里绝不含 URL 本身**（Stage 3 M5）：`MissingSchema` 的 `str` 会把完整 URL 带两遍，
    而该消息有一条**活链路**到客户端（`http_planner` 的 `except Exception` → `error`
    → `api/query.py` 存库 + yield）⇒ 会回归 v0.6.1.4 立的「user-facing error 不露完整 URL」。
    """


def _assert_fixed_point(normalized: str, host: str) -> None:
    """⭐ **运行期不动点自检**：对已规范化的串**再规范化一次**，host 必须不变。

    这是 §1.1 那句「上游一升级就会重新分叉，而**没有任何东西会红**」的解 ——
    有了它，分叉不再是静默的，而是**当场 fail-closed**。
    实测代价 ≈ 18.6 µs/请求（单次规范化 ≈ 18.8 µs）。

    ⚠️ 只比 **host**，不比整串 —— 「URL 串幂等」**按字面为假**
    （`http://%2E/x` 二次 prepare 抛 `InvalidURL`；实测 20160 例中 561 例串不等），
    而 host 在 27409 + 20160 例 fuzz 中**从未移动**。host 才是安全属性所在的那一维。
    """
    try:
        again = requests.Request("GET", normalized).prepare().url
        host2 = parse_url(again).host
    except Exception as e:                                   # noqa: BLE001
        raise UrlCanonError(
            f"URL 规范化不稳定（二次规范化失败：{type(e).__name__}）—— 拒绝出网。"
            "这通常意味着 requests/urllib3 的行为在升级后变了；请复核 url_canon 的假设。"
        ) from None
    if host2 != host:
        raise UrlCanonError(
            "URL 规范化**不是幂等的**（两次规范化得到不同的主机）—— 拒绝出网。"
            "本模块的安全性依赖这个不变量；它不成立说明 requests/urllib3 的行为已变，"
            "请复核 url_canon 的假设后再放行。"
        )


def canonicalize(url: str, *, method: str = "GET") -> tuple[str, str]:
    """→ `(规范化后的 URL, host)`。失败一律抛 `UrlCanonError`（**ValueError 子类**）。

    ⚠️ **调用方必须发返回的那个规范化串**，不得再发原始串 ——
    否则「门校验的」与「真正被发的」又变成两个东西，本模块就白做了。
    ⚠️ **写入/存储侧只取 host，不要落 `normalized`** —— 规范化会给裸 host 补 `/`
    （`http://api.example.com` → `http://api.example.com/`），落到存储侧会让
    `{base_url}` 拼接得到 `//`。

    Args:
        url: 待校验/发送的 URL。
        method: 仅用于构造 `PreparedRequest`；**不影响 host**（实测 GET/POST 同结果）。
    """
    if not url or not url.strip():
        raise UrlCanonError("出网地址为空 —— 拒绝出网。")
    try:
        normalized = requests.Request(method, url).prepare().url
    except (MissingSchema, InvalidURL, InvalidSchema, URLRequired, LocationParseError) as e:
        raise UrlCanonError(
            f"出网地址无法解析（{type(e).__name__}）—— 拒绝出网。"
            "请检查它是否带 http:// 或 https:// 前缀、以及主机名是否合法。"
        ) from None
    if not normalized:
        raise UrlCanonError("出网地址规范化后为空 —— 拒绝出网。")

    # ⚠️ scheme 硬断必须在**取 host 之前** —— pass-through 形态下 `normalized` 就是原串，
    #    而 `parse_url` 仍会给出 host ⇒ 不断言就等于放行一个未规范化的串。
    scheme = (parse_url(normalized).scheme or "").lower()
    if scheme not in _ALLOWED_SCHEMES:
        raise UrlCanonError(
            f"出网只允许 {'/'.join(_ALLOWED_SCHEMES)}，实际是 {scheme or '(无)'} —— 拒绝出网。"
        )

    try:
        host = parse_url(normalized).host
    except LocationParseError:
        raise UrlCanonError("出网地址的主机名无法解析 —— 拒绝出网。") from None
    if not host:
        raise UrlCanonError("出网地址不含主机名 —— 拒绝出网。")

    _assert_fixed_point(normalized, host)
    return normalized, host


def canonical_host_of_entry(entry: str) -> str | None:
    """把**allowlist 条目**（运维手打的裸主机名）规范化成与 `canonicalize()` 同一口径。

    ⭐ **为什么必须有这个**（Stage 2 B-P1-1）：等值的两边只规范化一边 = 拿两种产出方式比对
    （v3.1-C 六问⑤）。实测若不做，运维写的 `例え.jp` 与 `::1` 会**从今以后永不匹配**
    —— fail-closed，但**与 bug 不可区分**（v0.9.7 M5 同族）。

    ⚠️ **条目不能直接过 `canonicalize()`**（Stage 3 M4，实测）：
    `prepare("api.example.com")` 抛 `MissingSchema`（裸主机名没有 scheme）；
    `'::1'` 被 prepare **透传**，而 `'http://::1'` 抛 `InvalidURL`。
    ⇒ 这里**补上 `http://` 再走同一条路**，并对 IPv6 裸字面补方括号。

    Returns:
        规范化后的 host；**无法规范化时返回 `None`**（调用方丢弃该条目并 WARN ——
        绝不能静默当成「匹配任何东西」）。
    """
    e = (entry or "").strip()
    if not e:
        return None
    # IPv6 裸字面（`::1`）要补方括号才是合法 URL 主机部分；已带方括号的原样。
    if ":" in e and not e.startswith("[") and "." not in e.split(":")[0]:
        e = f"[{e}]"
    try:
        _, host = canonicalize(f"http://{e}/")
    except UrlCanonError:
        return None
    # ⚠️ 规范化**成功**不等于它是个合法主机名：实测 `'not a host!!'` → `'not%20a%20host!!'`
    #    —— 一个**永不匹配**的串。fail-closed 无害，但运维**拿不到任何信号**
    #    ⇒ 与「写错了一个字母」不可区分。⇒ 含百分号编码/空白的一律判为不可规范化，
    #      让调用方 WARN 出来（M4 要的就是「给不可规范化条目一个明确行为」）。
    if "%" in host or any(c.isspace() for c in host):
        return None
    return host
