"""ohx_catalog.example.py — 业务目录与词典模板（仓库内提交版本，**不含真实业务数据**）

【部署步骤】
  cp knot/core/ohx_catalog.example.py knot/core/ohx_catalog.py
然后按本项目实际业务，编辑 ohx_catalog.py（已加入 .gitignore，不会进 git）。

本模板用通用电商示例展示三个对象的结构契约：
  - TABLES        : list[dict]，给 schema_filter 做主题加分
  - LEXICON       : dict[str, list[str]]，业务词 → 表全名优先级队列
  - BUSINESS_RULES: str，注入到 3 个 agent 的 system prompt

业务方需要保持这三个名字与字段结构不变。schema_filter / multi_agent / sql_agent 通过
catalog_loader 加载本模块，缺失时自动 fallback 到本 example，不会让程序崩溃。
"""


# ── 表目录（示例：通用电商）───────────────────────────────────────────────────
TABLES = [
    {
        "db": "demo_dwd", "table": "dwd_user_reg",
        "topics": ["注册", "新用户"],
        "summary": "用户注册明细：created_at + user_id + channel",
    },
    {
        "db": "demo_dwd", "table": "dwd_order",
        "topics": ["订单", "支付", "GMV"],
        "summary": "订单明细：created_at + user_id + product_id + pay_amount",
    },
    {
        "db": "demo_ads", "table": "ads_daily_report",
        "topics": ["日报", "新增用户", "GMV", "活跃用户"],
        "summary": "运营日报：sta_date + new_user_num + active_user_num + gmv + paid_user_num",
    },
]


# ── 业务词典：问题片段 → 表全名（按相关性排序）─────────────────────────────
LEXICON = {
    "注册":     ["demo_dwd.dwd_user_reg", "demo_ads.ads_daily_report"],
    "新增用户": ["demo_ads.ads_daily_report", "demo_dwd.dwd_user_reg"],
    "订单":     ["demo_dwd.dwd_order"],
    "GMV":      ["demo_ads.ads_daily_report", "demo_dwd.dwd_order"],
    "活跃":     ["demo_ads.ads_daily_report"],
    "日报":     ["demo_ads.ads_daily_report"],
}


# ── 业务规则常量（注入到 3 个 agent prompt）──────────────────────────────────
BUSINESS_RULES = """## 业务规则（示例 — 请按实际业务替换）

### 时区与时间字段
- 默认时区 Asia/Shanghai；事件表的时间字段统一以 created_at 为准。

### 真实用户范围
- 排除内部测试号（按实际 user_id 区间填写）。

### 默认资产 / 货币
- 金额字段未指明币种时，默认 CNY。

### 表分层选择
- 单聚合指标（"昨天注册多少人"、"上月 GMV"）→ 走 ads_daily_report 等聚合层。
- 用户明细（列出 user_id）→ 走 dwd_* 明细层。

### 字段命名约定
- *_user_num = 用户数；*_amount / gmv = 金额；*_pnl = 盈亏。
"""


def get_table_full_names() -> list:
    return [f"{t['db']}.{t['table']}" for t in TABLES]


# ── v0.4.1.1：表关联元数据 RELATIONS（多表 JOIN ON 知识源）────────────────────
# 格式：list[tuple(left_table_full, left_column, right_table_full, right_column, semantics)]
# 用于 sql_planner / llm_client 拼接 prompt 时按需注入"必须 JOIN ... ON ..."的关联字段，
# 阻止 LLM 生成 `FROM a, b WHERE ...` 旧式笛卡尔积写法。
#
# 维护要求：真实 ohx_catalog.py（gitignored）合入 v0.4.1.1 后 7 天内必须按 OHX 实际
# Schema 补充本列表，否则真实业务库的笛卡尔积问题不会修复。
RELATIONS = [
    # 订单与注册用户：通过 user_id 关联
    ("demo_dwd.dwd_order", "user_id", "demo_dwd.dwd_user_reg", "user_id",
     "订单与注册用户：订单的下单用户即注册表中的 user_id"),
    # 渠道日报与全量日报：通过业务日期 sta_date 关联
    ("demo_ads.ads_daily_report_by_channel", "sta_date", "demo_ads.ads_daily_report", "sta_date",
     "渠道日报与全量日报：通过 sta_date 关联同一业务日"),
]


def get_table_meta(full_name: str) -> dict:
    for t in TABLES:
        if f"{t['db']}.{t['table']}" == full_name or t["table"] == full_name:
            return t
    return None
