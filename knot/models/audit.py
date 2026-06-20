"""knot/models/audit.py — 审计领域模型（v0.4.6）。

严守 Contract 2 models-is-leaf：不 import knot 内部任何其他包。

R-55：`AuditAction` Literal 锁死，禁止裸字符串。
R-63：`messages` 表 / SQL 查询不入审计（已用 messages 表覆盖）。
"""
from __future__ import annotations

from typing import Literal

# R-63 子类完整覆盖：8 类 mutation × 子动作 + 审计自身（meta-audit）
AuditAction = Literal[
    # 认证（D5：失败登录记 username 不记 password）
    "auth.login_success", "auth.login_fail", "auth.logout",
    # 用户管理（含 password_reset / role_change 子动作）
    "user.create", "user.update", "user.role_change",
    "user.disable", "user.delete", "user.password_reset",
    # 数据源管理
    "datasource.create", "datasource.update", "datasource.delete",
    # API Key 管理（set / clear 全局 + 用户级）
    "api_key.set_global", "api_key.clear_global",
    "api_key.set_user", "api_key.clear_user",
    # 预算管理
    "budget.create", "budget.update", "budget.delete",
    # 配置变更
    "config.agent_models_update", "config.prompt_update",
    "config.catalog_update", "config.few_shots_change",
    "config.budget_update",  # v0.6.5.9 修 admin.py budget-config 审计调用崩溃（原裸字符串错位 TypeError）
    # v0.6.2.5 段 4 (A1): 多 catalog 切换（per-user active catalog；AuditAction 38→39）
    "catalog.switch",
    # v0.6.2.6 段 4 (A1 并发半): Connection Context 隔离第②层 assert 失败（async race 漂移；39→40）
    # detail 含 attempted_catalog_id + expected_catalog_id（R-PB-A1-23 下游风控）
    "catalog.context_violation",
    # Saved Report
    "saved_report.create", "saved_report.update",
    "saved_report.delete", "saved_report.run",
    "saved_report.pin", "saved_report.unpin",
    # 数据导出
    "export.csv", "export.xlsx",
    # 用户反馈（v0.6.0.3 F-A）
    "feedback.submit",
    # v0.6.2.0 TOTP 2FA（R-PB-B1-11 修订 +4 — 含守护者第 12 次 §III.5 立约 recovery_code_used）
    "user.totp.enroll",              # 首次 enroll 成功（含 recovery codes 生成）
    "user.totp.verify_failed",       # TOTP 6 位码 / recovery code 验证失败（含 enroll / login 两路径）
    "user.totp.reset",               # admin 重置 user TOTP（高危 — bump_token_version 触发旧 JWT 失效）
    "user.totp.recovery_code_used",  # recovery code 单次使用（高危 — 2FA 兜底使用必入 audit）
    # 审计自身（meta-audit, R-57）
    "audit.retention_change", "audit.purge",
]

AuditResourceType = Literal[
    "user", "datasource", "api_key", "budget",
    "agent_model", "prompt", "catalog", "few_shots",
    "saved_report", "audit",
    # v0.6.0.3 F-A: 反馈关联 message
    "message",
]
