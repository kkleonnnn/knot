"""
main.py — KNOT FastAPI app factory
Run: uvicorn knot.main:app --reload --port 8000

v0.3.0：sys.path hack 已干掉；本包通过 `pip install -e .` 由解释器原生识别。
v0.5.0：包重命名 + env 双源（KNOT_MASTER_KEY 优先 + 旧名兼容）+ DB startup migration
"""

import mimetypes
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from knot.api import admin, auth, conversations, database, knowledge, query, uploads
from knot.api import audit as audit_router
from knot.api import catalog as catalog_router
from knot.api import exports as exports_router
from knot.api import few_shots as few_shots_router
from knot.api import prompts as prompts_router
from knot.api import saved_reports as saved_reports_router
from knot.api import templates as templates_router
from knot.core.logging_setup import logger, new_request_id, set_request_id
from knot.repositories import init_db
from knot.scripts.migrate_db_rename_v050 import migrate_db_rename

# 必须早于 StaticFiles 挂载；幂等 — 保留为模块级副作用
mimetypes.add_type("application/javascript", ".jsx")

app = FastAPI(title="KNOT", version="0.5.33")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# v0.5.0 R-69 / R-76：DB startup migration（bi_agent.db → knot.db）
# 在 init_db() 之前；幂等；atomic 异常保护内置
_DATA_DIR = Path(__file__).parent / "data"
_DATA_DIR.mkdir(parents=True, exist_ok=True)
migrate_db_rename(_DATA_DIR)
init_db()


# v0.4.5 R-45 / v0.5.0 R-68：master key fail-fast 在 init_db() 之后、所有路由注册之前。
# 缺失/格式错 → sys.exit(1) + 彩色边框错误（非 traceback，避免吓非技术运维）。
# 注意：必须在 module top-level 跑（不是 __main__），因为 uvicorn 走 import 加载。
def _check_master_key_or_exit():
    import sys

    from knot.core.crypto.fernet import (
        CryptoConfigError,
        assert_master_key_loaded,
        loaded_env_name,
    )
    try:
        assert_master_key_loaded()
        env_name = loaded_env_name() or "KNOT_MASTER_KEY"
        logger.info(f"{env_name} 已加载（Fernet）")
    except CryptoConfigError as e:
        bar = "━" * 60
        print(f"\033[1;31m{bar}", file=sys.stderr)
        print("✗ KNOT 启动失败 — 缺少加密主密钥", file=sys.stderr)
        print(f"  {e}", file=sys.stderr)
        print("", file=sys.stderr)
        print("  生成新密钥:", file=sys.stderr)
        print('    python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"', file=sys.stderr)
        print("", file=sys.stderr)
        print("  设置环境变量后重启（v0.5.0 起优先使用 KNOT_MASTER_KEY）:", file=sys.stderr)
        print("    export KNOT_MASTER_KEY=<生成的密钥>", file=sys.stderr)
        print("    （兼容旧名 BIAGENT_MASTER_KEY 至 v1.0；新部署请用 KNOT_MASTER_KEY）", file=sys.stderr)
        print(f"{bar}\033[0m", file=sys.stderr)
        sys.exit(1)


_check_master_key_or_exit()


@app.on_event("startup")
async def _bump_threadpool():
    """v0.4.4 R-29-anyio：LLM 全面异步化（AsyncAnthropic / AsyncOpenAI）后,
    threadpool 不再背 LLM 调用，只剩 sync SQLAlchemy 短查询 + 文件 IO。
    默认降至 32（v0.2.2 是 64，对应 sync LLM 时代）。
    可通过 ANYIO_TOKENS 环境变量覆写（高并发 SQLAlchemy 场景适当上调）。"""
    import os

    from anyio import to_thread
    tokens = int(os.getenv("ANYIO_TOKENS", "32"))
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
                catalog_router.router, exports_router.router, saved_reports_router.router,
                audit_router.router]:
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
