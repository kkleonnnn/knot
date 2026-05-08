"""
main.py — BI-Agent FastAPI app factory
Run: uvicorn bi_agent.main:app --reload --port 8000

v0.3.0：sys.path hack 已干掉；本包通过 `pip install -e .` 由解释器原生识别。
"""

import mimetypes
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from bi_agent.api import admin, auth, conversations, database, knowledge, query, uploads
from bi_agent.api import catalog as catalog_router
from bi_agent.api import exports as exports_router
from bi_agent.api import few_shots as few_shots_router
from bi_agent.api import prompts as prompts_router
from bi_agent.api import saved_reports as saved_reports_router
from bi_agent.api import templates as templates_router
from bi_agent.core.logging_setup import logger, new_request_id, set_request_id
from bi_agent.repositories import init_db

# 必须早于 StaticFiles 挂载；幂等 — 保留为模块级副作用
mimetypes.add_type("application/javascript", ".jsx")

app = FastAPI(title="BI-Agent", version="0.4.1.1")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

(Path(__file__).parent / "data").mkdir(parents=True, exist_ok=True)
init_db()


@app.on_event("startup")
async def _bump_threadpool():
    """v0.2.2: 把 anyio 默认线程池 token 数从 40 提到 ANYIO_TOKENS（默认 64）。
    所有 LLM 调用走 run_in_executor（同步 SDK），并发受这里限制。
    全异步化（httpx.AsyncClient + AsyncOpenAI/AsyncAnthropic）放下个 MINOR。"""
    import os

    from anyio import to_thread
    tokens = int(os.getenv("ANYIO_TOKENS", "64"))
    to_thread.current_default_thread_limiter().total_tokens = tokens
    logger.info(f"anyio threadpool tokens = {tokens}")


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    """每个请求绑一个 request_id，串起 agent 链路日志。
    支持上游传 X-Request-ID 透传；否则随机生成。"""
    req_id = request.headers.get("x-request-id") or new_request_id()
    set_request_id(req_id)
    logger.info(f"→ {request.method} {request.url.path}")
    try:
        response = await call_next(request)
    except Exception as exc:
        logger.exception(f"✗ {request.method} {request.url.path} unhandled: {exc}")
        raise
    response.headers["X-Request-ID"] = req_id
    logger.info(f"← {request.method} {request.url.path} {response.status_code}")
    return response

for _router in [auth.router, conversations.router, query.router, database.router,
                uploads.router, knowledge.router, admin.router,
                few_shots_router.router, prompts_router.router, templates_router.router,
                catalog_router.router, exports_router.router, saved_reports_router.router]:
    app.include_router(_router)

_STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")
# v0.2.0 Vite build 将资源输出到 /assets/*；此路径未挂载会被 SPA catch-all 兜回 index.html
app.mount("/assets", StaticFiles(directory=str(_STATIC_DIR / "assets")), name="assets")


@app.get("/{full_path:path}")
async def spa(full_path: str):
    # 真实文件直接返回（favicon.svg、icons.svg 等顶层资源），其他路径走 SPA fallback
    candidate = _STATIC_DIR / full_path
    if candidate.is_file():
        return FileResponse(str(candidate))
    return FileResponse(str(_STATIC_DIR / "index.html"))
