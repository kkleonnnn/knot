"""业务库数据源领域模型。

代表的真实实体：admin 在「数据源」面板登记的一个 Doris/MySQL 集群连接。
一个数据源可被多个 user 共享访问（user_sources 关联表）；查询时按
host:port:user 自动分组（MultiSourceEngine），跨组 SQL 直接拒绝。

Go 重写映射：internal/domain/data_source.go。
"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class DataSource:
    """业务库连接配置。

    db_password 在持久化层以明文存储（v0.4.x 计划加密）；
    建议每个数据源使用专用只读账号 + STRICT_READONLY_GRANTS=1 做防御。
    """
    id: int
    name: str
    db_host: str
    db_port: int = 9030
    db_user: str = ""
    db_password: str = ""
    db_database: str = ""
    db_type: str = "doris"  # doris | mysql（v0.3.2 Adapter 协议为后续 clickhouse/bigquery 留口）
    description: str = ""
    user_id: Optional[int] = None  # 创建者
    is_active: int = 1
    created_at: Optional[str] = None
