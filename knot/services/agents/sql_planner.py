"""
sql_agent.py — SQL Agent 推理链（ReAct 模式）
Think → Act → Observe → ... → Final Answer
"""

import re
import time
from dataclasses import dataclass, field

from knot.adapters.db import doris as db_connector
from knot.core import date_context
from knot.services import llm_client, sql_validator
from knot.services import prompt_service as _prompts_mod

try:
    from knot.services.agents import catalog as _cl
except Exception:
    _cl = None


def _business_rules() -> str:
    return getattr(_cl, "BUSINESS_RULES", "") if _cl else ""


def _relations_for_schema(schema_text: str) -> str:
    """v0.4.1.1：从 schema_text 解析出 selected 表全名，调 catalog.get_relations_for_tables
    按需渲染 RELATIONS 段（仅相关表的关联），避免 token 预算挤压（R-S4）。

    schema_text 格式约定（与 schema_filter / db_connector.get_schema 输出一致）：
      ## demo_dwd.dwd_user_reg
      - created_at ...
      ## demo_dwd.dwd_order
      ...
    """
    if not _cl:
        return ""
    try:
        get_rels = getattr(_cl, "get_relations_for_tables", None)
        if not callable(get_rels):
            return ""
    except Exception:
        return ""
    selected = re.findall(r"^##+\s*([\w.]+)\s*$", schema_text or "", re.MULTILINE)
    return get_rels(selected)


from knot.config import (  # noqa: E402  legacy import order；v0.3.x 不强制重排
    DEFAULT_MODEL,
    MAX_TOKENS_PER_QUERY,
    MODELS,
    PROVIDER_API_KEYS,
    PROVIDER_BASE_URLS,
)


@dataclass
class AgentStep:
    step_num: int
    thought: str
    action: str
    action_input: str
    observation: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class AgentResult:
    success: bool
    sql: str
    rows: list
    explanation: str
    confidence: str
    error: str
    steps: list[AgentStep]
    total_cost_usd: float
    total_input_tokens: int
    total_output_tokens: int


_AGENT_SYSTEM_TEMPLATE = """你是一个 SQL Agent，通过 ReAct（推理-行动）模式帮用户回答数据仓库问题。

{date_block}

{business_rules}

每一步必须按以下格式输出（严格遵守格式，不输出其他任何内容）:
Thought: [分析当前状况，决定下一步]
Action: [工具名称]
Action Input: [工具的输入]

## 可用工具

**execute_sql** — 执行一条 SQL，返回结果或错误信息
**describe_table** — 输入表名，返回该表的字段结构
**list_tables** — 无需输入，返回数据库中所有表名
**search_schema** — 输入关键词，在 Schema 中搜索相关表/字段
**final_answer** — 确认 SQL 正确时，输入最终 SQL 并结束推理

## 规则
- 每次只调用一个工具
- 优先直接 execute_sql；遇到「表不存在」先 list_tables 确认；遇到「字段不存在」先 describe_table
- 只生成 SELECT，禁止 INSERT/UPDATE/DELETE/DROP/ALTER
- 最多推理 {max_steps} 步；超过后直接输出当前最佳 SQL
- 严格遵守上方业务规则（时区/业务日 14:00 切日 / 真实用户范围 / 默认 USDT / 表分层）

## 多表查询规则（必读 — 防笛卡尔积）
- 当 SQL 涉及 ≥ 2 张表时，**必须**用 `JOIN ... ON 关联字段` 显式连接
- **严禁**旧式 `FROM a, b WHERE ...` 写法（隐式笛卡尔积，结果集会爆炸）
- 关联字段优先参考下方「## 表关系 RELATIONS」段；该段无明确关联时，先 search_schema
  查同名 _id 字段；仍找不到则 final_answer 报错"无法确定 JOIN 条件"，不要瞎猜

## ⚠️ 必读：SUM 膨胀陷阱（多 LEFT JOIN 聚合 — Fan-Out）

**自检：** 在 final_answer 之前，如果你的 SQL 形如

```
SELECT key, SUM(d.x), SUM(t.y)
FROM main m
LEFT JOIN d_table d ON m.key = d.key
LEFT JOIN t_table t ON m.key = t.key
GROUP BY key
```

**停！** 这是错的。即使每个 LEFT JOIN 都有正确的 ON 条件，行数也会相乘：
- `SUM(d.x)` 被 `t_table` 的行数倍数膨胀
- `SUM(t.y)` 被 `d_table` 的行数倍数膨胀
- 结果是**双向放大**的错误数字（比真实值大几倍～几十倍）

**唯一正确的写法 — 每张明细表先按 grain 预聚合再 JOIN：**

```
SELECT m.key, COALESCE(d.total, 0), COALESCE(t.total, 0)
FROM main m
LEFT JOIN (SELECT key, SUM(x) AS total FROM d_table GROUP BY key) d ON m.key = d.key
LEFT JOIN (SELECT key, SUM(y) AS total FROM t_table GROUP BY key) t ON m.key = t.key
```

或用 WITH CTE 同款效果。

**触发判定**（runtime 守护会强制拒绝）：
- 顶层 SELECT 含 ≥ 2 个 SUM/COUNT/AVG/MIN/MAX
- AND ≥ 2 个 LEFT JOIN 到具名表（非子查询）

满足以上**必须**用子查询/CTE 预聚合，否则 ReAct 会拒绝你的 final_answer 让你重写。

## 数据库环境
{db_env}

## 数据库 Schema
{schema}

{relations}

{business_ctx}"""


