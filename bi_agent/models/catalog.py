"""业务目录领域模型（KNOT 业务规则注入用）。"""
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CatalogTable:
    db: str
    table: str
    topics: list = field(default_factory=list)
    summary: str = ""

    @property
    def full_name(self) -> str:
        return f"{self.db}.{self.table}"


@dataclass
class Catalog:
    """业务目录三件套，由 services/knot/catalog 加载/编辑。"""
    tables: list = field(default_factory=list)        # list[CatalogTable]
    lexicon: dict = field(default_factory=dict)       # {term: [table_full_name, ...]}
    business_rules: str = ""
    source: str = "empty"  # db | real | example | empty
