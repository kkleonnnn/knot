"""v0.9.21 验收：出网 allowlist 的**单一 URL 解析口径**。

## 它测的缺陷
三处出网门此前各自用 `urlparse(url).hostname` 取 host，而实际发请求的是 `requests`（urllib3）
⇒ **同一个串两者可给出不同 host** ⇒ 门校验的 X 与真正被用的 X 不是同一个值。
⚠️ 分歧**双向**：既有**绕过**（门放行而实连内网），也有**误拒**（门拒而实连是合法 host）。
⇒ 判据是「**两者必须一致**」，不是「门够不够严」——
只测「堵住绕过」会让那两条误拒被当成「本来就该拒」而永远留着。

## ⚠️ 本文件的两条写法纪律（Stage 2/3 换来的）
1. **必须起真实 HTTP 服务，不能 mock** ——「实际连到哪个 host」是 `requests` 的**运行时行为**，
   mock 掉就等于在测我自己写的假货。三轮评审的关键发现**全部**来自真服务。
2. ⭐ **「零发送」这类否定断言，必须与同一测内的可达性正对照绑定**：
   实测设 `HTTP_PROXY` 后**目标监听器 0 收到**、代理收到 ⇒「零发送」**恒真**
   = 对空集做否定断言（本仓 `caplog` 那条规则的**网络版**）。
   ⇒ 每个断「没发出去」的测，都先证「同一个监听器这会儿真收得到」。
"""
from __future__ import annotations

import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from knot.adapters.http.url_canon import (
    UrlCanonError,
    canonical_host_of_entry,
    canonicalize,
)

_PROXY_ENVS = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
               "http_proxy", "https_proxy", "all_proxy", "NO_PROXY", "no_proxy")


@pytest.fixture
def listener(monkeypatch):
    """本地真 HTTP 服务 + **清空代理 env**。

    ⚠️ 清代理是承重的（Stage 3 M3）：不清的话「监听器零收到」在有代理的环境里恒真
    ⇒ 所有否定断言变成对空集的断言。
    """
    for k in _PROXY_ENVS:
        monkeypatch.delenv(k, raising=False)

    hits: list[dict] = []

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):        # 静音
            pass

        def do_GET(self):
            hits.append({"path": self.path, "host": self.headers.get("Host")})
            self.send_response(200)
            self.end_headers()

        do_POST = do_GET

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_port, hits
    srv.shutdown()


def _allowlist(monkeypatch, hosts: str):
    """把 env allowlist 设成 `hosts` 并进入起源租户 ctx（env 回退分支）。"""
    from knot.core import tenant_context as tc
    monkeypatch.setenv("KNOT_HTTP_ALLOWED_HOSTS", hosts)
    return tc.set_active_tenant({"id": 1, "db_dir": "."})


# ─── #1 核心：门放行 ⇒ 实连 host ∈ allowlist（真服务）────────────────────


def test_gate_verdict_matches_the_host_actually_connected(listener, monkeypatch):
    """⭐⭐ **本片最强的一条**：门放行 ⇒ 真连的 host **就是**它放行的那个。

    payload `http://127.0.0.1:<port>\\@allowed.corp/x`：
    旧门（`urlparse().hostname`）看到 `allowed.corp` ⇒ **放行**，而请求实连 **127.0.0.1**。

    ⚠️ oracle 是**监听器收到了什么**，不是「有没有报错」——
    「门拒了」与「本来就连不通」在只看异常时不可区分（v3.1-B #7 顶班）。

    revert-to-bad：把 `url_canon.canonicalize` 换回 `urlparse(url).hostname`
    ⇒ 门放行该 payload ⇒ **监听器收到请求** ⇒ 本测红。
    """
    import requests

    from knot.adapters.http import url_allowlist as ua
    from knot.core import tenant_context as tc

    port, hits = listener
    tok = _allowlist(monkeypatch, "allowed.corp")
    try:
        payload = f"http://127.0.0.1:{port}\\@allowed.corp/x"

        # ① 可达性正对照 —— 先证这个监听器**真收得到**（否则下面的「零收到」是空断言）
        requests.get(f"http://127.0.0.1:{port}/reachable", timeout=5, allow_redirects=False)
        assert hits and hits[-1]["path"] == "/reachable", "监听器不可达 ⇒ 下面的否定断言无意义"
        n_before = len(hits)

        # ② 门必须拒（它看到的 host 是 127.0.0.1，不在 allowlist）
        assert ua.is_url_allowed(payload) is False, (
            "门放行了一个实连 127.0.0.1 的 payload —— 解析口径又分叉了"
        )

        # ③ 且**真的没发出去**（与 ① 的正对照成对）
        assert len(hits) == n_before, "被拒之后仍然发出了请求"
    finally:
        tc.reset_active_tenant(tok)


