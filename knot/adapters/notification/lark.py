"""lark.py — v0.8.14 分享 Lark/飞书 图片投递（三步：tenant_access_token → 上传 image_key → 发消息）。

⚠️ R-BI-SHARE-3：tenant_access_token（Authorization header）+ app_secret（请求 body）= 机密。
  requests 异常 str 含 URL 但**不含** header/body → Lark URL 无 token；仍保守：异常只报 `type(e).__name__`
  + API `code`（不 interpolate 原始 e），永不含 token/secret；adapter 不 logger。
R-BI-SHARE-4：每个出站前过 is_im_host_allowed。
region：'feishu'→open.feishu.cn / 'lark'→open.larksuite.com（凭据/token/image_key 不跨区）。
content 双重编码：msg content 是 **JSON 字符串**（`json.dumps(dict)`），非嵌套对象（§9-C 常见坑）。
token 缓存 ~2h（Feishu >30min 返同 token；模块级 cache 避每发一次换取）。
Contract 7：adapter 禁 import core.crypto —— app_secret 由调用方解密后明文传入。
"""
from __future__ import annotations

import json
import time

from knot.adapters.notification.im_egress import is_im_host_allowed

_HOSTS = {"feishu": "https://open.feishu.cn", "lark": "https://open.larksuite.com"}
_TIMEOUT_SEC = 30
_TOKEN_SAFETY_SEC = 300               # 提前 5min 视为过期（避临界失效）
_LARK_IMAGE_MAX_BYTES = 10 * 1024 * 1024
_token_cache: dict = {}               # (region, app_id) -> (token, expires_at_epoch)


class LarkError(Exception):
    """Lark 投递失败。异常消息不含 token/secret。"""


def _base(region: str) -> str:
    b = _HOSTS.get(region or "feishu")
    if not b:
        raise LarkError(f"未知 Lark region: {region!r}（应 feishu / lark）")
    return b


def _post(url: str, **kw) -> dict:
    if not is_im_host_allowed(url):                    # R-BI-SHARE-4：每出站点 host 门
        raise LarkError("Lark host 不在 IM egress allowlist")
    import requests
    try:
        resp = requests.post(url, timeout=_TIMEOUT_SEC, **kw)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        raise LarkError(f"Lark 请求失败: {type(e).__name__}") from None  # 不含 URL/token/secret
    except ValueError as e:                            # resp.json() 解析失败
        raise LarkError(f"Lark 响应非 JSON: {type(e).__name__}") from None


def _tenant_token(region: str, app_id: str, app_secret: str) -> str:
    key = (region, app_id)
    cached = _token_cache.get(key)
    now = time.time()
    if cached and cached[1] - _TOKEN_SAFETY_SEC > now:
        return cached[0]
    data = _post(
        f"{_base(region)}/open-apis/auth/v3/tenant_access_token/internal",
        json={"app_id": app_id, "app_secret": app_secret},
    )
    token = data.get("tenant_access_token")
    if data.get("code") != 0 or not token:
        raise LarkError(f"Lark token 换取失败 code={data.get('code')}")  # 不含 secret
    _token_cache[key] = (token, now + int(data.get("expire", 7200)))
    return token


class LarkImageAdapter:
    """发 PNG 到 Lark chat（三步）。app_secret 明文由调用方传入（Contract 7）。失败抛 LarkError（无 token/secret）。"""

    def send_image(self, png: bytes, caption: str, chat_id: str, *,
                   app_id: str, app_secret: str, region: str = "feishu") -> None:
        if len(png) > _LARK_IMAGE_MAX_BYTES:
            raise LarkError("图片超过 Lark 10MB 上限")
        base = _base(region)
        token = _tenant_token(region, app_id, app_secret)
        auth = {"Authorization": f"Bearer {token}"}
        msg_url = f"{base}/open-apis/im/v1/messages?receive_id_type=chat_id"

        # 可选前置文本（Lark image 消息无原生 caption；caption 非空 → 先发 text）
        cap = (caption or "").strip()
        if cap:
            self._send_msg(msg_url, auth, chat_id, "text",
                           json.dumps({"text": cap[:2000]}, ensure_ascii=False))

        # step 2: 上传图片 → image_key
        up = _post(f"{base}/open-apis/im/v1/images", headers=auth,
                   data={"image_type": "message"},
                   files={"image": ("report.png", png, "image/png")})
        if up.get("code") != 0:
            raise LarkError(f"Lark 图片上传失败 code={up.get('code')}")
        image_key = (up.get("data") or {}).get("image_key")
        if not image_key:
            raise LarkError("Lark 图片上传无 image_key")

        # step 3: 发图片消息（content = 双重编码 JSON 字符串）
        self._send_msg(msg_url, auth, chat_id, "image",
                       json.dumps({"image_key": image_key}, ensure_ascii=False))

    @staticmethod
    def _send_msg(url: str, auth: dict, chat_id: str, msg_type: str, content: str) -> None:
        r = _post(url, headers=auth,
                  json={"receive_id": chat_id, "msg_type": msg_type, "content": content})
        if r.get("code") != 0:
            raise LarkError(f"Lark 发消息失败 code={r.get('code')} msg_type={msg_type}")
