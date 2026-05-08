import asyncio
import json
import time

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from bi_agent import config as cfg

# v0.3.0: import persistence → 直接 import 各 repo（保留"persistence.X"调用形态）
from bi_agent.adapters.db import doris as db_connector
from bi_agent.api.deps import get_current_user
from bi_agent.api.schemas import QueryRequest
from bi_agent.core.logging_setup import logger
from bi_agent.models.errors import BIAgentError
from bi_agent.repositories import conversation_repo, message_repo, settings_repo, upload_repo, user_repo
from bi_agent.services import budget_service, cost_service, error_translator, llm_client
from bi_agent.services import rag_service as doc_rag
from bi_agent.services.engine_cache import _upload_engine, get_user_engine
from bi_agent.services.knot import orchestrator as multi_agent_module
from bi_agent.services.knot import sql_planner as agent_module

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
    convs = conversation_repo.list_conversations(user["id"])
    if not any(c["id"] == conv_id for c in convs):
        raise HTTPException(status_code=404)

    if req.upload_id:
        rec = upload_repo.get_file_upload(req.upload_id)
        if not rec or rec["user_id"] != user["id"]:
            raise HTTPException(status_code=404, detail="上传文件不存在")
        engine = _upload_engine
        schema_text = db_connector.get_sqlite_schema_text(engine, rec["table_name"])
    else:
        engine, schema_text = get_user_engine(user)
        if engine is None:
            raise HTTPException(status_code=400, detail="数据库未配置或连接失败，请联系管理员")

    api_key = req.api_key or user.get("api_key") or ""
    openrouter_api_key = settings_repo.get_app_setting("openrouter_api_key", "") or user.get("openrouter_api_key") or ""
    embedding_api_key = settings_repo.get_app_setting("embedding_api_key", "") or user.get("embedding_api_key") or ""
    model_key = _resolve_model(
        req.model_key or user.get("preferred_model") or cfg.DEFAULT_MODEL,
        user, api_key, openrouter_api_key,
    )

    semantic = _enrich_semantic(
        req.question, message_repo.get_semantic_layer(),
        api_key, openrouter_api_key, embedding_api_key,
    )
    history = [{"question": m["question"], "sql": m["sql_text"], "rows": (m.get("rows") or [])[:10]}
               for m in message_repo.get_messages(conv_id)[-3:]]

    t0 = time.time()
    retry_count = 0
    agent_steps = []
    # v0.4.2: 非流式路径成本分桶（fix_sql 单独累加，与 sql_planner 分离）
    agent_buckets_ns = cost_service.empty_buckets()

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
        cost_service.add_agent_cost(
            agent_buckets_ns, "sql_planner",
            result.total_cost_usd, result.total_input_tokens, result.total_output_tokens,
        )
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
        cost_service.add_agent_cost(
            agent_buckets_ns, "sql_planner",
            gen["cost_usd"], gen["input_tokens"], gen["output_tokens"],
        )
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
                    # fix_sql 单独桶（资深 Stage 4 拍板：独立 agent_kind）
                    cost_service.add_agent_cost(
                        agent_buckets_ns, "fix_sql",
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

    query_time_ms = int((time.time() - t0) * 1000)
    # v0.4.2 R-S8 一致性入口
    cost_usd, _agg_tokens = cost_service.aggregate_agent_costs(agent_buckets_ns)

    mid = message_repo.save_message(
        conv_id=conv_id, question=req.question, sql=sql,
        explanation=explanation, confidence=confidence,
        rows=rows[:cfg.MAX_RESULT_ROWS], db_error=error,
        cost_usd=cost_usd, input_tokens=input_tokens,
        output_tokens=output_tokens, retry_count=retry_count,
        intent=None,
        agent_kind="sql_planner",
        recovery_attempt=retry_count,  # 非流式：fix_sql retry 等同 recovery_attempt
        **cost_service.to_save_message_kwargs(agent_buckets_ns),
    )

    all_msgs = message_repo.get_messages(conv_id)
    if len(all_msgs) == 1:
        title = req.question[:30] + ("…" if len(req.question) > 30 else "")
        conversation_repo.update_conversation_title(conv_id, title)

    user_repo.update_user_usage(user["id"], input_tokens, output_tokens, cost_usd, query_time_ms)

    # v0.4.3 R-22 一致性：非流式路径也必须返 budget_status / budget_meta
    # （update_user_usage 已落库；budget_service 读 user_repo 缓存即时一致）
    budget_status_ns, budget_meta_ns = budget_service.check_user_monthly_budget(user["id"])

    return {
        "id": mid, "question": req.question, "sql": sql,
        "explanation": explanation, "confidence": confidence,
        "rows": rows[:cfg.MAX_RESULT_ROWS], "error": error,
        "input_tokens": input_tokens, "output_tokens": output_tokens,
        "cost_usd": cost_usd, "retry_count": retry_count,
        "query_time_ms": query_time_ms, "agent_steps": agent_steps,
        # v0.4.2 新增（向前展开；旧 client 自动忽略）
        "agent_costs": cost_service.to_sse_payload(agent_buckets_ns),
        "recovery_attempt": retry_count,
        # v0.4.3 R-22：双路径同字段
        "budget_status": budget_status_ns,
        "budget_meta": budget_meta_ns,
        # v0.4.4 R-33：错误字段在成功路径全 None（保流式 vs 非流式字段集 diff = ∅）
        "error_kind": None,
        "user_message": None,
        "is_retryable": None,
        "intent": None,
    }


@router.post("/api/conversations/{conv_id}/query-stream")
async def query_stream(conv_id: int, req: QueryRequest, user=Depends(get_current_user)):
    convs = conversation_repo.list_conversations(user["id"])
    if not any(c["id"] == conv_id for c in convs):
        raise HTTPException(status_code=404)

    if req.upload_id:
        rec = upload_repo.get_file_upload(req.upload_id)
        if not rec or rec["user_id"] != user["id"]:
            raise HTTPException(status_code=404, detail="上传文件不存在")
        engine = _upload_engine
        schema_text = db_connector.get_sqlite_schema_text(engine, rec["table_name"])
    else:
        engine, schema_text = get_user_engine(user)
        if engine is None:
            raise HTTPException(status_code=400, detail="数据库未配置或连接失败，请联系管理员")

    api_key = req.api_key or user.get("api_key") or ""
    openrouter_api_key = settings_repo.get_app_setting("openrouter_api_key", "") or user.get("openrouter_api_key") or ""
    embedding_api_key = settings_repo.get_app_setting("embedding_api_key", "") or user.get("embedding_api_key") or ""
    model_key = _resolve_model(
        req.model_key or user.get("preferred_model") or cfg.DEFAULT_MODEL,
        user, api_key, openrouter_api_key,
    )

    semantic = _enrich_semantic(
        req.question, message_repo.get_semantic_layer(),
        api_key, openrouter_api_key, embedding_api_key,
    )
    history = [{"question": m["question"], "sql": m["sql_text"], "rows": (m.get("rows") or [])[:10]}
               for m in message_repo.get_messages(conv_id)[-3:]]

    user_agent_cfg = settings_repo.get_agent_model_config()

    def _agent_key(role: str) -> str:
        m = user_agent_cfg.get(role) or model_key
        if "/" in m or m == model_key:
            return m
        prov = cfg.MODELS.get(m, {}).get("provider", "")
        if prov and openrouter_api_key and not (api_key or cfg.PROVIDER_API_KEYS.get(prov, "")):
            return model_key
        return m

    t0 = time.time()

    logger.info(f"query-stream conv={conv_id} user={user['id']} model={model_key} q={req.question[:80]!r}")

    async def generate():
        # v0.4.2: 成本归因分桶（R-S8 单一一致性入口）
        # v0.4.4 R-24：流式路径切真异步（不再 run_in_executor）
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
            await asyncio.sleep(0)  # R-26-SSE：让 event loop 推送 agent_start 给前端
            # v0.4.4 R-24：直 await（不再 run_in_executor）
            clarifier_result = await multi_agent_module.arun_clarifier(
                req.question, schema_text, history,
                _agent_key("clarifier"), api_key, openrouter_api_key,
            )
            cost_service.add_agent_cost(
                agent_buckets, "clarifier",
                clarifier_result["cost_usd"],
                clarifier_result["input_tokens"], clarifier_result["output_tokens"],
            )

            if not clarifier_result["is_clear"]:
                cq = clarifier_result["clarification_question"] or "请补充更多信息"
                # 仅 clarifier 跑过 → agent_kind='clarifier'
                total_cost_clar, total_tok_clar = cost_service.aggregate_agent_costs(agent_buckets)
                mid = message_repo.save_message(
                    conv_id=conv_id, question=req.question,
                    sql="", explanation=cq, confidence="low",
                    rows=[], db_error="",
                    cost_usd=total_cost_clar,
                    input_tokens=clarifier_result["input_tokens"],
                    output_tokens=clarifier_result["output_tokens"],
                    retry_count=0,
                    intent=clarifier_result.get("intent"),
                    agent_kind="clarifier",
                    **cost_service.to_save_message_kwargs(agent_buckets),
                )
                all_msgs = message_repo.get_messages(conv_id)
                if len(all_msgs) == 1:
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
                await asyncio.sleep(0)  # R-26-SSE
                return

            logger.info(
                f"clarifier done refined={clarifier_result['refined_question'][:80]!r} "
                f"intent={clarifier_result.get('intent')!r}"
            )
            yield emit({"type": "agent_done", "agent": "clarifier",
                        "output": {"refined_question": clarifier_result["refined_question"],
                                   "approach": clarifier_result["analysis_approach"],
                                   "intent": clarifier_result.get("intent")}})
            await asyncio.sleep(0)  # R-26-SSE

            refined_q = clarifier_result["refined_question"]
            sql_planner_key = _agent_key("sql_planner")

            yield emit({"type": "agent_start", "agent": "sql_planner", "label": "生成 SQL"})
            await asyncio.sleep(0)  # R-26-SSE
            # v0.4.4 R-24：直 await
            sql_result = await agent_module.arun_sql_agent(
                refined_q, schema_text, engine,
                sql_planner_key, api_key, semantic, cfg.AGENT_MAX_STEPS, openrouter_api_key,
            )
            cost_service.add_agent_cost(
                agent_buckets, "sql_planner",
                sql_result.total_cost_usd,
                sql_result.total_input_tokens, sql_result.total_output_tokens,
            )
            # v0.4.2 R-14：recovery_attempt 含 fan-out reject 计数（v0.4.1.1 守护重试）
            recovery_attempt = sum(
                1 for s in sql_result.steps
                if "Fan-Out 反模式" in (s.observation or "") or "fan-out" in (s.observation or "").lower()
            )

            for s in sql_result.steps:
                yield emit({"type": "sql_step", "step": s.step_num, "thought": s.thought,
                            "action": s.action, "observation": s.observation})
                await asyncio.sleep(0)  # R-26-SSE 每步让步

            logger.info(f"sql_planner done steps={len(sql_result.steps)} ok={sql_result.success} sql={sql_result.sql[:120]!r}")
            yield emit({"type": "agent_done", "agent": "sql_planner",
                        "output": {"sql": sql_result.sql, "steps": len(sql_result.steps)}})
            await asyncio.sleep(0)  # R-26-SSE

            # v0.2.2: Validator removed; Presenter does inline anomaly check
            retry_count = 0

            yield emit({"type": "agent_start", "agent": "presenter", "label": "整理洞察"})
            await asyncio.sleep(0)
            # v0.4.4 R-24：直 await
            presenter_result = await multi_agent_module.arun_presenter(
                req.question, sql_result.sql, sql_result.rows,
                _agent_key("presenter"), api_key, openrouter_api_key,
            )
            cost_service.add_agent_cost(
                agent_buckets, "presenter",
                presenter_result["cost_usd"],
                presenter_result["input_tokens"], presenter_result["output_tokens"],
            )
            confidence = presenter_result.get("confidence", "high")

            final_rows = (sql_result.rows or [])[:cfg.MAX_RESULT_ROWS]
            query_time_ms = int((time.time() - t0) * 1000)
            intent = clarifier_result.get("intent")
            # v0.4.2 R-S8 一致性入口：唯一加和点
            total_cost, total_tokens = cost_service.aggregate_agent_costs(agent_buckets)
            total_input = (clarifier_result["input_tokens"] + sql_result.total_input_tokens
                           + presenter_result["input_tokens"])
            total_output = (clarifier_result["output_tokens"] + sql_result.total_output_tokens
                            + presenter_result["output_tokens"])
            logger.info(
                f"presenter done confidence={confidence} cost_usd={total_cost:.4f} "
                f"recovery_attempt={recovery_attempt}"
            )
            yield emit({"type": "agent_done", "agent": "presenter",
                        "output": {"insight": presenter_result["insight"],
                                   "confidence": confidence}})
            mid = message_repo.save_message(
                conv_id=conv_id, question=req.question,
                sql=sql_result.sql,
                explanation=clarifier_result["analysis_approach"] or sql_result.explanation,
                confidence=confidence,
                rows=final_rows, db_error=sql_result.error or "",
                cost_usd=total_cost, input_tokens=total_input,
                output_tokens=total_output, retry_count=retry_count,
                intent=intent,
                agent_kind="sql_planner",  # 主路径完成，记 sql_planner（fix_sql 桶在 cost 字段中体现）
                recovery_attempt=recovery_attempt,
                **cost_service.to_save_message_kwargs(agent_buckets),
            )
            all_msgs = message_repo.get_messages(conv_id)
            if len(all_msgs) == 1:
                title = req.question[:30] + ("…" if len(req.question) > 30 else "")
                conversation_repo.update_conversation_title(conv_id, title)
            user_repo.update_user_usage(user["id"], total_input, total_output, total_cost, query_time_ms)

            # v0.4.3 R-22：流式路径与非流式同款字段（user_repo 已 update，budget 检查实时一致）
            budget_status, budget_meta = budget_service.check_user_monthly_budget(user["id"])

            yield emit({
                "type": "final", "message_id": mid,
                "sql": sql_result.sql, "rows": final_rows,
                "explanation": clarifier_result["analysis_approach"] or sql_result.explanation,
                "confidence": confidence,
                "error": sql_result.error or "",
                "insight": presenter_result["insight"],
                "suggested_followups": presenter_result["suggested_followups"],
                "input_tokens": total_input, "output_tokens": total_output,
                "cost_usd": total_cost, "query_time_ms": query_time_ms,
                "intent": intent,
                # v0.4.2 新增：分桶 + recovery（向前展开，旧 client 自动忽略）
                "agent_costs": cost_service.to_sse_payload(agent_buckets),
                "recovery_attempt": recovery_attempt,
                # v0.4.3 R-22：budget 状态（流式 + 非流式双路径同字段）
                "budget_status": budget_status,
                "budget_meta": budget_meta,
                # v0.4.4 R-30 / R-33：错误字段（成功路径全 None；保字段集 diff = ∅）
                "error_kind": None,
                "user_message": None,
                "is_retryable": None,
            })
            await asyncio.sleep(0)  # R-26-SSE 末尾让步
        except BIAgentError as e:
            # R-30：领域异常 → error_translator 翻译为用户友好提示
            logger.warning(f"query-stream BIAgentError: {type(e).__name__}: {str(e)[:200]}")
            payload = error_translator.to_response(e)
            yield emit({"type": "error", **payload})
        except Exception as _exc:
            logger.exception(f"query-stream pipeline failed: {_exc}")
            payload = error_translator.to_response_unknown(_exc)
            yield emit({"type": "error", **payload})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
