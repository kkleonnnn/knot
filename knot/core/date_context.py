"""date_context.py — 日期口径上下文（v0.2.3）

所有 agent prompt 共用，避免 LLM 把"昨天/本周/上月"映射到训练截止时间。
统一时区到 Asia/Shanghai；服务器即使跑在 UTC 也按业务时区出值。
"""

from datetime import date, timedelta

try:
    from zoneinfo import ZoneInfo
    _TZ = ZoneInfo("Asia/Shanghai")
except Exception:
    _TZ = None


def today() -> date:
    if _TZ is not None:
        from datetime import datetime
        return datetime.now(_TZ).date()
    return date.today()


def today_iso() -> str:
    return today().isoformat()


def date_context_block() -> str:
    """返回 prompt 用的日期口径块（多行字符串）。

    枚举常用相对日期 → 绝对日期，避免 LLM 把"昨天"算成训练时间或者今日。
    """
    t = today()
    yest = t - timedelta(days=1)
    dby = t - timedelta(days=2)
    last_7_start = t - timedelta(days=6)
    last_30_start = t - timedelta(days=29)

    weekday = t.weekday()  # 周一=0
    this_week_mon = t - timedelta(days=weekday)
    last_week_mon = this_week_mon - timedelta(days=7)
    last_week_sun = this_week_mon - timedelta(days=1)

    this_month_first = t.replace(day=1)
    if this_month_first.month == 1:
        last_month_first = this_month_first.replace(year=this_month_first.year - 1, month=12)
    else:
        last_month_first = this_month_first.replace(month=this_month_first.month - 1)
    last_month_last = this_month_first - timedelta(days=1)

    return (
        f"今日：{t.isoformat()}（时区 Asia/Shanghai，系统时间，权威）\n"
        f"日期口径（业务约定，必须按此对应）：\n"
        f"  - 今天 = {t.isoformat()}\n"
        f"  - 昨天 = {yest.isoformat()}\n"
        f"  - 前天 = {dby.isoformat()}\n"
        f"  - 最近 7 天 = [{last_7_start.isoformat()}, {t.isoformat()}]\n"
        f"  - 最近 30 天 = [{last_30_start.isoformat()}, {t.isoformat()}]\n"
        f"  - 本周 = [{this_week_mon.isoformat()}, {t.isoformat()}]（周一至今日）\n"
        f"  - 上周 = [{last_week_mon.isoformat()}, {last_week_sun.isoformat()}]（周一至周日）\n"
        f"  - 本月 = [{this_month_first.isoformat()}, {t.isoformat()}]\n"
        f"  - 上月 = [{last_month_first.isoformat()}, {last_month_last.isoformat()}]\n"
        f"约束：≤ 今日的任何日期都是历史日期；不要因模型训练截止时间把它判定为未来。"
        f"SQL 中使用 CURDATE()/NOW() 时，等价于今日。"
    )
