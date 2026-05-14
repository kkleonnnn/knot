"""tests/core/test_time_resolver.py — v0.6.1 时间语义引擎守护测试。

LOCKED §3 R-PA-PB-2~5 守护对象：
- R-PA-PB-2: resolve_time_context() API 签名
- R-PA-PB-3: 2026 节假日 hardcoded 字面
- R-PA-PB-4: data_freshness_lag_days=1 默认
- R-PA-PB-5: TimeContext.prompt_block 字面 snapshot

测试覆盖（30+ 测试）：
- 基础时间解析：8 测试
- 数据更新延迟：4 测试
- 节假日检测：6 测试
- 同比基准对齐：4 测试
- 月初/月末边界：3 测试
- 跨年边界：3 测试
- prompt_block snapshot：2 测试
"""
from datetime import date

from knot.core.time_resolver import (
    HOLIDAYS_2026,
    _holidays_in_month,
    _is_in_holiday,
    resolve_time_context,
)

# ─── 1. 基础时间解析（8 测试）─────────────────────────────────────────────

def test_today_iso_format():
    ctx = resolve_time_context(today_override=date(2026, 5, 14))
    assert ctx.today_str == "2026-05-14"


def test_this_year_full_range():
    ctx = resolve_time_context(today_override=date(2026, 5, 14))
    assert ctx.this_year == ("2026-01-01", "2026-12-31")


def test_this_year_to_latest():
    ctx = resolve_time_context(today_override=date(2026, 5, 14))
    assert ctx.this_year_to_latest == ("2026-01-01", "2026-05-13")


def test_this_month_full_range():
    ctx = resolve_time_context(today_override=date(2026, 5, 14))
    assert ctx.this_month == ("2026-05-01", "2026-05-31")


def test_this_month_to_latest():
    ctx = resolve_time_context(today_override=date(2026, 5, 14))
    assert ctx.this_month_to_latest == ("2026-05-01", "2026-05-13")


def test_last_week_iso_monday_first():
    # 2026-05-14 是周四 — 本周一 = 2026-05-11；上周一 = 2026-05-04；上周日 = 2026-05-10
    ctx = resolve_time_context(today_override=date(2026, 5, 14))
    assert ctx.last_week == ("2026-05-04", "2026-05-10")


def test_last_7_days_to_latest():
    # latest=2026-05-13；最近 7 天到最新 = 2026-05-07 至 2026-05-13
    ctx = resolve_time_context(today_override=date(2026, 5, 14))
    assert ctx.last_7_days_to_latest == ("2026-05-07", "2026-05-13")


def test_timezone_default():
    ctx = resolve_time_context(today_override=date(2026, 5, 14))
    assert ctx.timezone == "Asia/Shanghai"


# ─── 2. 数据更新延迟（4 测试）─────────────────────────────────────────────

def test_lag_default_d_minus_1():
    """R-PA-PB-4: data_freshness_lag_days 默认 1 — 数据更新到昨天。"""
    ctx = resolve_time_context(today_override=date(2026, 5, 14))
    assert ctx.latest_data_date_str == "2026-05-13"


def test_lag_zero_real_time():
    ctx = resolve_time_context(today_override=date(2026, 5, 14), data_freshness_lag_days=0)
    assert ctx.latest_data_date_str == "2026-05-14"
    assert ctx.this_year_to_latest == ("2026-01-01", "2026-05-14")


def test_lag_7_days_weekly_etl():
    ctx = resolve_time_context(today_override=date(2026, 5, 14), data_freshness_lag_days=7)
    assert ctx.latest_data_date_str == "2026-05-07"
    assert ctx.this_year_to_latest == ("2026-01-01", "2026-05-07")


def test_lag_affects_same_period_last_year():
    """lag=7 时同比基准也对应去年 lag=7 那天。"""
    ctx = resolve_time_context(today_override=date(2026, 5, 14), data_freshness_lag_days=7)
    assert ctx.same_period_last_year == ("2025-01-01", "2025-05-07")


# ─── 3. 节假日检测（6 测试）──────────────────────────────────────────────

def test_holidays_2026_table_byte_equal():
    """R-PA-PB-3: 2026 节假日表 hardcoded byte-equal — 7 个节假日。"""
    assert len(HOLIDAYS_2026) == 7
    assert HOLIDAYS_2026[0] == ("2026-01-01", "2026-01-03", "元旦")
    assert HOLIDAYS_2026[1] == ("2026-02-17", "2026-02-23", "春节")
    assert HOLIDAYS_2026[3] == ("2026-05-01", "2026-05-05", "劳动节")
    assert HOLIDAYS_2026[6] == ("2026-10-01", "2026-10-08", "国庆")


