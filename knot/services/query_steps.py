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


def should_run_presenter(success: bool, error: str) -> bool:
    """v0.7.20（守护者 Stage 3 + adversarial 复核纠正）：是否运行 presenter（= 有可呈现的有效结果）。

    = `success and not error` = sql_planner success 公式第一子句 `bool(final_sql and not final_error)`。
    ⚠️ **不能只用 `not success`**：execute_query 出错返 `([], err)` 永不返 None → success 公式第二子句
    `final_rows is not None` 恒 True → **有 SQL 但执行失败（problem 1/2 Unknown db/column）success=True**，
    `not success` gate 会放行 presenter 幻觉「无数据」（守护者 Stage 3 表「DB 错→success=False」事实错，
    adversarial skeptic grounded 推翻）。也**不能只用 `not error`**：ReAct 放弃（无 SQL）error=""。
    三场景：① DB 错（success=True / error set）跳 ② 放弃（success=False / error="")跳 ③ 真空成功（success=True / error="")跑。
    """
    return bool(success and not error)


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


# ── v0.7.1 语义层确定性路径（flag-gated；命中替代 sql_planner ReAct）──────────

def _semantic_enabled() -> bool:
    """KNOT_SEMANTIC_LAYER 默认 off（R-SL-20）；on 才尝试确定性编译。"""
    import os
    return os.getenv("KNOT_SEMANTIC_LAYER", "false").strip().lower() == "true"


def _semantic_display_meta(lf, by_name: dict, field_labels: dict) -> tuple[dict, list, dict]:
    """v0.7.23/.25/.27 呈现：从 LogicForm 算前端呈现 meta（纯函数·可单测）。

    - column_labels: {metric.name → 中文 display}（缺 display → fallback name）= 表头中文 #5（R-SL-169）；
      **v0.7.27 维度中文标签**：再对 `lf.dimensions` 列补 `field_labels[d]`（catalog {列名:中文}），
      **仅 `d not in column_labels`**（metric.display 优先 R-SL-188；极端 dim名==metric名 不覆盖）；
      field_labels 空/缺 → 不加 → byte-equal v0.7.25（R-SL-187 additive-only）。
    - dimension_cols: list(lf.dimensions) = 图表 labelCols；前端 valueCols = 结果列 − dimension_cols
      = 全部度量（含 window/derived）。⚠️ 用 lf.dimensions **非 lf.metrics**：窗口列输出键 = `AS {as_name}`
      ∉ lf.metrics、派生列同理 → 「只画 lf.metrics」会排除窗口/移动平均/派生度量不画（守护者 Stage 3 R-SL-170）。
    - column_formats: {metric.name → unit}（v0.7.25 · R-SL-181；**仅非空 unit 入** → 前端 percentage 列 ×100+%，
      其余列无 key → fmtValue else 分支 byte-equal）。R1 承重：unit=percentage 假设值是 0-1 小数（÷派生费率）。
    锚点 ⑤：维度输出键 == lf.dimensions（compiler 单/多对象均 `<alias>.{d}` 无 AS 改键 — compiler.py:193/235 verified）。
    """
    column_labels = {n: (by_name[n].get("display") or n) for n in lf.metrics if n in by_name}
    # v0.7.27 维度中文标签 merge（仅 dimensions 列 + 仅 d ∉ column_labels → metric.display 优先 R-SL-188）
    for d in lf.dimensions:
        if d not in column_labels and field_labels.get(d):
            column_labels[d] = field_labels[d]
    column_formats = {n: (by_name[n].get("unit") or "") for n in lf.metrics
                      if n in by_name and (by_name[n].get("unit") or "")}
    return column_labels, list(lf.dimensions), column_formats


