"""通用 KV 配置 + 用户上传文件元数据。"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AppSetting:
    """app_settings 表的单行（通用 KV，admin 编辑用）。"""
    key: str
    value: str = ""
    updated_at: Optional[str] = None


@dataclass
class FileUpload:
    """用户上传的 CSV/Excel 元数据。"""
    id: int
    user_id: int
    filename: str
    table_name: str
    row_count: int = 0
    columns: list = field(default_factory=list)
    created_at: Optional[str] = None
