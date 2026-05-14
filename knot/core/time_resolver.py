"""knot/core/time_resolver.py — v0.6.1 时间语义统一引擎（Phase B 决议 B 修订版 F2）

LOCKED §3 R-PA-PB-2~6 守护对象：
- R-PA-PB-2: resolve_time_context() 单核函数 API 签名 byte-equal
- R-PA-PB-3: 2026 节假日 hardcoded dict byte-equal
- R-PA-PB-4: data_freshness_lag_days=1 默认 byte-equal
- R-PA-PB-5: TimeContext.prompt_block 字面 snapshot 守护
- R-PA-PB-6: SqlPlanner system prompt {date_context} 占位 byte-equal sustained
  （本模块由 date_context.py 调用 — date_context.py 接口不变）

设计原则：
1. 纯函数 — 不依赖网络 / DB / LLM；today 可显式覆盖（测试用）
2. 统一时区 Asia/Shanghai（v0.4.x date_context.py 既有约定 sustained）
3. 数据更新延迟（lag=1）= "今年到目前" 截止昨天（D-1）— 避免 LLM 把"今年同比"算到今天
4. 节假日表 hardcoded（v0.7+ 升级为外部 yaml）
5. 5 类核心时间表达：今年 / 本月 / 上周 / 最近 N 天 / 同比基准
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

try:
    from zoneinfo import ZoneInfo
    _TZ = ZoneInfo("Asia/Shanghai")
except Exception:
    _TZ = None


# ─── 2026 节假日表（R-PA-PB-3 hardcoded byte-equal）───────────────────────
# 国务院办公厅公告（2025-11 发布的 2026 年放假安排）
# 每条 (起, 止, 名称)；按时间顺序排列
HOLIDAYS_2026: list[tuple[str, str, str]] = [
    ("2026-01-01", "2026-01-03", "元旦"),
    ("2026-02-17", "2026-02-23", "春节"),
    ("2026-04-04", "2026-04-06", "清明"),
    ("2026-05-01", "2026-05-05", "劳动节"),
    ("2026-06-19", "2026-06-21", "端午"),
    ("2026-09-25", "2026-09-27", "中秋"),
    ("2026-10-01", "2026-10-08", "国庆"),
]


@dataclass(frozen=True)
class TimeContext:
    """v0.6.1 时间语义统一上下文 — 注入 SqlPlanner / Clarifier system prompt。

    R-PA-PB-2 守护：本类字段 byte-equal；新增字段需经守护者评审。
    """
    # 基础
    today_str: str                                # '2026-05-14'
    latest_data_date_str: str                     # '2026-05-13' (today - lag)
    timezone: str                                 # 'Asia/Shanghai'

    # 5 类核心时间表达（每对 (起, 止) 含两端 inclusive）
    this_year: tuple[str, str]                    # 全年范围
    this_year_to_latest: tuple[str, str]          # 今年到最新数据 — 同比基准
    this_month: tuple[str, str]                   # 自然月
    this_month_to_latest: tuple[str, str]         # 本月到最新数据
    last_week: tuple[str, str]                    # 上周（ISO 周一首）
    last_7_days_to_latest: tuple[str, str]        # 最近 7 天到最新数据

    # 同比基准（vs 去年同期）
    same_period_last_year: tuple[str, str]        # 去年对应"今年到最新"段

    # 节假日提示
    holidays_in_this_month: list[tuple[str, str, str]] = field(default_factory=list)
    is_holiday_today: bool = False

    # prompt_block：注入 system prompt 的标准段（R-PA-PB-5 字面守护）
    prompt_block: str = ""


def today() -> date:
    """获取当前时区日期 — 与 date_context.py:today() byte-equal。"""
    if _TZ is not None:
        from datetime import datetime
        return datetime.now(_TZ).date()
    return date.today()


def _iso(d: date) -> str:
    return d.isoformat()


def _is_in_holiday(check: date) -> bool:
    """check 是否落在 2026 节假日范围内。"""
    s = _iso(check)
    for start, end, _name in HOLIDAYS_2026:
        if start <= s <= end:
            return True
    return False


def _holidays_in_month(year: int, month: int) -> list[tuple[str, str, str]]:
    """返回该月含的节假日（含跨月部分命中本月）。"""
    out = []
    for start, end, name in HOLIDAYS_2026:
        s_year, s_month = int(start[:4]), int(start[5:7])
        e_year, e_month = int(end[:4]), int(end[5:7])
        # 命中本月：起 / 止任一在本月
        if (s_year == year and s_month == month) or (e_year == year and e_month == month):
            out.append((start, end, name))
    return out


def _build_prompt_block(ctx_partial: dict) -> str:
    """生成 prompt_block 字面（R-PA-PB-5 守护 snapshot 必稳定）。"""
    today_s = ctx_partial["today_str"]
    latest = ctx_partial["latest_data_date_str"]
    ty = ctx_partial["this_year"]
    tytl = ctx_partial["this_year_to_latest"]
    tm = ctx_partial["this_month"]
    tmtl = ctx_partial["this_month_to_latest"]
    lw = ctx_partial["last_week"]
    l7 = ctx_partial["last_7_days_to_latest"]
    sply = ctx_partial["same_period_last_year"]
    holidays = ctx_partial["holidays_in_this_month"]
    is_holiday = ctx_partial["is_holiday_today"]

    holiday_line = (
        "- 本月含节假日：" + " / ".join(f"{name}({s}~{e})" for s, e, name in holidays)
        if holidays else "- 本月无节假日"
    )
    is_holiday_line = (
        "- ⚠️ 今天是节假日（数据可能稀疏）" if is_holiday else "- 今天非节假日"
    )

    return (
        f"## 时间语义上下文（KNOT 时间引擎 v0.6.1）\n"
        f"\n"
        f"- 今天：{today_s}（时区 Asia/Shanghai，系统时间权威）\n"
        f"- 最新数据：{latest}（数据更新延迟默认 D-1）\n"
        f"\n"
        f"### 5 类核心时间表达（业务约定，必须按此对应）\n"
        f"\n"
        f"- 「今年」全年 = {ty[0]} 至 {ty[1]}\n"
        f"- 「今年到目前」/「截至最新」 = {tytl[0]} 至 {tytl[1]}\n"
        f"- 「本月」自然月 = {tm[0]} 至 {tm[1]}\n"
        f"- 「本月到目前」 = {tmtl[0]} 至 {tmtl[1]}\n"
        f"- 「上周」ISO 周一首 = {lw[0]} 至 {lw[1]}\n"
        f"- 「最近 7 天」到最新数据 = {l7[0]} 至 {l7[1]}\n"
        f"\n"
        f"### 同比基准（vs 去年同期）\n"
        f"\n"
        f"- 「今年同比」对照 = {sply[0]} 至 {sply[1]}\n"
        f"  （与「今年到目前」端点对齐，截取去年同段）\n"
        f"\n"
        f"### 节假日上下文（2026 节假日表）\n"
        f"\n"
        f"{holiday_line}\n"
        f"{is_holiday_line}\n"
        f"\n"
        f"### 约束\n"
        f"\n"
        f"- 用户问「今年」/「本月」默认按「到目前」截断（不含未来）— 除非用户明示「全年」\n"
        f"- 用户问「同比」默认以「今年到目前」为基准 — 截取去年同段对照\n"
        f"- ≤ 今天的任何日期都是历史日期（不要因 LLM 训练截止时间把它判定为未来）\n"
        f"- SQL 中 CURDATE() / NOW() 等价于今天 = {today_s}\n"
    )


def resolve_time_context(
    natural_language_hint: str | None = None,
    today_override: date | None = None,
    data_freshness_lag_days: int = 1,
    timezone: str = "Asia/Shanghai",
) -> TimeContext:
    """v0.6.1 时间语义统一解析。

    R-PA-PB-2 API 签名守护：本函数签名 byte-equal — 新参数走 kwargs 默认值扩展。

    Args:
        natural_language_hint: 用户自然语言时间提示（v0.6.1 暂不解析，预留 v0.7+）
        today_override: 显式指定今天（测试用 / 默认 None = 当前时区今天）
        data_freshness_lag_days: 数据更新延迟（默认 1 = 数据更新到昨天）
        timezone: 时区字面（默认 Asia/Shanghai）

    Returns:
        TimeContext: 含 5 类核心时间表达 + 同比基准 + 节假日 + prompt_block
    """
    t = today_override or today()
    lag = data_freshness_lag_days
    latest = t - timedelta(days=lag)

    # 5 类核心时间表达
    this_year_start = date(t.year, 1, 1)
    this_year_end = date(t.year, 12, 31)
    this_month_start = t.replace(day=1)
    # 月末 = 下月第 1 天 - 1 天
    if this_month_start.month == 12:
        next_month_start = date(this_month_start.year + 1, 1, 1)
    else:
        next_month_start = date(this_month_start.year, this_month_start.month + 1, 1)
    this_month_end = next_month_start - timedelta(days=1)

    # ISO 周一首
    this_week_mon = t - timedelta(days=t.weekday())
    last_week_mon = this_week_mon - timedelta(days=7)
    last_week_sun = this_week_mon - timedelta(days=1)

    # 最近 7 天到最新数据
    l7_start = latest - timedelta(days=6)

    # 同比基准（vs 去年同期）— 以 latest 为锚（不是 today），跨年时正确对齐
    # 例：today=2026-01-01 / lag=1 → latest=2025-12-31
    #   → 去年同期应是 (2024-01-01, 2024-12-31)（latest 减一年）
    # 正常场景 today.year == latest.year：行为等同于 (today.year-1) 减一年
    sply_year = latest.year - 1
    sply_start = date(sply_year, 1, 1)
    # 同期止 = latest 减一年（注意闰年边界 — 简化 2-29 → 2-28）
    try:
        sply_end = date(sply_year, latest.month, latest.day)
    except ValueError:
        # 闰年 2-29 → 同期年 2-28
        sply_end = date(sply_year, 2, 28)

    # 节假日
    holidays = _holidays_in_month(t.year, t.month)
    is_holiday = _is_in_holiday(t)

    # 构造 ctx 字典 + prompt_block
    partial = {
        "today_str": _iso(t),
        "latest_data_date_str": _iso(latest),
        "timezone": timezone,
        "this_year": (_iso(this_year_start), _iso(this_year_end)),
        "this_year_to_latest": (_iso(this_year_start), _iso(latest)),
        "this_month": (_iso(this_month_start), _iso(this_month_end)),
        "this_month_to_latest": (_iso(this_month_start), _iso(latest)),
        "last_week": (_iso(last_week_mon), _iso(last_week_sun)),
        "last_7_days_to_latest": (_iso(l7_start), _iso(latest)),
        "same_period_last_year": (_iso(sply_start), _iso(sply_end)),
        "holidays_in_this_month": holidays,
        "is_holiday_today": is_holiday,
    }
    partial["prompt_block"] = _build_prompt_block(partial)

    return TimeContext(**partial)