# ─── #2 误拒也是 bug（一条端到端 + 一条单元）──────────────────────────


def test_misdenial_backslash_at_is_fixed_end_to_end(listener, monkeypatch):
    """⭐ **误拒**：`http://<allowed>\\@127.0.0.1/x` 旧门看到 `127.0.0.1` ⇒ **拒**，
    而 `requests` 实连的是 **allowed 那个 host**。

    ⚠️ 只测「堵住绕过」的话，这一条会被当成「本来就该拒」而永远留着。
    这里 allowlist 配 `127.0.0.1`（= 监听器），故修好后**应当放行且真的连上**。
    """
    import requests

    from knot.adapters.http import url_allowlist as ua
    from knot.core import tenant_context as tc

    port, hits = listener
    tok = _allowlist(monkeypatch, "127.0.0.1")
    try:
        url = f"http://127.0.0.1:{port}\\@evil.invalid/x"
        assert ua.is_url_allowed(url) is True, "误拒未修：门仍然拒绝一个实连 allowlist 主机的 URL"
        normalized = ua.check_url_allowed(url)
        requests.get(normalized, timeout=5, allow_redirects=False)
        assert hits[-1]["host"].startswith("127.0.0.1"), f"连到了别处：{hits[-1]}"
    finally:
        tc.reset_active_tenant(tok)


def test_misdenial_backslash_dot_is_fixed_unit_level(monkeypatch):
    """⭐ 第二条**误拒**：`http://allowed.corp\\.evil.com/x` 旧门看到整串 ⇒ 拒，实连 `allowed.corp`。

    ⚠️ **本条刻意是单元级、不端到端**（Stage 2 lens C 实测）：该 payload 规范化后落在 **port 80**
    ⇒ 本地监听器（随机高位端口）**收不到** ⇒ 端到端 oracle 在这里不可观测。
    ⇒ 判据取 `(allow, host)` 二元组，仍然是「门看到的 = 将要连的」。
    """
    from knot.adapters.http import url_allowlist as ua
    from knot.core import tenant_context as tc

    tok = _allowlist(monkeypatch, "allowed.corp")
    try:
        _, host = canonicalize("http://allowed.corp\\.evil.com/x")
        assert host == "allowed.corp", f"规范化后的 host 不是 allowed.corp：{host!r}"
        assert ua.is_url_allowed("http://allowed.corp\\.evil.com/x") is True
    finally:
        tc.reset_active_tenant(tok)


# ─── #3 三处门共用同一口径（行为级，不是「谁 import 了什么」）──────────


def test_all_three_gates_share_one_parser():
    """⭐ 三处门对**同一个 payload** 给出**同一个 host** —— 行为级判据。

    ⚠️ 只禁 `urlparse` 这个**名字**证明不了共用（`urlsplit` / `parse_url` / `split("://")` 全逃逸，
    且某处改成直接比 `spec["host"]` 也照样绿）⇒ 这里断**行为一致**。
    """
    from knot.adapters.notification import im_egress, webhook

    payload = "http://127.0.0.1:9999\\@api.telegram.org/x"
    _, canon_host = canonicalize(payload)
    assert canon_host == "127.0.0.1", canon_host

    # IM 门：allowlist 含 api.telegram.org 而不含 127.0.0.1 ⇒ 必须拒
    assert im_egress.is_im_host_allowed(payload) is False, (
        "IM 门放行了一个实连 127.0.0.1 的 payload ⇒ 它没走同一口径"
    )

    # webhook 门：⚠️ 初版我写成 `pytest.raises(Exception)`（以为无 ctx 会抛），
    #    实测 **DID NOT RAISE** —— 因为规范化在**读 ctx 之前**就已判定，
    #    `canonicalize` 给出的 host 不在名单里就直接返 False，**根本走不到读 ctx 那一步**。
    #    ⇒ 那是六问① 的形状（探针没到达真属性）⇒ 改断**行为**：它不放行。
    assert webhook.is_webhook_url_allowed(payload) is False, (
        "webhook 门放行了一个实连 127.0.0.1 的 payload ⇒ 它没走同一口径"
    )

    # ⭐ 正对照：三处门对**同一个合法串**给出同一个 host（否则「都拒」也能让上面全绿）
    ok = "https://api.telegram.org/bot123/sendPhoto"
    assert canonicalize(ok)[1] == "api.telegram.org"
    assert im_egress.is_im_host_allowed(ok) is True