async def run_semantic_compile_step(refined_question: str, engine, sql_planner_key: str,
                                    api_key: str, openrouter_api_key: str, agent_buckets: dict,
                                    expected_cat, user: dict):
    """语义层确定性路径尝试：返回 `(result, audit)`（v0.7.3 改 — 原仅 result）。

    - result = AgentResult（命中）| None（未命中 → 回退 LLM，混合架构 R-SL-14）。
    - audit = 侧表行 dict（命中 + near-miss 均带：`catalog_id`(R-SL-40 解析时 active) + canonical
      `logicform_json` + `compile_error_reason`）| None（flag off / 无指标 / parse 未命中 → 无审计行）。
      调用方 save_message 后据此写 semantic_audit_repo（mid 已知）。
    成本：LogicForm 解析归 `sql_planner` 桶（R-SL-19）。隔离：执行前 assert catalog（R-SL-21/39 / v0.6.2.6）。
    """
    if not _semantic_enabled():
        return None, None
    from knot.core import time_resolver
    from knot.repositories import metric_repo
    from knot.services import query_helper
    from knot.services.agents import catalog as catalog_mod
    from knot.services.semantic import compiler, parser

    catalog = catalog_mod.current_catalog()
    catalog_id = catalog.get("catalog_id") or 1            # R-SL-40 落盘解析时 active catalog
    metrics = metric_repo.list_metrics(catalog_id)         # R-SL-21 active catalog 隔离
    if not metrics:
        return None, None
    parse_res = await parser.parse_to_logicform(
        refined_question, metrics, sql_planner_key, api_key, openrouter_api_key,
        business_rules=catalog.get("business_rules", ""),   # v0.7.19 库表时效路由（今天/实时→dwd）
    )
    cost_service.add_agent_cost(  # R-SL-19 复用 sql_planner planning 桶
        agent_buckets, "sql_planner",
        parse_res["cost_usd"], parse_res["input_tokens"], parse_res["output_tokens"],
    )
    lf = parse_res["logicform"]
    if lf is None:
        return None, None                                  # parse 未命中 → 无 LogicForm → 无审计行
    lf_json = lf.to_canonical_json()                       # canonical 单源（R-SL-17；非 sort_keys）
    # v0.7.19 per-metric 新鲜度：按引用 metric 的 freshness_lag_days 取 min（最新源）解析 time_ctx
    # → dwd metric(lag=0) 的 *_to_latest/today 解析到【今天】，ads(lag=1)到【昨天】；含今天窗口走 dwd 才真拿到今天。
    _by_name = {m["name"]: m for m in metrics}
    # ⚠️ 不能用 `or 1`：dwd 的 freshness_lag_days=0 是 falsy 会被吞成 1（→ latest 退回昨天 → 漏今天）。
    def _lag_of(m):
        v = m.get("freshness_lag_days")
        return 1 if v is None else int(v)
    _lags = [_lag_of(_by_name[n]) for n in lf.metrics if n in _by_name]
    _lag = min(_lags) if _lags else 1
    try:
        sql = compiler.compile_logicform(lf, catalog, time_resolver.resolve_time_context(data_freshness_lag_days=_lag))
    except compiler.CompileError as e:
        # near-miss：解析出 LF 但编译歧义 → 回退 LLM + 存审计行（诊断「为何回退」R-SL-34/D4）
        return None, {"catalog_id": catalog_id, "logicform_json": lf_json, "compile_error_reason": str(e)}
    query_helper.assert_catalog_context(expected_cat, user)  # 执行前隔离 assert（v0.6.2.6 / R-SL-39）
    rows, db_error = db_connector.execute_query(engine, sql)
    # v0.7.18 R-SL-147：AgentResult 携带 parse LLM cost+token（与 ReAct run_sql_planner_step 对称）。
    # 原置 0 = P1 bug：query.py 顶层 `clarifier + sql_result.token + presenter` 命中时漏 parse token
    # → message/user-usage token 偏低（cost 经 add_agent_cost 入桶仍对，token 走结果和故漏；top-level cost 仍取桶）。
    column_labels, dimension_cols, column_formats = _semantic_display_meta(  # v0.7.23/.25/.27 呈现 meta
        lf, _by_name, catalog.get("field_labels", {}))  # v0.7.27 维度中文标签（current_catalog 两载体均含）
    result = agent_module.AgentResult(
        success=not db_error, sql=sql, rows=rows or [], explanation="",
        confidence="high", error=db_error or "", steps=[],
        total_cost_usd=parse_res["cost_usd"],
        total_input_tokens=parse_res["input_tokens"],
        total_output_tokens=parse_res["output_tokens"],
        column_labels=column_labels, dimension_cols=dimension_cols, column_formats=column_formats,
    )
    return result, {"catalog_id": catalog_id, "logicform_json": lf_json, "compile_error_reason": ""}


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
