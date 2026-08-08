"""tests/adapters/test_im_share_adapters.py — v0.8.14 分享 IM 适配器守护。

守护者 B1（token 脱敏）+ B4（egress guard 逐出站点强制）+ Lark 三步/双重编码/token 缓存 + region。
"""
import pytest

from knot.adapters.notification import im_egress as eg
from knot.adapters.notification import lark as lk
from knot.adapters.notification import telegram as tg

_TOKEN = "123456789:AAExampleSecretTokenXYZ-_"


class _Resp:
    def __init__(self, payload, status_ok=True):
        self._payload = payload
        self._status_ok = status_ok

    def raise_for_status(self):
        if not self._status_ok:
            import requests
            raise requests.HTTPError(f"404 for url ...{self._url}")  # pragma: no cover

    def json(self):
        return self._payload


# ── im_egress host allowlist ─────────────────────────────────────────
def test_im_egress_allows_fixed_hosts():
    assert eg.is_im_host_allowed(f"https://api.telegram.org/bot{_TOKEN}/sendPhoto")
    assert eg.is_im_host_allowed("https://open.feishu.cn/open-apis/im/v1/images")
    assert eg.is_im_host_allowed("https://open.larksuite.com/open-apis/im/v1/messages")


def test_im_egress_denies_others():
    assert eg.is_im_host_allowed("https://evil.com/x") is False
    assert eg.is_im_host_allowed("") is False
    assert eg.is_im_host_allowed("https://api-telegram-org.evil.com/x") is False


# ── Telegram：token 脱敏 + host 门 + 成功路径 ────────────────────────
def test_tg_mask_scrubs_token():
    leaky = f"ConnectionError: https://api.telegram.org/bot{_TOKEN}/sendPhoto timed out"
    masked = tg._mask(leaky)
    assert _TOKEN not in masked and "/bot***/" in masked


def test_tg_host_gate_rejects_before_request(monkeypatch):
    """B4：出站前 host 门。改 _TG_API 到非白名单 → send_image 在任何 requests 前 raise。"""
    monkeypatch.setattr(tg, "_TG_API", "https://evil.com")
    import requests
    monkeypatch.setattr(requests, "post", lambda *a, **k: pytest.fail("host 门未拦，竟发出 request"))
    with pytest.raises(tg.TelegramError):
        tg.TelegramImageAdapter().send_image(b"PNG", "cap", "-100123", _TOKEN)


def test_tg_error_message_never_leaks_token(monkeypatch):
    """B1：requests 异常 str 含 token URL → TelegramError 消息必 mask。"""
    import requests

    def _raise(*a, **k):
        raise requests.ConnectionError(f"failed https://api.telegram.org/bot{_TOKEN}/sendPhoto")

    monkeypatch.setattr(requests, "post", _raise)
    with pytest.raises(tg.TelegramError) as ei:
        tg.TelegramImageAdapter().send_image(b"PNG", "cap", "-100123", _TOKEN)
    assert _TOKEN not in str(ei.value)
    assert ei.value.__cause__ is None  # from None：切断 __context__（原始异常不串进链）


def test_tg_success_multipart_and_caption_cap(monkeypatch):
    calls = {}
    import requests

    def _post(url, data=None, files=None, timeout=None, **k):
        calls.update(url=url, data=data, files=files)
        return _Resp({"ok": True})

    monkeypatch.setattr(requests, "post", _post)
    tg.TelegramImageAdapter().send_image(b"PNGBYTES", "x" * 2000, "-100123", _TOKEN)
    assert calls["data"]["chat_id"] == "-100123"
    assert len(calls["data"]["caption"]) == 1024           # 截到 TG 上限
    assert calls["files"]["photo"][2] == "image/png"
    assert _TOKEN in calls["url"]                          # 真实出站 URL 带 token（仅出站，不入异常/日志）


def test_tg_ok_false_raises_masked(monkeypatch):
    import requests
    monkeypatch.setattr(requests, "post",
                        lambda *a, **k: _Resp({"ok": False, "description": f"bad bot{_TOKEN}"}))
    with pytest.raises(tg.TelegramError) as ei:
        tg.TelegramImageAdapter().send_image(b"P", "c", "-1", _TOKEN)
    assert _TOKEN not in str(ei.value)


# ── Lark：三步 + 双重编码 content + token 缓存 + region + host 门 ─────
@pytest.fixture(autouse=True)
def _clear_lark_cache():
    lk._token_cache.clear()
    yield
    lk._token_cache.clear()


