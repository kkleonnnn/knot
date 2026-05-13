"""系统设置 + 用户上传文件的领域模型。

代表的真实实体：
  - AppSetting ：app_settings 表的一行 KV，admin 在各面板编辑的全局配置
                 （catalog.tables / openrouter_api_key / agent_model_config 等）
  - FileUpload ：analyst 上传的一份 CSV/Excel 元数据（实际数据落入 SQLite 同库表）

Go 重写映射：internal/domain/setting.go。
"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AppSetting:
    """通用 KV 配置项（无 schema 约束，由调用方约定 key 规范）。

    已在用 key（v0.3.x）：
      - openrouter_api_key / embedding_api_key
      - agent_model_config（JSON：{clarifier, sql_planner, presenter}）
      - catalog.tables / catalog.lexicon / catalog.business_rules（v0.2.5 业务目录覆盖）
    """
    key: str
    value: str = ""
    updated_at: Optional[str] = None


@dataclass
class FileUpload:
    """analyst 通过「上传 CSV」入口上传的临时数据集元数据。

    实际行数据存入 SQLite 主库的 upload_<id> 表（v0.2.4 起合并入主 DB），
    可在 ChatScreen 选中后作为 SQL 查询源（与 doris/mysql 数据源平行）。
    """
    id: int
    user_id: int
    filename: str
    table_name: str  # SQLite 中实际存放的表名
    row_count: int = 0
    columns: list = field(default_factory=list)  # [{"name", "type"}]
    created_at: Optional[str] = None