# ─── #4 设计前提：host 幂等（不是 URL 串幂等）────────────────────────


@pytest.mark.parametrize("url", [
    "http://allowed.corp/x",
    "http://127.0.0.1:9999\\@allowed.corp/x",
    "http://[::1]:8080/x",
    "http://allowed.corp/x?a=1&b=%20",
    "https://allowed.corp:8443/a/b/c",
])
def test_host_is_idempotent_under_renormalization(url):
    """⭐ **本片的设计前提**（不是附加检查）：host 在重复规范化下不变。

    ⚠️ **判据是 host 幂等，不是 URL 串幂等** —— 后者**按字面为假**
    （`http://%2E/x` 二次 prepare 抛 `InvalidURL`；fuzz 20160 例中 561 例串不等），
    而 host 在 47000+ 例 fuzz 中从未移动。host 才是安全属性所在的那一维。

    ⚠️ 这条不成立 ⇒「调用方发规范化串」这个设计**本身不成立**（helper 内有运行期自检兜底）。
    """
    normalized, host = canonicalize(url)
    again, host2 = canonicalize(normalized)
    assert host2 == host, f"host 在二次规范化后变了：{host!r} → {host2!r}"


def test_fixed_point_selfcheck_refuses_when_renormalization_diverges(monkeypatch):
    """⭐ **不动点自检真的会拦** —— 这是「上游升级后静默分叉」的解。

    `requirements.txt` 是 `requests>=2.34,<3`（**浮动 minor**）⇒ fuzz 只能证当前版本；
    自检把「分叉」从**静默**变成**当场 fail-closed**。

    revert-to-bad：删掉 `_assert_fixed_point` 的调用 ⇒ 本测红（不再抛）。
    """
    import knot.adapters.http.url_canon as uc

    real = uc.parse_url
    calls = {"n": 0}

    def flaky(u):
        calls["n"] += 1
        r = real(u)
        if calls["n"] > 2:                 # 二次规范化时给出不同 host
            class _R:
                host = "evil.example.com"
                scheme = r.scheme
                port = r.port
            return _R()
        return r

    monkeypatch.setattr(uc, "parse_url", flaky)
    with pytest.raises(UrlCanonError) as ei:
        uc.canonicalize("http://allowed.corp/x")
    assert "幂等" in str(ei.value), f"拒绝了但理由不是幂等失败：{ei.value}"


# ─── #5 scheme 硬断 + 条目规范化 + fail-closed ─────────────────────────


@pytest.mark.parametrize("url", ["ftp://allowed.corp:21/x", "file:///etc/passwd", "//allowed.corp/x"])
def test_non_http_scheme_is_refused(url):
    """⭐ `prepare()` 对某些形态是 **pass-through**（一个字节都不规范化）
    而 `parse_url` 仍给 host ⇒ 不硬断 scheme 就等于放行一个**从未被规范化**的串。
    今天不可利用只因两个前缀判断**碰巧互补** —— 那是巧合，不是结构保证。
    """
    with pytest.raises(UrlCanonError):
        canonicalize(url)


