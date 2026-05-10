"""sql_planner.py — SQL Agent 推理链（ReAct 模式）

v0.5.2 拆分：本主文件作"调度员"（R-106），子模块作"工具箱"
- prompts → sql_planner_prompts.py（_AGENT_SYSTEM_TEMPLATE + _business_rules + _relations_for_schema）
- tools   → sql_planner_tools.py  （_strip_sql + _parse_agent_output + _is_fan_out + _run_tool 含 v0.5.1 cartesian / v0.4.1.1 fan-out 守护）
- llm     → sql_planner_llm.py    （_call_llm + _acall_llm 含 v0.4.4 R-26 budget gate + R-30 透传）

R-100 re-export：测试 import 路径 0 修改（`from knot.services.agents.sql_planner import _is_fan_out` 等仍工作）。
"""
import time
from dataclasses import dataclass, field

from knot.adapters.db import doris as db_connector
from knot.config import DEFAULT_MODEL, MODELS, PROVIDER_API_KEYS
from knot.core import date_context
from knot.services import llm_client
from knot.services import prompt_service as _prompts_mod
from knot.services.agents.sql_planner_llm import _acall_llm, _call_llm  # noqa: F401  re-export
from knot.services.agents.sql_planner_prompts import (  # noqa: F401  re-export
    _AGENT_SYSTEM_TEMPLATE,
    _business_rules,
    _relations_for_schema,
)
from knot.services.agents.sql_planner_tools import (  # noqa: F401  re-export
    _is_fan_out,
    _parse_agent_output,
    _run_tool,
    _strip_sql,
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
    """[DEPRECATED v0.5.5; target removal in v1.0] Use async equivalent (a*) instead."""
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
