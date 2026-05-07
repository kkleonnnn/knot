"""Few-shot 示例领域模型。

代表的真实实体：admin 在「Few-shot 示例」面板登记的一条「问题 → SQL」样例，
用于注入 SQL Planner system prompt 的 ## 示例章节，提升 NL→SQL 命中率。

services/llm_client._load_few_shots 按 type 字段分桶（metric/trend/rank/...），
按问题分类挑相似示例 ≤ FEW_SHOT_MAX_EXAMPLES 注入。

Go 重写映射：internal/domain/few_shot.go。
"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class FewShotExample:
    """一条 NL→SQL 示范样例。

    type：metric | trend | compare | rank | distribution | retention | detail
          （未来扩展时同步更新 services/llm_client.classify_question_type 关键词表）
    is_active=0 时不参与 prompt 注入但保留 DB 记录（admin 可恢复）。
    """
    id: int
    question: str
    sql: str
    type: str = ""
    is_active: int = 1
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
