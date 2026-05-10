"""knot/services/query_steps.py — v0.5.2 起从 api/query.py 抽出。

源行号区间（v0.5.1 final 状态 api/query.py 457 行）：
- L37-49   enrich_semantic（RAG 文档检索增强）
- L91-112  非流式 agent 分支业务（run_sql_agent + cost 累加 + agent_steps）
- L113-161 非流式 non-agent 分支（generate_sql + fix_sql 重试循环 + cost 累加）
- L243-252 流式 _agent_key 嵌套（select_agent_key）
- L281-289 流式 clarifier step 业务（arun_clarifier + cost 累加）
- L340-353 流式 sql_planner step 业务（arun_sql_agent + cost + recovery_attempt 计算）
- L371-379 流式 presenter step 业务（arun_presenter + cost 累加）

R-109 SSE 稳定性：本模块仅含**纯业务步骤函数**（输入参数 + 返回结果），
**严禁含 generator / yield**；SSE 主控结构（yield emit + asyncio.sleep）保留在
api/query.py 的 query_stream 内，仅把每步的业务计算 delegate 给本模块函数。

R-106 单向依赖：本模块依赖 stdlib + knot.services.* + knot.adapters.* + knot.config；
严禁反向 import knot.api.*。
"""
from knot import config as cfg
from knot.adapters.db import doris as db_connector
from knot.services import cost_service, llm_client
from knot.services import rag_service as doc_rag
from knot.services.agents import orchestrator as multi_agent_module
from knot.services.agents import sql_planner as agent_module


def enrich_semantic(question: str, base_semantic: str,
                    api_key: str, openrouter_api_key: str, embedding_api_key: str) -> str:
    """RAG 文档检索 + business_context 拼接。失败 fail-open 返原 semantic。"""
    try:
        doc_chunks = doc_rag.search_docs(
            question, top_k=3,
            api_key=api_key, openrouter_api_key=openrouter_api_key,
            embedding_api_key=embedding_api_key,
        )
        if doc_chunks:
            doc_section = "\n\n## 相关业务文档\n" + "\n---\n".join(doc_chunks)
            return (base_semantic + doc_section) if base_semantic else doc_section.lstrip()
    except Exception:
        pass
    return base_semantic


def select_agent_key(role: str, agent_cfg: dict, default_model_key: str,
                     api_key: str, openrouter_api_key: str) -> str:
    """流式：每个 agent role 选 agent_key（agent_cfg 配置优先；无 OR key 时回退 default_model_key）。"""
    m = agent_cfg.get(role) or default_model_key
    if "/" in m or m == default_model_key:
        return m
    prov = cfg.MODELS.get(m, {}).get("provider", "")
    if prov and openrouter_api_key and not (api_key or cfg.PROVIDER_API_KEYS.get(prov, "")):
        return default_model_key
    return m


# ── 流式 3 个 agent step（async；R-109 严禁含 yield）─────────────────────────

async def run_clarifier_step(question: str, schema_text: str, history: list,
                             agent_key: str, api_key: str, openrouter_api_key: str,
                             agent_buckets: dict) -> dict:
    """流式 clarifier step：调 arun_clarifier + cost 累加。返 result dict 原样。"""
    result = await multi_agent_module.arun_clarifier(
        question, schema_text, history, agent_key, api_key, openrouter_api_key,
    )
    cost_service.add_agent_cost(
        agent_buckets, "clarifier",
        result["cost_usd"], result["input_tokens"], result["output_tokens"],
    )
    return result


async def run_sql_planner_step(refined_question: str, schema_text: str, engine,
                                sql_planner_key: str, api_key: str, semantic: str,
                                openrouter_api_key: str, agent_buckets: dict) -> tuple:
    """流式 sql_planner step：调 arun_sql_agent + cost 累加 + recovery_attempt 计算。
    返 (sql_result, recovery_attempt)。"""
    result = await agent_module.arun_sql_agent(
        refined_question, schema_text, engine,
        sql_planner_key, api_key, semantic, cfg.AGENT_MAX_STEPS, openrouter_api_key,
    )
    cost_service.add_agent_cost(
        agent_buckets, "sql_planner",
        result.total_cost_usd, result.total_input_tokens, result.total_output_tokens,
    )
    # v0.4.2 R-14：recovery_attempt 含 fan-out reject 计数（v0.4.1.1 守护重试）
    recovery_attempt = sum(
        1 for s in result.steps
        if "Fan-Out 反模式" in (s.observation or "") or "fan-out" in (s.observation or "").lower()
    )
    return result, recovery_attempt