#: mock 认可的 (app_id → app_secret)。**其余一律视为凭据错误。**
#: ⚠️ 现有用例用的两组：`("cli_x","sec")` 与 `("c","s")` —— 保持它们通过，
#: 但**任何第三组组合从此拿不到 token**。
_LARK_VALID_CREDS = {"cli_x": "sec", "c": "s"}


def _lark_router(counter, *, valid_creds=None, token_by_app=None):
    """按 URL 路由 mock 响应；counter 记 token 端点命中次数。

    ⭐ **v0.9.18 P-a0：token 端点从此校验 `app_secret`**（原先**无条件**返 `code:0`+token）。

    ⚠️ **为什么这是本片的必做项而不是加强**（Stage 2 lens A 实跑坐实）：
    P-a 的核心验收是「**同 `app_id` + 错 secret ⇒ 拿不到 token**」。
    在旧 router 下，那条判据**修复前后都不成立** —— 因为 mock 无论 secret 是什么都发 token
    ⇒ 「拿到了 token」这个事件在 oracle 里**无法区分**「缓存串了」与「mock 太宽松」。
    ⇒ **五问②：注入产生不了要测的后果 ⇒ 取材证明是空的。**
    先修 harness，P-a 的判据才有意义。

    `token_by_app` 可选：让不同 app_id 拿到**不同** token 串，供 P-a 断言
    「B 从未取得 A 的 token」这类**内容级**判据（比「拿到了/没拿到」更强）。
    """
    creds = _LARK_VALID_CREDS if valid_creds is None else valid_creds

    def _post(url, timeout=None, headers=None, json=None, data=None, files=None, **k):
        if "tenant_access_token" in url:
            counter["token"] += 1
            body = json or {}
            app_id, app_secret = body.get("app_id"), body.get("app_secret")
            # ⭐ 真实飞书对错误凭据返 code=10014；照抄它，让 adapter 走它真实的失败分支
            if creds.get(app_id) != app_secret:
                counter.setdefault("rejected", []).append(app_id)
                return _Resp({"code": 10014, "msg": "invalid app_secret"})
            tok = (token_by_app or {}).get(app_id, "t-abc")
            return _Resp({"code": 0, "tenant_access_token": tok, "expire": 7200})
        if "im/v1/images" in url:
            return _Resp({"code": 0, "data": {"image_key": "img_v2_KEY"}})
        if "im/v1/messages" in url:
            counter.setdefault("msgs", []).append(json)
            return _Resp({"code": 0, "data": {"message_id": "om_1"}})
        return _Resp({"code": 99})  # pragma: no cover
    return _post


def test_lark_three_step_double_encoded_content(monkeypatch):
    import json as _json

    import requests
    counter = {"token": 0}
    monkeypatch.setattr(requests, "post", _lark_router(counter))
    lk.LarkImageAdapter().send_image(b"PNG", "本月日报", "oc_chat", app_id="cli_x",
                                     app_secret="sec", region="feishu")
    img_msg = counter["msgs"][-1]
    assert img_msg["msg_type"] == "image"
    assert isinstance(img_msg["content"], str)              # 双重编码：content 是 JSON 字符串非嵌套对象
    assert _json.loads(img_msg["content"]) == {"image_key": "img_v2_KEY"}
    assert img_msg["receive_id"] == "oc_chat"
    # caption 非空 → 先发 text 消息
    assert any(m.get("msg_type") == "text" for m in counter["msgs"])


def test_lark_router_rejects_wrong_secret(monkeypatch):
    """⭐ 守 **harness 本身**（v0.9.18 P-a0）：错 secret ⇒ 换不到 token。

    ⚠️ **为什么这条测的对象是 mock 而不是生产码**：P-a 要断言的性质是
    「同 `app_id` + 错 secret ⇒ 拿不到 token」。若 mock 无条件发 token，
    那条断言**在修复前后都不成立** ⇒ 它证明不了任何事（五问②）。
    ⇒ 本测钉住 harness 的判别力：**mock 必须能区分对/错 secret**。
    删掉 `_lark_router` 里的 secret 校验 ⇒ 本测红 ⇒ P-a 的核心判据不会在无声中变空。
    """
    import requests
    counter = {"token": 0}
    monkeypatch.setattr(requests, "post", _lark_router(counter))
    with pytest.raises(lk.LarkError):
        lk.LarkImageAdapter().send_image(b"P", "", "oc_1", app_id="cli_x",
                                         app_secret="WRONG", region="feishu")
    assert counter["token"] == 1, "应当**真的**去换过一次 token（而不是在更早的地方就失败了）"
    assert counter.get("rejected") == ["cli_x"], "mock 未按 secret 拒绝 —— harness 无判别力"


