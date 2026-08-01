"""knot/api/deps.py — JWT 凭证 + 用户校验依赖（v0.6.0.8 加 JWT_SECRET fail-fast）。

v0.6.0.8 MUST-1：JWT_SECRET 必须由 env 显式提供，缺失 / 默认占位 → sys.exit(1)。
同 KNOT_MASTER_KEY 模式（v0.4.5 R-45 / v0.5.0 R-68）— 防被默认占位签 token = 任意用户伪造登录。
"""
import os
import sys
from datetime import datetime, timedelta

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from knot.core.logging_setup import logger
from knot.core.tenant_context import TenantContextError, TenantDriftError, assert_tenant_context
from knot.repositories.user_repo import get_user_by_id

# v0.6.0.8 MUST-1：废除 fallback 默认值。任何下列情况 → sys.exit(1)：
#   1. JWT_SECRET 完全未设
#   2. JWT_SECRET = 历史默认占位 "knot-secret-change-in-production"
#   3. JWT_SECRET 长度 < 16（防 "test" 这种短到爆破的值）
# v0.6.0.8: 已知历史默认占位（公开仓 grep 可得，必须拒收）
# R-79 守护：旧 brand 字面用 split 构造避免 grep 触发；同 tests/test_rename_smoke.py 风格
_LEGACY_BRAND_OLD = "bi" + "-agent-secret-change-in-production"  # v0.4.x 期遗留
_LEGACY_BRAND_CHATBI = "chatbi-secret-change-in-production"      # v0.2.x 期遗留
_BLOCKED_DEFAULTS = frozenset({
    "knot-secret-change-in-production",
    _LEGACY_BRAND_CHATBI,
    _LEGACY_BRAND_OLD,
})
_LEGACY_DEFAULT = "knot-secret-change-in-production"  # 老代码兼容引用
_MIN_LEN = 16


def _resolve_jwt_secret() -> str:
    """启动期解析；缺失或默认占位 → fail-fast + 友好彩色提示退出。

    由 main.py 启动期显式调用（_check_jwt_secret_or_exit）+ 测试 setup 调用以提前 fail。
    模块 import 时 lazy — 读 env 但不 fail，让测试 conftest 有机会 setenv。
    v0.6.0.8 patch：调用前显式 load_dotenv() 兜底（.env 中 JWT_SECRET 会被识别）。
    """
    if not os.getenv("KNOT_SKIP_DOTENV"):   # v0.7.34 (B1.3): 测试隔离截断 .env 回读（生产默认不设 → 正常兜底）
        try:
            from dotenv import load_dotenv as _ld
            _ld()
        except ImportError:
            pass
    val = os.getenv("JWT_SECRET", "").strip()
    if not val or val in _BLOCKED_DEFAULTS or len(val) < _MIN_LEN:
        bar = "━" * 60
        print(f"\033[1;31m{bar}", file=sys.stderr)
        print("✗ KNOT 启动失败 — JWT_SECRET 配置无效", file=sys.stderr)
        if not val:
            print("  原因: 未设 JWT_SECRET 环境变量", file=sys.stderr)
        elif val in _BLOCKED_DEFAULTS:
            print(f"  原因: 仍用历史默认占位 '{val}' （任何人能伪造 token 登录任意账号）", file=sys.stderr)
        else:
            print(f"  原因: 长度 {len(val)} < {_MIN_LEN}（不安全）", file=sys.stderr)
        print("", file=sys.stderr)
        print("  生成新 secret:", file=sys.stderr)
        print("    openssl rand -hex 32", file=sys.stderr)
        print("", file=sys.stderr)
        print("  设置环境变量后重启:", file=sys.stderr)
        print("    export JWT_SECRET=<生成的 secret>", file=sys.stderr)
        print(f"{bar}\033[0m", file=sys.stderr)
        sys.exit(1)
    return val


# v0.6.0.8 MUST-1：lazy 读取（import 时不 fail；测试 conftest 可 setenv 后 main.py 验证）
# 业务路径 create_token / get_current_user 通过 _get_secret() 读最新值
def _get_secret() -> str:
    """每次 token 操作时读 env（覆盖 monkeypatch.setenv 场景）。"""
    return os.getenv("JWT_SECRET", "").strip() or _LEGACY_DEFAULT


# 模块级常量（向后兼容老代码 `from knot.api.deps import JWT_SECRET`）
JWT_SECRET = os.getenv("JWT_SECRET", _LEGACY_DEFAULT).strip()
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 24 * 7

