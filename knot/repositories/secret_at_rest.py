"""secret_at_rest —— 静态敏感值扫描（v0.9.12 · 只读，不改任何数据）。

**为什么需要它**：v0.4.5 立了「这些列必须静态加密」，但三年里它**只是一条散文规则** ——
写入路径会加密 ✅、有一个一次性迁移脚本 ✅，而**没有任何东西在问「现有数据里还有没有明文」**：
0 启动检查 · 0 CI · 0 巡检命令；既有 12 条加密测**全部在空的临时库上测写入路径**。
后果（2026-08-01 实测 kk 本地真实库）：**2 个敏感值以明文躺了三个月**，其中一个是付所有
LLM 费用的 API key。读路径对无前缀的值**原样返回**（刻意的向后兼容）⇒ **明文完美工作、永不报错**。

═══ ⭐ 两个 oracle，各自具名 —— **别把完整判据搬进启动期** ═══
| oracle | 定义 | 用在哪 | 成本 |
|---|---|---|---|
| **廉价判据** `looks_plaintext` | **没有 `enc_v1:` 前缀** ⇒ 是明文 | **启动期扫描**（本模块） | 一次 `startswith` |
| **完整判据** | **用当前加载的那把 key 解得开** | `scripts/migrate_encrypt_v045._preflight_decrypt_all`（写前）+ 只读 CLI | 每个密文一次 HMAC+AES |

**为什么启动期只能用廉价判据**：完整判据要对每个密文做真解密，成本 = N 租户 × 落点 × 行数
⇒ **随租户数线性增长**，而 v0.9.3 删掉 catalog warm-up 的理由正是这个。
⚠️ **两者不等价，差别要知道**：混 key 库里所有值都是「**某把** key 的合法密文」⇒ 廉价判据
**看不出 key 错了**，只有完整判据能。⇒ 廉价判据答的是「有没有人忘了加密」，不是「加密对不对」。
⚠️ **若将来引入 `MultiFernet`**，「解得开」的含义会**静默改变**（变成「任一把 key 解得开」）
⇒ 届时必须回来重读本段。

═══ 扫描范围 = **租户库；平台库不在内** ═══
今天平台库（`platform.db`）**无凭据列**：`tenants.allowed_http_hosts` 是主机名不是凭据；
`platform_audit.detail_json` 有 v0.9.8 的 AST 哨兵禁写凭据。⇒ 不扫是**正确的**。
⚠️ 但 R-T-GATE 路线图里有 **per-tenant 初始口令**（v0.9.4 登记项 ②）⇒ **平台库将来会有凭据列**
⇒ 那一片必须回来把平台库纳入扫描，否则本模块会**静默漏掉它**。
"""
from __future__ import annotations

import sqlite3
from typing import NamedTuple

from knot.core.crypto.fernet import ENC_PREFIX


class Spot(NamedTuple):
    """一个敏感落点。`key_filter` 非空时表示按 `key IN (...)` 取行（`app_settings` 形态）。"""
    table: str
    pk_col: str
    col: str
    key_filter: str | None = None


class Finding(NamedTuple):
    """⛔ **永不含值**（#262 族）—— 只有表 / 列 / 行主键，够定位、不泄露。"""
    table: str
    col: str
    pk: object


def landing_spots() -> tuple[Spot, ...]:
    """敏感落点 = **三个既有真相源的并集**（不造第 N 份清单）+ 确定性排序。

    新增敏感列只要进了这三个常量之一，**自动**进入扫描面 —— 不需要改本文件。
    """
    from knot.repositories.data_source_repo import _DS_ENCRYPTED_COLS
    from knot.repositories.settings_repo import _SENSITIVE_KEYS
    from knot.repositories.user_repo import _USER_ENCRYPTED_COLS

    spots = [Spot("users", "id", c) for c in sorted(_USER_ENCRYPTED_COLS)]
    spots += [Spot("data_sources", "id", c) for c in sorted(_DS_ENCRYPTED_COLS)]
    spots += [Spot("app_settings", "key", "value", key_filter=k) for k in sorted(_SENSITIVE_KEYS)]
    return tuple(spots)


# ── 「名字看着像凭据、但刻意不加密」的登记表 ──────────────────────────────
#
# ⚠️ **每项理由必须具名指向一个片或一条决策**（Stage 4 要求）—— 否则「豁免」会退化成
#    一条**新的无守护散文规则**，正是本弧在治的形状。判据可机械校验（见 `exemption_reason_ok`）。
NOT_ENCRYPTED_BY_DESIGN: dict[tuple[str, str], str] = {
    ("users", "password_hash"):
        "bcrypt 哈希 —— 单向、不是可逆凭据，加密它没有意义（v0.4.5 立「哈希不入 Fernet 面」）",
    ("model_settings", "model_key"):
        "模型**标识符**（如 anthropic/claude-…），公开信息非机密（v0.4.5）",
    ("app_settings", "key"):
        "settings 的**键名**而非值；值的机密性由 `settings_repo._SENSITIVE_KEYS` 逐键判定（v0.4.5）",
    ("monitors", "action_target"):
        "webhook URL —— v0.9.12 **显式豁免**：加密它必须**同片迁移存量行**，而存量迁移正是 "
        "`migrate_encrypt_v045` ⇒ 顺序上不可能。已登记 backlog（依赖 P-a 硬化后的脚本），"
        "出网侧另有 `KNOT_WEBHOOK_ALLOWED_HOSTS` 守护（R-SL-69）",
}