def _strip_sql(s: str) -> str:
    """剥掉 LLM 常见的 markdown 围栏：```sql ... ``` / ``` ... ``` / 单反引号。"""
    s = s.strip()
    m = re.match(r"^```(?:sql)?\s*([\s\S]*?)\s*```$", s, re.IGNORECASE)
    if m:
        s = m.group(1)
    return s.strip().strip("`").strip()


def _parse_agent_output(text: str) -> tuple[str, str, str]:
    thought = action = action_input = ""

    m = re.search(r'Thought:\s*(.*?)(?=\nAction:|\Z)', text, re.DOTALL)
    if m:
        thought = m.group(1).strip()

    m = re.search(r'Action:\s*(\S+)', text)
    if m:
        action = m.group(1).strip().lower()

    m = re.search(r'Action Input:\s*(.*)\Z', text, re.DOTALL)
    if m:
        action_input = m.group(1).strip()

    return thought, action, action_input


# ── Fan-Out 静态检测（v0.4.1.1 实战补丁 C 升级：runtime 守护）─────────────
# 检测语义错误的 SUM 膨胀反模式：≥ 2 个 LEFT JOIN 到具名表（非子查询）+ 外层 SELECT
# 含 ≥ 2 个聚合函数。CTE / 子查询 join 模式由前置启发式跳过避免误杀。
_AGG_FUNC_RE = re.compile(r"\b(?:sum|count|avg|min|max)\s*\(", re.IGNORECASE)
_LEFT_JOIN_NAMED_TABLE_RE = re.compile(
    r"\bleft\s+join\s+(?!\()(?:\w+\.)?\w+",  # LEFT JOIN <ident>(.<ident>)?，但不接 (
    re.IGNORECASE,
)


def _is_fan_out(sql: str) -> tuple[bool, str]:
    """返 (是否 fan-out, 原因)。
    跳过的合法场景（避免误杀）：
    - 顶层是 WITH（CTE 预聚合）
    - 没有 ≥ 2 个 LEFT JOIN 到具名表
    - 顶层 SELECT 没有 ≥ 2 个聚合函数
    """
    if not sql:
        return False, ""
    s = sql.strip()
    # 1. CTE：顶层是 WITH 关键字 → 跳过（CTE 通常已做预聚合）
    if re.match(r"^\s*with\s+", s, re.IGNORECASE):
        return False, ""

    # 2. 顶层 SELECT...FROM 提取（找第一个 SELECT 到第一个 FROM 之间的字段列表）
    sl = s.lower()
    m = re.search(r"\bselect\b(.*?)\bfrom\b", sl, re.DOTALL)
    if not m:
        return False, ""
    outer_select = m.group(1)
    # 3. 顶层 SELECT 中聚合函数计数（≥ 2 才有 fan-out 风险）
    aggs = _AGG_FUNC_RE.findall(outer_select)
    if len(aggs) < 2:
        return False, ""

    # 4. LEFT JOIN 到具名表的次数（不计 LEFT JOIN ( ... ) 子查询）
    direct_left_joins = _LEFT_JOIN_NAMED_TABLE_RE.findall(sl)
    if len(direct_left_joins) < 2:
        return False, ""

    return True, (
        f"外层 SELECT 含 {len(aggs)} 个聚合函数 + {len(direct_left_joins)} 个 LEFT JOIN 到具名明细表，"
        f"行数相乘会让聚合结果膨胀"
    )


