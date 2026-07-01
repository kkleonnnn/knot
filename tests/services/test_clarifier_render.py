"""v0.7.24 C1 — _render_clarifier_inputs 澄清选项进 history 守护（Part A · #2）。

- R-SL-176：澄清轮（agent_kind=clarifier + sql 空 + explanation=编号选项）→ 渲染含「上轮澄清选项」
  → clarifier 见自己上轮问的选项 → 靠既有 L25 解析用户数字回复「2」→ 选项②。
- byte-equal：普通轮（sql 非空）+ 非 clarifier 的 sql-空轮（错误轮）+ 缺 agent_kind 轮 → 渲染不变（不误渲）。
"""
from knot.services.agents.clarifier import _render_clarifier_inputs


def test_clarifier_turn_renders_options():
    history = [{"question": "本月各交易对的持仓盈亏", "sql": "", "rows": [],
                "agent_kind": "clarifier", "explanation": "①当前持仓 ②本月已平仓 ③本月成交"}]
    _, hist_text = _render_clarifier_inputs("schema", history)
    assert "上轮澄清选项" in hist_text
    assert "②本月已平仓" in hist_text          # 选项文本可见 → clarifier 能把用户「2」连到②
    assert "本月各交易对的持仓盈亏" in hist_text  # 原问题也在


def test_normal_turn_byte_equal():
    # 普通轮（sql 非空）→ Q+SQL+结果 byte-equal（A2 不影响 if-sql 分支）
    history = [{"question": "今日充值", "sql": "SELECT SUM(amt) FROM x", "rows": [{"amt": 100}],
                "agent_kind": "sql_planner", "explanation": "充值汇总"}]
    _, hist_text = _render_clarifier_inputs("schema", history)
    assert hist_text == 'Q: 今日充值\n  SQL: SELECT SUM(amt) FROM x\n  结果(前2行,共1行): [{"amt": 100}]'
    assert "上轮澄清选项" not in hist_text


def test_non_clarifier_sql_empty_turn_byte_equal():
    # 非 clarifier 的 sql-空轮（如错误轮 agent_kind=sql_planner）→ Q only；explanation 不误渲成选项
    history = [{"question": "坏查询", "sql": "", "rows": [],
                "agent_kind": "sql_planner", "explanation": "某错误信息"}]
    _, hist_text = _render_clarifier_inputs("schema", history)
    assert hist_text == "Q: 坏查询"
    assert "上轮澄清选项" not in hist_text


def test_missing_agent_kind_sql_empty_byte_equal():
    # 缺 agent_kind（旧消息兜底）+ sql 空 → Q only（不渲染，防误判）
    history = [{"question": "旧问题", "sql": "", "rows": []}]
    _, hist_text = _render_clarifier_inputs("schema", history)
    assert hist_text == "Q: 旧问题"
