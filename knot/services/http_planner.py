"""knot.services.http_planner — HTTP virtual table 路由 + 参数提取 + 执行 (v0.6.1.4)

OVERRIDE #3 — 通用 HTTP executor 由 catalog 驱动。本模块负责：
1. schema text 注入 HTTP 虚拟表（让 clarifier 看到）
2. clarifier 输出后路由判定（http vs sql）
3. 参数提取（refined_question → endpoint params）
4. 调 executor 拿 rows
5. R-PB2-10 PII redact + truncate(20)
6. R-PB2-4 跨源 JOIN 守护（在 pick_http_route 中触发）

红线遵守：
- R-PB2-4: 多源命中时 raise CrossSourceJoinNotSupported（在 pick_http_route 处）
- R-PB2-10: rows 进 presenter 前 redact PII + truncate(20)
- R-PB2-15: timeout 由 spec 控制（executor 内部）
"""
from __future__ import annotations

import re
from typing import Any

from knot.adapters.http import HTTPAdapterError, execute
from knot.services.agents import catalog as catalog_loader

# R-PB2-10: PII 字段 — 防御性 redact 列表（即使 API 不返也保留代码）
_PII_FIELDS = frozenset({
    "email", "phone", "mobile", "id_card", "passport",
    "real_name", "address", "wechat", "bank_card",
})

_TRUNCATE_LIMIT = 20  # R-PB2-10 max rows


class CrossSourceJoinNotSupported(Exception):
    """R-PB2-4: catalog 命中多个 source_type（SQL + HTTP）— 跨源 JOIN narrow 二刀不支持。"""


# ─── 路由决策 ──────────────────────────────────────────────────────────


def pick_http_route(refined_question: str) -> tuple[str, dict] | None:
    """根据 refined_question 在 catalog 中匹配 HTTP 虚拟表。

    匹配逻辑（lexicon 优先 + topics 兜底）：
    1. 遍历 catalog.LEXICON，找 refined_question 包含的 key
    2. 对应 value 列表中第一个 source_type=http 表 = 命中
    3. R-PB2-4 守护：若同时命中 source_type=db 表 + HTTP 表 → raise CrossSourceJoinNotSupported

    Returns:
        (table_full_name, http_spec) 命中 HTTP 路由
        None — 未命中 HTTP 虚拟表（走 SQL 路径）

    Raises:
        CrossSourceJoinNotSupported: 检测到混源
    """
    catalog_loader.reload()  # R-PB2-13: catalog 变更立即生效
    lex = catalog_loader.LEXICON or {}

    matched_db_tables: set[str] = set()
    matched_http_tables: set[str] = set()

    for keyword, table_names in lex.items():
        if not keyword or not isinstance(keyword, str):
            continue
        if keyword.lower() not in refined_question.lower():
            continue
        for tname in table_names or []:
            if catalog_loader.is_http_table(tname):
                matched_http_tables.add(tname)
            else:
                matched_db_tables.add(tname)

    # v0.6.1.4 R-PB2-4 修订：lexicon 同关键词命中 SQL + HTTP 表是合理常态
    # （DB admin UI 配的 SQL 持仓表 + file 配的 HTTP 持仓表 都关联到"持仓"关键词）。
    # 当前规则：HTTP 优先（catalog driven 单源路由）。
    # 真正跨源 JOIN（多表必须 JOIN 才能答）由 query.py 后续语义判定，不在 lexicon 层 raise。
    if not matched_http_tables:
        return None

    # entity-aware 路由（v0.6.1.4）：
    # - 问题含 user_id 数字 → 偏好含 "user" 字面的 endpoint（如 futures_user_pending）
    # - 无 user_id → 平台视图 endpoint（如 futures_position_list）
    # 这是 demo MVP heuristic；v0.6.1.5+ 可用 LLM 调用做精准路由
    has_user_id = bool(_USER_ID_RE.search(refined_question))

    def _rank(name: str) -> int:
        is_user_endpoint = "user" in name.lower()
        if has_user_id and is_user_endpoint:
            return 0   # 最高优先
        if not has_user_id and not is_user_endpoint:
            return 1   # 平台视图
        return 2       # mismatch（仍可调，但靠后）

    selected = sorted(matched_http_tables, key=_rank)[0]
    spec = catalog_loader.get_http_spec(selected)
    if not spec:
        return None
    return selected, spec


# ─── 参数提取 ──────────────────────────────────────────────────────────

