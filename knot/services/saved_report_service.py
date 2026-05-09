"""saved_report_service — v0.4.1 收藏报表业务编排。

职责（手册 §3 / §4）：
- snapshot：从 message 创建 saved_report，物化 intent / display_hint / sql / rows
- 软限制：last_run_rows_json 截到 200 行（R-3 防御性）
- R-S6 兜底：老消息 intent=None → fallback 'detail'
- R-S5：title 默认值 sanitize（empty / >30 字 / None）
- R-12 幂等：UNIQUE 冲突回查既存对象返回
- R-S2：重跑优先用 pin 时的 data_source；失效时 fallback + warning

不做：
- LLM 调用（冻结 SQL，不重新生成）
- 日期占位符替换（资深 Stage 2 严禁）
- 跨用户访问（权限校验在调用方 / api 层）
"""
from __future__ import annotations

import json
import time
from datetime import datetime

from knot.adapters.db import doris as db_connector
from knot.repositories import data_source_repo, saved_report_repo
from knot.services import engine_cache
from knot.services.agents.orchestrator import INTENT_TO_HINT

_LAST_RUN_ROW_LIMIT = 200  # R-3 软限制


# ── snapshot / 创建 ───────────────────────────────────────────────────────────

def create_from_message(
    user: dict,
    msg: dict,
    title: str | None = None,
    pin_note: str | None = None,
) -> tuple[dict, bool]:
    """从 message 创建 saved_report。返回 (saved_report, already_existed)。

    R-12 幂等：如果该 user 已有该 message_id 的 pin，不创建新行，回查既存返回
    already_existed=True。
    """
    existing = saved_report_repo.get_by_unique(user["id"], msg["id"])
    if existing:
        return existing, True

    intent = msg.get("intent") or "detail"                          # R-S6 老消息兜底
    hint = INTENT_TO_HINT.get(intent, "detail_table")
    rows = msg.get("rows") or []
    truncated = len(rows) > _LAST_RUN_ROW_LIMIT
    rows_snap = rows[:_LAST_RUN_ROW_LIMIT] if truncated else rows
    rows_json = json.dumps(rows_snap, ensure_ascii=False, default=str)

    final_title = _default_title(title or msg.get("question"))      # R-S5
    data_source_id = _resolve_pin_data_source(user)

    rid = saved_report_repo.create(
        user_id=user["id"],
        source_message_id=msg["id"],
        data_source_id=data_source_id,
        title=final_title,
        question=msg.get("question"),
        sql_text=msg.get("sql_text") or "",
        intent=intent,
        display_hint=hint,
        pin_note=pin_note,
        last_run_at=msg.get("created_at"),                          # 用 message 时间作首次 last_run
        last_run_rows_json=rows_json,
        last_run_truncated=1 if truncated else 0,
        last_run_ms=msg.get("query_time_ms") or 0,
    )
    if rid == 0:
        # UNIQUE 冲突（罕见竞争条件 — get_by_unique 之后被并发插入）
        again = saved_report_repo.get_by_unique(user["id"], msg["id"])
        if again:
            return again, True
        raise RuntimeError("saved_report 创建失败：INSERT 返回 0 但回查也无")
    return saved_report_repo.get(rid), False


def _default_title(s: str | None) -> str:
    """R-S5 sanitize：空 → '未命名报表'；>30 字截断加省略号；strip 空白。"""
    q = (s or "").strip() or "未命名报表"
    return q[:30] + ("…" if len(q) > 30 else "")


def _resolve_pin_data_source(user: dict) -> int | None:
    """R-S2 解析当前 user 在用的 data_source（用于 pin 时记录）。
    fallback 链：default_source_id → user_sources 唯一一条 → None。
    返回 None 表示重跑时走 get_user_engine 当前默认（可能不一致）。
    """
    if user.get("default_source_id"):
        return user["default_source_id"]
    src_ids = data_source_repo.get_user_source_ids(user["id"])
    if len(src_ids) == 1:
        return src_ids[0]
    return None


