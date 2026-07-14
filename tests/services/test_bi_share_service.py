"""tests/services/test_bi_share_service.py — v0.8.14 分享编排守护。

R-BI-SHARE-1 fail-fast（target_id ∈ 白名单 / 凭据预检，fan-out 前）+ 部分失败不中断 + chat_id 从白名单取。
"""
import pytest

from knot.services import bi_share_service as svc


@pytest.fixture
def wired(monkeypatch):
    """接线：白名单 2 行（tg+lark）+ 凭据齐 + adapter 记录调用（不真发）。"""
    targets = {
        1: {"id": 1, "name": "运营TG", "platform": "tg", "chat_id": "-100tg", "region": None},
        2: {"id": 2, "name": "日报Lark", "platform": "lark", "chat_id": "oc_lark", "region": "feishu"},
    }
    monkeypatch.setattr(svc.target_repo, "get_targets_by_ids",
                        lambda ids: [targets[i] for i in dict.fromkeys(ids) if i in targets])
    monkeypatch.setattr(svc.settings_repo, "get_app_setting",
                        lambda k, default="": {"telegram_bot_token": "tg-tok",
                                               "lark_app_id": "cli", "lark_app_secret": "sec"}.get(k, default))
    sent = []

    class _TG:
        def send_image(self, png, caption, chat_id, token):
            sent.append(("tg", chat_id, token))

    class _Lark:
        def send_image(self, png, caption, chat_id, *, app_id, app_secret, region):
            sent.append(("lark", chat_id, region))

    monkeypatch.setattr(svc, "TelegramImageAdapter", _TG)
    monkeypatch.setattr(svc, "LarkImageAdapter", _Lark)
    return sent


def test_happy_path_fans_out_with_whitelist_chat_id(wired):
    res = svc.share_report(b"PNG", [1, 2], caption="日报")
    assert all(r["ok"] for r in res)
    # chat_id 来自白名单行（非用户输入）；tg 收到 token
    assert ("tg", "-100tg", "tg-tok") in wired
    assert ("lark", "oc_lark", "feishu") in wired


def test_bad_target_id_fails_fast_no_send(wired):
    """任一 target_id ∉ 白名单 → 整请求 raise，且 0 adapter 调用（fan-out 前拦）。"""
    with pytest.raises(svc.ShareValidationError):
        svc.share_report(b"PNG", [1, 999], caption="x")
    assert wired == []                                     # 没发出任何一条


def test_empty_targets_raises(wired):
    with pytest.raises(svc.ShareValidationError):
        svc.share_report(b"PNG", [], caption="x")
    assert wired == []


def test_missing_tg_creds_fails_before_send(monkeypatch):
    monkeypatch.setattr(svc.target_repo, "get_targets_by_ids",
                        lambda ids: [{"id": 1, "name": "t", "platform": "tg", "chat_id": "-1", "region": None}])
    monkeypatch.setattr(svc.settings_repo, "get_app_setting", lambda k, default="": "")  # 无凭据
    called = []
    monkeypatch.setattr(svc, "TelegramImageAdapter",
                        lambda: type("X", (), {"send_image": lambda *a, **k: called.append(1)})())
    with pytest.raises(svc.ShareValidationError):
        svc.share_report(b"PNG", [1])
    assert called == []                                    # 凭据缺 → fan-out 前失败


def test_partial_failure_collected_not_interrupted(monkeypatch):
    monkeypatch.setattr(svc.target_repo, "get_targets_by_ids",
                        lambda ids: [{"id": 1, "name": "TG坏", "platform": "tg", "chat_id": "-1", "region": None},
                                     {"id": 2, "name": "Lark好", "platform": "lark", "chat_id": "oc", "region": "feishu"}])
    monkeypatch.setattr(svc.settings_repo, "get_app_setting",
                        lambda k, default="": {"telegram_bot_token": "t", "lark_app_id": "c",
                                               "lark_app_secret": "s"}.get(k, default))
    from knot.adapters.notification.telegram import TelegramError

    class _TG:
        def send_image(self, *a, **k):
            raise TelegramError("TG 挂了")

    lark_hit = []

    class _Lark:
        def send_image(self, *a, **k):
            lark_hit.append(1)

    monkeypatch.setattr(svc, "TelegramImageAdapter", _TG)
    monkeypatch.setattr(svc, "LarkImageAdapter", _Lark)
    res = svc.share_report(b"PNG", [1, 2])
    by_id = {r["id"]: r for r in res}
    assert by_id[1]["ok"] is False and "TG 挂了" in by_id[1]["error"]
    assert by_id[2]["ok"] is True                          # 第一个失败不中断第二个
    assert lark_hit == [1]