_USER_ID_RE = re.compile(r"用户\s*(\d{3,})|user[\s_]?id[\s=:]+(\d{3,})")
_MARKET_RE = re.compile(r"\b([A-Z]{3,}USDT|[A-Z]{2,}USD)\b")
_SHORT_MARKET_RE = re.compile(r"\b(BTC|ETH|SOL|BNB|XRP|ADA|DOT|MATIC|LINK|AVAX)\b", re.I)
_SIDE_LONG_WORDS = ("多头", "多仓", "long", "buy", "做多", "看多")
_SIDE_SHORT_WORDS = ("空头", "空仓", "short", "sell", "做空", "看空")


def extract_params_for_endpoint(refined_question: str, endpoint_key: str | None = None) -> dict[str, Any]:
    """从 refined_question 中提取 HTTP endpoint 参数（demo MVP regex 版）。

    覆盖场景：
    - user_id: "用户 1234567 ..." or "user_id=1234567"
    - market: "BTCUSDT" / "ETHUSDT" 全大写；fallback "BTC"/"ETH" 短名 → 拼 USDT
    - side: "多头"=2 / "空头"=1 / 默认不填（API 可能也接 null 返全部）
    - page / page_size: 默认 1/10

    Args:
        refined_question: clarifier 输出的精确化问题
        endpoint_key: 可选；未来按 endpoint 定制提取逻辑

    Returns:
        params dict — endpoint 需要的字段（未命中字段不填，由 executor 报错）
    """
    params: dict[str, Any] = {}
    q = refined_question

    # user_id
    m = _USER_ID_RE.search(q)
    if m:
        params["user_id"] = int(m.group(1) or m.group(2))

    # market（先匹配完整 BTCUSDT 形态，再 fallback BTC 短名）
    m = _MARKET_RE.search(q)
    if m:
        params["market"] = m.group(1)
    else:
        m = _SHORT_MARKET_RE.search(q)
        if m:
            params["market"] = (m.group(1) or "").upper() + "USDT"

    # side: 多头=2 / 空头=1
    q_lower = q.lower()
    if any(w in q_lower for w in _SIDE_LONG_WORDS):
        params["side"] = 2
    elif any(w in q_lower for w in _SIDE_SHORT_WORDS):
        params["side"] = 1

    # 分页默认（仅平台视图需要）
    if "page" not in params and "_list" in (endpoint_key or ""):
        params["page"] = 1
        params["page_size"] = 10

    return params


# ─── PII 脱敏 + 截断（R-PB2-10）──────────────────────────────────────────


def redact_pii(rows: list[dict]) -> list[dict]:
    """防御性 PII 脱敏 — 实际 API 不返 email/phone 等，但仍保留作为防御。

    替换为 "[REDACTED]" 字符串（保字段存在，前端不崩）。
    """
    if not rows:
        return rows
    redacted = []
    for row in rows:
        if not isinstance(row, dict):
            redacted.append(row)
            continue
        new_row = dict(row)
        for field in list(new_row.keys()):
            if field.lower() in _PII_FIELDS:
                new_row[field] = "[REDACTED]"
        redacted.append(new_row)
    return redacted


def truncate_rows(rows: list[dict], max_n: int = _TRUNCATE_LIMIT) -> tuple[list[dict], bool]:
    """R-PB2-10: 截断到 max_n 行，防 LLM token 灌爆。

    Returns: (truncated_rows, was_truncated)
    """
    if not rows:
        return rows, False
    if len(rows) <= max_n:
        return rows, False
    return rows[:max_n], True


# ─── HTTP step 执行（query_stream 调）──────────────────────────────────


def resolve_spec(catalog_spec: dict) -> dict:
    """v0.6.1.4 OVERRIDE #4: 解析 catalog http_spec，把 source_id 引用注入为直填值。

    模式 A (env 引用 — v0.6.1.4 backward compat): spec 含 base_url_env/auth_*_env → 透传给 executor 用 env 路径
    模式 B (source_id 引用 — v0.6.1.4 first-class): spec 含 source_id → 查 datasource → 注入直填 base_url/auth_*

    Returns: ready spec for executor.execute()

    Raises: HTTPAdapterError 数据源不存在 / 类型错误 / http_config 无法解析
    """
    if "source_id" not in catalog_spec:
        return dict(catalog_spec)  # 无 source_id → env 路径透传

    import json as _json

    from knot.repositories import data_source_repo

    source_id = catalog_spec["source_id"]
    ds = data_source_repo.get_datasource(source_id)
    if ds is None:
        raise HTTPAdapterError(f"数据源 id={source_id} 不存在")
    if ds.get("db_type") != "http":
        raise HTTPAdapterError(
            f"数据源 id={source_id} 类型 '{ds.get('db_type')}' ≠ 'http'"
        )

    http_cfg_str = ds.get("http_config") or ""
    if not http_cfg_str:
        raise HTTPAdapterError(f"数据源 id={source_id} 缺 http_config")
    try:
        http_cfg = _json.loads(http_cfg_str)
    except _json.JSONDecodeError as e:
        raise HTTPAdapterError(f"数据源 id={source_id} http_config 非合法 JSON: {e}") from e

    # 合并：catalog spec 字段优先，datasource 兜底
    ready = dict(catalog_spec)
    ready["base_url"] = http_cfg.get("base_url", "")
    ready["auth_header"] = http_cfg.get("auth_header", "")
    ready["auth_value"] = http_cfg.get("auth_value", "")
    if "timeout_sec" not in ready and "timeout_sec" in http_cfg:
        ready["timeout_sec"] = http_cfg["timeout_sec"]
    return ready


