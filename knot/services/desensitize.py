"""knot.services.desensitize — v0.6.0.19 脱敏链 3/3 后端模块。

业务用户（analyst role）在历史消息回放时，explanation / db_error 文本中含的
业务表全名（如 `dwd_user_deal`）应被替换为业务别名（如 `用户交易`），防止内部
schema 暴露给业务用户。admin 路径保留完整原文（已由 v0.6.0.17 API 边界守护）。

设计 §LOCKED 手册 v0.6.0.19-desensitize-3-3-locked.md §3 commit 1：
  - build_table_alias_map(catalog) 反转 catalog.lexicon ({业务词: [表名,...]})
    构建 {表名: 业务别名} 映射；多业务词指向同一表时选最短词（最具体语义启发式）
  - desensitize_text(text, alias_map) word-boundary regex 替换；fail-open

v0.7.35（B1.2 SSE 脱敏 · 对抗 review REVISE 后扩）：脱敏面从「历史回放（get_messages）
的 explanation/db_error」扩至**实时 SSE 流 + 同步 /query 响应**。新增 scrub_query_payload
单一真相源（SSE emit / 同步 /query / get_messages 三路共用），字段集扩至 _LEAK_TEXT_FIELDS
（含 clarifier 生成的 question/approach 等 — clarifier.md 靠 prompt 纪律，代码兜底）+ 嵌套
output.sql + details 多态。保 SSE live ≈ reload 一致（否则非 admin 实时流泄真实表名/SQL）。

红线（手册 §2 + v0.7.35 §3）：
  R-脱敏-1  word-boundary 严格（防 user → username 部分匹配）
  R-脱敏-2  fail-open — alias_map 空 / lexicon 缺失时不替换（但 sql pop 与 alias_map 无关，恒执行）
  R-脱敏-3  admin 路径 0 改动（本模块仅被 non-admin path 调用）
  R-脱敏-4  不脱敏 sql/sql_text — 整字段 pop 删除（v0.6.0.17 起；scrub_query_payload 顶层 + 嵌套 output）
  R-脱敏-6  case insensitive 匹配（SQL 通常不区分）；替换写业务别名（中文）
"""
from __future__ import annotations

import re
from collections.abc import Iterable


def build_table_alias_map(lexicon: dict | None) -> dict[str, str]:
    """反转 lexicon 构建 {table_full_name: business_alias}。

    lexicon 形如 ``{业务词: [table_full_name, table_full_name, ...]}``，
    一个表可能被多个业务词指向（例：'用户' + '注册用户' → users 表）。
    本函数反转为 ``{table_full_name: business_alias}``，每张表挑**最短的业务词**
    作为别名（启发式：最短词通常最具体；如 '用户' vs '注册新增用户'）。

    Args:
        lexicon: catalog.lexicon dict 或 None

    Returns:
        dict 形如 ``{"db.table": "业务别名", ...}``；lexicon 为空 / None → 空 dict
    """
    if not lexicon or not isinstance(lexicon, dict):
        return {}

    result: dict[str, str] = {}
    for term, tables in lexicon.items():
        if not isinstance(tables, (list, tuple)):
            continue
        if not isinstance(term, str) or not term.strip():
            continue
        for table in tables:
            if not isinstance(table, str) or not table.strip():
                continue
            existing = result.get(table)
            # 启发式：选最短业务词（更具体语义）；同长保留先到的
            if existing is None or len(term) < len(existing):
                result[table] = term
    return result


def desensitize_text(text: str | None, alias_map: dict[str, str]) -> str:
    """word-boundary regex 替换 text 中出现的表全名（含 db.table 形式）。

    替换策略：
      - case insensitive 匹配（SQL 表名通常不区分大小写）
      - word boundary `\\b` 严格匹配，防 ``user`` 命中 ``username`` 等
      - fail-open：alias_map 空 / text 空时直接返回原值
      - 单次扫描，已替换的部分不再二次匹配（用 dict 排序 + 长 key 优先避免冲突）

    Args:
        text: 待脱敏文本（如 explanation / db_error）；None 返回 None
        alias_map: build_table_alias_map 输出的 {table: alias}

    Returns:
        替换后文本；text 为 None 或 alias_map 空 → 原值返回
    """
    if text is None or not text:
        return text
    if not alias_map:
        return text

    # 按 key 长度倒序：先匹配 "db.table" 全名，再匹配 "table" 短名
    # 防止 short key (`table`) 优先吃掉应被 long key (`db.table`) 替换的位置
    sorted_keys: Iterable[str] = sorted(alias_map.keys(), key=len, reverse=True)
    result = text
    for table_full_name in sorted_keys:
        alias = alias_map[table_full_name]
        # re.escape 防表名含 regex 元字符（如 `.` 在 db.table 中）
        # \b word boundary 严格；但 `.` 不是 word char → 需要明确边界匹配
        # 解法：用 lookbehind/lookahead 而非 \b （兼容 `db.table` 这种含 `.` 形式）
        pattern = r"(?<![\w\.])" + re.escape(table_full_name) + r"(?![\w])"
        result = re.sub(pattern, alias, result, flags=re.IGNORECASE)
    return result


