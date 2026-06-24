"""knot/services/semantic/logicform.py — LogicForm 结构化中间表示（v0.7.1 C1 · F1）。

LogicForm = NL 解析产物（LLM 出结构），确定性编译的输入：`NL → LogicForm → SQL`。
确定性铁律（R-SL-17）：同一 LogicForm（given 固定 time_ctx）→ byte-equal SQL。
本模块仅纯数据结构 + 确定性序列化；LLM 解析见 parser.py（C3），确定性编译见 compiler.py（C2）。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field


@dataclass
class LogicForm:
    """结构化语义查询。字段顺序 = 序列化/编译固定序（确定性基础）。

    - metrics: 引用 metric.name（顺序 = SELECT 指标列序；**保序不归一**，不同序 = 不同查询）
    - dimensions: 下钻维度（GROUP BY）
    - filters: 附加 WHERE 过滤（口径内置 filters 由编译器从 metric_repo 注入，不在此）
    - time: time_resolver 枚举 key（如 this_month_to_latest）；"" = 不限时间窗
    - order_by: [{"field": <metric|dim>, "dir": "asc"|"desc"}]
    - limit: 0 = 不限（编译器兜底默认 LIMIT）
    - having: 聚合后过滤（HAVING；v0.7.8）—— **强制 alias-based** 引 metric name（如 ["gmv > 10000"]），
      严禁原始 o.col/裸 caliber（多对象 o. 不重写 → DB 报未知列 R-SL-80）
    """

    metrics: list[str]
    dimensions: list[str] = field(default_factory=list)
    filters: list[str] = field(default_factory=list)
    time: str = ""
    order_by: list[dict] = field(default_factory=list)
    limit: int = 0
    having: list[str] = field(default_factory=list)

    def to_canonical_json(self) -> str:
        """确定性 canonical JSON —— 固定字段序 + 紧凑分隔；同内容 LogicForm → byte-equal。

        list 保序（metrics/dimensions 顺序语义相关）；order_by 内 dict key 排序（确定性）。
        用途：① 确定性自检（R-SL-17 基础）② 编译缓存 key ③ admin 审计 surface（v0.7.3）。
        """
        obj = {
            "metrics": list(self.metrics),
            "dimensions": list(self.dimensions),
            "filters": list(self.filters),
            "time": self.time,
            "order_by": [dict(sorted(o.items())) for o in self.order_by],
            "limit": int(self.limit),
        }
        if self.having:   # R-SL-81：空省略键（末位）→ 与存量 canonical（无 having）byte-equal
            obj["having"] = list(self.having)
        return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))

    @classmethod
    def from_dict(cls, d: dict) -> LogicForm:
        """从 LLM 解析的 dict 构造（缺键 → 默认 / 类型兜底）。

        语义校验（metric 全部 ∈ 注册表 / 单对象 / 高置信）是 parser.py 职责（C3），不在此。
        """
        if not isinstance(d, dict):
            raise ValueError("LogicForm.from_dict 需 dict")
        return cls(
            metrics=list(d.get("metrics") or []),
            dimensions=list(d.get("dimensions") or []),
            filters=list(d.get("filters") or []),
            time=str(d.get("time") or ""),
            order_by=[dict(o) for o in (d.get("order_by") or []) if isinstance(o, dict)],
            limit=int(d.get("limit") or 0),
            having=list(d.get("having") or []),
        )
