"""
llm_client.py — Service 层 LLM 封装

v0.5.2 拆分：本主文件作"调度员"（R-106），子模块作"工具箱"
- few_shots          → few_shots.py            (DB / yaml few-shot 装配)
- prompt builder     → llm_prompt_builder.py   (build_system_prompt 大模板)
- invoke + cost + parse → _llm_invoke.py       (sync/async _invoke + parse + calculate_cost
                                               + R-26 budget gate + R-30 透传)

R-100 re-export：测试 `monkeypatch.setattr(llm_client, "_ainvoke_via_adapter", ...)`
+ 业务侧 `llm_client.calculate_cost(...)` 调用路径不变。
R-108：calculate_cost 平移到 _llm_invoke.py，但通过 re-export 保持
`llm_client.calculate_cost` 调用兼容（sql_planner / orchestrator 不修改）。
"""
from knot.config import DEFAULT_MODEL, MODELS, PROVIDER_API_KEYS

# v0.5.2 R-100 re-export — 测试 + 业务 import 路径 0 修改
from knot.services._llm_invoke import (  # noqa: F401  re-export
    _ainvoke_via_adapter,
    _error_result,
    _estimate_cost_for_budget_check,
    _invoke_via_adapter,
    _normalize_result,
    _parse_llm_response,
    calculate_cost,
)
from knot.services.few_shots import (  # noqa: F401  re-export
    _load_few_shots,
    classify_question_type,
    get_few_shot_examples,
)
from knot.services.llm_prompt_builder import build_system_prompt  # noqa: F401  re-export

# ── OpenRouter detection ───────────────────────────────────────────────

def _app_or_key() -> str:
    try:
        from knot.repositories.settings_repo import get_app_setting
        return get_app_setting("openrouter_api_key", "") or ""
    except Exception:
        return ""


def _is_openrouter_model(model_key: str) -> bool:
    cfg = MODELS.get(model_key)
    if cfg and cfg.get("provider") == "openrouter":
        return True
    return "/" in model_key and model_key not in MODELS


# ── Main entry: generate_sql ───────────────────────────────────────────

def generate_sql(
    question: str,
    schema_text: str,
    model_key: str = DEFAULT_MODEL,
    api_key: str = "",
    business_context: str = "",
    history: list = None,
    openrouter_api_key: str = "",
) -> dict:
    """[DEPRECATED v0.5.5; target removal in v1.0] Use async equivalent (a*) instead."""
    if _is_openrouter_model(model_key):
        key = openrouter_api_key or _app_or_key() or PROVIDER_API_KEYS.get("openrouter", "")
        if not key:
            return _error_result("未设置 OpenRouter API Key，请在「API & 模型」页面填写")
        model_cfg = {"provider": "openrouter", "input_price": 0.0, "output_price": 0.0}
        provider = "openrouter"
    else:
        model_cfg = MODELS.get(model_key)
        if not model_cfg:
            return _error_result(f"未知模型: {model_key}")
        provider = model_cfg["provider"]
        key = api_key or PROVIDER_API_KEYS.get(provider, "")
        if not key and provider != "ollama":
            return _error_result(f"未设置 {provider} 的 API Key")

    try:
        from knot.services.schema_filter import filter_schema_for_question
        filtered_schema = filter_schema_for_question(schema_text, question, max_tables=12)
    except Exception:
        filtered_schema = schema_text

    if business_context.strip():
        try:
            from knot.services.rag_retriever import retrieve_semantic_context
            relevant_ctx = retrieve_semantic_context(question, business_context, top_k=5)
        except Exception:
            relevant_ctx = business_context
    else:
        relevant_ctx = business_context

    system_prompt = build_system_prompt(filtered_schema, relevant_ctx, question)
    user_message = _build_user_message(question, history or [])

    return _invoke_via_adapter(system_prompt, user_message, model_key, key, model_cfg, provider)


def _build_user_message(question: str, history: list) -> str:
    parts = []
    if history:
        recent = history[-3:]
        parts.append("## 本次对话历史（供参考）")
        for h in recent:
            entry = f"问: {h['question']}\nSQL: {h['sql']}"
            rows = h.get('rows') or []
            if rows:
                cols = list(rows[0].keys())
                lines = [" | ".join(cols)]
                for r in rows[:10]:
                    lines.append(" | ".join(str(r.get(c, '')) for c in cols))
                entry += "\n结果数据:\n" + "\n".join(lines)
            parts.append(entry)
        parts.append("---")
    parts.append(question)
    parts.append(
        "\n【重要】只输出 JSON，不要提问，不要解释，不要说任何其他文字。\n"
        '格式: {"sql": "...", "explanation": "...", "confidence": "high/medium/low", "error": ""}\n'
        '如果问题是对上述历史数据的分析性追问（无需新 SQL），请将分析结论放在 explanation 字段，sql 留空。'
    )
    return "\n\n".join(parts)


# ── SQL auto-fix ───────────────────────────────────────────────────────