def _run_tool(action: str, action_input: str, engine, schema_text: str) -> str:
    if action == "execute_sql":
        sql = _strip_sql(action_input)
        rows, error = db_connector.execute_query(engine, sql)
        if error:
            return f"执行失败: {error}"
        if not rows:
            return "查询成功，返回 0 行"
        import json
        preview = json.dumps(rows[:5], ensure_ascii=False, default=str)
        return f"查询成功，共 {len(rows)} 行，前几行:\n{preview}"

    elif action == "describe_table":
        table_name = action_input.strip().strip("`")
        in_table = False
        result_lines = []
        for line in schema_text.split("\n"):
            if line.strip().startswith(f"### {table_name}"):
                in_table = True
            elif line.strip().startswith("### ") and in_table:
                break
            if in_table:
                result_lines.append(line)
        if result_lines:
            return "\n".join(result_lines)
        rows, err = db_connector.execute_query(engine, f"DESCRIBE `{table_name}`")
        if err:
            return f"无法获取表 {table_name} 的结构: {err}"
        import json
        return f"表 {table_name} 的字段:\n" + json.dumps(rows, ensure_ascii=False)

    elif action == "list_tables":
        rows, err = db_connector.execute_query(engine, "SHOW TABLES")
        if err:
            tables = re.findall(r'^### (.+)$', schema_text, re.MULTILINE)
            return "表名列表（来自 Schema）: " + ", ".join(tables)
        tables = [str(list(r.values())[0]) for r in rows]
        return "数据库中的表: " + ", ".join(tables)

    elif action == "search_schema":
        keyword = action_input.strip().lower()
        results = []
        current_table = ""
        for line in schema_text.split("\n"):
            if line.startswith("### "):
                current_table = line[4:].strip()
            if keyword in line.lower() and current_table:
                results.append(f"[{current_table}] {line.strip()}")
        if results:
            return "找到以下匹配:\n" + "\n".join(results[:10])
        return f"Schema 中没有找到包含 '{keyword}' 的内容"

    elif action == "final_answer":
        # v0.4.1.1 C 升级：final_answer 时 runtime 守护反模式
        # v0.5.1 R-85：cartesian 优先（更基础错误，先于 fan-out 细分聚合错误）
        candidate = _strip_sql(action_input)
        is_cart, cart_reason = sql_validator.is_cartesian(candidate)
        if is_cart:
            return (
                f"__REJECT_CARTESIAN__:{cart_reason} "
                f"Regenerate the SQL with explicit JOIN ... ON conditions."
            )
        is_fan, reason = _is_fan_out(candidate)
        if is_fan:
            return (
                f"__REJECT_FAN_OUT__:你提交的 SQL 是 fan-out 反模式（{reason}）。"
                f"必须重写：每个明细表先用 `LEFT JOIN (SELECT key, SUM/COUNT(...) FROM <table> "
                f"GROUP BY key) AS alias ON ...` 子查询/CTE 按 grain 预聚合后再 JOIN，"
                f"不要让外层 SELECT 直接对多个 LEFT JOIN 后字段聚合。重新生成 SQL。"
            )
        return f"__FINAL__:{action_input}"

    else:
        return f"未知工具 '{action}'，请使用 execute_sql/describe_table/list_tables/search_schema/final_answer"


def _call_llm(model_key, api_key, model_cfg, system_prompt, messages) -> tuple[str, int, int]:
    provider = model_cfg["provider"]

    if provider == "anthropic":
        import anthropic
        base_url = PROVIDER_BASE_URLS.get("anthropic", "")
        client = anthropic.Anthropic(
            api_key=api_key,
            **({"base_url": base_url} if base_url else {}),
        )
        resp = client.messages.create(
            model=model_key,
            max_tokens=MAX_TOKENS_PER_QUERY,
            temperature=0,
            system=[{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}],
            messages=messages,
        )
        return resp.content[0].text, resp.usage.input_tokens, resp.usage.output_tokens
    else:
        import openai
        base_url = PROVIDER_BASE_URLS.get(provider, "")
        client = openai.OpenAI(api_key=api_key, base_url=base_url or None)
        full_msgs = [{"role": "system", "content": system_prompt}] + messages
        resp = client.chat.completions.create(
            model=model_key, max_tokens=MAX_TOKENS_PER_QUERY, temperature=0, messages=full_msgs
        )
        raw = resp.choices[0].message.content or ""
        it = resp.usage.prompt_tokens if resp.usage else 0
        ot = resp.usage.completion_tokens if resp.usage else 0
        return raw, it, ot