# ── 权限 / 读取 ───────────────────────────────────────────────────────────────

def get_owned(report_id: int, user: dict) -> dict | None:
    """返 saved_report；非所有者（admin 例外）一律返 None。
    api 层据此返 404 防 id 枚举。"""
    sr = saved_report_repo.get(report_id)
    if not sr:
        return None
    if sr["user_id"] == user["id"] or user.get("role") == "admin":
        return sr
    return None


def list_for_user(user: dict) -> list[dict]:
    """admin 仅看自己的；如需 admin 看全表后续 v0.5.x 加。"""
    return saved_report_repo.list_for_user(user["id"])


def update_owned(report_id: int, user: dict, title: str | None, pin_note: str | None) -> dict | None:
    sr = get_owned(report_id, user)
    if not sr:
        return None
    saved_report_repo.update(report_id, title=title, pin_note=pin_note)
    return saved_report_repo.get(report_id)


def delete_owned(report_id: int, user: dict) -> bool:
    sr = get_owned(report_id, user)
    if not sr:
        return False
    saved_report_repo.delete(report_id)
    return True


# ── 重跑（冻结 SQL）───────────────────────────────────────────────────────────

def run(report_id: int, user: dict) -> dict | None:
    """重跑冻结 SQL。返 None 表示报表不存在 / 无权访问（api 层转 404）。

    返回 dict：{rows, truncated, last_run_ms, last_run_at, error, warning}
    """
    sr = get_owned(report_id, user)
    if not sr:
        return None

    engine, warning = _resolve_run_engine(sr, user)
    if engine is None:
        return {
            "rows": [], "truncated": False,
            "last_run_ms": 0, "last_run_at": _now_iso(),
            "error": "无可用数据库引擎（检查数据源配置）",
            "warning": warning,
        }

    t0 = time.time()
    try:
        rows, db_error = db_connector.execute_query(engine, sr["sql_text"])
    except Exception as e:
        rows, db_error = [], str(e)[:200]
    elapsed_ms = int((time.time() - t0) * 1000)

    truncated = len(rows) > _LAST_RUN_ROW_LIMIT
    rows_snap = rows[:_LAST_RUN_ROW_LIMIT] if truncated else rows
    rows_json = json.dumps(rows_snap, ensure_ascii=False, default=str)
    run_at = _now_iso()
    saved_report_repo.update_last_run(
        report_id,
        rows_json=rows_json,
        truncated=1 if truncated else 0,
        elapsed_ms=elapsed_ms,
        run_at=run_at,
    )
    return {
        "rows": rows_snap,
        "truncated": truncated,
        "last_run_ms": elapsed_ms,
        "last_run_at": run_at,
        "error": db_error or "",
        "warning": warning,
    }


def _resolve_run_engine(sr: dict, user: dict):
    """R-S2 重跑引擎解析。返 (engine_or_None, warning_or_None)。

    优先级：
      1. 用 pin 时记录的 data_source_id（仍 active 且 user 仍有权限或 admin）
      2. fallback 到 get_user_engine + warning（口径可能不一致）
    """
    sid = sr.get("data_source_id")
    if sid:
        src = data_source_repo.get_datasource(sid)
        if src and src.get("is_active"):
            owned = sid in data_source_repo.get_user_source_ids(user["id"])
            if owned or user.get("role") == "admin":
                eng = engine_cache.get_engine_for_source(sid)
                if eng is not None:
                    return eng, None
        # source 已删 / 失活 / 失去关联 → fallback
        eng, _ = engine_cache.get_user_engine(user)
        return eng, "原数据源已不可用，已切换到当前默认数据源（口径可能不一致）"

    eng, _ = engine_cache.get_user_engine(user)
    return eng, None


def _now_iso() -> str:
    return datetime.now().isoformat(sep=" ", timespec="seconds")
