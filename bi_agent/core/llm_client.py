"""
llm_client.py — LLM 层（多模型路由 + Text-to-SQL）
支持 Anthropic Prompt Cache，多 provider 统一接口。
"""

import json
import os
import re
import anthropic
import openai

from config import (
    MODELS, DEFAULT_MODEL,
    PROVIDER_BASE_URLS, PROVIDER_API_KEYS,
    MAX_TOKENS_PER_QUERY, SQL_TEMPERATURE,
    MAX_RETRY_COUNT,
)


# ── Few-Shot library ───────────────────────────────────────────────────

def _load_few_shots() -> dict:
    """优先从 DB 读取（admin 维护）；DB 为空时回退 few_shots.yaml。"""
    yaml_data = {"examples": [], "type_keywords": {}}
    yaml_path = os.path.join(os.path.dirname(__file__), "few_shots.yaml")
    if os.path.exists(yaml_path):
        try:
            import yaml
            with open(yaml_path, "r", encoding="utf-8") as f:
                yaml_data = yaml.safe_load(f) or yaml_data
        except Exception:
            pass

    try:
        import persistence
        rows = persistence.list_few_shots(only_active=True)
        if rows:
            return {
                "examples": [
                    {
                        "id": r["id"],
                        "question": r["question"],
                        "sql": r["sql"],
                        "type": r.get("type") or "aggregation",
                        "explanation": "",
                        "confidence": "medium",
                    }
                    for r in rows
                ],
                "type_keywords": yaml_data.get("type_keywords", {}),
            }
    except Exception:
        pass
    return yaml_data


def classify_question_type(question: str, type_keywords: dict) -> str:
    q_lower = question.lower()
    scores: dict = {}
    for qtype, keywords in type_keywords.items():
        hit = sum(1 for kw in keywords if kw.lower() in q_lower)
        if hit > 0:
            scores[qtype] = hit
    return max(scores, key=scores.get) if scores else "aggregation"