async def run_presenter_step(question: str, sql: str, rows: list,
                             presenter_key: str, api_key: str, openrouter_api_key: str,
                             agent_buckets: dict) -> dict:
    """流式 presenter step：调 arun_presenter + cost 累加。"""
    result = await multi_agent_module.arun_presenter(
        question, sql, rows, presenter_key, api_key, openrouter_api_key,
    )
    cost_service.add_agent_cost(
        agent_buckets, "presenter",
        result["cost_usd"], result["input_tokens"], result["output_tokens"],
    )
    return result


# ── 非流式 2 个分支（sync；含 fix_sql 重试循环）─────────────────────────────

def run_agent_step_sync(question: str, schema_text: str, engine,
                        model_key: str, api_key: str, semantic: str,
                        openrouter_api_key: str, agent_buckets: dict) -> tuple:
    """非流式 use_agent 分支：调 run_sql_agent + cost 累加。
    返 (result, agent_steps_dicts)。"""
    result = agent_module.run_sql_agent(
        question=question, schema_text=schema_text, engine=engine,
        model_key=model_key, api_key=api_key, business_context=semantic,
        max_steps=cfg.AGENT_MAX_STEPS, openrouter_api_key=openrouter_api_key,
    )
    cost_service.add_agent_cost(
        agent_buckets, "sql_planner",
        result.total_cost_usd, result.total_input_tokens, result.total_output_tokens,
    )
    agent_steps = [
        {"step": s.step_num, "thought": s.thought,
         "action": s.action, "action_input": s.action_input,
         "observation": s.observation}
        for s in result.steps
    ]
    return result, agent_steps


def run_generate_sql_with_fix_retry(question: str, schema_text: str, engine,
                                     model_key: str, api_key: str, semantic: str,
                                     history: list, openrouter_api_key: str,
                                     agent_buckets: dict) -> dict:
    """非流式 non-agent 分支：generate_sql + fix_sql 重试循环 + cost 分桶。
    返 dict {sql, explanation, confidence, error, input_tokens, output_tokens, rows, retry_count}。
    """
    gen = llm_client.generate_sql(
        question=question, schema_text=schema_text,
        model_key=model_key, api_key=api_key,
        business_context=semantic, history=history,
        openrouter_api_key=openrouter_api_key,
    )
    sql = gen["sql"]
    explanation = gen["explanation"]
    confidence = gen["confidence"]
    error = gen["error"]
    input_tokens = gen["input_tokens"]
    output_tokens = gen["output_tokens"]
    cost_service.add_agent_cost(
        agent_buckets, "sql_planner",
        gen["cost_usd"], gen["input_tokens"], gen["output_tokens"],
    )
    rows: list = []
    retry_count = 0

    if sql and not error:
        rows, db_error = db_connector.execute_query(engine, sql)
        if db_error:
            for _ in range(cfg.MAX_RETRY_COUNT):
                fix = llm_client.fix_sql(
                    question, schema_text, sql, db_error,
                    model_key, api_key, semantic,
                    openrouter_api_key=openrouter_api_key,
                )
                retry_count += 1
                input_tokens += fix["input_tokens"]
                output_tokens += fix["output_tokens"]
                # fix_sql 单独桶（资深 Stage 4 拍板：独立 agent_kind）
                cost_service.add_agent_cost(
                    agent_buckets, "fix_sql",
                    fix["cost_usd"], fix["input_tokens"], fix["output_tokens"],
                )
                if fix["sql"] and not fix["error"]:
                    sql = fix["sql"]
                    explanation = fix["explanation"] or explanation
                    rows, db_error = db_connector.execute_query(engine, sql)
                    if not db_error:
                        error = ""
                        break
                    error = db_error
                else:
                    error = fix["error"] or db_error
                    break
            else:
                error = db_error

    return {
        "sql": sql, "explanation": explanation, "confidence": confidence, "error": error,
        "input_tokens": input_tokens, "output_tokens": output_tokens,
        "rows": rows, "retry_count": retry_count,
    }
