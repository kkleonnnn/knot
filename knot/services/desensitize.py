"""knot.services.desensitize — v0.6.0.19 脱敏链 3/3 后端模块。

业务用户（analyst role）在历史消息回放时，explanation / db_error 文本中含的
业务表全名（如 `dwd_user_deal`）应被替换为业务别名（如 `用户交易`），防止内部
schema 暴露给业务用户。admin 路径保留完整原文（已由 v0.6.0.17 API 边界守护）。

设计 §LOCKED 手册 v0.6.0.19-desensitize-3-3-locked.md §3 commit 1：
  - build_table_alias_map(catalog) 反转 catalog.lexicon ({业务词: [表名,...]})
    构建 {表名: 业务别名} 映射；多业务词指向同一表时选最短词（最具体语义启发式）
  - desensitize_text(text, alias_map) word-boundary regex 替换；fail-open

红线（手册 §2）：
  R-脱敏-1  word-boundary 严格（防 user → username 部分匹配）
  R-脱敏-2  fail-open — alias_map 空 / lexicon 缺失时不替换
  R-脱敏-3  admin 路径 0 改动（本模块仅被 non-admin path 调用）
  R-脱敏-4  不替换 sql_text（v0.6.0.17 已 strip；本模块仅扫 explanation/db_error）
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


def desensitize_messages_for_non_admin(messages: list[dict], lexicon: dict | None) -> list[dict]:
    """便利函数：批量对 messages list 做 explanation + db_error 脱敏。

    本函数被 knot/api/conversations.py GET messages endpoint 在 non-admin 路径调用。
    admin 路径不应调本函数（已由 v0.6.0.17 API 边界守护）。

    Args:
        messages: List of message dicts（含 explanation / db_error 字段）
        lexicon: catalog.lexicon dict 或 None

    Returns:
        同一 list（原地改）；fail-open（lexicon 缺失则原样返回）
    """
    alias_map = build_table_alias_map(lexicon)
    if not alias_map:
        return messages  # fail-open
    for m in messages:
        if "explanation" in m and m["explanation"]:
            m["explanation"] = desensitize_text(m["explanation"], alias_map)
        if "db_error" in m and m["db_error"]:
            m["db_error"] = desensitize_text(m["db_error"], alias_map)
    return messages
