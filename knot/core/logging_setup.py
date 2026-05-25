"""
logging_setup.py — loguru 全局配置 + request_id 链路追踪 + 双格式输出

用法：
    from logging_setup import logger, bind_request_id
    logger.info("message")
    with bind_request_id(req_id):
        logger.info("inside request scope")  # 自动带上 request_id

日志写到 knot/data/logs/knot_{date}.log，rotate 每天，保留 7 天。
console 同时输出。

格式控制（v0.6.1.11 加 — Ann Tillis 运维需求）：
- env KNOT_LOG_FORMAT=auto (默认): isatty? text : json
  * 终端 (本地 dev / 直跑 uvicorn) → 彩色 text 格式
  * 非终端 (docker / systemd / pipe) → 一行一条 flat JSON（Kibana 直接索引）
- env KNOT_LOG_FORMAT=text: 强制彩色文本
- env KNOT_LOG_FORMAT=json: 强制 flat JSON
- env LOG_LEVEL=INFO|DEBUG|WARNING|ERROR (默认 INFO)
"""
import json
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
_FORMAT_MODE = os.getenv("KNOT_LOG_FORMAT", "auto").lower()

# request_id 上下文变量（异步安全，FastAPI 单请求 task 内可见）
_request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")


def _patcher(record):
    record["extra"].setdefault("request_id", _request_id_ctx.get())


def _is_json_mode() -> bool:
    """决定本次启动用 JSON 还是 text 格式。

    auto (默认): isatty 检测 — 终端 = text，docker / systemd / pipe = json
    text:        强制彩色文本
    json:        强制 JSON
    """
    if _FORMAT_MODE == "json":
        return True
    if _FORMAT_MODE == "text":
        return False
    # auto
    return not sys.stderr.isatty()


# Text 格式（dev / 终端友好）─────────────────────────────────────
_TEXT_FMT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> "
    "<level>{level: <7}</level> "
    "<cyan>req={extra[request_id]}</cyan> "
    "<magenta>{name}</magenta>:<magenta>{function}</magenta>:{line} - "
    "<level>{message}</level>"
)
_FILE_TEXT_FMT = (
    "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <7} | "
    "req={extra[request_id]} | {name}:{function}:{line} - {message}"
)


# JSON 格式（Kibana / Filebeat / Logstash 友好）─────────────────
# v0.6.1.11: 用 loguru 原生 sink callable（不能用 format callable — loguru
# format callable 仍走 .format_map() 模板路径，JSON 输出的 {key} 被当 placeholder 失败）


def _emit_json(message) -> str:
    """构造 flat JSON line（loguru sink callable 用）。"""
    record = message.record
    out = {
        "time": record["time"].isoformat(),
        "level": record["level"].name,
        "msg": record["message"],
        "logger": record["name"],
        "func": record["function"],
        "line": record["line"],
        "request_id": record["extra"].get("request_id", "-"),
    }
    if record["exception"]:
        ex = record["exception"]
        out["exception"] = {
            "type": ex.type.__name__ if ex.type else None,
            "value": str(ex.value) if ex.value else None,
        }
    return json.dumps(out, ensure_ascii=False) + "\n"


def _json_stderr_sink(message):
    sys.stderr.write(_emit_json(message))
    sys.stderr.flush()


class _JsonFileSink:
    """文件 sink — 按日期 rotate（手动实现，loguru native file rotation 不兼容 sink callable）"""
    def __init__(self, log_dir: Path):
        self._dir = log_dir
        self._current_date = None
        self._fp = None

    def __call__(self, message):
        from datetime import datetime
        today = datetime.now().strftime("%Y-%m-%d")
        if today != self._current_date:
            if self._fp:
                self._fp.close()
            self._fp = open(self._dir / f"knot_{today}.log", "a", encoding="utf-8")
            self._current_date = today
            # 简易 retention: 删 >7 天的旧 .log
            try:
                from time import time as _now
                cutoff = _now() - 7 * 86400
                for old in self._dir.glob("knot_*.log"):
                    if old.stat().st_mtime < cutoff:
                        old.unlink()
            except Exception:
                pass  # 清理失败不影响日志写入
        self._fp.write(_emit_json(message))
        self._fp.flush()


# 仅初始化一次（避免 reload 时重复 sink）
if not getattr(logger, "_knot_configured", False):
    logger.remove()
    logger.configure(patcher=_patcher)

    if _is_json_mode():
        # JSON 模式（生产 / kibana）— 用 sink callable bypass loguru 模板
        logger.add(_json_stderr_sink, level=_LEVEL)
        logger.add(_JsonFileSink(_LOG_DIR), level=_LEVEL)
    else:
        # Text 模式（dev / 终端）— loguru 原生 format 模板
        logger.add(sys.stderr, level=_LEVEL, format=_TEXT_FMT, enqueue=False)
        logger.add(
            str(_LOG_DIR / "knot_{time:YYYY-MM-DD}.log"),
            level=_LEVEL,
            format=_FILE_TEXT_FMT,
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