def test_is_in_holiday_today():
    assert _is_in_holiday(date(2026, 5, 1)) is True  # 劳动节首日
    assert _is_in_holiday(date(2026, 5, 5)) is True  # 劳动节末日
    assert _is_in_holiday(date(2026, 5, 6)) is False  # 劳动节后
    assert _is_in_holiday(date(2026, 5, 14)) is False  # 普通工作日


def test_holidays_in_month_may():
    holidays = _holidays_in_month(2026, 5)
    assert len(holidays) == 1
    assert holidays[0] == ("2026-05-01", "2026-05-05", "劳动节")


def test_holidays_in_month_feb():
    """春节跨月（2-17 到 2-23），命中本月。"""
    holidays = _holidays_in_month(2026, 2)
    assert len(holidays) == 1
    assert holidays[0][2] == "春节"


def test_holidays_in_month_no_holiday():
    """7 月无节假日。"""
    holidays = _holidays_in_month(2026, 7)
    assert len(holidays) == 0


def test_is_holiday_today_context_field():
    ctx_workday = resolve_time_context(today_override=date(2026, 5, 14))
    assert ctx_workday.is_holiday_today is False

    ctx_holiday = resolve_time_context(today_override=date(2026, 5, 1))
    assert ctx_holiday.is_holiday_today is True


# ─── 4. 同比基准对齐（4 测试）────────────────────────────────────────────

def test_same_period_last_year_with_lag():
    """同比基准 = (去年首日, 去年 latest 对应日)。"""
    ctx = resolve_time_context(today_override=date(2026, 5, 14))
    assert ctx.same_period_last_year == ("2025-01-01", "2025-05-13")


def test_same_period_last_year_january_first():
    """1 月 1 日问 — latest 跨年到上年（lag=1 时 latest=2025-12-31）。

    业务设计：同比基准锚定 latest（不锚定 today）— 避免反序范围。
    today=2026-01-01 / latest=2025-12-31 → 同期 = latest 减一年完整段 (2024-01-01, 2024-12-31)
    """
    ctx = resolve_time_context(today_override=date(2026, 1, 1))
    assert ctx.latest_data_date_str == "2025-12-31"
    # 锚定 latest 年份 - 1 = 2024
    assert ctx.same_period_last_year == ("2024-01-01", "2024-12-31")


def test_same_period_last_year_leap_year_handling():
    """闰年 2-29 同比降级到 2-28。"""
    # 2024 是闰年；2025-03-01 latest=2025-02-28；同期=(2024-01-01, 2024-02-28)
    ctx = resolve_time_context(today_override=date(2025, 3, 1))
    assert ctx.same_period_last_year == ("2024-01-01", "2024-02-28")


def test_same_period_last_year_july():
    ctx = resolve_time_context(today_override=date(2026, 7, 15))
    assert ctx.same_period_last_year == ("2025-01-01", "2025-07-14")


# ─── 5. 月初/月末边界（3 测试）───────────────────────────────────────────

def test_month_start_boundary():
    """5-01 问 — this_month_to_latest = (2026-05-01, 2026-04-30) — latest 在上月末。"""
    ctx = resolve_time_context(today_override=date(2026, 5, 1))
    # latest = 2026-04-30
    assert ctx.latest_data_date_str == "2026-04-30"
    # this_month = (2026-05-01, 2026-05-31) — 自然月不受 lag 影响
    assert ctx.this_month == ("2026-05-01", "2026-05-31")
    # this_month_to_latest 跨月一对（特殊场景）
    assert ctx.this_month_to_latest == ("2026-05-01", "2026-04-30")


def test_month_end_boundary():
    """5-31 问 — this_month_to_latest 几乎覆盖整月。"""
    ctx = resolve_time_context(today_override=date(2026, 5, 31))
    assert ctx.latest_data_date_str == "2026-05-30"
    assert ctx.this_month_to_latest == ("2026-05-01", "2026-05-30")


def test_february_month_end():
    """2026-02 月底（非闰年）— 28 天。"""
    ctx = resolve_time_context(today_override=date(2026, 2, 28))
    assert ctx.this_month == ("2026-02-01", "2026-02-28")


# ─── 6. 跨年边界（3 测试）────────────────────────────────────────────────

def test_year_end_dec_31():
    """12-31 问"今年"— 全年范围 + this_year_to_latest 截止到 12-30。"""
    ctx = resolve_time_context(today_override=date(2026, 12, 31))
    assert ctx.this_year == ("2026-01-01", "2026-12-31")
    assert ctx.this_year_to_latest == ("2026-01-01", "2026-12-30")


