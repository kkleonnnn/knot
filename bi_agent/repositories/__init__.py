"""bi_agent.repositories — SQLite 数据访问层（v0.3.1 收口）

设计契约（import-linter 强制）：
  - 只做 SQL CRUD，零业务逻辑
  - 不得 import services / api / adapters / routers
  - 可 import models / config / core
  - 入口：from bi_agent.repositories.X_repo import Y

v0.3.1 BREAKING：v0.3.0 临时保留的 facade re-export（30+ 函数）已删除。
所有调用方必须按 *_repo.py 模块化访问，例如：
  from bi_agent.repositories.user_repo import get_user_by_id
  from bi_agent.repositories.settings_repo import get_app_setting
"""
from bi_agent.repositories.base import get_conn, init_db  # noqa: F401