async def _acall_llm(model_key, api_key, model_cfg, system_prompt, messages) -> tuple[str, int, int]:
    """v0.4.4 _call_llm 的 async 版本（ReAct 循环每步用）。

    - 走 adapters/llm/factory.get_async_adapter (R-31)
    - R-26-Senior：调用前 budget 守护（agent_kind='sql_planner'）
    - R-30：原 SDK 异常已由 adapter 包装为 BIAgentError 子类 → 透传给 ReAct 循环 catch
    """
    from knot.adapters.llm import LLMRequest, get_async_adapter
    from knot.models.errors import BIAgentError, BudgetExceededError, LLMNetworkError
    from knot.services import budget_service

    # R-26-Senior：每步 LLM 调用前 budget 守护（防 ReAct 循环烧钱）
    estimated_cost = MAX_TOKENS_PER_QUERY / 1_000_000 * (
        float(model_cfg.get("input_price", 0) or 0) + float(model_cfg.get("output_price", 0) or 0)
    )
    allowed, meta = budget_service.check_agent_per_call_budget("sql_planner", estimated_cost)
    if not allowed:
        raise BudgetExceededError(meta or {})

    provider = model_cfg["provider"]
    base_url = PROVIDER_BASE_URLS.get(provider, "")
    req = LLMRequest(
        model_key=model_key,
        system=system_prompt,
        messages=list(messages),
        api_key=api_key,
        base_url=base_url,
        max_tokens=MAX_TOKENS_PER_QUERY,
        temperature=0,
        enable_prompt_cache=(provider == "anthropic"),
    )
    try:
        adapter = get_async_adapter(provider)
        resp = await adapter.acomplete(req)
    except BIAgentError:
        raise
    except Exception as e:
        raise LLMNetworkError(str(e)[:200]) from e
    return resp.text, resp.input_tokens, resp.output_tokens