# ─── v0.9.18 P-a · D2：token 缓存键含租户 + secret 摘要 ────────────────
def _tenant_ctx(tid: int):
    from knot.core.tenant_context import set_active_tenant
    return set_active_tenant({"id": tid, "db_dir": "."})


def _reset(tok):
    from knot.core.tenant_context import reset_active_tenant
    reset_active_tenant(tok)


def test_cache_is_really_hit_for_same_tenant_same_secret(monkeypatch):
    """⭐ **先证明缓存真被命中**，否则下面「跨租户不命中」测的是「两次都去换 token」（五问③）。

    ⚠️ **不能复用 `test_lark_token_cached_across_sends`**：它两次传**同一个** `app_secret`
    且不涉及租户 —— 键加了 secret 摘要后它**照样绿**，故对本片的改动**零判别力**（Stage 2 A6）。
    本测显式在**同一租户 ctx** 下跑，才是「新键仍然会命中」的证据。
    """
    import requests
    counter = {"token": 0}
    monkeypatch.setattr(requests, "post", _lark_router(counter))
    tok = _tenant_ctx(1)
    try:
        a = lk.LarkImageAdapter()
        a.send_image(b"P", "", "oc_1", app_id="cli_x", app_secret="sec", region="feishu")
        a.send_image(b"P", "", "oc_2", app_id="cli_x", app_secret="sec", region="feishu")
    finally:
        _reset(tok)
    assert counter["token"] == 1, "同租户同凭据第二次没命中缓存 —— 后续「不命中」类断言将失去意义"


def test_tenant_b_never_obtains_tenant_a_token(monkeypatch):
    """⭐ **内容级判据**：B 不只是「也去换了一次」，而是**从未持有 A 的那个 token 串**。

    ⚠️ 「不同租户拿到不同 token」只证明**隔离**；本测更进一步 ——
    断言**所有出站请求的 Authorization 头里都不出现 A 的 token**（P-a0 备的 `token_by_app` 使之可能）。
    revert-to-bad：键去掉租户维度 ⇒ B 命中 A 的缓存 ⇒ 本测红且**点名那个 token 串**。
    """
    import requests
    counter = {"token": 0}
    seen_auth: list = []
    router = _lark_router(counter, token_by_app={"cli_x": "TOKEN-OF-A"})

    def _spy(url, timeout=None, headers=None, **k):
        if headers and "Authorization" in headers:
            seen_auth.append(headers["Authorization"])
        return router(url, timeout=timeout, headers=headers, **k)

    monkeypatch.setattr(requests, "post", _spy)

    tok = _tenant_ctx(1)                       # 租户 A 先发一次 ⇒ 其 token 进缓存
    try:
        lk.LarkImageAdapter().send_image(b"P", "", "oc_a", app_id="cli_x", app_secret="sec", region="feishu")
    finally:
        _reset(tok)
    assert any("TOKEN-OF-A" in h for h in seen_auth), "前置不成立：A 根本没拿到它的 token"

    seen_auth.clear()
    counter["token"] = 0
    tok = _tenant_ctx(2)                       # 租户 B：**app_id 与 secret 都与 A 相同**
    try:
        lk.LarkImageAdapter().send_image(b"P", "", "oc_b", app_id="cli_x",
                                         app_secret="sec", region="feishu")
    finally:
        _reset(tok)
    # ⭐ 隔离的是**租户维度**：凭据完全相同 ⇒ 唯一能让键不同的就是租户
    #    ⇒ B 必须**自己去换一次**，不得直接复用 A 的缓存条目。
    assert counter["token"] == 1, (
        "租户 B 用相同凭据时**命中了 A 的缓存条目** —— 缓存键里没有租户维度。\n"
        "⇒ 这是纵深防御层：secret 摘要挡住了「猜 app_id」那条路，本断言挡住的是"
        "「缓存条目跨租户共用」本身。"
    )