def fix_sql(question, schema_text, failed_sql, error_message,
            model_key=DEFAULT_MODEL, api_key="", business_context="",
            openrouter_api_key: str = "") -> dict:
    """[DEPRECATED v0.5.5; target removal in v1.0] Use async equivalent (a*) instead."""
    if _is_openrouter_model(model_key):
        key = openrouter_api_key or _app_or_key() or PROVIDER_API_KEYS.get("openrouter", "")
        if not key:
            return _error_result("未设置 OpenRouter API Key")
        model_cfg = {"provider": "openrouter", "input_price": 0.0, "output_price": 0.0}
        provider = "openrouter"
    else:
        model_cfg = MODELS.get(model_key)
        if not model_cfg:
            return _error_result(f"未知模型: {model_key}")
        provider = model_cfg["provider"]
        key = api_key or PROVIDER_API_KEYS.get(provider, "")
        if not key and provider != "ollama":
            return _error_result(f"未设置 {provider} 的 API Key")

    system_prompt = build_system_prompt(schema_text, business_context, question)
    fix_message = (
        f"用户的原始问题:\n{question}\n\n"
        f"上次生成的 SQL（执行失败）:\n{failed_sql}\n\n"
        f"数据库报错信息:\n{error_message}\n\n"
        "请分析报错原因，生成修正后的 SQL。\n"
        "【重要】只输出 JSON，不要解释，不要说其他文字。\n"
        '格式: {"sql": "...", "explanation": "修正说明", "confidence": "high/medium/low", "error": ""}'
    )

    return _invoke_via_adapter(system_prompt, fix_message, model_key, key, model_cfg, provider)


# ── v0.4.4 async API（R-24 双 API 并存：sync 保留，新增 async）───────────────

async def agenerate_sql(
    question: str,
    schema_text: str,
    model_key: str = DEFAULT_MODEL,
    api_key: str = "",
    business_context: str = "",
    history: list = None,
    openrouter_api_key: str = "",
) -> dict:
    """v0.4.4 R-24：generate_sql 的 async 版本。

    复用所有 sync 路径的辅助函数（_resolve_provider_key / build_system_prompt /
    _build_user_message）；仅最末步 _invoke_via_adapter → _ainvoke_via_adapter。
    """
    if _is_openrouter_model(model_key):
        key = openrouter_api_key or _app_or_key() or PROVIDER_API_KEYS.get("openrouter", "")
        if not key:
            return _error_result("未设置 OpenRouter API Key，请在「API & 模型」页面填写")
        model_cfg = {"provider": "openrouter", "input_price": 0.0, "output_price": 0.0}
        provider = "openrouter"
    else:
        model_cfg = MODELS.get(model_key)
        if not model_cfg:
            return _error_result(f"未知模型: {model_key}")
        provider = model_cfg["provider"]
        key = api_key or PROVIDER_API_KEYS.get(provider, "")
        if not key and provider != "ollama":
            return _error_result(f"未设置 {provider} 的 API Key")

    try:
        from knot.services.schema_filter import filter_schema_for_question
        filtered_schema = filter_schema_for_question(schema_text, question, max_tables=12)
    except Exception:
        filtered_schema = schema_text

    if business_context.strip():
        try:
            from knot.services.rag_retriever import retrieve_semantic_context
            relevant_ctx = retrieve_semantic_context(question, business_context, top_k=5)
        except Exception:
            relevant_ctx = business_context
    else:
        relevant_ctx = business_context

    system_prompt = build_system_prompt(filtered_schema, relevant_ctx, question)
    user_message = _build_user_message(question, history or [])

    # R-32：generate_sql 主路径 agent_kind='sql_planner'
    return await _ainvoke_via_adapter(
        system_prompt, user_message, model_key, key, model_cfg, provider,
        agent_kind="sql_planner",
    )


async def afix_sql(question, schema_text, failed_sql, error_message,
                   model_key=DEFAULT_MODEL, api_key="", business_context="",
                   openrouter_api_key: str = "") -> dict:
    """v0.4.4 R-32：fix_sql 的 async 版本，必须传 agent_kind='fix_sql'。

    与 sync fix_sql 行为一致；分桶 cost 进入 fix_sql_cost 桶（query.py 流程已就位）；
    recovery_attempt 累加在 query.py 调用方（v0.4.2 不变量保留）。
    R-26-Senior：fix_sql 同样跑 budget per_call 守护（防 fix_sql 死循环烧钱）。
    """
    if _is_openrouter_model(model_key):
        key = openrouter_api_key or _app_or_key() or PROVIDER_API_KEYS.get("openrouter", "")
        if not key:
            return _error_result("未设置 OpenRouter API Key")
        model_cfg = {"provider": "openrouter", "input_price": 0.0, "output_price": 0.0}
        provider = "openrouter"
    else:
        model_cfg = MODELS.get(model_key)
        if not model_cfg:
            return _error_result(f"未知模型: {model_key}")
        provider = model_cfg["provider"]
        key = api_key or PROVIDER_API_KEYS.get(provider, "")
        if not key and provider != "ollama":
            return _error_result(f"未设置 {provider} 的 API Key")

    system_prompt = build_system_prompt(schema_text, business_context, question)
    fix_message = (
        f"用户的原始问题:\n{question}\n\n"
        f"上次生成的 SQL（执行失败）:\n{failed_sql}\n\n"
        f"数据库报错信息:\n{error_message}\n\n"
        "请分析报错原因，生成修正后的 SQL。\n"
        "【重要】只输出 JSON，不要解释，不要说其他文字。\n"
        '格式: {"sql": "...", "explanation": "修正说明", "confidence": "high/medium/low", "error": ""}'
    )

    # R-32 显式 agent_kind='fix_sql'：cost 进 fix_sql_cost 桶；R-26-Senior 自动生效
    return await _ainvoke_via_adapter(
        system_prompt, fix_message, model_key, key, model_cfg, provider,
        agent_kind="fix_sql",
    )
