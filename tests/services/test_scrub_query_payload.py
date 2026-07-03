"""tests/services/test_scrub_query_payload.py — v0.7.35（B1.2）scrub_query_payload 单一真相源守护。

scrub_query_payload 是 SSE emit / 同步 /query / get_messages 三路共用的脱敏 helper。
本文件用**真实 SSE 事件形状**作输入，证明每类事件的脱敏行为：
  - pop sql（顶层 final + 嵌套 agent_done.output.sql — 两星标最高泄漏点）
  - desensitize _LEAK_TEXT_FIELDS（顶层 + 嵌套 output — clarifier approach/refined_question）
  - details 多态 walk（error_translator {"raw":...} / err.meta）
  - fail-open（空 alias_map 仍 pop sql，文本不动 R-脱敏-2）
  - R-B1.2-14：http_planner user_message 中「db.table」CJK 括号边界正确 alias
"""
from __future__ import annotations

from knot.services.desensitize import build_table_alias_map, scrub_query_payload

# 典型 catalog.lexicon（业务词 → 物理表全名）
_LEX = {
    "用户交易": ["dwd_user_deal"],
    "用户": ["app.users"],
    "持仓": ["futures_admin.positions"],
}
_AMAP = build_table_alias_map(_LEX)


def test_pop_sql_top_and_nested():
    """final 顶层 sql + agent_done 嵌套 output.sql 均被整删（R-脱敏-4 / R-B1.2-10）。"""
    final = {"type": "final", "sql": "SELECT * FROM dwd_user_deal", "rows": []}
    scrub_query_payload(final, _AMAP)
    assert "sql" not in final, "顶层 sql 应 pop"
    assert final["type"] == "final" and final["rows"] == []  # 其他字段不动

    done = {"type": "agent_done", "agent": "sql_planner",
            "output": {"sql": "SELECT * FROM dwd_user_deal", "steps": 3}}
    scrub_query_payload(done, _AMAP)
    assert "sql" not in done["output"], "嵌套 output.sql 应 pop（星标最高泄漏点）"
    assert done["output"]["steps"] == 3  # 非泄漏字段保留


def test_desensitize_leak_fields_top():
    """final 顶层 explanation/error/insight/user_message 表名 → 业务别名。"""
    ev = {
        "type": "final",
        "explanation": "基于 dwd_user_deal 分析",
        "error": "Table dwd_user_deal locked",
        "insight": "app.users 活跃度上升",
        "user_message": "查询 app.users 失败",
    }
    scrub_query_payload(ev, _AMAP)
    assert "dwd_user_deal" not in ev["explanation"] and "用户交易" in ev["explanation"]
    assert "dwd_user_deal" not in ev["error"] and "用户交易" in ev["error"]
    assert "app.users" not in ev["insight"] and "用户" in ev["insight"]
    assert "app.users" not in ev["user_message"] and "用户" in ev["user_message"]


def test_desensitize_nested_output_clarifier_fields():
    """clarifier agent_done 嵌套 output.approach/refined_question 脱敏（R-B1.2-9）。

    clarifier.md:28 靠 prompt 纪律禁物理表名，代码兜底 —— 若 LLM 漏出表名，此处脱敏。
    """
    ev = {"type": "agent_done", "agent": "clarifier",
          "output": {"refined_question": "查 dwd_user_deal 的 GMV",
                     "approach": "对 dwd_user_deal 聚合",
                     "intent": "trend"}}
    scrub_query_payload(ev, _AMAP)
    assert "dwd_user_deal" not in ev["output"]["refined_question"]
    assert "dwd_user_deal" not in ev["output"]["approach"]
    assert "用户交易" in ev["output"]["approach"]
    assert ev["output"]["intent"] == "trend"  # 非文本字段不动


def test_clarification_needed_question_desensitized():
    """clarification_needed.question（= clarification_question）脱敏（R-B1.2-9 MISS#2）。"""
    ev = {"type": "clarification_needed", "question": "你是指 app.users 还是别的表？"}
    scrub_query_payload(ev, _AMAP)
    assert "app.users" not in ev["question"] and "用户" in ev["question"]


def test_details_polymorphic_walk():
    """error 事件 details 多态：{"raw":...} + err.meta dict 的 string value 都 walk 脱敏。"""
    ev = {"type": "error", "error_kind": "db_error",
          "user_message": "查询失败",
          "details": {"raw": "pymysql error near dwd_user_deal", "code": 1146}}
    scrub_query_payload(ev, _AMAP)
    assert "dwd_user_deal" not in ev["details"]["raw"]
    assert "用户交易" in ev["details"]["raw"]
    assert ev["details"]["code"] == 1146  # 非 string 不动


def test_fail_open_empty_alias_map_still_pops_sql():
    """空 alias_map（lexicon 缺失）：sql 仍 pop（与 alias_map 无关），文本不动（fail-open R-脱敏-2）。"""
    ev = {"type": "final", "sql": "SELECT * FROM dwd_user_deal",
          "explanation": "基于 dwd_user_deal 分析"}
    scrub_query_payload(ev, {})
    assert "sql" not in ev, "空 alias_map 仍应 pop sql"
    assert ev["explanation"] == "基于 dwd_user_deal 分析", "空 alias_map 文本不脱敏（fail-open）"


def test_non_dict_passthrough():
    """非 dict 输入原样返回不崩溃。"""
    assert scrub_query_payload(None, _AMAP) is None
    assert scrub_query_payload("str", _AMAP) == "str"
    assert scrub_query_payload([1, 2], _AMAP) == [1, 2]


def test_R_B1_2_14_http_db_table_bracket_user_message():
    """R-B1.2-14：http_planner failure_error_meta case① 的「db.table」CJK 括号边界脱敏。

    user_message 形如 `「futures_admin.positions」是平台实时接口数据...`；
    desensitize_text 的 (?<![\\w\\.]) / (?![\\w]) 边界对 CJK 括号「」（非 \\w 非 .）成立 → 正确 alias。
    """
    ev = {"type": "final", "error_kind": "data_unavailable",
          "user_message": "「futures_admin.positions」是平台实时接口数据（如当前持仓 / 挂单），无法用 SQL 查询。"}
    scrub_query_payload(ev, _AMAP)
    assert "futures_admin.positions" not in ev["user_message"], f"未脱敏：{ev['user_message']}"
    assert "「持仓」" in ev["user_message"], f"CJK 括号内应 alias 为「持仓」：{ev['user_message']}"


def test_column_labels_and_dimension_cols_not_touched():
    """column_labels/dimension_cols 是 metric/列名（非物理表名）→ 不脱敏（v0.7.23/.25 呈现字段保真）。"""
    ev = {"type": "final", "sql": "SELECT 1",
          "column_labels": {"user_position_pnl": "持仓盈亏"},
          "dimension_cols": ["city", "symbol"]}
    scrub_query_payload(ev, _AMAP)
    assert "sql" not in ev  # sql 仍 pop
    assert ev["column_labels"] == {"user_position_pnl": "持仓盈亏"}, "column_labels 不应被脱敏改动"
    assert ev["dimension_cols"] == ["city", "symbol"], "dimension_cols 不应被脱敏改动"
