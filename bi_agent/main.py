"""
main.py — BI-Agent FastAPI app factory
Run: uvicorn bi_agent.main:app --reload --port 8000
"""

import sys
import mimetypes
from pathlib import Path

# Must happen before any core/ imports
sys.path.insert(0, str(Path(__file__).parent / "core"))
mimetypes.add_type("application/javascript", ".jsx")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

import persistence
from .dependencies import UPLOADS_DB
from .routers import auth, conversations, query, database, uploads, knowledge, admin, user
from .routers import few_shots as few_shots_router
from .routers import prompts as prompts_router
from .routers import templates as templates_router

app = FastAPI(title="BI-Agent", version="0.2.1")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

UPLOADS_DB.parent.mkdir(parents=True, exist_ok=True)
persistence.init_db()

for _router in [auth.router, conversations.router, query.router, database.router,
                uploads.router, knowledge.router, admin.router, user.router,
                few_shots_router.router, prompts_router.router, templates_router.router]:
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
