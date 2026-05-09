"""
logging_setup.py — loguru 全局配置 + request_id 链路追踪

用法：
    from logging_setup import logger, bind_request_id
    logger.info("message")
    with bind_request_id(req_id):
        logger.info("inside request scope")  # 自动带上 request_id

日志写到 knot/data/logs/knot_{date}.log，rotate 每天，保留 7 天。
console 同时输出（彩色），生产可通过 LOG_LEVEL 调高到 INFO/WARNING。
"""
import os
import sys
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

from loguru import logger

_LOG_DIR = Path(__file__).resolve().parent.parent / "data" / "logs"
_LOG_DIR.mkdir(parents=True, exist_ok=True)

_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# request_id 上下文变量（异步安全，FastAPI 单请求 task 内可见）
_request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")


def _patcher(record):
    record["extra"].setdefault("request_id", _request_id_ctx.get())


_FMT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> "
    "<level>{level: <7}</level> "
    "<cyan>req={extra[request_id]}</cyan> "
    "<magenta>{name}</magenta>:<magenta>{function}</magenta>:{line} - "
    "<level>{message}</level>"
)

_FILE_FMT = (
    "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <7} | "
    "req={extra[request_id]} | {name}:{function}:{line} - {message}"
)

# 仅初始化一次（避免 reload 时重复 sink）
if not getattr(logger, "_knot_configured", False):
    logger.remove()
    logger.configure(patcher=_patcher)
    logger.add(sys.stderr, level=_LEVEL, format=_FMT, enqueue=False)
    logger.add(
        str(_LOG_DIR / "knot_{time:YYYY-MM-DD}.log"),
        level=_LEVEL,
        format=_FILE_FMT,
        rotation="00:00",
        retention="7 days",
        encoding="utf-8",
        enqueue=True,
    )
    logger._knot_configured = True


def new_request_id() -> str:
    return uuid.uuid4().hex[:12]


@contextmanager
def bind_request_id(req_id: str):
    """在 with 块内把 request_id 绑到 logger 上下文。"""
    token = _request_id_ctx.set(req_id)
    try:
        yield req_id
    finally:
        _request_id_ctx.reset(token)


def set_request_id(req_id: str):
    """直接 set（不返回 context manager），适合中间件使用。"""
    _request_id_ctx.set(req_id)


__all__ = ["logger", "bind_request_id", "set_request_id", "new_request_id"]
