"""knot/api/query.py — v0.5.2 后端瘦身：路由 + SSE 协议层 thin facade。

业务计算抽到 knot/services/query_steps.py（R-109：本文件保留 SSE generator 主控
结构 `for ... yield emit(...)`；query_steps 内 0 yield，纯业务步骤函数）。

源行号区间（v0.5.1 final 状态 457 行）：抽出 enrich_semantic / select_agent_key /
4 个 step 函数（clarifier/sql_planner/presenter/agent_sync）/ generate_sql + fix_sql 重试循环。
"""
import asyncio
import json
import time

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from knot import config as cfg
from knot.adapters.db import doris as db_connector
from knot.api.deps import get_current_user
from knot.api.schemas import QueryRequest
from knot.core.logging_setup import logger
from knot.models.errors import BIAgentError
from knot.repositories import conversation_repo, message_repo, settings_repo, upload_repo, user_repo
from knot.services import (
    budget_service,
    cost_service,
    error_translator,
    llm_client,  # noqa: F401  v0.5.2 R-100：test_api_smoke.py monkeypatch 兼容
    query_steps,
)
from knot.services.engine_cache import _upload_engine, get_user_engine

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


def _get_engine_and_schema(req: QueryRequest, user: dict):
    """共用 setup：返 (engine, schema_text) 或抛 HTTPException。"""
    if req.upload_id:
        rec = upload_repo.get_file_upload(req.upload_id)
        if not rec or rec["user_id"] != user["id"]:
            raise HTTPException(status_code=404, detail="上传文件不存在")
        return _upload_engine, db_connector.get_sqlite_schema_text(_upload_engine, rec["table_name"])
    engine, schema_text = get_user_engine(user)
    if engine is None:
        raise HTTPException(status_code=400, detail="数据库未配置或连接失败，请联系管理员")
    return engine, schema_text


def _resolve_keys_and_semantic(req: QueryRequest, user: dict, conv_id: int):
    """共用 setup：返 (api_key, openrouter_api_key, embedding_api_key, model_key, semantic, history)。"""
    api_key = req.api_key or user.get("api_key") or ""
    openrouter_api_key = settings_repo.get_app_setting("openrouter_api_key", "") or user.get("openrouter_api_key") or ""
    embedding_api_key = settings_repo.get_app_setting("embedding_api_key", "") or user.get("embedding_api_key") or ""
    model_key = _resolve_model(
        req.model_key or user.get("preferred_model") or cfg.DEFAULT_MODEL,
        user, api_key, openrouter_api_key,
    )
    semantic = query_steps.enrich_semantic(
        req.question, message_repo.get_semantic_layer(),
        api_key, openrouter_api_key, embedding_api_key,
    )
    history = [{"question": m["question"], "sql": m["sql_text"], "rows": (m.get("rows") or [])[:10]}
               for m in message_repo.get_messages(conv_id)[-3:]]
    return api_key, openrouter_api_key, model_key, semantic, history


def _check_conv_owner(conv_id: int, user_id: int) -> None:
    convs = conversation_repo.list_conversations(user_id)
    if not any(c["id"] == conv_id for c in convs):
        raise HTTPException(status_code=404)


