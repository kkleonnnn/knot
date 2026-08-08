"""knot.repositories.tenant_provisioning — 租户开通（v0.9.15 d1/d2/d3/d5/d6 · lift 弧 P2）。

**为什么单独一个模块**：`tenant_repo.py` 是「tenants 行的 CRUD + 解析器」，
开通是**跨两个库的编排**（平台库写行 + 租户库建表 seed admin）—— 关注点不同，
且 `tenant_repo` 已顶在 R-94 size gate 附近。

═══ 三条承重设计（Stage 1' §1.1 / §1.2 / §1.3 · 守护者 Stage 3 裁定）═══

**① `db_dir` 是服务端生成的不透明串，调用方无输入面**（§1.1，推翻了草案的 `tenants/<slug>`）：
`slug` 由调用方传且**当前零格式校验** ⇒ 从它派生 `db_dir` 等于让「路径含容」依赖一条
**不存在**的校验（`slug='../evil'` 会把主库路径逃逸经 API 复现）。本仓 v0.9.7 已因同一前提
否决过 slug 派生。⇒ `secrets.token_hex(8)`：
  · 满足写口契约（插入前已知 ⇒ **单条 INSERT**，无需回填 ⇒ 不新增 UPDATE 站点、不破同事务审计）；
  · **唯一索引因此变回真守护**（唯一性不再由 `slug` 派生）；
  · 纯小写 hex ⇒ 对「大小写不敏感文件系统 × 大小写敏感 `UNIQUE(slug)`」那个洞**结构性免疫**
    （`AcmeCo` 与 `acmeco` 是两个租户却会共用一个目录 —— 守护者 Q1 补的洞）；
  · 与既有注释一致：`core/tenant_context.py` 明写「**`db_dir` 不可用作标识**」。
⚠️ 运维辨识**不靠目录名** —— 查 `GET /api/platform/tenants` / `platform_audit`（DEPLOY 已写）。

**② 跨两库不可能同一事务 ⇒ 不选策略，选留痕的顺序**（§2-10）：
**平台库先**（行 + 审计，单次 commit），**租户库后**。
行在而库没建 ⇒ 该租户 `suspended` 对两条解析路径都不可见 + **审计里有记录**
⇒ 可发现、且经 §1.2 **真的可重试**；反序则留下无人引用也无记录的孤儿目录。

**③ 建 `suspended` 租户的库需要第二个 ctx 生产者，故三条同时**（§1.3）：
`resolve_tenant_by_id` 对非 `active` 返 `None` ⇒ 解析器拿不到 ctx；唯一可用的是
`get_tenant`（**刻意不过滤 status**）+ `set_active_tenant`。⇒
  (a) 只在本模块内部用；(b) **`try/finally: reset_active_tenant`**；
  (c) 配测**直接比对 contextvar**（成功 + 异常两条路径）——
      守护者 Q3：别用「后续请求看到的 ctx」，那是本仓 conftest autouse ctx +
      中间件每请求自 set 会让它**空转**的那一种（v0.9.4 记过的盲区）。
"""

from __future__ import annotations

import re
import secrets

from knot.core.logging_setup import logger
from knot.core.tenant_context import reset_active_tenant, set_active_tenant
from knot.repositories import base, platform_audit_repo, tenant_repo

#: 开通出来的租户**恒** suspended（kk 2026-08-03 裁定①）。
#: ⚠️ 服务端强制、**不读入参** —— 若可传 `active`，一个调用就制造第二 active 租户
#: ⇒ `assert_no_second_active_tenant_served` 让**全站**每个请求 fail-closed（拒绝服务）。
#: 「激活」是 lift 门之后的独立动作，走 `tenant_repo.update_tenant`。
_NEW_TENANT_STATUS = "suspended"

