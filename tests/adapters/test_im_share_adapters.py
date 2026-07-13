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


def _lark_router(counter):
    """按 URL 路由 mock 响应；counter 记 token 端点命中次数。"""
    def _post(url, timeout=None, headers=None, json=None, data=None, files=None, **k):
        if "tenant_access_token" in url:
            counter["token"] += 1
            return _Resp({"code": 0, "tenant_access_token": "t-abc", "expire": 7200})
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