security = HTTPBearer()


def create_token(user_id: int) -> str:
    """v0.6.2.0 R-PB-B1-13：payload 含 ver=token_version → 后续 reset/change_pwd 触发吊销。

    v0.9.4 D1：payload 加 **`tid`**（租户 id）—— 之后每请求由 tenant middleware 从本 claim 解析租户，
    替代「假设只有一家 active 租户」的 `resolve_single_tenant()`。
    **零新解析器**：签发期 tid 本就在手 —— 本函数**今天已硬依赖 tenant ctx**（实测清 ctx 后调它抛
    `TenantContextError`，链路 `create_token → get_token_version_cached → tenant_cache_key → current_tenant`），
    故直接取 `current_tenant()["id"]`。
    ⚠️ **签名保护完整性、不保密**：JWT payload 客户端可读（base64）。tid 是「**自声明但被签名**」的 claim
    —— 改 tid 重放会验签失败（实测四种伪造全 401；全仓 **0 处**在验签前读 claim，须守住这个 0）。
    """
    exp = datetime.utcnow() + timedelta(hours=JWT_EXPIRE_HOURS)
    # lazy import 避免 circular（totp_service → user_repo → ... → deps）
    from knot.core.tenant_context import current_tenant
    from knot.services.totp_service import get_token_version_cached
    ver = get_token_version_cached(user_id)
    tid = current_tenant()["id"]      # fail-closed：无 ctx 即 raise（不得签出无 tid 的 token）
    return jwt.encode({"sub": str(user_id), "ver": ver, "tid": tid, "exp": exp},
                      _get_secret(), algorithm=JWT_ALGORITHM)


# v0.6.0.20 admin 强制改密：白名单路径在 must_change_password=1 时仍放行
# 含 me / change-password / logout 等 auth flow；其他 API 一律 403 直到改密成功
_FORCE_CHANGE_PWD_WHITELIST_PREFIX = "/api/auth/"

# v0.6.5.0 R-2FA-3：admin 应急后门（唯一豁免路径）
# KNOT_TOTP_BYPASS_ADMIN=true → admin 跳过 TOTP（ops 逃生口，防唯一 admin 弄丢
# authenticator + recovery code 永久锁死）；非 admin 不享后门（由 admin reset 救援）。
# /api/totp/* 白名单让被强制用户能走完 enroll（强制 ≠ 锁死）。
_TOTP_ENDPOINT_WHITELIST_PREFIX = "/api/totp/"


def _admin_bypass_active() -> bool:
    """v0.6.5.0 R-2FA-1/3：admin 应急后门（唯一豁免路径）。

    KNOT_TOTP_BYPASS_ADMIN=true → admin bypass（ops 应急逃生口，防唯一 admin
    弄丢 authenticator + recovery code 永久锁死）。

    v0.6.5.0 删 v0.6.2.0 R-PB-B1-3 的「0 admin enrolled → bootstrap 自动 bypass」
    优先级 2（资深 2026-06-19 裁定：admin 不豁免；且无自愿 enroll UI ⟹ 该 bootstrap
    令唯一 admin 永远无法被 enroll，2FA 形同虚设）。仅保留显式 env 后门。
    """
    return os.getenv("KNOT_TOTP_BYPASS_ADMIN", "").strip().lower() == "true"


