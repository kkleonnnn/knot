"""totp api — v0.6.2.0 TOTP 2FA 4 端点 + interim_token 流程。

红线落地（commit 3 范围 — R-PB-B1-3/6/9/13）：
- R-PB-B1-3：admin 三层防御 — 在 deps.py + main.py 启动期；本文件不动
- R-PB-B1-6：enforce_totp_verify_rate_limit / enforce_totp_enroll_rate_limit
- R-PB-B1-9 Session 验证补充：login 成功 + totp_enrolled → interim_token（短期，仅含 verify 权限）
- R-PB-B1-13：reset 必 invalidate_token_version_cache + bump_token_version_in_tx（service 内已落）

interim_token 设计（区别于完整 JWT）：
- payload = {"sub": user_id, "totp_pending": true, "exp": now+5min, "ver": token_version}
- 仅 /api/totp/verify 接受；其他端点拒绝（防绕过 TOTP 直接拿 interim 调业务接口）
- verify 通过后 → 颁发完整 JWT（含 totp_verified=true）
"""
import contextlib
from datetime import datetime, timedelta

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request

from knot.api._audit_helpers import audit
from knot.api._rate_limit import (
    enforce_totp_enroll_complete_rate_limit,
    enforce_totp_enroll_rate_limit,
    enforce_totp_verify_rate_limit,
)
from knot.api.deps import (
    JWT_ALGORITHM,
    _get_secret,
    create_token,
    get_current_user,
    require_admin,
)
from knot.api.schemas import (
    TotpEnrollCompleteRequest,
    TotpResetRequest,
    TotpVerifyRequest,
)
from knot.core.tenant_context import (
    clear_active_tenant,
    reset_active_tenant,
    set_active_tenant,
)
from knot.repositories import tenant_repo
from knot.services import totp_service

router = APIRouter()

# interim_token：5 分钟有效期 — 用户扫码后慢慢输入也够（业界标准）
_INTERIM_EXPIRE_MIN = 5


def create_interim_token(user_id: int, token_version: int) -> str:
    """login 成功 + totp_enrolled 后颁发 — 仅 /api/totp/verify 接受。

    v0.9.4 D1/B-3：payload 加 **`tid`**。本函数是**第二条独立签发路径**（与 `create_token` 不共码：
    不同文件、`ver` 由调用方传、此前**不依赖 tenant ctx**）⇒ 漏加 tid **不会崩、只会静默失能**
    （TOTP 二阶段登录在多租户下无 tid 可用）。
    ⭐ **F-4 裁定：tid 由本函数内部从 `current_tenant()` 取，不由调用方传** —— 守护者的理由：
    `token_version` 本就是调用方传的参数，**正是这种签名风格让「漏传」变成静默**；内部取 ctx 把
    静默失能变成**响亮崩溃**（无 ctx 即 raise）。
    """
    exp = datetime.utcnow() + timedelta(minutes=_INTERIM_EXPIRE_MIN)
    from knot.core.tenant_context import current_tenant
    tid = current_tenant()["id"]      # fail-closed：无 ctx 即 raise
    return jwt.encode(
        {"sub": str(user_id), "totp_pending": True, "ver": token_version, "tid": tid, "exp": exp},
        _get_secret(), algorithm=JWT_ALGORITHM,
    )


def _verify_interim_signature(token: str) -> dict:
    """**第一段（ctx-free）**：验签 + 形状校验 + 取 `sub`/`ver`/`tid`。**不查吊销**（那要读租户库）。

    ⚠️ **模块私有，且禁止在 `interim_session` 之外调用**（v0.9.4 R-12，AST 哨兵守）——
    本函数返回的 payload 是「**验了签但没验吊销**」的半成品；任何拿到它就往下走的代码
    都会复活 #259 修掉的洞。**没有任何 public API 会交出这个半成品**，所以「忘记验吊销」
    不是一个能犯的错（守护者 Q1 裁定：我原提的「marker 类型让漏调在类型层面暴露」在本仓
    **不成立** —— 闸门只有 ruff + import-linter + pytest，**无类型检查器** ⇒ 拿不到类型级保证，
    只能靠「不暴露半成品」这个结构性手段）。

    `type(ver) is int` 严格化：`bool` 是 `int` 子类且 `True == 1`，宽松比较会让 `{"ver": true}` 误过。
    `tid` 同口径严格（v0.9.4 R-10 D9）：缺失 / 非 int / ≤0 一律 401 —— **禁 SQLite 隐式类型转换
    参与租户解析**。存量（升级前签发的）interim 无 `tid` ⇒ 在此 401，用户重登一次即可（D8）。
    """
    try:
        payload = jwt.decode(token, _get_secret(), algorithms=[JWT_ALGORITHM])
        if not payload.get("totp_pending"):
            raise HTTPException(status_code=401, detail="非 interim token")
        sub, ver, tid = payload.get("sub"), payload.get("ver"), payload.get("tid")
        if type(ver) is not int or not isinstance(sub, str) or not sub.isdigit():
            raise HTTPException(status_code=401, detail="无效的 interim token")
        if type(tid) is not int or tid <= 0:
            raise HTTPException(status_code=401, detail="无效的 interim token")
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="TOTP 验证窗口超时，请重新登录")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="无效的 interim token")