def run_sql_agent(
    question: str,
    schema_text: str,
    engine,
    model_key: str = DEFAULT_MODEL,
    api_key: str = "",
    business_context: str = "",
    max_steps: int = 5,
    openrouter_api_key: str = "",
) -> AgentResult:
    def _err(msg):
        return AgentResult(
            success=False, sql="", rows=[], explanation="",
            confidence="low", error=msg,
            steps=[], total_cost_usd=0, total_input_tokens=0, total_output_tokens=0,
        )

    _registered = MODELS.get(model_key)
    _is_or = (_registered and _registered.get("provider") == "openrouter") or \
             ("/" in model_key and not _registered)
    if _is_or:
        _app_key = ""
        try:
            from knot.repositories.settings_repo import get_app_setting
            _app_key = get_app_setting("openrouter_api_key", "") or ""
        except Exception:
            pass
        key = openrouter_api_key or _app_key or PROVIDER_API_KEYS.get("openrouter", "")
        if not key:
            return _err("未设置 OpenRouter API Key，请在「API & 模型」页面填写")
        model_cfg = _registered or {"provider": "openrouter", "input_price": 0.0, "output_price": 0.0}
    else:
        model_cfg = _registered
        if not model_cfg:
            return _err(f"未知模型: {model_key}")
        key = api_key or PROVIDER_API_KEYS.get(model_cfg["provider"], "")
        if not key and model_cfg["provider"] != "ollama":
            return _err(f"未设置 {model_cfg['provider']} 的 API Key")

    business_section = f"## 业务语义层\n{business_context.strip()}" if business_context.strip() else ""
    system_prompt = _prompts_mod.get_prompt(
        "sql_planner", _AGENT_SYSTEM_TEMPLATE,
        {
            "max_steps": max_steps,
            "db_env": "Apache Doris（兼容 MySQL 5.7 语法）",
            "schema": schema_text,
            "relations": _relations_for_schema(schema_text),  # v0.4.1.1 RELATIONS 注入
            "business_ctx": business_section,
            "today": date_context.today_iso(),
            "date_block": date_context.date_context_block(),
            "business_rules": _business_rules(),
        },
    )

    messages = [{"role": "user", "content": f"用户问题: {question}"}]
    steps: list[AgentStep] = []
    total_cost = 0.0
    total_it = total_ot = 0
    final_sql = final_error = ""
    final_rows: list = []
    cart_reject_count = 0  # v0.5.1 R-91：连续 3 次 cartesian 拒收强制终止

    for step_num in range(1, max_steps + 1):
        try:
            raw_text, it, ot = _call_llm(model_key, key, model_cfg, system_prompt, messages)
        except Exception as e:
            final_error = f"LLM 调用失败: {str(e)[:200]}"
            break

        total_it += it
        total_ot += ot
        total_cost += llm_client.calculate_cost(it, ot, model_cfg["input_price"], model_cfg["output_price"])

        thought, action, action_input = _parse_agent_output(raw_text)
        observation = _run_tool(action, action_input, engine, schema_text)

        steps.append(AgentStep(
            step_num=step_num, thought=thought, action=action,
            action_input=action_input, observation=observation,
        ))

        if observation.startswith("__FINAL__:"):
            final_sql = _strip_sql(observation[len("__FINAL__:"):])
            if final_sql.upper().startswith("SELECT"):
                final_rows, exec_err = db_connector.execute_query(engine, final_sql)
                if exec_err:
                    final_error = exec_err
            break

        # v0.5.1 R-91：cartesian 拒收 — 计数 + ≥3 次强制终止；否则继续反馈 LLM 重生成
        if observation.startswith("__REJECT_CARTESIAN__:"):
            cart_reject_count += 1
            if cart_reject_count >= 3:
                final_error = (
                    f"SQL 校验连续 {cart_reject_count} 次发现笛卡尔积 / 恒真 ON，"
                    f"LLM 未能收敛。最近一次原因：{observation[len('__REJECT_CARTESIAN__:'):]}"
                )
                break
            observation = observation[len("__REJECT_CARTESIAN__:"):]

        # v0.4.1.1 C 升级：fan-out 拒绝 — 不 break，把拒绝理由作为 observation 反馈给 LLM 继续 ReAct 重试
        if observation.startswith("__REJECT_FAN_OUT__:"):
            observation = observation[len("__REJECT_FAN_OUT__:"):]
            # 不动 final_sql；继续 messages append 让 LLM 看到 observation 重写

        if action == "execute_sql" and not observation.startswith("执行失败"):
            final_sql = _strip_sql(action_input)
            final_rows, exec_err = db_connector.execute_query(engine, final_sql)
            if not exec_err:
                break
            observation = f"重新执行失败: {exec_err}"

        messages.append({"role": "assistant", "content": raw_text})
        messages.append({"role": "user", "content": f"Observation: {observation}"})

    success = bool(final_sql and not final_error) or bool(final_sql and final_rows is not None)

    return AgentResult(
        success=success,
        sql=final_sql,
        rows=final_rows or [],
        explanation=f"通过 {len(steps)} 步推理生成 SQL",
        confidence="high" if success else ("medium" if final_sql else "low"),
        error=final_error,
        steps=steps,
        total_cost_usd=total_cost,
        total_input_tokens=total_it,
        total_output_tokens=total_ot,
    )