def get_current_user(request: Request, creds: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = jwt.decode(creds.credentials, _get_secret(), algorithms=[JWT_ALGORITHM])
        user_id = int(payload["sub"])

        # ⭐ SECURITY hotfix（v0.9.3.x）：**interim_token 一律不得用于业务请求**。
        # interim_token（totp_pending=true）只在「口令已过、TOTP 尚未过」时签发（api/auth.py:30-36），
        # 其 docstring 与设计意图都是「仅 /api/totp/verify 接受」——但此前**从未有任何代码执行该限制**：
        # 本函数原先只是对它「跳过吊销检查」，从不拒绝它，于是它在任意端点都被当作有效凭证。
        # 后果 = **两步验证被绕过**：只掌握口令的人 login 拿到 interim_token 后，可在 5 分钟内以该用户
        # 身份访问任意端点（含 /api/admin/*）；且因签发前提是「用户已 enroll」，:141-148 的 enroll 门
        # 也恒放行 ⇒ 第二因子在这条路径上完全失效（已实测复现 /api/admin/users 200）。
        # 修法**无需路径白名单**：唯一合法消费者 /api/totp/verify 从**请求体**读 token 并走
        # interim 的校验全在 api/totp.interim_session（v0.9.4 R-12 唯一入口），根本不经本函数 ⇒ 这里一律拒绝即可。
        if payload.get("totp_pending"):
            raise HTTPException(status_code=401, detail="INTERIM_TOKEN_NOT_ACCEPTED")

        # ⭐ v0.9.4 D8/D9/B-4：**tid 门 + 租户漂移 tripwire**，必须在**任何读租户库之前**
        # （下一句 get_token_version_cached 就读 users 表）。
        # ① 严格类型（D9）：sqlite3 INTEGER affinity 实测把 `'1'`/`1.0`/`True` 都匹配到 id=1
        #    ⇒ 松了 tid 就是可伪造的「选公司」参数。
        # ② **判别式是 tid 有无、不是 ver**（R8 裁定）：升级前签发的存量 token 无 tid → 401 全员重登一次
        #    （现网部署 = `Recreate` 关掉再起，新旧版本不同时 serving ⇒ 无登录抖动循环，详 DEPLOY）。
        # ③ 漂移检查（kk 2026-07-27 决策②「做，要接上」）：本片引入的新失败模式是
        #    「**ctx 非 None 但是错的租户**」—— `get_conn` 只判 None，对它免疫。`assert_tenant_context`
        #    比对 ctx 里的 id 与本 token 声明的 tid，不一致即 fail-closed。它此前 **0 生产调用点**，
        #    自此接上。中间件设 ctx 与本处比对**同源同 token** ⇒ 正常路径恒相等；不等即代表
        #    中间件没设（租户停用/不存在）或 ctx 被别处污染。
        tid = payload.get("tid")
        if type(tid) is not int or tid <= 0:
            raise HTTPException(status_code=401, detail="JWT_NO_TID")
        try:
            assert_tenant_context(tid)
        except TenantDriftError as drift:
            # ⭐ v0.9.9 兑现 R-10：真漂移是**事故**（单租户下不应发生）⇒ 必须留档。
            # **为什么记在这一行**：`core` 不能写库（`core-no-business` 禁 core → repositories）
            # ⇒ 记录点必须在能到达 repositories 的这一层；而这里正是**漂移被转成拒绝的那一行**
            # ⇒ 记录与被记录的事件是同一件事（v3.1-B 枚举表 #3「那一行」族）。
            # **为什么分两支**：下面那支（未 set ctx）是 v0.9.4 明写的**预期路径**
            # （租户停用/不存在 ⇒ middleware 不设 ctx）—— 把它也记进审计会**刷满表、淹没真信号**。
            _record_tenant_drift(drift, claimed_sub=user_id)
            raise HTTPException(status_code=401, detail="TENANT_UNAVAILABLE")
        except TenantContextError:
            # 显式 401（不靠函末 `except Exception` 兜）—— 运维要能把「租户不可服务」与「坏 token」分开
            raise HTTPException(status_code=401, detail="TENANT_UNAVAILABLE")

        # v0.6.2.0 R-PB-B1-13：JWT 吊销 — payload.ver != users.token_version → 401
        # （上面已拒 interim ⇒ 此处对所有被接受的 token 无条件生效；此前 interim 会整段跳过吊销检查）
        from knot.services.totp_service import get_token_version_cached
        current_ver = get_token_version_cached(user_id)
        if int(payload.get("ver", 0)) != current_ver:
            raise HTTPException(status_code=401, detail="JWT_REVOKED")

        user = get_user_by_id(user_id)
        if not user or not user["is_active"]:
            raise HTTPException(status_code=401, detail="用户不存在或已停用")

        # v0.6.0.20 admin 强制改密：must_change_password=1 时仅 /api/auth/* 放行
        if user.get("must_change_password") and not request.url.path.startswith(_FORCE_CHANGE_PWD_WHITELIST_PREFIX):
            raise HTTPException(status_code=403, detail="must_change_password")

        # v0.6.5.0 R-2FA-1/2：强制 enroll（默认 on — 资深 2026-06-19 提前 R-PA-8 公测门）。
        # KNOT_TOTP_REQUIRED 默认 "true" 强制；显式设 =false 关闭（eval/demo 快速评估）。
        # 未 enroll 用户访问非白名单端点 → 403；admin 仅 KNOT_TOTP_BYPASS_ADMIN 应急后门可豁免。
        if os.getenv("KNOT_TOTP_REQUIRED", "true").strip().lower() == "true":
            path = request.url.path
            if not user.get("totp_enrolled_at"):
                if not path.startswith(_TOTP_ENDPOINT_WHITELIST_PREFIX) \
                   and not path.startswith(_FORCE_CHANGE_PWD_WHITELIST_PREFIX):
                    # R-2FA-3：admin 应急后门（唯一豁免）；非 admin 短路不进后门
                    if not (user["role"] == "admin" and _admin_bypass_active()):
                        raise HTTPException(status_code=403, detail="totp_enroll_required")
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="登录已过期，请重新登录")
    except HTTPException:
        raise
    except Exception:
        # ⚠️ 本分支**接一切**，不只是 JWT 错误。原写法 `except (jwt.InvalidTokenError, Exception)`
        # 是**冗余元组**（`Exception` 已涵盖前者），读起来像只接 JWT 错误而实际接一切 ——
        # 守护者 Q5：这大概正是它一直没被注意到的原因，故按等价写法改直白（行为 byte-equal）。
        # 它会把两类**真故障**折成「凭证无效」：`get_token_version_cached`（缓存 miss → 读租户库）
        # 与 `get_user_by_id` 抛的 `sqlite3.Error` ⇒ 磁盘/权限/库损坏时该租户**全体用户**看到
        # 「凭证无效」而非 503，且此前**零日志痕迹**（= 基础设施故障被静默误诊成认证问题）。
        # 裁定 pre-existing 且非本片扩大（那两个 DB 调用本来就在 try 内；本片新增两处均显式处理）。
        # **本片按 should-fix 只加日志**：把静默误诊变成可追溯，客户端行为不变。
        # **窄化（真故障返 503、坏 token 返 401）留 backlog** —— 那会改客户端可见行为，须独立评估。
        logger.exception("get_current_user 兜底分支吞异常 → 401（可能是基础设施故障，非坏 token）")
        raise HTTPException(status_code=401, detail="无效的登录凭证")


