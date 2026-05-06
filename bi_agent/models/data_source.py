"""业务库数据源领域模型。"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class DataSource:
    id: int
    name: str
    db_host: str
    db_port: int = 9030
    db_user: str = ""
    db_password: str = ""
    db_database: str = ""
    db_type: str = "doris"  # doris | mysql
    description: str = ""
    user_id: Optional[int] = None
    is_active: int = 1
    created_at: Optional[str] = None