async def run_http_step(refined_question: str, table_full_name: str, http_spec: dict) -> dict:
    """执行 HTTP 路径：参数提取 → executor 调用 → PII 脱敏 + 截断。

    Args:
        refined_question: clarifier 输出
        table_full_name: e.g. "futures_admin.futures_position_list"
        http_spec: catalog 中的 HTTPEndpointSpec

    Returns:
        dict with keys:
            success (bool)
            rows (list[dict] — already redacted + truncated)
            row_count (int — original 行数)
            truncated (bool)
            error (str — 业务可读)
            error_kind (str — "http_unavailable" / "http_timeout" / "http_auth" / None)
            params (dict — 实际调 API 用的参数)
            endpoint_url (str — log 用)
    """
    # endpoint_key 从 table name 推断（用于参数 default 处理）
    endpoint_key = table_full_name.rsplit(".", 1)[-1]
    params = extract_params_for_endpoint(refined_question, endpoint_key)

    # v0.6.1.4 OVERRIDE #4: resolve source_id → 直填 spec（兼容 env 路径）
    try:
        ready_spec = resolve_spec(http_spec)
    except HTTPAdapterError as e:
        return {
            "success": False, "rows": [], "row_count": 0, "truncated": False,
            "error": str(e), "error_kind": "http_unavailable",
            "params": params, "endpoint_url": http_spec.get("url_template", ""),
        }

    # URL allowlist 守护：source_id 路径下 allowed_hosts 从 datasource 注入到全局 env
    # （demo MVP：仍依赖 KNOT_HTTP_ALLOWED_HOSTS env；v0.6.1.5 可加 per-source allowlist）

    try:
        raw_rows = execute(ready_spec, params)
    except HTTPAdapterError as e:
        # 区分 error_kind for error_translator
        err_name = type(e).__name__
        kind = "http_unavailable"
        if "HTTPAuth" in err_name:
            kind = "http_auth"
        elif "HTTPTimeout" in err_name:
            kind = "http_timeout"
        return {
            "success": False,
            "rows": [],
            "row_count": 0,
            "truncated": False,
            "error": str(e),
            "error_kind": kind,
            "params": params,
            "endpoint_url": http_spec.get("url_template", ""),
        }
    except Exception as e:
        return {
            "success": False,
            "rows": [],
            "row_count": 0,
            "truncated": False,
            "error": f"HTTP 调用异常: {e}",
            "error_kind": "http_unavailable",
            "params": params,
            "endpoint_url": http_spec.get("url_template", ""),
        }

    original_count = len(raw_rows) if isinstance(raw_rows, list) else 0
    # R-PB2-10 双过滤
    truncated_rows, was_truncated = truncate_rows(raw_rows or [])
    safe_rows = redact_pii(truncated_rows)

    return {
        "success": True,
        "rows": safe_rows,
        "row_count": original_count,
        "truncated": was_truncated,
        "error": "",
        "error_kind": None,
        "params": params,
        "endpoint_url": http_spec.get("url_template", ""),
    }


# ─── Schema 注入（让 clarifier 看到 HTTP 虚拟表）────────────────────────


def augment_schema_with_http_tables(schema_text: str) -> str:
    """在 schema_text 末尾追加 HTTP 虚拟表描述供 clarifier / sql_planner 参考。

    格式与 SQL schema markdown 风格对齐（### 表名 + 字段描述）。
    """
    catalog_loader.reload()
    http_tables = [
        t for t in catalog_loader.TABLES
        if t.get("source_type", "db") == "http"
    ]
    if not http_tables:
        return schema_text

    sections = ["\n\n## HTTP 虚拟表（外部 API 数据源 — catalog source_type=http）\n"]
    for t in http_tables:
        full_name = f"{t['db']}.{t['table']}"
        topics = ", ".join(t.get("topics", []) or [])
        summary = t.get("summary", "")
        sections.append(f"### {full_name}")
        if topics:
            sections.append(f"- 主题: {topics}")
        if summary:
            sections.append(f"- 说明: {summary}")
        sections.append("- 类型: HTTP API（不可 SQL JOIN）")
        sections.append("")

    return schema_text + "\n".join(sections)
