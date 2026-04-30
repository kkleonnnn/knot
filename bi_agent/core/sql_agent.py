"""
sql_agent.py — SQL Agent 推理链（ReAct 模式）
Think → Act → Observe → ... → Final Answer
"""

import re
import time
from dataclasses import dataclass, field
from typing import List, Tuple

import db_connector
import llm_client
import prompts as _prompts_mod
import date_context

try:
    import catalog_loader as _cl
    _OHX_RULES = _cl.BUSINESS_RULES
except Exception:
    _OHX_RULES = ""
from config import (
    DEFAULT_MODEL, MAX_TOKENS_PER_QUERY,
    MODELS, PROVIDER_API_KEYS, PROVIDER_BASE_URLS,
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
    steps: List[AgentStep]
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

## 数据库环境
{db_env}

## 数据库 Schema
{schema}

{business_ctx}"""


def _strip_sql(s: str) -> str:
    """剥掉 LLM 常见的 markdown 围栏：```sql ... ``` / ``` ... ``` / 单反引号。"""
    s = s.strip()
    m = re.match(r"^```(?:sql)?\s*([\s\S]*?)\s*```$", s, re.IGNORECASE)
    if m:
        s = m.group(1)
    return s.strip().strip("`").strip()


def _parse_agent_output(text: str) -> Tuple[str, str, str]:
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
        return f"__FINAL__:{action_input}"

    else:
        return f"未知工具 '{action}'，请使用 execute_sql/describe_table/list_tables/search_schema/final_answer"


def _call_llm(model_key, api_key, model_cfg, system_prompt, messages) -> Tuple[str, int, int]:
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
    _err = lambda msg: AgentResult(
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
            import persistence
            _app_key = persistence.get_app_setting("openrouter_api_key", "") or ""
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
            "business_ctx": business_section,
            "today": date_context.today_iso(),
            "date_block": date_context.date_context_block(),
            "business_rules": _OHX_RULES,
        },
    )

    messages = [{"role": "user", "content": f"用户问题: {question}"}]
    steps: List[AgentStep] = []
    total_cost = 0.0
    total_it = total_ot = 0
    final_sql = final_error = ""
    final_rows: list = []

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
