"""bi_share_service — v0.8.14 分享编排：校验白名单 → 解密凭据 → fan-out 到 IM 适配器。

R-BI-SHARE-1：target_id 逐查白名单、任一 miss 即整请求失败（fail-fast，**fan-out 前**完成全校验 +
  凭据预检）；不半发。chat_id 从白名单行取（用户从不直接提供 chat_id）。
Contract 7：service 经 settings_repo 拿**明文**凭据传入 adapter（adapter 不碰 core.crypto）。
阻塞 HTTP：调用方（async 端点）用 loop.run_in_executor 卸载本 **SYNC** 函数。
"""
from __future__ import annotations

from knot.adapters.notification.lark import LarkError, LarkImageAdapter
from knot.adapters.notification.telegram import TelegramError, TelegramImageAdapter
from knot.repositories import bi_share_target_repo as target_repo
from knot.repositories import settings_repo


class ShareValidationError(Exception):
    """校验失败（target_id 不在白名单 / 未选目标 / 凭据缺失）→ 端点映射 400。fan-out 前抛。"""


def _resolve_targets(target_ids: list[int]) -> list[dict]:
    """逐 target_id 校验 ∈ bi_share_targets；任一 miss → 整请求失败（保序去重）。"""
    uniq = list(dict.fromkeys(int(i) for i in target_ids))
    if not uniq:
        raise ShareValidationError("未选择投递目标")
    found = {t["id"]: t for t in target_repo.get_targets_by_ids(uniq)}
    missing = [i for i in uniq if i not in found]
    if missing:
        raise ShareValidationError(f"投递目标不存在：{missing}")
    return [found[i] for i in uniq]


def _resolve_creds(platforms: set[str]) -> dict:
    """按需解密平台凭据；缺失即整请求失败（fan-out 前）。"""
    creds: dict = {}
    if "tg" in platforms:
        token = settings_repo.get_app_setting("telegram_bot_token")
        if not token:
            raise ShareValidationError("Telegram bot token 未配置（管理员设置里填）")
        creds["tg_token"] = token
    if "lark" in platforms:
        app_id = settings_repo.get_app_setting("lark_app_id")
        app_secret = settings_repo.get_app_setting("lark_app_secret")
        if not (app_id and app_secret):
            raise ShareValidationError("Lark app_id/app_secret 未配置（管理员设置里填）")
        creds["lark_app_id"] = app_id
        creds["lark_app_secret"] = app_secret
    return creds


def share_report(png: bytes, target_ids: list[int], caption: str = "") -> list[dict]:
    """SYNC 分享编排。校验全 target_id + 凭据（fail-fast，任一缺 → raise ShareValidationError）→
    逐目标发（单目标失败收集不中断其余）。返回 per-target 结果 [{id,name,ok,error?}]。
    """
    targets = _resolve_targets(target_ids)                 # fail-fast：全校验先行
    creds = _resolve_creds({t["platform"] for t in targets})  # 凭据预检（仍 fan-out 前）

    tg, lark = TelegramImageAdapter(), LarkImageAdapter()
    results = []
    for t in targets:
        try:
            if t["platform"] == "tg":
                tg.send_image(png, caption, t["chat_id"], creds["tg_token"])
            elif t["platform"] == "lark":
                lark.send_image(png, caption, t["chat_id"], app_id=creds["lark_app_id"],
                                app_secret=creds["lark_app_secret"], region=t.get("region") or "feishu")
            else:
                raise ShareValidationError(f"未知平台：{t['platform']}")
            results.append({"id": t["id"], "name": t["name"], "ok": True})
        except (TelegramError, LarkError, ShareValidationError) as e:
            # adapter 异常消息已 mask token/secret → 收集安全
            results.append({"id": t["id"], "name": t["name"], "ok": False, "error": str(e)})
    return results
