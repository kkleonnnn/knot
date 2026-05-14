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
    # Saved Report
    "saved_report.create", "saved_report.update",
    "saved_report.delete", "saved_report.run",
    "saved_report.pin", "saved_report.unpin",
    # 数据导出
    "export.csv", "export.xlsx",
    # 用户反馈（v0.6.0.3 F-A）
    "feedback.submit",
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