def test_year_start_jan_1():
    """1-1 问"今年" — latest=2025-12-31，this_year_to_latest 是跨年边界。"""
    ctx = resolve_time_context(today_override=date(2026, 1, 1))
    assert ctx.this_year == ("2026-01-01", "2026-12-31")
    # this_year_to_latest 仍以 today 年份为基线；latest 是 2025-12-31
    assert ctx.this_year_to_latest == ("2026-01-01", "2025-12-31")


def test_year_start_last_week_cross_year():
    """1-2 问 — 上周可能跨年。"""
    ctx = resolve_time_context(today_override=date(2026, 1, 2))
    # 2026-01-02 是周五，本周一 = 2025-12-29，上周一 = 2025-12-22，上周日 = 2025-12-28
    assert ctx.last_week == ("2025-12-22", "2025-12-28")


# ─── 7. prompt_block snapshot（2 测试 — R-PA-PB-5 字面守护）─────────────

def test_prompt_block_contains_key_literals():
    """R-PA-PB-5: prompt_block 必含关键字面。"""
    ctx = resolve_time_context(today_override=date(2026, 5, 14))
    pb = ctx.prompt_block
    assert "时间语义上下文（KNOT 时间引擎 v0.6.1）" in pb
    assert "5 类核心时间表达" in pb
    assert "同比基准" in pb
    assert "节假日上下文" in pb
    assert "约束" in pb
    assert "Asia/Shanghai" in pb
    assert "2026-05-14" in pb  # today
    assert "2026-05-13" in pb  # latest
    assert "劳动节" in pb       # 本月节假日


def test_prompt_block_snapshot_byte_equal_2026_05_14():
    """R-PA-PB-5: prompt_block 字面 snapshot — 2026-05-14 完整对账。"""
    ctx = resolve_time_context(today_override=date(2026, 5, 14))
    expected = (
        "## 时间语义上下文（KNOT 时间引擎 v0.6.1）\n"
        "\n"
        "- 今天：2026-05-14（时区 Asia/Shanghai，系统时间权威）\n"
        "- 最新数据：2026-05-13（数据更新延迟默认 D-1）\n"
        "\n"
        "### 5 类核心时间表达（业务约定，必须按此对应）\n"
        "\n"
        "- 「今年」全年 = 2026-01-01 至 2026-12-31\n"
        "- 「今年到目前」/「截至最新」 = 2026-01-01 至 2026-05-13\n"
        "- 「本月」自然月 = 2026-05-01 至 2026-05-31\n"
        "- 「本月到目前」 = 2026-05-01 至 2026-05-13\n"
        "- 「上周」ISO 周一首 = 2026-05-04 至 2026-05-10\n"
        "- 「最近 7 天」到最新数据 = 2026-05-07 至 2026-05-13\n"
        "\n"
        "### 同比基准（vs 去年同期）\n"
        "\n"
        "- 「今年同比」对照 = 2025-01-01 至 2025-05-13\n"
        "  （与「今年到目前」端点对齐，截取去年同段）\n"
        "\n"
        "### 节假日上下文（2026 节假日表）\n"
        "\n"
        "- 本月含节假日：劳动节(2026-05-01~2026-05-05)\n"
        "- 今天非节假日\n"
        "\n"
        "### 约束\n"
        "\n"
        "- 用户问「今年」/「本月」默认按「到目前」截断（不含未来）— 除非用户明示「全年」\n"
        "- 用户问「同比」默认以「今年到目前」为基准 — 截取去年同段对照\n"
        "- ≤ 今天的任何日期都是历史日期（不要因 LLM 训练截止时间把它判定为未来）\n"
        "- SQL 中 CURDATE() / NOW() 等价于今天 = 2026-05-14\n"
    )
    assert ctx.prompt_block == expected


# ─── 8. API 签名守护（R-PA-PB-2）─────────────────────────────────────────

def test_api_signature_byte_equal():
    """R-PA-PB-2: resolve_time_context API 签名 byte-equal。"""
    # 全位置参数
    ctx1 = resolve_time_context(None, date(2026, 5, 14), 1, "Asia/Shanghai")
    # kwargs 命名
    ctx2 = resolve_time_context(
        natural_language_hint=None,
        today_override=date(2026, 5, 14),
        data_freshness_lag_days=1,
        timezone="Asia/Shanghai",
    )
    assert ctx1.today_str == ctx2.today_str
    assert ctx1.prompt_block == ctx2.prompt_block


def test_timecontext_is_frozen():
    """TimeContext 是 frozen dataclass — 字段不可修改（避免误用）。"""
    import dataclasses
    ctx = resolve_time_context(today_override=date(2026, 5, 14))
    try:
        ctx.today_str = "2099-01-01"  # type: ignore
        raise AssertionError("应抛 FrozenInstanceError")
    except dataclasses.FrozenInstanceError:
        pass
