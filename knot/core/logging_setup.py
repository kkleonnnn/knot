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
import inspect as _inspect
import json
import logging as _stdlib_logging
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


class _InterceptHandler(_stdlib_logging.Handler):
    """把 **stdlib `logging`** 的记录转发进 loguru（v0.9.19 C0'' —— 修一个既有的观测缺陷）。

    ⛔ **不接管会怎样**（实测，`KNOT_LOG_FORMAT=json` 即容器非 tty 的默认）：
        loguru → {"time":…, "level":"WARNING", "msg":"…", …}     ← 结构化，Kibana 可索引
        stdlib → 裸消息                                            ← **无 JSON、无 level 字段**
    因为本模块**从不配置 stdlib root**，那些记录落到 `logging.lastResort`。

    ⚠️ **它不是「日志格式不统一」这种整齐问题** —— 全仓有 **6 个模块 / ~19 处**用 stdlib
    （`adapters/http/executor` · `url_allowlist` · `agents/catalog_loaders` · `catalog` ·
    `query_helper` · `core/crypto/fernet`），其中包含**运维唯一观测口**那几条启动 WARN。
    ⚠️⚠️ 实证：`DEPLOY.md` 记录升级排练用 `docker logs … | grep -i warn` 认定
    「v0.9.7 的 allowlist WARN 真的响了」—— 而那条消息**原文无 "warn" 字样**、
    `lastResort` 又不加 level 前缀 ⇒ **那次验证复现不出来**。
    ⇒ **两条被当成「同形」的 WARN（stdlib 的与 loguru 的）其实不同形。**

    实现照 loguru 官方范式：找到对应 level、回溯到**真实调用点**的栈深度再转发。
    """

    def emit(self, record: _stdlib_logging.LogRecord) -> None:
        try:
            level = logger.level(record.levelname).name
        except ValueError:                       # stdlib 自定义等级 loguru 不认 ⇒ 用数值
            level = record.levelno
        # ⚠️ **depth 算法照 loguru 官方范式**（我的初版写错过）：从**本帧**起走，
        #    直到跳出 stdlib logging 自己的文件 —— 否则 `logger`/`func`/`line` 三个字段
        #    会指向 `logging.callHandlers` 这类内部帧，而不是**真实调用点**
        #    ⇒ 日志「有 level 了」但**指不出是谁打的** = 修了一半。
        frame, depth = _inspect.currentframe(), 0
        while frame and (depth == 0 or frame.f_code.co_filename == _stdlib_logging.__file__):
            frame = frame.f_back
            depth += 1
        # ⛔ **绝不把「活的异常对象」交给 loguru**（v0.9.19 —— 一条测抓出来的）：
        #    `exception=record.exc_info` 会让**任何** `diagnose=True` 的 sink 渲染出
        #    traceback 各帧的**局部变量值**。实证：`catalog_loaders` 那条带 `exc_info` 的兜底日志
        #    会把**整个 catalog（真实库表名）**打进日志。
        #    ⚠️ 在生产 sink 上设 `diagnose=False` **不够** —— 它只挡住我配的那几个 sink；
        #    只要对象还是活的，将来任何新 sink / 调试时临时加的 sink 都会再次泄漏。
        # ⇒ **改为把 traceback 渲染成纯文本并入消息** ⇒ 局部变量在结构上**不可能**被渲染出来。
        msg = record.getMessage()
        if record.exc_info:
            msg = f"{msg}\n{_stdlib_logging.Formatter().formatException(record.exc_info)}"
        logger.opt(depth=depth).log(level, msg)


# 仅初始化一次（避免 reload 时重复 sink）
if not getattr(logger, "_knot_configured", False):
    logger.remove()
    logger.configure(patcher=_patcher)

    # ⭐ v0.9.19 C0''：**先**接管 stdlib root —— 否则 6 个模块 / ~19 处 stdlib 日志
    # （含运维唯一观测口的那几条启动 WARN）在生产 JSON 模式下是**裸消息、无 level**。
    _stdlib_logging.basicConfig(handlers=[_InterceptHandler()], level=0, force=True)

    # ⛔ **`diagnose=False` 是安全要求，不是风格**（v0.9.19 C0''）：
    # loguru 默认 `diagnose=True` 会把 traceback **各帧的局部变量值**渲染进日志。
    # 实证：`catalog_loaders` 那条带 `exc_info` 的兜底日志，会把**整个 catalog**（真实库表名）
    # 打进日志 —— 由 `test_catalog_tenant_isolation::test_observability_never_logs_catalog_content` 抓到。
    # ⚠️ 这**不是本片引入的类**：`logger.exception` 今天已在 4 个文件里（含 `api/deps.py` 鉴权路径、
    # `api/query.py`）⇒ 那些路径的异常日志**今天就在 dump 局部变量**（口令 / token / 业务数据都可能在作用域里）。
    # 本片只是把 stdlib 那一批也接了进来，从而让这个既有暴露**被一条既有测抓住**。
    # ⇒ `backtrace` 保留（栈本身有价值、不含值），**`diagnose` 全部关掉**。
    if _is_json_mode():
        # JSON 模式（生产 / kibana）— 用 sink callable bypass loguru 模板
        logger.add(_json_stderr_sink, level=_LEVEL, diagnose=False)
        logger.add(_JsonFileSink(_LOG_DIR), level=_LEVEL, diagnose=False)
    else:
        # Text 模式（dev / 终端）— loguru 原生 format 模板
        logger.add(sys.stderr, level=_LEVEL, format=_TEXT_FMT, enqueue=False, diagnose=False)
        logger.add(
            str(_LOG_DIR / "knot_{time:YYYY-MM-DD}.log"),
            level=_LEVEL,
            format=_FILE_TEXT_FMT,
            diagnose=False,
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