_REASON_ANCHOR = r"v\d+\.\d+(\.\d+)*|ADR-\d{4}|docs/plans/"


def exemption_reason_ok(reason: str) -> bool:
    """理由必须**具名指向**一个片 / ADR / plan 文档 —— 不接受只有一段话。"""
    import re
    return bool(re.search(_REASON_ANCHOR, reason))


def looks_plaintext(value: object) -> bool:
    """**廉价判据**（启动期用）：非空 str 且**没有 `enc_v1:` 前缀** ⇒ 判为明文。

    ⚠️ 不做解密 —— 见模块头「两个 oracle」。空值 / 非 str 不算明文（NULL 与空占位是合法状态）。
    """
    return isinstance(value, str) and value != "" and not value.startswith(ENC_PREFIX)


def scan_plaintext_secrets(conn: sqlite3.Connection) -> list[Finding]:
    """扫**调用方给的这个连接**所指的库，返回明文落点（可能为空）。

    ⚠️ **连接由调用方注入**（不自己开）：迁移/巡检要与自己的写入同源，避免
    「校验的是另一个库」；启动期则在租户 ctx 下用 `base.get_conn()`。
    ⚠️ 表/列不存在时**跳过而不抛** —— 本函数是**只读探测器**，绝不能因为库比代码旧而
    改变启动的可用性（缺列的硬报错归 `migrate_encrypt_v045`，那里是写路径、fail-closed 才对）。
    """
    out: list[Finding] = []
    for spot in landing_spots():
        try:
            sql = f"SELECT {spot.pk_col}, {spot.col} FROM {spot.table}"
            params: tuple = ()
            if spot.key_filter is not None:
                sql += f" WHERE {spot.pk_col}=?"
                params = (spot.key_filter,)
            rows = conn.execute(sql, params).fetchall()
        except sqlite3.Error:
            continue        # 表/列不存在（旧库）⇒ 跳过，不抛
        for pk, value in rows:
            if looks_plaintext(value):
                out.append(Finding(spot.table, spot.col, pk))
    return out


def format_findings(findings: list[Finding], *, sample: int = 5) -> str:
    """给日志/CLI 的一行摘要 —— **聚合计数 + 有界样本**，⛔ 永不含值。

    有界是刻意的：无界枚举在大库上会刷满日志（守护者 R7）。
    """
    if not findings:
        return "0 处"
    head = "、".join(f"{f.table}.{f.col}(pk={f.pk!r})" for f in findings[:sample])
    more = f" …等 {len(findings)} 处" if len(findings) > sample else ""
    return f"{len(findings)} 处：{head}{more}"


def warn_all_tenants_at_startup() -> None:
    """启动期逐租户扫描 → **WARN，不阻断**。由 `main.py` 在 master-key fail-fast 之后调用一次。

    **为什么不阻断**：存量部署带 legacy 明文是**合法状态**（读路径刻意容忍无前缀值，
    `test_legacy_plaintext_row_decrypts_as_passthrough` 明确祝福了它）⇒ 拒启动 = 升级即自造停机。
    硬行为放在**没有两难**的那一侧：`scripts/migrate_encrypt_v045` 的 preflight 与后置校验
    （写路径，fail-closed 才对）。
    **任何异常都只降级为 WARN** —— 一个非阻断探测器绝不该改变启动的可用性。
    """
    from knot.core import tenant_context as _tc
    from knot.core.logging_setup import logger
    from knot.repositories import tenant_repo as _tr
    from knot.repositories.base import get_conn

    for t in _tr.list_tenants():
        tok = _tc.set_active_tenant(t)
        try:
            conn = get_conn()
            try:
                found = scan_plaintext_secrets(conn)
            finally:
                conn.close()
            if found:
                logger.warning(
                    f"⚠️ [secret-at-rest] tenant#{t['id']} 存在**明文**敏感值 "
                    f"{format_findings(found)} —— 修：python3 -m knot.scripts.migrate_encrypt_v045 "
                    f"--tenant {t['id']}（巡检：python3 -m knot.scripts.scan_secrets_at_rest --all-tenants）"
                )
        except Exception as e:
            logger.warning(f"[secret-at-rest] tenant#{t['id']} 扫描跳过：{type(e).__name__}: {e}")
        finally:
            _tc.reset_active_tenant(tok)