def _assert_interim_not_revoked(user_id: int, ver: int) -> None:
    """**第二段（需 ctx）**：吊销比对。读 `users.token_version`（租户库）⇒ 必须在 ctx 已建之后调。

    ⭐ SECURITY hotfix：此前本函数**只验签 + 只看 totp_pending，从不读 `ver`** —— 而
    `create_interim_token` 明明把 `ver` 放进了 payload（:49）。后果是**「吊销所有会话」对登录中途的人无效**：
    吊销机制 = `users.token_version + 1`（`user_repo.py:174/192`）使所有旧 token 作废（`deps.py:134-136`
    比对 payload.ver）；但 interim token 不参与该比对 ⇒ 用户改密 / 管理员 TOTP reset 之后，攻击者手里
    5 分钟窗口内的旧 interim **仍能通过本函数**，并经 verify 端点 `create_token()` **换出一张当前有效的
    完整 JWT**（实测：bump 1→2 后旧 interim 仍过，换出的 JWT ver=2）⇒ **改密救不了受害者**，作废的凭证
    被升级成有效凭证。与刚修的 2FA 绕过（`579b0f4`）落在同一条路径上，是该路径的第二个洞。

    v0.9.4 拆两段时**收敛点性质没丢**（守护者 Q1）：本函数与第一段都是模块私有，对外只有
    `interim_session` 一个入口、且它必然跑完两段 ⇒ 「新增第二个 interim 消费点」只能经组合入口，
    自动受保护。**拆成两个 public 函数才会把该性质拆掉**，所以没那么拆。
    """
    # 吊销比对（与 deps.py:134-136 同口径）：payload.ver != users.token_version → 401
    if ver != totp_service.get_token_version_cached(user_id):
        raise HTTPException(status_code=401, detail="INTERIM_TOKEN_REVOKED")


@contextlib.contextmanager
def interim_session(token: str):
    """⭐ **interim token 的唯一对外入口**（v0.9.4 R-12 / D4''-c · 守护者 I-1/I-2/Q1 定稿）。

    yield `(payload, user_id)`，并在 `with` 块内保证 **本请求的 tenant ctx = interim 里那个 tid 的租户**；
    退出时 reset（作用域化，不留 ctx 给后续）。

    **ctx-free 前缀契约（R-12 的表述，务必照抄理解）**：
    > **ctx-free 前缀恰为 [验签, 取 tid]；此后一切都在已建 ctx 内。**

    不写成「有 2 处需要 ctx」—— 验签之后**几乎全身**都需要 ctx（吊销读 users · 限流的 tenant 桶 ·
    `totp_service.verify` / `consume_recovery` · `get_user_by_id` · `audit()` 写租户库 · `create_token`）。
    列举 N 项会让后人以为「第 N+1 项放在外面也安全」。

    **顺序 `① ② ③ ⑤ ④`（守护者 I-1 把限流提到吊销之前）**：
      ① 入口 `clear_active_tenant()` —— 无条件清掉 middleware 可能已 set 的 ctx（可能是**别的租户**：
         前端 axios 拦截器会把陈旧 Authorization 带上来 = B-5）。R-13 入口不变量。
      ② `_verify_interim_signature`（ctx-free）—— 验签 + 取 `sub`/`ver`/`tid`。
      ③ `resolve_tenant_by_id(tid)`（读**平台库**，ctx-free）+ 校 active → `set_active_tenant`。
      ⑤ 限流（只碰进程内桶）。
      ④ 吊销（要读 DB）。
    ⑤ 早于 ④ 的理由：现序下，持「已吊销但签名有效」interim 的攻击者**每次尝试都触发一次 DB 读**才被
    限流；调换后限流同时护住吊销读与随后的 TOTP 码校验，且仍满足「限流在真正码校验之前」。

    tid 指向的租户不存在 / 已停用 → 401（**不回退到任何默认租户** —— 回退 = 静默跨租户供数）。
    """
    entry_tok = clear_active_tenant()                      # ①
    try:
        payload = _verify_interim_signature(token)         # ②
        user_id = int(payload["sub"])
        tenant = tenant_repo.resolve_tenant_by_id(payload["tid"])   # ③（平台库，ctx-free）
        if tenant is None:
            raise HTTPException(status_code=401, detail="无效的 interim token")
        tenant_tok = set_active_tenant(tenant)
        try:
            enforce_totp_verify_rate_limit(user_id)        # ⑤
            _assert_interim_not_revoked(user_id, payload["ver"])   # ④
            yield payload, user_id
        finally:
            reset_active_tenant(tenant_tok)
    finally:
        reset_active_tenant(entry_tok)


# ─── 4 端点 ────────────────────────────────────────────────────────────


