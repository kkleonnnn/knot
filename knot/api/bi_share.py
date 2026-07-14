"""bi_share 路由（v0.8.14）— BI 报表分享（快照 PNG → Lark/TG admin 白名单群）。

新建独立文件（bi_reports.py 近 ACK cap）。R-BI-SHARE-1 三重出境控制：
  ① require_report_perm("share") 权限门 ② 服务端 target_id ∈ 白名单（bi_share_service fail-fast）
  ③ 独立 IM egress allowlist（adapter 层）。
R-BI-1：与 saved_reports/Chat 0 触；全新 /api/bi/reports/{id}/share。
审计（R-BI-8）：bi_report.share 常量直调 emit（AST 可抓；无 sql_text / 无 token — R-BI-6/SHARE-3）。
"""
from __future__ import annotations

import asyncio
import base64
import binascii

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from knot.api._audit_helpers import audit
from knot.api.bi_reports import require_report_perm
from knot.api.deps import get_current_user
from knot.repositories import bi_share_target_repo as target_repo
from knot.services import bi_share_service as share_svc

router = APIRouter()


@router.get("/api/bi/share/targets")
async def list_share_targets_for_picker(user=Depends(get_current_user)):
    """用户分享选择器用：列白名单目标（仅 id/name/platform；**不含 chat_id/凭据**）。
    任何已认证用户可列（选择器；实际投递由 /share 端点 require_report_perm('share') + 服务端 target_id 校验守）。"""
    return [{"id": t["id"], "name": t["name"], "platform": t["platform"]}
            for t in target_repo.list_targets()]

_MAX_PNG_BYTES = 8 * 1024 * 1024        # 快照 PNG 原始上限 8MB（TG/Lark 各 10MB，留裕量）
_MAX_BODY_BYTES = 12 * 1024 * 1024      # 请求体声明上限（base64 膨胀 ~33% + JSON 开销）
_MAX_TARGETS = 20                       # 单次分享目标数上限


class ReportShareRequest(BaseModel):
    image_png: str                      # base64 PNG（前端离屏截图）
    target_ids: list[int]
    caption: str = ""


@router.post("/api/bi/reports/{report_id}/share")
async def share_report_endpoint(report_id: int, req: ReportShareRequest, request: Request,
                                user=Depends(require_report_perm("share"))):
    # body-size 声明上限早拒（§9-C2；真正 pre-buffer 防护依赖反代 body 限，本端点须 auth+share 权、缓解面窄）
    cl = request.headers.get("content-length")
    if cl and cl.isdigit() and int(cl) > _MAX_BODY_BYTES:
        raise HTTPException(status_code=413, detail="请求体过大")
    if not req.target_ids:
        raise HTTPException(status_code=400, detail="未选择投递目标")
    if len(req.target_ids) > _MAX_TARGETS:
        raise HTTPException(status_code=400, detail=f"投递目标过多（≤{_MAX_TARGETS}）")
    try:
        png = base64.b64decode(req.image_png or "", validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(status_code=400, detail="image_png 非合法 base64") from None
    if not png:
        raise HTTPException(status_code=400, detail="image_png 为空")
    if len(png) > _MAX_PNG_BYTES:
        raise HTTPException(status_code=413, detail=f"图片过大（≤{_MAX_PNG_BYTES // (1024 * 1024)}MB）")

    loop = asyncio.get_event_loop()
    try:  # SYNC 分享（阻塞 HTTP fan-out）卸载线程池
        results = await loop.run_in_executor(None, share_svc.share_report, png, req.target_ids, req.caption)
    except share_svc.ShareValidationError as e:
        # 校验失败（target_id∉白名单/凭据缺，fan-out 前 0 出境）→ 400，无出境尝试不审计
        raise HTTPException(status_code=400, detail=str(e)) from None
    except Exception as e:
        # 意外错误（如 KNOT_MASTER_KEY 轮换后凭据解密失败）→ 出境尝试仍留痕（审计完整性），再 502
        audit(request, user, action="bi_report.share", resource_type="bi_report", resource_id=report_id,
              detail={"target_count": len(req.target_ids), "ok_count": 0, "error": type(e).__name__})
        raise HTTPException(status_code=502, detail="分享投递失败") from None

    ok = sum(1 for r in results if r.get("ok"))
    audit(request, user, action="bi_report.share", resource_type="bi_report", resource_id=report_id,
          detail={"target_count": len(results), "ok_count": ok, "target_ids": [r["id"] for r in results]})
    return {"results": results, "ok_count": ok, "total": len(results)}
