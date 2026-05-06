"""bi_agent.repositories — SQLite 数据访问层（v0.3.0）

设计契约（import-linter 强制）：
  - 只做 SQL CRUD，零业务逻辑
  - 不得 import services / api / adapters
  - 可 import models / config / core
  - 入口：from bi_agent.repositories import init_db；其他按 *_repo.py 模块化访问

v0.3.0 BREAKING：原 `bi_agent/core/persistence.py` 内的 30 余个函数已迁移至本包。
旧路径 `import persistence` 已不可用；routers 暂用 `from bi_agent import repositories as persistence`
统一兼容（v0.3.1 收尾时删除该简写，全部改为 `from bi_agent.repositories.X_repo import ...`）。

# FIXME-v0.3.1: 删除本文件下方的 facade re-export 块。
"""
from bi_agent.repositories.base import init_db, get_conn  # noqa: F401

# ── Legacy facade（routers/engine_cache 兼容期） ────────────────────────
# 让 `persistence.get_user_by_id` 等老调用形态继续工作。
from bi_agent.repositories.user_repo import (  # noqa: F401
    get_user_by_username, get_user_by_id, list_users,
    create_user, update_user, update_user_usage,
    get_user_monthly_usage, get_monthly_cost,
    get_user_agent_model_config, set_user_agent_model_config,
)
from bi_agent.repositories.conversation_repo import (  # noqa: F401
    create_conversation, list_conversations,
    update_conversation_title, delete_conversation,
)
from bi_agent.repositories.message_repo import (  # noqa: F401
    save_message, get_messages,
    get_semantic_layer, save_semantic_layer,
)
from bi_agent.repositories.data_source_repo import (  # noqa: F401
    list_datasources, get_datasource,
    create_datasource, update_datasource, delete_datasource,
    set_user_sources, get_user_source_ids, get_all_user_source_ids,
)
from bi_agent.repositories.settings_repo import (  # noqa: F401
    get_app_setting, set_app_setting,
    get_model_settings, set_model_enabled, set_default_model,
    get_agent_model_config, set_agent_model_config,
)
from bi_agent.repositories.few_shot_repo import (  # noqa: F401
    list_few_shots, create_few_shot, update_few_shot,
    delete_few_shot, bulk_insert_few_shots,
)
from bi_agent.repositories.prompt_repo import (  # noqa: F401
    list_prompt_templates, get_prompt_template,
    set_prompt_template, delete_prompt_template,
)
from bi_agent.repositories.knowledge_repo import (  # noqa: F401
    create_knowledge_doc, list_knowledge_docs, delete_knowledge_doc,
    save_doc_chunks, list_doc_chunks,
)
from bi_agent.repositories.upload_repo import (  # noqa: F401
    create_file_upload, list_file_uploads, get_file_upload, delete_file_upload,
)
