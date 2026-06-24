"""knot/services/semantic/parser.py — NL → LogicForm 解析（v0.7.1 C3 · F2）。

LLM 出结构（NL → LogicForm JSON），确定性编译（compiler.py）消费。
- async-native（R-SL-15）：走 `orchestrator._allm`（继承 R-26 budget gate）。
- 成本归既有 `sql_planner` planning 桶（R-SL-19 re-rule：LogicForm 解析 = 确定性路径 planning 阶段）。
- 保守命中（R-SL-14 / D3）：引用 metric 全 ∈ 注册表 + 单对象 → 返 LogicForm；否则 None（未命中 → 回退 LLM）。
  宁退化不报错 —— 解析失败 / 越界 / 多对象 一律 None。
"""
from __future__ import annotations

from knot.services.agents import orchestrator
from knot.services.semantic.logicform import LogicForm

# time 枚举（与 compiler._TIME_KEYS / TimeContext tuple 字段一致）
_TIME_ENUMS = (
    "this_year", "this_year_to_latest", "this_month", "this_month_to_latest",
    "last_week", "last_7_days_to_latest", "same_period_last_year",
)

_LOGICFORM_SYS = """你是 KNOT 语义层的 LogicForm 抽取器。给定用户问题 + 已定义指标清单，
输出一个结构化 JSON LogicForm（**不要写 SQL，不要解释**）。

可用指标（只能按 name 引用以下）：
{metrics_block}

时间枚举（time 字段只能取以下之一，或留空 ""）：
{time_block}

输出 JSON 格式：
{{"metrics": ["<name>", ...], "dimensions": ["<维度>", ...], "filters": ["<附加过滤>", ...],
  "time": "<时间枚举或空>", "order_by": [{{"field": "<name或维度>", "dir": "desc|asc"}}], "limit": <整数,0=不限>,
  "having": ["<聚合后过滤>", ...],
  "window": [{{"func": "<row_number|rank|dense_rank|lag|lead|sum|avg>", "arg": "<metric name，lag/lead/sum/avg 用>", "partition_by": ["<维度>"], "order_by": [{{"field": "<name或维度>", "dir": "desc|asc"}}], "as_name": "<列名>"}}]}}

铁律：
- metrics 只能用上面清单里的 name；问题无法映射到已定义指标 → 输出 {{"metrics": []}}（未命中）。
- 所有引用 metric（聚合口径）必须属于**同一对象**（单一聚合 grain）；多对象聚合 → 输出 {{"metrics": []}}（回退）。
- dimensions **可跨对象** —— 用任一已定义指标的可用维度（含相关对象的维度，如按用户属性切订单指标）；系统自动沿 n:1/1:1 安全关系 JOIN，无安全路径/歧义则安全回退。
- **having = 聚合后过滤**（如「GMV 超 1 万的城市」→ dimensions=["city"] + having=["gmv > 10000"]）：⚠️ **必须用 metric name 作 alias**（如 `gmv > 10000`），**严禁**写原始口径或带表前缀（如 `SUM(o.pay_amount) > 10000` / `o.col` —— 跨对象会编译失败）。无聚合后过滤需求 → 留空 []。
- **window = 窗口函数（排名/同环比/累计）**（如「各地区 GMV 排名」→ dimensions=["region"] + window=[{{"func":"row_number","partition_by":["region"],"order_by":[{{"field":"gmv","dir":"desc"}}],"as_name":"rank"}}]；「GMV 环比」→ window=[{{"func":"lag","arg":"gmv","order_by":[{{"field":"date","dir":"asc"}}],"as_name":"prev_gmv"}}]）：⚠️ func 只能取白名单 `row_number|rank|dense_rank|lag|lead|sum|avg`；partition_by/order_by/arg **必须用 metric name 或维度**（alias-based，**严禁原始口径/带表前缀**）。无窗口需求 → 留空 []。
- **宁可输出 {{"metrics": []}} 也不要猜**（未命中会安全回退 LLM）。"""


def _build_prompt(metrics: list[dict]) -> str:
    """注入已定义指标清单（name/display/aliases/dimensions）→ 完整 system prompt。"""
    lines = [
        f"- {m['name']}（{m.get('display', '')}）: 别名={m.get('aliases') or '[]'} 维度={m.get('dimensions') or '[]'}"
        for m in metrics
    ]
    return _LOGICFORM_SYS.format(
        metrics_block="\n".join(lines) or "（无）",
        time_block="\n".join(f"- {t}" for t in _TIME_ENUMS),
    )


def _validate_hit(lf: LogicForm, metrics: list[dict]) -> bool:
    """保守命中校验：引用 metric 全 ∈ 注册表 + 单对象（与 compiler 双重防御 R-SL-14）。"""
    if not lf.metrics:
        return False
    by_name = {m["name"]: m for m in metrics}
    objs = set()
    for name in lf.metrics:
        m = by_name.get(name)
        if m is None:
            return False
        objs.add((m.get("base_object") or "").strip())
    return len(objs) == 1 and "" not in objs


async def parse_to_logicform(question: str, metrics: list[dict], model_key: str,
                             api_key: str = "", openrouter_api_key: str = "") -> dict:
    """NL → LogicForm（async）。返回 {logicform, input_tokens, output_tokens, cost_usd}。

    logicform = LogicForm | None（None = 未命中 → 回退 LLM）。即使未命中，LLM 已调用 →
    cost 仍返回供调用方归 sql_planner 桶（R-SL-19）。无已定义指标 → 0 LLM 调用 / 0 cost。
    """
    if not metrics:
        return {"logicform": None, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}
    resolved, key, cfg = orchestrator._resolve(model_key, api_key, openrouter_api_key)
    system = _build_prompt(metrics)
    text, it, ot, cost = await orchestrator._allm(
        resolved, key, cfg, system, [{"role": "user", "content": question}],
        agent_kind="sql_planner",  # R-SL-19 复用 planning 桶（0 扩桶 0 schema）
    )
    data = orchestrator._parse_json(text)
    lf = None
    if isinstance(data, dict) and data.get("metrics"):
        candidate = LogicForm.from_dict(data)
        if _validate_hit(candidate, metrics):
            lf = candidate
    return {"logicform": lf, "input_tokens": it, "output_tokens": ot, "cost_usd": cost}