@router.post("/api/conversations/{conv_id}/query")
async def query(conv_id: int, req: QueryRequest, user=Depends(get_current_user)):
    _check_conv_owner(conv_id, user["id"])
    engine, schema_text = _get_engine_and_schema(req, user)
    api_key, openrouter_api_key, model_key, semantic, history = _resolve_keys_and_semantic(req, user, conv_id)

    t0 = time.time()
    retry_count = 0
    agent_steps: list = []
    agent_buckets_ns = cost_service.empty_buckets()  # v0.4.2 R-S8 一致性入口

    if req.use_agent:
        result, agent_steps = query_steps.run_agent_step_sync(
            req.question, schema_text, engine, model_key, api_key, semantic,
            openrouter_api_key, agent_buckets_ns,
        )
        sql = result.sql
        rows = result.rows
        explanation = result.explanation
        confidence = result.confidence
        error = result.error if not result.success else ""
        input_tokens = result.total_input_tokens
        output_tokens = result.total_output_tokens
    else:
        ns = query_steps.run_generate_sql_with_fix_retry(
            req.question, schema_text, engine, model_key, api_key, semantic,
            history, openrouter_api_key, agent_buckets_ns,
        )
        sql, explanation, confidence, error = ns["sql"], ns["explanation"], ns["confidence"], ns["error"]
        rows = ns["rows"]
        input_tokens, output_tokens = ns["input_tokens"], ns["output_tokens"]
        retry_count = ns["retry_count"]

    query_time_ms = int((time.time() - t0) * 1000)
    cost_usd, _agg_tokens = cost_service.aggregate_agent_costs(agent_buckets_ns)

    mid = message_repo.save_message(
        conv_id=conv_id, question=req.question, sql=sql,
        explanation=explanation, confidence=confidence,
        rows=rows[:cfg.MAX_RESULT_ROWS], db_error=error,
        cost_usd=cost_usd, input_tokens=input_tokens, output_tokens=output_tokens,
        retry_count=retry_count, intent=None, agent_kind="sql_planner",
        recovery_attempt=retry_count,  # 非流式：fix_sql retry 等同 recovery_attempt
        **cost_service.to_save_message_kwargs(agent_buckets_ns),
    )

    all_msgs = message_repo.get_messages(conv_id)
    if len(all_msgs) == 1:
        title = req.question[:30] + ("…" if len(req.question) > 30 else "")
        conversation_repo.update_conversation_title(conv_id, title)

    user_repo.update_user_usage(user["id"], input_tokens, output_tokens, cost_usd, query_time_ms)
    # v0.4.3 R-22 一致性：非流式路径也必须返 budget_status / budget_meta
    budget_status_ns, budget_meta_ns = budget_service.check_user_monthly_budget(user["id"])

    return {
        "id": mid, "question": req.question, "sql": sql,
        "explanation": explanation, "confidence": confidence,
        "rows": rows[:cfg.MAX_RESULT_ROWS], "error": error,
        "input_tokens": input_tokens, "output_tokens": output_tokens,
        "cost_usd": cost_usd, "retry_count": retry_count,
        "query_time_ms": query_time_ms, "agent_steps": agent_steps,
        "agent_costs": cost_service.to_sse_payload(agent_buckets_ns),
        "recovery_attempt": retry_count,
        "budget_status": budget_status_ns, "budget_meta": budget_meta_ns,
        # v0.4.4 R-33：错误字段在成功路径全 None（保流式 vs 非流式字段集 diff = ∅）
        "error_kind": None, "user_message": None, "is_retryable": None, "intent": None,
    }