# v0.7.35（B1.2）：query-output 中可能含物理表名、需对 non-admin 脱敏的文本字段集。
# 各路径子集：get_messages（explanation/db_error）· SSE final（explanation/error/insight/user_message）·
# clarifier（question/clarification_question/approach/refined_question — clarifier.md:28 靠 prompt 纪律，代码兜底）。
# 并集统一扫，desensitize_text 对不含表名的文本 no-op（安全冗余；如用户自己的 question）。
_LEAK_TEXT_FIELDS = (
    "explanation", "db_error", "error", "insight", "user_message",
    "question", "clarification_question", "refined_question",
    "approach", "analysis_approach",
)


def non_admin_alias_map() -> dict[str, str]:
    """v0.7.35（B1.2）：按当前请求 per-user active catalog lexicon 构造 {表全名: 业务别名}。

    SSE / 同步 /query / get_messages 非 admin 路径共用 —— 收口 current_catalog().lexicon +
    build_table_alias_map + fail-open（R-脱敏-2 / R-B1.2-11；构造失败或 lexicon 缺失 → {}）。
    调用方须已 capture_active_catalog（否则 current_catalog 回退全局，等价旧 LEXICON 行为）。
    """
    try:
        from knot.services.agents import catalog as _cat
        return build_table_alias_map(_cat.current_catalog().get("lexicon"))
    except Exception as e:
        # ⭐ D8'（Codex R3 · 本片安全最重）：脱敏绝不 fail-open —— 返 {} → alias_map 空 → scrub_* 全 no-op
        # → 非 admin 直接看到内部库表全名/错误原文。
        from knot.core.tenant_context import reraise_if_tenant_error as _rt
        _rt(e)
        return {}


def scrub_query_payload(payload: dict, alias_map: dict[str, str]) -> dict:
    """v0.7.35（B1.2）非 admin 脱敏单个 query-output dict（原地改）— SSE emit / 同步 /query /
    get_messages 三路共用单一真相源。

      - pop `sql` / `sql_text`（整删 R-脱敏-4；SSE final 顶层 + agent_done 嵌套 output.sql — 两星标最高泄漏点）
      - desensitize `_LEAK_TEXT_FIELDS`（顶层 + 一层嵌套 output — SSE clarifier agent_done.output.approach/refined_question）
      - walk `details` 的 string values（error_translator 多态 — {"raw":...} 或 err.meta dict 皆覆盖）

    fail-open（R-脱敏-2）：alias_map 空 → desensitize no-op，但 sql pop 恒执行（pop 与 alias_map 无关）。
    非 dict → 原样返回。sql_step（thought/action/observation）由调用方 call-site suppress，不走本函数。
    """
    if not isinstance(payload, dict):
        return payload
    payload.pop("sql", None)
    payload.pop("sql_text", None)
    for k in _LEAK_TEXT_FIELDS:
        if payload.get(k):
            payload[k] = desensitize_text(payload[k], alias_map)
    # 一层嵌套 output（SSE agent_done：{"output": {"sql":..., "approach":..., "refined_question":...}}）
    out = payload.get("output")
    if isinstance(out, dict):
        out.pop("sql", None)
        out.pop("params", None)   # B6.4-Q36 v0.8.3：HTTP 内部形态（sql+params）均不发非 admin（统一 sql pop 口径）
        for k in _LEAK_TEXT_FIELDS:
            if out.get(k):
                out[k] = desensitize_text(out[k], alias_map)
    # error_translator details 多态：{"raw": "..."} 或 err.meta（dict）— walk 所有 string value
    det = payload.get("details")
    if isinstance(det, dict):
        for dk, dv in det.items():
            if isinstance(dv, str) and dv:
                det[dk] = desensitize_text(dv, alias_map)
    return payload


def desensitize_messages_for_non_admin(messages: list[dict], lexicon: dict | None) -> list[dict]:
    """便利函数：批量对 messages list 做泄漏文本字段脱敏（历史消息回放 non-admin 路径）。

    v0.7.35（B1.2）：字段集从 explanation+db_error 扩至 _LEAK_TEXT_FIELDS（含 error/insight），经
    scrub_query_payload 单一真相源 — 保 live SSE ≈ reload 一致（否则 reload 反 under-scrub）。
    scrub 也 pop sql/sql_text（幂等；conversations.py 已先 pop）。

    本函数被 knot/api/conversations.py GET messages endpoint 在 non-admin 路径调用。
    admin 路径不应调本函数（已由 v0.6.0.17 API 边界守护）。

    Args:
        messages: List of message dicts
        lexicon: catalog.lexicon dict 或 None

    Returns:
        同一 list（原地改）；fail-open（lexicon 缺失 → alias_map 空 → desensitize no-op）
    """
    alias_map = build_table_alias_map(lexicon)
    for m in messages:
        scrub_query_payload(m, alias_map)
    return messages