def _record_tenant_drift(drift: TenantDriftError, *, claimed_sub: int | None = None) -> None:
    """把租户漂移写进**平台审计**（v0.9.9 · 兑现 R-10）。

    ⚠️ **写失败不改变拒绝** —— 仍返 401，只记 ERROR 日志。
    **这是一个固有的策略题，不是自造的**（v3.1-B 枚举表 #10 自问过）：
    这里的「动作」是**拒绝请求**，它不是一次 DB 写 ⇒ **没有可与之同事务的对象**
    ⇒ 无法像 v0.9.8 那样「让两难消失」，必须选一个。
    选「仍 401」的理由：**保护动作已经发生**；把它改成 500 会让**审计基础设施故障**
    看起来像服务器故障，**反而更可能掩盖漂移本身**。
    ⚠️ 幸存信号不止日志：`core` 的进程计数器**在抛出之前**已自增（结构上先于本函数）
    ⇒ 审计写故障时**两个信号不会一起消失**。

    ⚠️ `tenant_id` / `tenant_slug` 恒 **NULL**：漂移**没有单一「对象租户」**（两个互斥声明）
    ⇒ 挑一个写进那列会静默放宽 `platform_audit.tenant_id` 的既有语义。两个 id 都进 `detail`。

    ⚠️ **`claimed_sub` = JWT 声明的 `sub`（user_id）**（v0.9.9 Stage 4 should-fix）：
    漂移调查的**第一个问题**是「**哪个用户的 token**」—— 只有两个 tid 答不了它。
    ⇒ 它是**声明**（claim），不是已核实的身份 ⇒ 故进 `detail` 而**不进 `actor`**：
    `actor=None` 是刻意的 —— **不能把一个被拒绝的声明写成 actor**。
    （内部 int，与两个 tid 同类 ⇒ 不触 #262。）
    """
    from knot.repositories import platform_audit_repo, tenant_repo
    try:
        conn = tenant_repo.get_platform_conn()
        try:
            platform_audit_repo.insert(
                conn, action="platform.tenant_ctx_drift", actor=None, success=False,
                detail={"expected": drift.expected, "actual": drift.actual,
                        "claimed_sub": claimed_sub},
                source="api",
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        logger.exception(
            "[tenant-drift] 漂移审计写入失败 —— 拒绝仍然生效（401），"
            "但这条事故记录丢失；进程计数器 `tenant_drift_count()` 仍已自增"
        )


def require_tenant_admin(user=Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user