def get_few_shot_examples(question: str, max_examples: int = 4) -> str:
    data = _load_few_shots()
    examples = data.get("examples", [])
    type_keywords = data.get("type_keywords", {})

    if not examples:
        return ""

    question_type = classify_question_type(question, type_keywords)
    typed: dict = {}
    for ex in examples:
        t = ex.get("type", "aggregation")
        typed.setdefault(t, []).append(ex)

    selected = []
    primary = typed.get(question_type, [])
    selected.extend(primary[: max(1, max_examples // 2)])

    remaining = max_examples - len(selected)
    other_types = [t for t in typed if t != question_type]
    for t in other_types:
        if remaining <= 0:
            break
        for ex in typed[t][:1]:
            if remaining <= 0:
                break
            selected.append(ex)
            remaining -= 1

    lines = []
    for ex in selected:
        lines.append(f"问题: {ex['question']}")
        sql_str = ex["sql"].replace("\n", " ")
        out = json.dumps(
            {"sql": sql_str, "explanation": ex.get("explanation", ""),
             "confidence": ex.get("confidence", "medium"), "error": ""},
            ensure_ascii=False,
        )
        lines.append(f"输出: {out}")
        lines.append("")

    return "\n".join(lines).strip()


# ── System Prompt builder ──────────────────────────────────────────────

def build_system_prompt(schema_text: str, business_context: str = "", question: str = "") -> str:
    section_role = """你是一个 Text-to-SQL 专家助手。
你的唯一任务是把用户的自然语言问题转换成可执行的 SQL 查询语句。
不要解释你自己，不要打招呼，只输出要求格式的 JSON。"""

    import date_context
    section_db = f"""## 数据库环境
{date_context.date_context_block()}
- 数据库类型: Apache Doris（完全兼容 MySQL 5.7 语法）
- 时间函数: DATE_SUB(CURDATE(), INTERVAL N DAY) 或 CURRENT_DATE - INTERVAL N DAY
- 字符串函数: CONCAT(), SUBSTRING(), LENGTH()
- 聚合函数: COUNT(), SUM(), AVG(), MAX(), MIN()"""

    section_schema = f"""## 数据库表结构
以下是可以查询的表和字段:

{schema_text}"""

    section_safety = """## 安全规则（必须严格遵守）
- 只允许生成 SELECT 语句
- 严禁生成 INSERT / UPDATE / DELETE / DROP / TRUNCATE / ALTER / CREATE
- 如果用户的问题无法用已知表结构回答，在 JSON 的 error 字段说明原因"""

    section_format = """## 输出格式（严格遵守）
只输出以下格式的 JSON，不输出任何其他文字、解释或 markdown:
{"sql": "SELECT ...", "explanation": "这条 SQL 查询了...", "confidence": "high 或 medium 或 low", "error": ""}

如果无法生成有效 SQL:
{"sql": "", "explanation": "", "confidence": "low", "error": "原因说明"}"""

    examples_text = get_few_shot_examples(question, max_examples=4)
    if examples_text:
        section_examples = f"## 示例（参考这些模式生成 SQL）\n\n{examples_text}"
    else:
        section_examples = """## 示例
问题: 查看有哪些表
输出: {"sql": "SHOW TABLES", "explanation": "列出当前数据库所有表名", "confidence": "high", "error": ""}

问题: 昨天的订单总金额是多少
输出: {"sql": "SELECT SUM(pay_amount) AS gmv FROM orders WHERE DATE(created_at) = DATE_SUB(CURDATE(), INTERVAL 1 DAY)", "explanation": "过滤昨天日期，对支付金额求和", "confidence": "medium", "error": ""}"""

    section_confidence = """## 置信度（confidence）含义
- high:   Schema 中明确包含所需表和字段
- medium: 需要推断字段含义，建议执行前确认
- low:    Schema 信息不足，SQL 可能需要修改"""

    section_ordering = """## 排序规则
- 当查询结果包含日期/时间列时，必须加 ORDER BY 该列 ASC，确保时序排列
- 当结果用于趋势分析时，按时间升序排列"""

    sections = [section_role, section_db, section_schema]
    if business_context.strip():
        sections.append(f"## 业务术语与表关系（优先参考）\n{business_context.strip()}")
    sections += [section_safety, section_ordering, section_format, section_examples, section_confidence]
    return "\n\n".join(sections)


# ── OpenRouter detection ───────────────────────────────────────────────

def _app_or_key() -> str:
    try:
        import persistence
        return persistence.get_app_setting("openrouter_api_key", "") or ""
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
        from schema_filter import filter_schema_for_question
        filtered_schema = filter_schema_for_question(schema_text, question, max_tables=12)
    except Exception:
        filtered_schema = schema_text

    if business_context.strip():
        try:
            from rag_retriever import retrieve_semantic_context
            relevant_ctx = retrieve_semantic_context(question, business_context, top_k=5)
        except Exception:
            relevant_ctx = business_context
    else:
        relevant_ctx = business_context

    system_prompt = build_system_prompt(filtered_schema, relevant_ctx, question)
    user_message = _build_user_message(question, history or [])

    if provider == "anthropic":
        return _invoke_anthropic(system_prompt, user_message, model_key, key, model_cfg)
    else:
        return _invoke_openai_compatible(system_prompt, user_message, model_key, key, model_cfg, provider)


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


# ── Provider calls ─────────────────────────────────────────────────────

def _invoke_anthropic(system_prompt, user_message, model_key, api_key, model_cfg) -> dict:
    base_url = PROVIDER_BASE_URLS.get("anthropic", "")
    client_kwargs = {"api_key": api_key}
    if base_url:
        client_kwargs["base_url"] = base_url
    client = anthropic.Anthropic(**client_kwargs, timeout=90.0)

    try:
        response = client.messages.create(
            model=model_key,
            max_tokens=MAX_TOKENS_PER_QUERY,
            temperature=SQL_TEMPERATURE,
            system=[{
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{"role": "user", "content": user_message}],
        )
        raw_text = response.content[0].text
        parsed = _parse_llm_response(raw_text)
        usage = response.usage
        parsed["input_tokens"]  = usage.input_tokens
        parsed["output_tokens"] = usage.output_tokens
        parsed["cost_usd"] = calculate_cost(
            usage.input_tokens, usage.output_tokens,
            model_cfg["input_price"], model_cfg["output_price"],
        )
        return parsed
    except anthropic.AuthenticationError:
        return _error_result("Anthropic API Key 无效或已过期")
    except anthropic.RateLimitError:
        return _error_result("Anthropic API 调用频率超限，请稍后再试")
    except Exception as e:
        return _error_result(f"Anthropic 调用失败: {str(e)[:200]}")


def _invoke_openai_compatible(system_prompt, user_message, model_key, api_key, model_cfg, provider) -> dict:
    base_url = PROVIDER_BASE_URLS.get(provider, "")
    client = openai.OpenAI(api_key=api_key, base_url=base_url, timeout=90.0)

    try:
        response = client.chat.completions.create(
            model=model_key,
            max_tokens=MAX_TOKENS_PER_QUERY,
            temperature=SQL_TEMPERATURE,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_message},
            ],
        )
        raw_text = response.choices[0].message.content or ""
        parsed = _parse_llm_response(raw_text)
        input_tokens  = response.usage.prompt_tokens     if response.usage else 0
        output_tokens = response.usage.completion_tokens if response.usage else 0
        parsed["input_tokens"]  = input_tokens
        parsed["output_tokens"] = output_tokens
        parsed["cost_usd"] = calculate_cost(
            input_tokens, output_tokens,
            model_cfg["input_price"], model_cfg["output_price"],
        )
        return parsed
    except openai.AuthenticationError:
        return _error_result(f"{provider} API Key 无效")
    except openai.RateLimitError:
        return _error_result(f"{provider} 调用频率超限")
    except openai.APIConnectionError:
        return _error_result(f"无法连接到 {provider} API")
    except Exception as e:
        return _error_result(f"{provider} 调用失败: {str(e)[:200]}")


# ── JSON parsing ───────────────────────────────────────────────────────

def _parse_llm_response(raw_text: str) -> dict:
    text = raw_text.strip()
    try:
        return _normalize_result(json.loads(text))
    except json.JSONDecodeError:
        pass

    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if match:
        try:
            return _normalize_result(json.loads(match.group(1)))
        except json.JSONDecodeError:
            pass

    for m in sorted(re.findall(r"\{[\s\S]*?\}", text, re.DOTALL), key=len, reverse=True):
        try:
            return _normalize_result(json.loads(m))
        except json.JSONDecodeError:
            continue

    return {
        "sql": "", "explanation": "", "confidence": "low",
        "error": f"无法解析 LLM 输出: {text[:300]}",
        "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0,
    }


def _normalize_result(result: dict) -> dict:
    return {
        "sql":          result.get("sql", ""),
        "explanation":  result.get("explanation", ""),
        "confidence":   result.get("confidence", "low"),
        "error":        result.get("error", ""),
        "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0,
    }


def _error_result(message: str) -> dict:
    return {
        "sql": "", "explanation": "", "confidence": "low", "error": message,
        "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0,
    }


# ── Cost calculation ───────────────────────────────────────────────────

def calculate_cost(input_tokens, output_tokens, input_price, output_price) -> float:
    return (input_tokens / 1_000_000 * input_price) + (output_tokens / 1_000_000 * output_price)


# ── SQL auto-fix ───────────────────────────────────────────────────────

def fix_sql(question, schema_text, failed_sql, error_message,
            model_key=DEFAULT_MODEL, api_key="", business_context="",
            openrouter_api_key: str = "") -> dict:
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

    if provider == "anthropic":
        return _invoke_anthropic(system_prompt, fix_message, model_key, key, model_cfg)
    else:
        return _invoke_openai_compatible(system_prompt, fix_message, model_key, key, model_cfg, provider)