#: slug 的合法形态 —— **仅小写**（v0.9.15 d2''，守护者 Q4 裁定的口径）。
#: ⭐ **决定性理由是大小写，不是「整洁」**：SQLite 的 `UNIQUE` 对 TEXT **大小写敏感**
#: ⇒ `Acme` 与 `acme` 会是**两个租户**，而它们的登录链接 `?c=Acme` / `?c=acme`
#: **肉眼完全一样** ⇒ 混淆 / 钓鱼面。仅小写一次关掉它，且**不需要 schema 迁移**
#: （`COLLATE NOCASE` 要改表）。
#: ⚠️ **另一半洞由不透明 `db_dir` 关掉**（大小写不敏感文件系统会让两者共用目录）——
#: 那两半是**两个**洞，一条论证只关得掉一个（守护者 Stage 4 #2 指出我把它当一条用了）。
#: ⚠️ 还挡功能面：无校验时 slug 可含 `/` `&` `#` 空格 unicode 或 500 字符 ——
#: 它既进 URL（`?c=`）也进 `platform_audit.tenant_slug`。
#: ⚠️ 非 ASCII 必须由调用方转写：对一个 **URL 组件**来说这是正确的收窄，不是不便。
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,30}$")
#: 给 Pydantic `Field(pattern=...)` 用的同一个字面 —— **单一真相源**，两个执行点
#: （本仓既有形状：「一个谓词、多个执行点」是正确的，「多份判断」才是 N 份清单病）。
SLUG_PATTERN = SLUG_RE.pattern


class TenantProvisioningError(RuntimeError):
    """开通被拒（调用方可读的原因 —— 端点直接把消息交给运维）。"""


def _new_db_dir() -> str:
    """服务端生成的不透明 `db_dir`（见模块 docstring ①）。"""
    return f"tenants/{secrets.token_hex(8)}"


def _tenant_db_exists(tenant_row: dict) -> bool:
    """该租户的主库文件**是否已存在** —— §1.2 的分支判据。

    ⚠️ **判据必须是「文件是否存在」而不是「users 表是否为空」**：后者要先建连接，
    而 `base.get_conn()` 会 `mkdir` + 创建文件 ⇒ **测量动作本身会改变被测状态**。
    ⚠️ 借 `base._tenant_db_path()` 而不自己拼路径：它带**含容校验**（v0.9.15 d2'）
    ⇒ 复用那唯一一处守护，而不是在这里造第二份判据（两份必然漂）。它是纯路径计算，不建任何东西。
    """
    tok = set_active_tenant(tenant_row)
    try:
        return base._tenant_db_path().exists()
    finally:
        reset_active_tenant(tok)


