"""业务目录领域模型（KNOT 业务规则注入到 3-Agent system prompt 用）。

代表的真实实体：
  - CatalogTable ：admin 在「业务目录」面板登记的一张业务库表 + 主题标签
  - Catalog      ：完整业务知识包（表目录 + 词典 + 规则文本），由 services/agents/catalog
                   按 DB → _local_catalog.py → _template_catalog.py 三层 fallback 加载

Go 重写映射：internal/domain/catalog.go。
"""
from dataclasses import dataclass, field


@dataclass
class CatalogTable:
    """业务库一张表的元数据（schema_filter 主题加分用）。

    topics 是业务概念词列表（"注册"/"GMV"/"用户"），与问题分词重合即加分；
    summary 是一句话表说明，给 LLM 在 prompt 里看到。
    """
    db: str
    table: str
    topics: list = field(default_factory=list)
    summary: str = ""

    @property
    def full_name(self) -> str:
        return f"{self.db}.{self.table}"


@dataclass
class Catalog:
    """完整业务知识包。

    source 字段标记加载来源：
      - "db"      ：admin 在 UI 编辑后保存到 app_settings 三键
      - "real"    ：knot/services/agents/_local_catalog.py（部署方填，gitignored）
      - "example" ：仓库内 _template_catalog.py（通用电商模板兜底）
      - "empty"   ：上述全空（v0.3.x 不应出现）
    """
    tables: list = field(default_factory=list)        # list[CatalogTable]
    lexicon: dict = field(default_factory=dict)       # {term: [table_full_name, ...]}
    business_rules: str = ""
    source: str = "empty"