@router.post("/api/conversations/{conv_id}/query-stream")
async def query_stream(conv_id: int, req: QueryRequest, user=Depends(get_current_user)):
    _check_conv_owner(conv_id, user["id"])
    engine, schema_text = _get_engine_and_schema(req, user)
    api_key, openrouter_api_key, model_key, semantic, history = _resolve_keys_and_semantic(req, user, conv_id)

    user_agent_cfg = settings_repo.get_agent_model_config()
    t0 = time.time()
    logger.info(f"query-stream conv={conv_id} user={user['id']} model={model_key} q={req.question[:80]!r}")

    async def generate():
        # R-109 SSE 主控保留：本 generator 内 yield emit + asyncio.sleep；
        # 业务计算 delegate query_steps（R-S8 单一一致性入口分桶；v0.4.4 R-24 真异步）
        agent_buckets = cost_service.empty_buckets()

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
            await asyncio.sleep(0)  # R-26-SSE：让 event loop 推送给前端
            clarifier_result = await query_steps.run_clarifier_step(
                req.question, schema_text, history,
                query_steps.select_agent_key("clarifier", user_agent_cfg, model_key, api_key, openrouter_api_key),
                api_key, openrouter_api_key, agent_buckets,
            )

            if not clarifier_result["is_clear"]:
                cq = clarifier_result["clarification_question"] or "请补充更多信息"
                total_cost_clar, _tok_clar = cost_service.aggregate_agent_costs(agent_buckets)
                mid = message_repo.save_message(
                    conv_id=conv_id, question=req.question, sql="", explanation=cq,
                    confidence="low", rows=[], db_error="",
                    cost_usd=total_cost_clar,
                    input_tokens=clarifier_result["input_tokens"],
                    output_tokens=clarifier_result["output_tokens"],
                    retry_count=0, intent=clarifier_result.get("intent"),
                    agent_kind="clarifier",
                    **cost_service.to_save_message_kwargs(agent_buckets),
                )
                if len(message_repo.get_messages(conv_id)) == 1:
                    conversation_repo.update_conversation_title(conv_id, req.question[:30])
                user_repo.update_user_usage(
                    user["id"], clarifier_result["input_tokens"],
                    clarifier_result["output_tokens"], total_cost_clar, 0,
                )
                yield emit({"type": "clarification_needed", "question": cq,
                            "message_id": mid,
                            "input_tokens": clarifier_result["input_tokens"],
                            "output_tokens": clarifier_result["output_tokens"],
                            "cost_usd": total_cost_clar,
                            "agent_costs": cost_service.to_sse_payload(agent_buckets),
                            "intent": clarifier_result.get("intent")})
                await asyncio.sleep(0)
                return

            logger.info(f"clarifier done refined={clarifier_result['refined_question'][:80]!r} "
                        f"intent={clarifier_result.get('intent')!r}")
            yield emit({"type": "agent_done", "agent": "clarifier",
                        "output": {"refined_question": clarifier_result["refined_question"],
                                   "approach": clarifier_result["analysis_approach"],
                                   "intent": clarifier_result.get("intent")}})
            await asyncio.sleep(0)

            yield emit({"type": "agent_start", "agent": "sql_planner", "label": "生成 SQL"})
            await asyncio.sleep(0)
            sql_result, recovery_attempt = await query_steps.run_sql_planner_step(
                clarifier_result["refined_question"], schema_text, engine,
                query_steps.select_agent_key("sql_planner", user_agent_cfg, model_key, api_key, openrouter_api_key),
                api_key, semantic, openrouter_api_key, agent_buckets,
            )

            for s in sql_result.steps:
                yield emit({"type": "sql_step", "step": s.step_num, "thought": s.thought,
                            "action": s.action, "observation": s.observation})
                await asyncio.sleep(0)  # R-26-SSE 每步让步

            logger.info(f"sql_planner done steps={len(sql_result.steps)} ok={sql_result.success} "
                        f"sql={sql_result.sql[:120]!r}")
            yield emit({"type": "agent_done", "agent": "sql_planner",
                        "output": {"sql": sql_result.sql, "steps": len(sql_result.steps)}})
            await asyncio.sleep(0)

            yield emit({"type": "agent_start", "agent": "presenter", "label": "整理洞察"})
            await asyncio.sleep(0)
            presenter_result = await query_steps.run_presenter_step(
                req.question, sql_result.sql, sql_result.rows,
                query_steps.select_agent_key("presenter", user_agent_cfg, model_key, api_key, openrouter_api_key),
                api_key, openrouter_api_key, agent_buckets,
            )
            confidence = presenter_result.get("confidence", "high")

            final_rows = (sql_result.rows or [])[:cfg.MAX_RESULT_ROWS]
            query_time_ms = int((time.time() - t0) * 1000)
            intent = clarifier_result.get("intent")
            total_cost, _total_tokens = cost_service.aggregate_agent_costs(agent_buckets)
            total_input = (clarifier_result["input_tokens"] + sql_result.total_input_tokens
                           + presenter_result["input_tokens"])
            total_output = (clarifier_result["output_tokens"] + sql_result.total_output_tokens
                            + presenter_result["output_tokens"])
            logger.info(f"presenter done confidence={confidence} cost_usd={total_cost:.4f} "
                        f"recovery_attempt={recovery_attempt}")
            yield emit({"type": "agent_done", "agent": "presenter",
                        "output": {"insight": presenter_result["insight"], "confidence": confidence}})
            mid = message_repo.save_message(
                conv_id=conv_id, question=req.question, sql=sql_result.sql,
                explanation=clarifier_result["analysis_approach"] or sql_result.explanation,
                confidence=confidence, rows=final_rows, db_error=sql_result.error or "",
                cost_usd=total_cost, input_tokens=total_input, output_tokens=total_output,
                retry_count=0, intent=intent, agent_kind="sql_planner",
                recovery_attempt=recovery_attempt,
                **cost_service.to_save_message_kwargs(agent_buckets),
            )
            if len(message_repo.get_messages(conv_id)) == 1:
                title = req.question[:30] + ("…" if len(req.question) > 30 else "")
                conversation_repo.update_conversation_title(conv_id, title)
            user_repo.update_user_usage(user["id"], total_input, total_output, total_cost, query_time_ms)
            budget_status, budget_meta = budget_service.check_user_monthly_budget(user["id"])

            yield emit({
                "type": "final", "message_id": mid,
                "sql": sql_result.sql, "rows": final_rows,
                "explanation": clarifier_result["analysis_approach"] or sql_result.explanation,
                "confidence": confidence, "error": sql_result.error or "",
                "insight": presenter_result["insight"],
                "suggested_followups": presenter_result["suggested_followups"],
                "input_tokens": total_input, "output_tokens": total_output,
                "cost_usd": total_cost, "query_time_ms": query_time_ms, "intent": intent,
                "agent_costs": cost_service.to_sse_payload(agent_buckets),
                "recovery_attempt": recovery_attempt,
                "budget_status": budget_status, "budget_meta": budget_meta,
                # v0.4.4 R-30/33：成功路径错误字段全 None（双路径字段集 diff = ∅）
                "error_kind": None, "user_message": None, "is_retryable": None,
            })
            await asyncio.sleep(0)
        except BIAgentError as e:
            logger.warning(f"query-stream BIAgentError: {type(e).__name__}: {str(e)[:200]}")
            yield emit({"type": "error", **error_translator.to_response(e)})
        except Exception as _exc:
            logger.exception(f"query-stream pipeline failed: {_exc}")
            yield emit({"type": "error", **error_translator.to_response_unknown(_exc)})

    return StreamingResponse(
        generate(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
