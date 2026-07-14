"""telegram.py — v0.8.14 分享 Telegram 图片投递（sendPhoto multipart，超限走 sendDocument）。

⚠️ R-BI-SHARE-3：bot token 在 URL path（`/bot<TOKEN>/sendPhoto`）= 机密 → 所有异常消息**必 mask**
  token（`/bot<TOKEN>/` → `/bot***/`），永不含裸 URL/裸 token；adapter 不 logger（service 只 log 已 mask 的
  TelegramError.message；`from None` 切断 __context__ 防原始 requests 异常[含裸 URL]串进 traceback）。
R-BI-SHARE-4：出站前过 is_im_host_allowed。
Contract 7：adapter 禁 import core.crypto —— token 由调用方（service 经 settings_repo 解密）明文传入。
"""
from __future__ import annotations

import re

from knot.adapters.notification.im_egress import is_im_host_allowed

_TG_API = "https://api.telegram.org"
_TIMEOUT_SEC = 30                      # 图片上传比 webhook 5s 需更长
_TG_PHOTO_MAX_BYTES = 10 * 1024 * 1024  # TG sendPhoto <=10MB；超则 sendDocument 兜底（D8）
_CAPTION_MAX = 1024                     # TG caption 上限
_TOKEN_RE = re.compile(r"/bot[^/]+/")   # /bot<TOKEN>/ ；TG token 无 '/' → [^/]+ 吃全段


class TelegramError(Exception):
    """Telegram 投递失败（host 拒 / API 错）。异常消息已 mask token。"""


def _mask(text) -> str:
    """脱敏：URL 中 /bot<TOKEN>/ → /bot***/（异常 str 常含完整 URL；token-agnostic）。"""
    return _TOKEN_RE.sub("/bot***/", str(text))


def _mask_token(text, token: str) -> str:
    """token-aware 脱敏：先 URL-pattern scrub，再抹掉 token 字面（防裸 token 出现在任何位置）。"""
    s = _mask(text)
    return s.replace(token, "***") if token else s


class TelegramImageAdapter:
    """发 PNG 到 TG chat。token 明文由调用方传入（Contract 7）。send 失败抛 TelegramError（已 mask）。"""

    def send_image(self, png: bytes, caption: str, chat_id: str, token: str) -> None:
        method = "sendPhoto" if len(png) <= _TG_PHOTO_MAX_BYTES else "sendDocument"
        field = "photo" if method == "sendPhoto" else "document"
        url = f"{_TG_API}/bot{token}/{method}"
        def m(t):                                            # token-aware：URL pattern + token 字面双抹
            return _mask_token(t, token)
        if not is_im_host_allowed(url):                      # R-BI-SHARE-4：出站前 host 门
            raise TelegramError(f"TG host 不在 IM egress allowlist: {m(url)}")
        import requests  # 延迟 import（与 http executor 同库）

        cap = (caption or "")[:_CAPTION_MAX]                  # 纯文本，不设 parse_mode（防标记注入 §9-C）
        try:
            resp = requests.post(
                url,
                data={"chat_id": chat_id, "caption": cap},
                files={field: ("report.png", png, "image/png")},
                timeout=_TIMEOUT_SEC,
            )
            resp.raise_for_status()
        except requests.RequestException as e:
            raise TelegramError(f"TG {method} 失败: {m(e)}") from None
        # TG 返 {ok:true/false}；ok=false 也是 200 → 显式查
        try:
            body = resp.json()
        except ValueError:
            body = {}
        if not body.get("ok", False):
            raise TelegramError(f"TG {method} 返回 ok=false: {m(body.get('description', ''))}")