def _seed_tenant_db_with_fresh_password(tenant_row: dict) -> str:
    """建该租户的库并把 admin 口令换成**本租户专属**的随机口令；返回明文（仅此一次）。

    ⚠️ **为什么不能直接用 `init_db()` 的 seed 口令**（kk 裁定②）：那段读**全局**
    `KNOT_INITIAL_ADMIN_PASSWORD` ⇒ 每个新租户拿到**同一个**口令 = 「A 公司能进 B 公司」，
    而开通动作本身就在制造它。故建库后立即改成本租户专属的。
    ⚠️ 口令**只出现在返回值里** —— 不入库（只存 bcrypt 哈希）、不入审计、不进日志。
    """
    import bcrypt

    tok = set_active_tenant(tenant_row)
    try:
        base.init_db()                      # 幂等：建表 + 迁移 + seed admin
        pwd = secrets.token_urlsafe(16)
        pwd_hash = bcrypt.hashpw(pwd.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        conn = base.get_conn()
        try:
            cur = conn.execute(
                "UPDATE users SET password_hash=?, must_change_password=1 WHERE username='admin'",
                (pwd_hash,),
            )
            conn.commit()
            if cur.rowcount == 0:           # init_db 恒 seed admin ⇒ 到不了；到了就是真出事了
                raise TenantProvisioningError(
                    f"租户 {tenant_row['slug']!r} 的库里没有 admin 账号 —— 建库未按预期完成。"
                )
        finally:
            conn.close()
        return pwd
    finally:
        reset_active_tenant(tok)            # ⭐ §1.3(b)：异常路径也必须 reset


def create_tenant(
    *,
    slug: str,
    name: str,
    allowed_http_hosts: str,
    allowed_webhook_hosts: str,
    actor: str | None = None,
    source: str | None = None,
) -> dict:
    """开通一个租户（**恒 `suspended`**）；返回 `{tenant, initial_password, resumed}`。

    `allowed_http_hosts` **必填**（d5）：v0.9.7 的三态语义里 `''`（部署方明确的「禁」）
    与 `NULL`（未配置）**不同** ⇒ 不能用「留空 = 默认」，否则开通就静默选了一种语义。

    §1.2 四分支（判据 = **库文件是否存在**）：
      · 无该 slug 行                          → 正常开通
      · 有行 + suspended + **库不存在**       → **续做**（库是全新的 ⇒ 口令也是全新的）
      · 有行 + suspended + 库已存在           → **拒绝**，指向 `reset_admin_password.py --tenant`
      · 有行 + active                         → **拒绝**（不碰在服务的租户）
    ⚠️ 「库已存在则不续做」不是保守而是**唯一不猜的分支**（守护者 Q2）：此时无法区分
    「建库后被中断」与「一个真实在用、只是被停用了的租户」⇒ 重置口令就是对**可能在用**的
    租户改凭据，而本函数观察不到那个区别。

    Raises:
        TenantProvisioningError: 上面两条「拒绝」分支。
    """
    if not slug or not name:
        raise TenantProvisioningError("slug / name 不得为空")
    if not SLUG_RE.match(slug):
        raise TenantProvisioningError(
            f"slug {slug!r} 不合法 —— 须匹配 `{SLUG_PATTERN}`（**仅小写**，2–31 字符，"
            "首字符为字母或数字，其余可含 `-`）。\n"
            "  ⇒ 为什么仅小写：数据库的唯一性检查**区分**大小写 ⇒ `Acme` 与 `acme` 会是两个租户，"
            "而它们的登录链接肉眼**完全一样**（混淆/钓鱼面）。\n"
            "  ⇒ 非 ASCII 请转写（slug 是 URL 组件）。"
        )

    existing = tenant_repo.get_tenant_by_slug(slug)   # get_* = 不过滤 status（见该函数 docstring）
    if existing is not None:
        if existing["status"] == "active":
            raise TenantProvisioningError(
                f"租户 {slug!r}（id={existing['id']}）正在服务中 —— 开通端点不碰 active 租户。"
            )
        if _tenant_db_exists(existing):
            raise TenantProvisioningError(
                f"租户 {slug!r}（id={existing['id']}）的行已存在**且库已建好** —— 不续做。\n"
                "  ⇒ 无法区分「上次建库后被中断」与「一个真实在用、只是被停用的租户」，\n"
                "     而续做会重置一个**可能在用**的租户的 admin 口令。\n"
                "  ⇒ 要重置口令请显式执行："
                f"`python -m knot.scripts.reset_admin_password --tenant {slug}`"
            )
        # 续做：行在、库没建（= §2-10 那个「留痕的失败模式」真的可重试）
        pwd = _seed_tenant_db_with_fresh_password(existing)
        logger.info(f"租户开通续做完成 slug={slug} id={existing['id']}（行已存在、库刚建好）")
        return {"tenant": existing, "initial_password": pwd, "resumed": True}

    # ── 平台库先：行 + 审计，**单次 commit**（§2-10）───────────────────────
    db_dir = _new_db_dir()
    conn = tenant_repo.get_platform_conn()
    try:
        cur = conn.execute(
            "INSERT INTO tenants (slug, name, status, db_dir, allowed_http_hosts, allowed_webhook_hosts) "
            "VALUES (?,?,?,?,?,?)",
            (slug, name, _NEW_TENANT_STATUS, db_dir, allowed_http_hosts, allowed_webhook_hosts),
        )
        tenant_id = int(cur.lastrowid)
        platform_audit_repo.insert(
            conn,
            action="platform.tenant_create",
            tenant_id=tenant_id,
            tenant_slug=slug,
            actor=actor,
            source=source,
            # ⛔ 绝不记：初始口令 · allowed_http_hosts 的**内容**（后者是部署方内网主机清单，
            #    而 `GET /api/platform/audit` 会返回 detail —— v0.9.8 已立同款禁令）。
            detail={"db_dir": db_dir, "status": _NEW_TENANT_STATUS,
                    "allowed_http_hosts_configured": allowed_http_hosts != "",
                    # v0.9.18 P-a：同样**只记「配了没配」，绝不记内容**（内网主机清单）
                    "allowed_webhook_hosts_configured": allowed_webhook_hosts != ""},
        )
        conn.commit()          # ⚠️ **单次** commit —— 拆成两次就把「不存在做了但没记」这条性质丢了
    finally:
        conn.close()

    # ── 租户库后（失败留在「行在、库没建」这个可发现可重试的状态）───────────
    row = tenant_repo.get_tenant(tenant_id)
    pwd = _seed_tenant_db_with_fresh_password(row)
    logger.info(f"租户开通完成 slug={slug} id={tenant_id} status={_NEW_TENANT_STATUS}")
    return {"tenant": row, "initial_password": pwd, "resumed": False}