def test_rotating_secret_takes_effect_immediately(monkeypatch):
    """理由②：同租户换 secret ⇒ **立刻**重新换取，而非沿用缓存里的旧 token（≤2h）。

    ⚠️⚠️ **初版这条测判别力为零，是跑 revert 才发现的**（记在这里因为它是本片最贵的一课）：
    初版让旧 secret **一开始就无效** ⇒ 换取失败 ⇒ **失败不写缓存** ⇒ 第二次仍是 miss
    ⇒ `counter == 2` 在「键含 secret」与「键不含 secret」两种实现下**都成立**
    ⇒ 判据**表示不了**「旧 token 被复用」这个我要排除的事件（五问②）。
    ⇒ 修法：**旧 secret 必须先成功一次并进缓存**，然后才轮换 —— 那时「复用旧 token」才可能发生。
    """
    import requests
    counter = {"token": 0}
    creds = {"cli_x": "sec-OLD"}                       # ⚠️ 可变 ⇒ 中途轮换
    monkeypatch.setattr(requests, "post",
                        _lark_router(counter, valid_creds=creds,
                                     token_by_app={"cli_x": "TOKEN-OLD"}))
    tok = _tenant_ctx(1)
    try:
        a = lk.LarkImageAdapter()
        a.send_image(b"P", "", "oc_1", app_id="cli_x", app_secret="sec-OLD", region="feishu")
        assert counter["token"] == 1                   # 前置：旧凭据成功且**已进缓存**
        creds["cli_x"] = "sec-NEW"                     # ← 轮换
        a.send_image(b"P", "", "oc_2", app_id="cli_x", app_secret="sec-NEW", region="feishu")
    finally:
        _reset(tok)
    assert counter["token"] == 2, (
        "换 secret 后**没有**重新换取 token —— 说明它命中了旧 secret 那条缓存 ⇒ 键里没有 secret 维度"
    )


def test_lark_token_cached_across_sends(monkeypatch):
    import requests
    counter = {"token": 0}
    monkeypatch.setattr(requests, "post", _lark_router(counter))
    a = lk.LarkImageAdapter()
    a.send_image(b"P", "", "oc_1", app_id="cli_x", app_secret="sec", region="feishu")
    a.send_image(b"P", "", "oc_2", app_id="cli_x", app_secret="sec", region="feishu")
    assert counter["token"] == 1                            # 第二次复用缓存，不再换取


def test_lark_region_hosts(monkeypatch):
    import requests
    seen = {"hosts": set()}

    def _post(url, timeout=None, **k):
        from urllib.parse import urlparse
        seen["hosts"].add(urlparse(url).hostname)
        if "tenant_access_token" in url:
            return _Resp({"code": 0, "tenant_access_token": "t", "expire": 7200})
        if "images" in url:
            return _Resp({"code": 0, "data": {"image_key": "k"}})
        return _Resp({"code": 0})

    monkeypatch.setattr(requests, "post", _post)
    lk.LarkImageAdapter().send_image(b"P", "", "oc_1", app_id="c", app_secret="s", region="lark")
    assert seen["hosts"] == {"open.larksuite.com"}          # 国际 region 走 larksuite


def test_lark_unknown_region_raises():
    with pytest.raises(lk.LarkError):
        lk.LarkImageAdapter().send_image(b"P", "", "oc", app_id="c", app_secret="s", region="qq")


def test_lark_token_failure_no_secret_leak(monkeypatch):
    import requests
    monkeypatch.setattr(requests, "post",
                        lambda url, timeout=None, **k: _Resp({"code": 99, "msg": "bad app_secret sec-XYZ"}))
    with pytest.raises(lk.LarkError) as ei:
        lk.LarkImageAdapter().send_image(b"P", "", "oc", app_id="c", app_secret="sec-XYZ", region="feishu")
    assert "sec-XYZ" not in str(ei.value)                   # secret 不进异常


def test_lark_host_gate_rejects(monkeypatch):
    import requests
    monkeypatch.setitem(lk._HOSTS, "feishu", "https://evil.com")
    monkeypatch.setattr(requests, "post", lambda *a, **k: pytest.fail("host 门未拦"))
    with pytest.raises(lk.LarkError):
        lk.LarkImageAdapter().send_image(b"P", "", "oc", app_id="c", app_secret="s", region="feishu")


def test_lark_non_dict_json_raises_larkerror(monkeypatch):
    """对抗复核 fix：合法但非 dict JSON（list）→ LarkError（非 AttributeError 逃逸出 adapter）。"""
    import requests
    monkeypatch.setattr(requests, "post", lambda url, timeout=None, **k: _Resp(["not", "a", "dict"]))
    with pytest.raises(lk.LarkError):
        lk.LarkImageAdapter().send_image(b"P", "", "oc", app_id="c", app_secret="s", region="feishu")
