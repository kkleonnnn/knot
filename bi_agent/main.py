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

app = FastAPI(title="BI-Agent", version="0.1.1")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

UPLOADS_DB.parent.mkdir(parents=True, exist_ok=True)
persistence.init_db()

for _router in [auth.router, conversations.router, query.router, database.router,
                uploads.router, knowledge.router, admin.router, user.router]:
    app.include_router(_router)

_STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


@app.get("/{full_path:path}")
async def spa(full_path: str):
    return FileResponse(str(_STATIC_DIR / "index.html"))