@router.post("/api/totp/enroll-init")
async def enroll_init(request: Request, user=Depends(get_current_user)):
    """Step 1：生成 secret + QR otpauth:// URI + 内联 PNG data URL（不持久化）。

    返 {secret, qr_uri, qr_dataurl} — 前端 <img src={qr_dataurl}> 直接展示 QR。
    qr_dataurl 服务端生成（qrcode lib commit 1 sustained）避免前端 npm 依赖。
    R-PB-B1-6 rate limit：enroll 3/hour/user 防恶意频繁。
    """
    enforce_totp_enroll_rate_limit(user["id"])
    secret, qr_uri = totp_service.enroll_init(user["id"])
    # v0.6.2.0 commit 5：QR PNG 内联 base64 data URL（commit 1 qrcode[pil] dep sustained）
    import base64
    import io

    import qrcode

    qr = qrcode.QRCode(version=1, box_size=8, border=2)
    qr.add_data(qr_uri)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    qr_dataurl = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    return {"secret": secret, "qr_uri": qr_uri, "qr_dataurl": qr_dataurl}


@router.post("/api/totp/enroll-complete")
async def enroll_complete(req: TotpEnrollCompleteRequest, request: Request,
                          user=Depends(get_current_user)):
    """Step 2：1 次动态码验证（R-PB-B1-7）+ R-46-Tx 事务持久化。

    返 {recovery_codes} — 前端必须强制下载才能完成 enroll（前端 commit 5 落地）。
    成功 → audit user.totp.enroll
    """
    # v0.6.5.2 F2：独立分桶（10/hour）— 与 enroll-init（3/hour）隔离，防共桶卡死
    enforce_totp_enroll_complete_rate_limit(user["id"])
    codes = totp_service.enroll_complete(user["id"], req.secret, req.code)
    if not codes:
        audit(request, actor=user, action="user.totp.verify_failed",
              resource_type="user", resource_id=user["id"], success=False,
              detail={"phase": "enroll", "recovery": False})  # v0.6.3.0 远古补3 schema 统一 {phase, recovery}
        raise HTTPException(status_code=400, detail="验证码错误，请重新扫码后再试")
    audit(request, actor=user, action="user.totp.enroll",
          resource_type="user", resource_id=user["id"])
    return {"recovery_codes": codes}


@router.post("/api/totp/verify")
async def verify(req: TotpVerifyRequest, request: Request):
    """login 后 verify — interim_token + 6 位码 → 完整 JWT（含 totp_verified）。

    R-PB-B1-6 rate limit：5/min/user（解析 interim 拿 user_id 后限流）。
    R-PB-B1-9 Session 验证：verify 失败不颁发完整 JWT；interim 仍有效但只能用于 verify。
    """
    # v0.9.4 R-12：interim 的唯一入口。`with` 块内 tenant ctx = interim 的 tid 所指租户；
    # 块内**一切**（限流 / 吊销 / 码校验 / audit / 签发）都在该 ctx 内 —— 见 interim_session docstring。
    with interim_session(req.interim_token) as (payload, user_id):
        # recovery code 兜底（10-char 含 "-" 自动识别 — 与 6 位 TOTP 冲突小）
        is_recovery = "-" in req.code and len(req.code) >= 10
        ok = (totp_service.consume_recovery(user_id, req.code) if is_recovery
              else totp_service.verify(user_id, req.code))

        from knot.repositories.user_repo import get_user_by_id
        user = get_user_by_id(user_id)
        if not ok:
            audit(request, actor=user, action="user.totp.verify_failed",
                  resource_type="user", resource_id=user_id, success=False,
                  detail={"phase": "login", "recovery": is_recovery})  # v0.6.3.0 远古补3 schema 统一 {phase, recovery}
            raise HTTPException(status_code=401, detail="TOTP 验证失败")

        if is_recovery:
            audit(request, actor=user, action="user.totp.recovery_code_used",
                  resource_type="user", resource_id=user_id,
                  detail={"phase": "login_recovery"})

        # 颁发完整 JWT（含当前 token_version；后续业务请求 deps.py 验证）
        full_token = create_token(user_id)
        return {
            "token": full_token,
            "user": {
                "id": user["id"], "username": user["username"],
                "display_name": user["display_name"] or user["username"],
                "role": user["role"],
                "must_change_password": bool(user.get("must_change_password")),
            },
        }


@router.post("/api/totp/reset")
async def reset(req: TotpResetRequest, request: Request,
                admin=Depends(require_admin)):
    """admin 重置 user TOTP — R-PB-B1-5：audit + recovery_codes 全清 + token_version +1。

    R-PB-B1-13：reset 必触发被重置用户的旧 JWT 立即 401（cache invalidate +
    DB token_version +1，下次请求 deps.py 验证不匹配）。
    """
    totp_service.reset(req.target_user_id)
    audit(request, actor=admin, action="user.totp.reset",
          resource_type="user", resource_id=req.target_user_id)
    return {"ok": True, "message": "TOTP 已重置，用户下次登录需重新 enroll"}
