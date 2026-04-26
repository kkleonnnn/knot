import asyncio
import json
import time

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

import config as cfg
import persistence
import db_connector
import doc_rag
import sql_agent as agent_module
import multi_agent as multi_agent_module
import llm_client
from ..dependencies import get_current_user
from ..engine_cache import get_user_engine, _upload_engine
from ..schemas import QueryRequest

router = APIRouter()


def _resolve_model(model_key: str, user: dict, api_key: str, openrouter_api_key: str) -> str:
    if model_key not in cfg.MODELS and "/" not in model_key:
        model_key = cfg.DEFAULT_MODEL
    if "/" not in model_key and openrouter_api_key:
        provider = cfg.MODELS.get(model_key, {}).get("provider", "")
        if provider and not (api_key or cfg.PROVIDER_API_KEYS.get(provider, "")):
            pref = user.get("preferred_model", "")
            model_key = pref if "/" in pref else "google/gemini-2.0-flash-001"
    return model_key


def _enrich_semantic(question: str, base_semantic: str, api_key: str, openrouter_api_key: str, embedding_api_key: str) -> str:
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


@router.post("/api/conversations/{conv_id}/query")
async def query(conv_id: int, req: QueryRequest, user=Depends(get_current_user)):
    convs = persistence.list_conversations(user["id"])
    if not any(c["id"] == conv_id for c in convs):
        raise HTTPException(status_code=404)

    if req.upload_id:
        rec = persistence.get_file_upload(req.upload_id)
        if not rec or rec["user_id"] != user["id"]:
            raise HTTPException(status_code=404, detail="上传文件不存在")
        engine = _upload_engine
        schema_text = db_connector.get_sqlite_schema_text(engine, rec["table_name"])
    else:
        engine, schema_text = get_user_engine(user)
        if engine is None:
            raise HTTPException(status_code=400, detail="数据库未配置或连接失败，请联系管理员")

    api_key = req.api_key or user.get("api_key") or ""
    openrouter_api_key = persistence.get_app_setting("openrouter_api_key", "") or user.get("openrouter_api_key") or ""
    embedding_api_key = persistence.get_app_setting("embedding_api_key", "") or user.get("embedding_api_key") or ""
    model_key = _resolve_model(
        req.model_key or user.get("preferred_model") or cfg.DEFAULT_MODEL,
        user, api_key, openrouter_api_key,
    )

    semantic = _enrich_semantic(
        req.question, persistence.get_semantic_layer(),
        api_key, openrouter_api_key, embedding_api_key,
    )
    history = [{"question": m["question"], "sql": m["sql_text"], "rows": (m.get("rows") or [])[:10]}
               for m in persistence.get_messages(conv_id)[-3:]]

    t0 = time.time()
    retry_count = 0
    agent_steps = []

    if req.use_agent:
        result = agent_module.run_sql_agent(
            question=req.question, schema_text=schema_text, engine=engine,
            model_key=model_key, api_key=api_key, business_context=semantic,
            max_steps=cfg.AGENT_MAX_STEPS, openrouter_api_key=openrouter_api_key,
        )
        sql = result.sql
        rows = result.rows
        explanation = result.explanation
        confidence = result.confidence
        error = result.error if not result.success else ""
        input_tokens = result.total_input_tokens
        output_tokens = result.total_output_tokens
        cost_usd = result.total_cost_usd
        agent_steps = [
            {"step": s.step_num, "thought": s.thought,
             "action": s.action, "action_input": s.action_input,
             "observation": s.observation}
            for s in result.steps
        ]
    else:
        gen = llm_client.generate_sql(
            question=req.question, schema_text=schema_text,
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
        cost_usd = gen["cost_usd"]
        rows = []

        if sql and not error:
            rows, db_error = db_connector.execute_query(engine, sql)
            if db_error:
                for _ in range(cfg.MAX_RETRY_COUNT):
                    fix = llm_client.fix_sql(
                        req.question, schema_text, sql, db_error,
                        model_key, api_key, semantic,
                        openrouter_api_key=openrouter_api_key,
                    )
                    retry_count += 1
                    input_tokens += fix["input_tokens"]
                    output_tokens += fix["output_tokens"]
                    cost_usd += fix["cost_usd"]
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

    query_time_ms = int((time.time() - t0) * 1000)

    mid = persistence.save_message(
        conv_id=conv_id, question=req.question, sql=sql,
        explanation=explanation, confidence=confidence,
        rows=rows[:cfg.MAX_RESULT_ROWS], db_error=error,
        cost_usd=cost_usd, input_tokens=input_tokens,
        output_tokens=output_tokens, retry_count=retry_count,
    )

    all_msgs = persistence.get_messages(conv_id)
    if len(all_msgs) == 1:
        title = req.question[:30] + ("…" if len(req.question) > 30 else "")
        persistence.update_conversation_title(conv_id, title)

    persistence.update_user_usage(user["id"], input_tokens, output_tokens, cost_usd, query_time_ms)

    return {
        "id": mid, "question": req.question, "sql": sql,
        "explanation": explanation, "confidence": confidence,
        "rows": rows[:cfg.MAX_RESULT_ROWS], "error": error,
        "input_tokens": input_tokens, "output_tokens": output_tokens,
        "cost_usd": cost_usd, "retry_count": retry_count,
        "query_time_ms": query_time_ms, "agent_steps": agent_steps,
    }


@router.post("/api/conversations/{conv_id}/query-stream")
async def query_stream(conv_id: int, req: QueryRequest, user=Depends(get_current_user)):
    convs = persistence.list_conversations(user["id"])
    if not any(c["id"] == conv_id for c in convs):
        raise HTTPException(status_code=404)

    if req.upload_id:
        rec = persistence.get_file_upload(req.upload_id)
        if not rec or rec["user_id"] != user["id"]:
            raise HTTPException(status_code=404, detail="上传文件不存在")
        engine = _upload_engine
        schema_text = db_connector.get_sqlite_schema_text(engine, rec["table_name"])
    else:
        engine, schema_text = get_user_engine(user)
        if engine is None:
            raise HTTPException(status_code=400, detail="数据库未配置或连接失败，请联系管理员")

    api_key = req.api_key or user.get("api_key") or ""
    openrouter_api_key = persistence.get_app_setting("openrouter_api_key", "") or user.get("openrouter_api_key") or ""
    embedding_api_key = persistence.get_app_setting("embedding_api_key", "") or user.get("embedding_api_key") or ""
    model_key = _resolve_model(
        req.model_key or user.get("preferred_model") or cfg.DEFAULT_MODEL,
        user, api_key, openrouter_api_key,
    )

    semantic = _enrich_semantic(
        req.question, persistence.get_semantic_layer(),
        api_key, openrouter_api_key, embedding_api_key,
    )
    history = [{"question": m["question"], "sql": m["sql_text"], "rows": (m.get("rows") or [])[:10]}
               for m in persistence.get_messages(conv_id)[-3:]]

    user_agent_cfg = persistence.get_agent_model_config()

    def _agent_key(role: str) -> str:
        m = user_agent_cfg.get(role) or model_key
        if "/" in m or m == model_key:
            return m
        prov = cfg.MODELS.get(m, {}).get("provider", "")
        if prov and openrouter_api_key and not (api_key or cfg.PROVIDER_API_KEYS.get(prov, "")):
            return model_key
        return m

    t0 = time.time()

    async def generate():
        loop = asyncio.get_running_loop()
        total_input = total_output = 0
        total_cost = 0.0

        def _default(obj):
            import datetime
            from decimal import Decimal
            if isinstance(obj, Decimal):
                return float(obj)
            if isinstance(obj, (datetime.datetime, datetime.date, datetime.time)):
                return str(obj)
            if isinstance(obj, bytes):
                return obj.decode("utf-8", errors="replace")
            return str(obj)

        def emit(event: dict) -> str:
            return f"data: {json.dumps(event, ensure_ascii=False, default=_default)}\n\n"

        try:
            yield emit({"type": "agent_start", "agent": "clarifier", "label": "理解问题"})
            clarifier_result = await loop.run_in_executor(
                None, multi_agent_module.run_clarifier,
                req.question, schema_text, history,
                _agent_key("clarifier"), api_key, openrouter_api_key,
            )
            total_input += clarifier_result["input_tokens"]
            total_output += clarifier_result["output_tokens"]
            total_cost += clarifier_result["cost_usd"]

            if not clarifier_result["is_clear"]:
                cq = clarifier_result["clarification_question"] or "请补充更多信息"
                mid = persistence.save_message(
                    conv_id=conv_id, question=req.question,
                    sql="", explanation=cq, confidence="low",
                    rows=[], db_error="",
                    cost_usd=total_cost, input_tokens=total_input,
                    output_tokens=total_output, retry_count=0,
                )
                all_msgs = persistence.get_messages(conv_id)
                if len(all_msgs) == 1:
                    persistence.update_conversation_title(conv_id, req.question[:30])
                persistence.update_user_usage(user["id"], total_input, total_output, total_cost, 0)
                yield emit({"type": "clarification_needed", "question": cq,
                            "message_id": mid, "input_tokens": total_input,
                            "output_tokens": total_output, "cost_usd": total_cost})
                return

            yield emit({"type": "agent_done", "agent": "clarifier",
                        "output": {"refined_question": clarifier_result["refined_question"],
                                   "approach": clarifier_result["analysis_approach"]}})

            refined_q = clarifier_result["refined_question"]
            sql_planner_key = _agent_key("sql_planner")

            yield emit({"type": "agent_start", "agent": "sql_planner", "label": "生成 SQL"})
            sql_result = await loop.run_in_executor(
                None, agent_module.run_sql_agent,
                refined_q, schema_text, engine,
                sql_planner_key, api_key, semantic, cfg.AGENT_MAX_STEPS, openrouter_api_key,
            )
            total_input += sql_result.total_input_tokens
            total_output += sql_result.total_output_tokens
            total_cost += sql_result.total_cost_usd

            for s in sql_result.steps:
                yield emit({"type": "sql_step", "step": s.step_num, "thought": s.thought,
                            "action": s.action, "observation": s.observation})

            yield emit({"type": "agent_done", "agent": "sql_planner",
                        "output": {"sql": sql_result.sql, "steps": len(sql_result.steps)}})

            yield emit({"type": "agent_start", "agent": "validator", "label": "验证结果"})
            validator_key = _agent_key("validator")
            retry_count = 0

            validator_result = await loop.run_in_executor(
                None, multi_agent_module.run_validator,
                req.question, sql_result.sql, sql_result.rows,
                validator_key, api_key, openrouter_api_key,
            )
            total_input += validator_result["input_tokens"]
            total_output += validator_result["output_tokens"]
            total_cost += validator_result["cost_usd"]

            for _attempt in range(2):
                if validator_result["confidence"] != "low" or not sql_result.sql:
                    break
                issues_text = "; ".join(validator_result["issues"]) or "结果异常"
                retry_q = f"{refined_q}\n[注意：上次查询发现问题：{issues_text}，请修正 SQL]"
                yield emit({"type": "sql_step", "step": 0,
                            "thought": f"验证发现问题：{issues_text}，触发重试",
                            "action": "retry_sql", "observation": ""})
                sql_result = await loop.run_in_executor(
                    None, agent_module.run_sql_agent,
                    retry_q, schema_text, engine,
                    sql_planner_key, api_key, semantic, cfg.AGENT_MAX_STEPS, openrouter_api_key,
                )
                total_input += sql_result.total_input_tokens
                total_output += sql_result.total_output_tokens
                total_cost += sql_result.total_cost_usd
                retry_count += 1
                validator_result = await loop.run_in_executor(
                    None, multi_agent_module.run_validator,
                    req.question, sql_result.sql, sql_result.rows,
                    validator_key, api_key, openrouter_api_key,
                )
                total_input += validator_result["input_tokens"]
                total_output += validator_result["output_tokens"]
                total_cost += validator_result["cost_usd"]

            yield emit({"type": "agent_done", "agent": "validator",
                        "output": {"confidence": validator_result["confidence"],
                                   "notes": validator_result["notes"]}})

            yield emit({"type": "agent_start", "agent": "presenter", "label": "整理洞察"})
            presenter_result = await loop.run_in_executor(
                None, multi_agent_module.run_presenter,
                req.question, sql_result.sql, sql_result.rows, validator_result["notes"],
                _agent_key("presenter"), api_key, openrouter_api_key,
            )
            total_input += presenter_result["input_tokens"]
            total_output += presenter_result["output_tokens"]
            total_cost += presenter_result["cost_usd"]

            yield emit({"type": "agent_done", "agent": "presenter",
                        "output": {"insight": presenter_result["insight"]}})

            final_rows = (sql_result.rows or [])[:cfg.MAX_RESULT_ROWS]
            query_time_ms = int((time.time() - t0) * 1000)
            mid = persistence.save_message(
                conv_id=conv_id, question=req.question,
                sql=sql_result.sql,
                explanation=clarifier_result["analysis_approach"] or sql_result.explanation,
                confidence=validator_result["confidence"],
                rows=final_rows, db_error=sql_result.error or "",
                cost_usd=total_cost, input_tokens=total_input,
                output_tokens=total_output, retry_count=retry_count,
            )
            all_msgs = persistence.get_messages(conv_id)
            if len(all_msgs) == 1:
                title = req.question[:30] + ("…" if len(req.question) > 30 else "")
                persistence.update_conversation_title(conv_id, title)
            persistence.update_user_usage(user["id"], total_input, total_output, total_cost, query_time_ms)

            yield emit({
                "type": "final", "message_id": mid,
                "sql": sql_result.sql, "rows": final_rows,
                "explanation": clarifier_result["analysis_approach"] or sql_result.explanation,
                "confidence": validator_result["confidence"],
                "error": sql_result.error or "",
                "insight": presenter_result["insight"],
                "suggested_followups": presenter_result["suggested_followups"],
                "input_tokens": total_input, "output_tokens": total_output,
                "cost_usd": total_cost, "query_time_ms": query_time_ms,
            })
        except Exception as _exc:
            yield emit({"type": "error", "message": str(_exc)})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