@pytest.mark.parametrize("entry,expected", [
    ("api.example.com", "api.example.com"),
    ("Allowed.Corp", "allowed.corp"),          # 既有缺陷：原实现不小写化 ⇒ 今天就两向全拒
    ("例え.jp", "xn--r8jz45g.jp"),              # IDN：不规范化则永不匹配
    ("::1", "[::1]"),                          # IPv6：方括号
    ("[::1]", "[::1]"),
    ("  ", None),
    ("not a host!!", None),                    # 垃圾条目必须**可见地**被丢弃
])
def test_allowlist_entries_go_through_the_same_parser(entry, expected):
    """⭐ 等值的两边**同法产出**（六问⑤）。

    不这么做的话，运维手打的条目与请求侧的 host 是**两种产出方式** ⇒ 静默永不匹配
    （fail-closed，但**与 bug 不可区分**）。
    """
    assert canonical_host_of_entry(entry) == expected


def test_unparseable_url_is_fail_closed_and_message_has_no_url(monkeypatch):
    """⭐ 无法规范化 ⇒ **拒绝**，且**消息里不含 URL**。

    ⚠️ 后半句承重：`MissingSchema` 的 `str` 会把完整 URL 带**两遍**，而该消息有一条活链路到客户端
    （`http_planner` 的 `except Exception` → `error` → `api/query.py` 存库 + yield）
    ⇒ 会回归 v0.6.1.4 立的「user-facing error 不露完整 URL」。
    """
    from knot.adapters.http import url_allowlist as ua
    from knot.adapters.http.base import HTTPAuthError
    from knot.core import tenant_context as tc

    secret = "internal-host.corp/secret-path"
    tok = _allowlist(monkeypatch, "allowed.corp")
    try:
        assert ua.is_url_allowed(secret) is False          # 无 scheme ⇒ fail-closed
        with pytest.raises(HTTPAuthError) as ei:
            ua.check_url_allowed(secret)
        assert "secret-path" not in str(ei.value), f"消息里露了 URL：{ei.value}"
    finally:
        tc.reset_active_tenant(tok)


# ─── #6 正对照：合法 URL 照常放行并连通（防「一律拒绝」式假通过）──────


def test_normal_url_still_works(listener, monkeypatch):
    """⭐ **正对照** —— 没有它，一个「一律拒绝」的实现也能让上面所有测变绿。"""
    import requests

    from knot.adapters.http import url_allowlist as ua
    from knot.core import tenant_context as tc

    port, hits = listener
    tok = _allowlist(monkeypatch, "127.0.0.1")
    try:
        normalized = ua.check_url_allowed(f"http://127.0.0.1:{port}/v1/ok")
        requests.get(normalized, timeout=5, allow_redirects=False)
        assert hits[-1]["path"] == "/v1/ok", f"正常 URL 没连通：{hits}"
    finally:
        tc.reset_active_tenant(tok)


def test_proxy_env_names_cover_what_production_considers_routing_changing():
    """⭐ 本文件 fixture 清空的代理 env **必须覆盖**生产认为「能改道」的全部名字。

    ⚠️ **这是六问⑥第二形态的机械守护**：`listener` 的所有否定断言（「目标监听器零收到」）
    只有在**没有代理**时才有意义。若哪天生产在 `_PROXY_ENVS` 里加了一个新名字
    （比如某个 `*_PROXY` 变体）而本 fixture 没跟着清，那么在设了该变量的机器上
    ——**包括 CI**—— 那些否定断言会重新变成「对空集的断言」而**不会红**。

    ⚠️ 两份清单刻意**各自独立**（不 import 复用）：测里那份是「让否定断言有意义」的**前提**，
    不该由被测代码定义 —— 否则被测代码把某个名字删掉，前提也跟着悄悄放松。
    ⇒ 独立 + 交叉核对，而不是共用一份。
    """
    from knot.adapters.http import url_canon as ua

    missing = sorted(set(ua._PROXY_ENVS) - set(_PROXY_ENVS))
    assert not missing, (
        f"生产 `url_canon._PROXY_ENVS` 里的 {missing} 没被本文件 fixture 清空 ——\n"
        "⇒ 在设了这些变量的机器上，本文件的「零收到」断言会静默变成对空集的断言。\n"
        "请把它们加进本文件的 `_PROXY_ENVS`。"
    )
