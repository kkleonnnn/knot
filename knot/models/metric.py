"""指标领域模型（v0.7.0 C1 — 语义层第一刀）。

代表的真实实体：metric = (口径公式 caliber, 维度集 dimensions, 血缘 lineage) 的单一真源定义。
把"GMV""一次成功率"从"每次 LLM 现写 SQL"变成"查注册表 → 确定性编译"（编译留 v0.7.1 LogicForm）。
v0.7.0 仅注册表 + admin 管理，不进用户查询链路（仅 admin 可见）。

⚠️ OOS-1 死线：metric 归 catalog_id（语义层水平切分，per-catalog 指标命名空间）；严禁
   tenant_id / project_id（真多租户隔离推 v1.x+）。catalog_id = soft ref（无 enforced FK）。
lineage：派生指标依赖（JSON list）；v0.7.0 仅 inert 存储，自引用/循环 DFS 校验留 v0.7.1（编译时）。

Go 重写映射：internal/domain/metric.go。每个 dataclass = 一个 struct。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Metric:
    name: str                          # 唯一标识（per catalog_id 唯一）
    caliber: str                       # 口径表达式（基于对象层字段，如 SUM(o.pay_amount)）
    id: int | None = None
    catalog_id: int = 1                # soft ref catalogs(id)；OOS-1 水平切分非租户
    display: str = ""                  # 中文展示名
    aliases: str = ""                  # JSON list（v0.7.1+ 喂 LEXICON / clarifier）
    base_object: str = ""              # 挂的对象/表（v0.7.2 对象层消费）
    filters: str = ""                  # JSON list 口径内置过滤（防口径漂移）
    dimensions: str = ""               # JSON list 可下钻维度
    lineage: str = ""                  # JSON list 派生依赖（inert；v0.7.1 编译校验）
    freshness_lag_days: int = 1        # 复用 time_resolver D-1 默认
    enabled: int = 1                   # 软开关
    created_at: str | None = None
    updated_at: str | None = None
