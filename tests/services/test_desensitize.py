"""v0.6.0.19 — knot/services/desensitize.py 守护测试。

按 LOCKED 手册 §3 commit 2 范围：
- build_table_alias_map 反转 lexicon（多业务词指向同表选最短）
- desensitize_text word-boundary（防 user → username 部分匹配）
- desensitize_text case insensitive 匹配
- desensitize_text fail-open（alias_map 空 / text 空 / lexicon None）
- desensitize_text 防二次替换（已替换的部分不再扫）
- desensitize_messages_for_non_admin 批量入口
"""
from __future__ import annotations

from knot.services.desensitize import (
    build_table_alias_map,
    desensitize_messages_for_non_admin,
    desensitize_text,
)


# ─── build_table_alias_map ──────────────────────────────────────────────


def test_build_alias_map_inverts_lexicon():
    """lexicon `{业务词: [表]}` → `{表: 业务词}`。"""
    lexicon = {
        "用户": ["app.users"],
        "订单": ["app.orders"],
    }
    result = build_table_alias_map(lexicon)
    assert result == {"app.users": "用户", "app.orders": "订单"}


def test_build_alias_map_multiple_terms_per_table_picks_shortest():
    """多业务词指向同表时选最短词（启发式：最短最具体）。"""
    lexicon = {
        "用户": ["app.users"],
        "注册新增用户": ["app.users"],  # 更长，应被丢弃
        "U": ["app.users"],  # 更短，应被选中
    }
    result = build_table_alias_map(lexicon)
    assert result["app.users"] == "U"


def test_build_alias_map_empty_lexicon():
    """空 / None lexicon → 空 dict（fail-open 输入）。"""
    assert build_table_alias_map({}) == {}
    assert build_table_alias_map(None) == {}


def test_build_alias_map_skips_non_string_terms():
    """非 string key / 非 list value 被跳过（防 lexicon 数据污染崩溃）。"""
    lexicon = {
        "用户": ["app.users"],
        123: ["app.bad"],          # 非 string key
        "": ["app.empty"],         # 空 key
        "订单": "app.orders",      # 非 list value（字符串）
        "好": ["app.orders"],
    }
    result = build_table_alias_map(lexicon)
    assert result == {"app.users": "用户", "app.orders": "好"}


# ─── desensitize_text ──────────────────────────────────────────────────


def test_desensitize_text_basic_replacement():
    """基本表名替换。"""
    alias_map = {"app.users": "用户表", "app.orders": "订单表"}
    text = "查询 app.users 与 app.orders 关联"
    assert desensitize_text(text, alias_map) == "查询 用户表 与 订单表 关联"


def test_desensitize_text_word_boundary_protects_partial_match():
    """word boundary 防部分匹配 — `user` 不替换 `username` / `users_log`。"""
    alias_map = {"user": "用户"}
    # `user` 应替换，`username` / `users_log` 不应替换
    text = "user vs username vs users_log"
    result = desensitize_text(text, alias_map)
    assert result == "用户 vs username vs users_log"


def test_desensitize_text_case_insensitive_matching():
    """SQL 表名大小写不敏感；DB.TABLE / db.table / Db.Table 全匹配。"""
    alias_map = {"app.users": "用户"}
    for variant in ["APP.USERS", "App.Users", "app.users"]:
        text = f"FROM {variant}"
        assert desensitize_text(text, alias_map) == "FROM 用户", f"variant={variant} failed"


def test_desensitize_text_fail_open_empty_alias_map():
    """alias_map 空 → 原文返回（fail-open）。"""
    text = "查询 app.users 表"
    assert desensitize_text(text, {}) == text


def test_desensitize_text_fail_open_none_text():
    """text 为 None → 返回 None（防 NPE）。"""
    assert desensitize_text(None, {"a": "b"}) is None


def test_desensitize_text_fail_open_empty_text():
    """text 空字符串 → 返回空字符串。"""
    assert desensitize_text("", {"a": "b"}) == ""


def test_desensitize_text_longer_key_wins_over_shorter():
    """`db.table` 全名 应优先于 `table` 短名 — 防 short 吃掉 long 应替换的位置。"""
    alias_map = {"users": "用户短", "app.users": "用户全名"}
    text = "FROM app.users JOIN users"
    result = desensitize_text(text, alias_map)
    # `app.users` 命中全名替换；末尾的 `users` 走短名替换
    assert "用户全名" in result
    assert "JOIN 用户短" in result


def test_desensitize_text_no_double_replacement():
    """已替换的部分不再二次匹配（单次 re.sub 扫描天然防）。"""
    # 如果别名内含 alias 本身的字面，可能引发递归替换
    alias_map = {"app.users": "users_alias"}  # alias 包含 'users' 字符串
    text = "FROM app.users"
    result = desensitize_text(text, alias_map)
    assert result == "FROM users_alias"  # 不会被二次替换为 'users_alias_alias' 等


def test_desensitize_text_dot_in_table_name_safe():
    """`db.table` 中的 `.` 是 regex 元字符 — re.escape 确保字面匹配。"""
    alias_map = {"app.users": "用户"}
    # `appXusers`（X 当作 wildcard 命中）不应误匹配
    text = "FROM appXusers"
    assert desensitize_text(text, alias_map) == "FROM appXusers"


# ─── desensitize_messages_for_non_admin ────────────────────────────────


def test_desensitize_messages_for_non_admin_replaces_explanation_and_db_error():
    """批量入口：explanation + db_error 同时替换。"""
    lexicon = {"用户": ["app.users"]}
    messages = [
        {"explanation": "查询 app.users 表", "db_error": ""},
        {"explanation": "", "db_error": "Table app.users not found"},
    ]
    result = desensitize_messages_for_non_admin(messages, lexicon)
    assert result[0]["explanation"] == "查询 用户 表"
    assert result[1]["db_error"] == "Table 用户 not found"


def test_desensitize_messages_for_non_admin_fail_open_no_lexicon():
    """lexicon None → 原 list 返回不动（fail-open）。"""
    messages = [{"explanation": "查询 app.users", "db_error": ""}]
    result = desensitize_messages_for_non_admin(messages, None)
    assert result[0]["explanation"] == "查询 app.users"  # 未替换


def test_desensitize_messages_for_non_admin_skips_missing_fields():
    """messages 中缺 explanation / db_error 字段不崩溃。"""
    lexicon = {"用户": ["app.users"]}
    messages = [
        {"question": "test"},  # 全无脱敏字段
        {"explanation": None, "db_error": None},  # None 值不崩溃
    ]
    # 不抛异常即可
    desensitize_messages_for_non_admin(messages, lexicon)