async def arun_sql_agent(
    question: str,
    schema_text: str,
    engine,
    model_key: str = DEFAULT_MODEL,
    api_key: str = "",
    business_context: str = "",
    max_steps: int = 5,
    openrouter_api_key: str = "",
) -> AgentResult:
    """v0.4.4 R-24：run_sql_agent 的 async 版本。

    ReAct 循环每步用 _acall_llm（含 R-26-Senior budget 守护 + R-30 错误标准化）。
    R-32：每步 agent_kind='sql_planner'；fix_sql 是独立路径（query.py 的非流式回路用），
    arun_sql_agent 内部不调 fix_sql。
    R-30：BIAgentError（如 BudgetExceededError）必须透传给 query.py 上层；
    其他异常包成 final_error 由 AgentResult.success=False 报回。
    """
    from knot.models.errors import BIAgentError  # R-30 透传守护

    def _err(msg):
        return AgentResult(
            success=False, sql="", rows=[], explanation="",
            confidence="low", error=msg,
            steps=[], total_cost_usd=0, total_input_tokens=0, total_output_tokens=0,
        )

    _registered = MODELS.get(model_key)
    _is_or = (_registered and _registered.get("provider") == "openrouter") or \
             ("/" in model_key and not _registered)
    if _is_or:
        _app_key = ""
        try:
            from knot.repositories.settings_repo import get_app_setting
            _app_key = get_app_setting("openrouter_api_key", "") or ""
        except Exception:
            pass
        key = openrouter_api_key or _app_key or PROVIDER_API_KEYS.get("openrouter", "")
        if not key:
            return _err("未设置 OpenRouter API Key，请在「API & 模型」页面填写")
        model_cfg = _registered or {"provider": "openrouter", "input_price": 0.0, "output_price": 0.0}
    else:
        model_cfg = _registered
        if not model_cfg:
            return _err(f"未知模型: {model_key}")
        key = api_key or PROVIDER_API_KEYS.get(model_cfg["provider"], "")
        if not key and model_cfg["provider"] != "ollama":
            return _err(f"未设置 {model_cfg['provider']} 的 API Key")

    business_section = f"## 业务语义层\n{business_context.strip()}" if business_context.strip() else ""
    system_prompt = _prompts_mod.get_prompt(
        "sql_planner", _AGENT_SYSTEM_TEMPLATE,
        {
            "max_steps": max_steps,
            "db_env": "Apache Doris（兼容 MySQL 5.7 语法）",
            "schema": schema_text,
            "relations": _relations_for_schema(schema_text),  # v0.4.1.1 RELATIONS 注入
            "business_ctx": business_section,
            "today": date_context.today_iso(),
            "date_block": date_context.date_context_block(),
            "business_rules": _business_rules(),
        },
    )

    messages = [{"role": "user", "content": f"用户问题: {question}"}]
    steps: list[AgentStep] = []
    total_cost = 0.0
    total_it = total_ot = 0
    final_sql = final_error = ""
    final_rows: list = []
    cart_reject_count = 0  # v0.5.1 R-91：连续 3 次 cartesian 拒收强制终止

    for step_num in range(1, max_steps + 1):
        try:
            raw_text, it, ot = await _acall_llm(model_key, key, model_cfg, system_prompt, messages)
        except BIAgentError:
            # R-30：领域异常（含 LLMNetworkError / BudgetExceededError 等）透传给
            # api/query.py，由 error_translator 翻译为友好提示
            raise
        except Exception as e:
            # 非领域异常兜底（罕见内部 bug）→ AgentResult.error，避免单步崩溃 5xx
            final_error = f"LLM 调用失败: {str(e)[:200]}"
            break

        total_it += it
        total_ot += ot
        total_cost += llm_client.calculate_cost(it, ot, model_cfg["input_price"], model_cfg["output_price"])

        thought, action, action_input = _parse_agent_output(raw_text)
        observation = _run_tool(action, action_input, engine, schema_text)

        steps.append(AgentStep(
            step_num=step_num, thought=thought, action=action,
            action_input=action_input, observation=observation,
        ))

        if observation.startswith("__FINAL__:"):
            final_sql = _strip_sql(observation[len("__FINAL__:"):])
            if final_sql.upper().startswith("SELECT"):
                final_rows, exec_err = db_connector.execute_query(engine, final_sql)
                if exec_err:
                    final_error = exec_err
            break

        # v0.5.1 R-91：cartesian 拒收 — 计数 + ≥3 次强制终止；否则继续反馈 LLM 重生成
        if observation.startswith("__REJECT_CARTESIAN__:"):
            cart_reject_count += 1
            if cart_reject_count >= 3:
                final_error = (
                    f"SQL 校验连续 {cart_reject_count} 次发现笛卡尔积 / 恒真 ON，"
                    f"LLM 未能收敛。最近一次原因：{observation[len('__REJECT_CARTESIAN__:'):]}"
                )
                break
            observation = observation[len("__REJECT_CARTESIAN__:"):]

        # v0.4.1.1 fan-out 拒绝：不 break，把拒绝理由作为 observation 反馈给 LLM 继续 ReAct 重试
        if observation.startswith("__REJECT_FAN_OUT__:"):
            observation = observation[len("__REJECT_FAN_OUT__:"):]
            # 不动 final_sql；继续 messages append 让 LLM 看到 observation 重写

        if action == "execute_sql" and not observation.startswith("执行失败"):
            final_sql = _strip_sql(action_input)
            final_rows, exec_err = db_connector.execute_query(engine, final_sql)
            if not exec_err:
                break
            observation = f"重新执行失败: {exec_err}"

        messages.append({"role": "assistant", "content": raw_text})
        messages.append({"role": "user", "content": f"Observation: {observation}"})

    success = bool(final_sql and not final_error) or bool(final_sql and final_rows is not None)

    return AgentResult(
        success=success,
        sql=final_sql,
        rows=final_rows or [],
        explanation=f"通过 {len(steps)} 步推理生成 SQL",
        confidence="high" if success else ("medium" if final_sql else "low"),
        error=final_error,
        steps=steps,
        total_cost_usd=total_cost,
        total_input_tokens=total_it,
        total_output_tokens=total_ot,
    )
