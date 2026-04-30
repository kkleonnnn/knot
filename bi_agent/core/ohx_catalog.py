"""ohx_catalog.py — OHX 数据仓库表目录与业务词典（v0.2.3）

来源：/Users/kk/Documents/work_space/ohx_doris 下的 18 张 DDL（ohx_dwd 8 张 + ohx_ads 10 张）。
用途：
  1) schema_filter 根据问题选表时的"先验"——表 → 主题 → 关键词
  2) Clarifier / SQL Planner / Presenter prompt 可以直接引用业务词汇
  3) eval / few-shot 测试集的口径基准

业务约定（核心，全栈共用）：
  - 时区：所有 DWD 事件表都有 sta_time（UTC）+ sta_time_bjt（北京时间 UTC+8）。
    业务统计**默认走北京时间**：sta_time_bjt
  - 业务日：14:00 (UTC+8) 切日。今日 = [今日14:00, 明日14:00)。日报/周报/月报均按此口径。
  - 真实用户范围：user_id >= 10001000 AND user_id < 100000000，并排除测试号 10056103
  - 默认资产：USDT。涉及"充值/提现金额"且未指明币种时，加 asset='USDT'
  - 选表分层：
    * 单聚合指标 / 趋势 / 对比 → 优先 ohx_ads.ads_operation_report_{daily,weekly,monthly}
    * 用户名细（"哪些用户"、"列出 user_id"）→ ohx_dwd.dwd_user_*
    * 资产余额快照 → ohx_dwd.dwd_*_log_slice_balance_new / ohx_ads.ads_platform_balance
    * 活动专项 → ohx_ads.ads_arbitrage_tool_record_daily / ads_discount_buy_record_daily / ads_gen_ying_bao_detail_record_daily / ads_struct_arbitrage_record_daily
"""


# ── 表目录 ────────────────────────────────────────────────────────────────────
# topics: 一组业务主题标签，与下方 LEXICON 中的主题一一对应，用于"主题命中"加分
# always_include_when: 关键词命中时，无论评分高低都要把此表带上（兜底）
TABLES = [
    # ── ohx_dwd（用户事件 / 余额明细）─────────────────────────────
    {
        "db": "ohx_dwd", "table": "dwd_user_reg",
        "topics": ["注册", "邀请", "代理"],
        "summary": "用户注册明细：sta_time_bjt + user_id + register_ip + invitees_id(邀请人) + root_id(代理) + nick_name",
    },
    {
        "db": "ohx_dwd", "table": "dwd_user_deposit",
        "topics": ["充值", "入金", "首充"],
        "summary": "用户充值明细：sta_time_bjt + user_id + asset(币种) + deposit(金额)。USDT 净充值常用。",
    },
    {
        "db": "ohx_dwd", "table": "dwd_user_deal",
        "topics": ["交易", "合约交易量", "现货交易量"],
        "summary": "用户交易明细：sta_time_bjt + user_id + future_match_amt(合约交易量) + spot_match_amt(现货交易量)",
    },
    {
        "db": "ohx_dwd", "table": "dwd_perpetual_log_slice_balance_new",
        "topics": ["合约余额", "永续余额"],
        "summary": "永续合约用户余额快照：user_id + asset + market + balance(合约余额)",
    },
    {
        "db": "ohx_dwd", "table": "dwd_trade_log_slice_balance_new",
        "topics": ["现货余额"],
        "summary": "现货用户余额快照：user_id + account + asset + balance(现货余额) + update_time",
    },
    {
        "db": "ohx_dwd", "table": "dwd_sign_price_history",
        "topics": ["价格", "币价", "标记价格"],
        "summary": "参照合约日均价：sta_date + asset + price",
    },
    {
        "db": "ohx_dwd", "table": "static_future_user_list",
        "topics": ["合约做市", "做市账号"],
        "summary": "合约做市账号清单：user_id + asset_usdt(交易对) + usdt_initial(期初USDT)",
    },
    {
        "db": "ohx_dwd", "table": "static_spot_user_list",
        "topics": ["现货做市", "做市账号"],
        "summary": "现货做市账号清单：user_id + asset_usdt + token_initial + usdt_initial",
    },
    # ── ohx_ads（运营聚合 / 报表）─────────────────────────────────
    {
        "db": "ohx_ads", "table": "ads_operation_report_daily",
        "topics": [
            "日报", "运营日报", "注册用户数", "活跃用户数", "充值用户数", "首充", "提现",
            "净充值", "合约用户数", "合约交易量", "现货用户数", "现货交易量",
            "手续费", "盈亏", "代理渠道", "散户",
        ],
        "summary": "运营日报（按 sta_date）：reg_user_num / active_user_num / first_deposit_user_num / "
                   "deposit / withdraw / net_deposit / future_user_num / future_match_amt / future_fee / future_pnl / "
                   "spot_user_num / spot_match_amt / spot_fee / spot_pnl / platform_pnl + 代理/散户拆分。",
    },
    {
        "db": "ohx_ads", "table": "ads_operation_report_weekly",
        "topics": ["周报", "运营周报"],
        "summary": "运营周报（sta_date varchar(23) 形如 '2026-W17'）：列与日报一致，按周聚合。",
    },
    {
        "db": "ohx_ads", "table": "ads_operation_report_monthly",
        "topics": ["月报", "运营月报"],
        "summary": "运营月报（sta_date varchar(7) 形如 '2026-04'）：列与日报一致，按月聚合。",
    },
    {
        "db": "ohx_ads", "table": "ads_platform_balance",
        "topics": ["平台余额", "总余额", "现货余额", "合约余额", "理财余额", "Cobo"],
        "summary": "平台资金余额日快照：sta_date + asset + price + 各项余额（spot/future/earn/cobo）+ 折合 USDT。",
    },
    {
        "db": "ohx_ads", "table": "ads_future_market",
        "topics": ["合约做市", "做市账号", "USDT 变化"],
        "summary": "合约做市账号每日：sta_date + user_id + asset_usdt + usdt_initial + balance_new + usdt_change",
    },
    {
        "db": "ohx_ads", "table": "ads_spot_market",
        "topics": ["现货做市", "做市账号", "Token 变化"],
        "summary": "现货做市账号每日：sta_date + user_id + asset_usdt + token_initial + usdt_initial + token_change + usdt_change + change_cost",
    },
    {
        "db": "ohx_ads", "table": "ads_arbitrage_tool_record_daily",
        "topics": ["套利工具", "套利", "结算订单", "100xt"],
        "summary": "套利工具日报：sta_date + target_token_name + order_num + settle_order_num + amount + token_amount(USDT) + discount_token_amount(PUSD) + lock_token_amount(100XT)",
    },
    {
        "db": "ohx_ads", "table": "ads_discount_buy_record_daily",
        "topics": ["折扣购", "PUSD", "用户收益"],
        "summary": "折扣购日报：sta_date + target_token_name + order_num + amount + token_amount + discount_token_amount + lock_token_amount + user_profit",
    },
    {
        "db": "ohx_ads", "table": "ads_gen_ying_bao_detail_record_daily",
        "topics": ["金鹰宝", "理财", "结算利息", "分润"],
        "summary": "金鹰宝（理财产品）日报：sta_date + product_name + order_num + order_user_num + total_amount + lock_amount + buy_fees + obtained_interest + settle_amount + profit_amount + pay_amount",
    },
    {
        "db": "ohx_ads", "table": "ads_struct_arbitrage_record_daily",
        "topics": ["结构化套利", "期权"],
        "summary": "结构化套利日报：sta_date + order_num + settle_order_num + token_amount + lock_token_amount + total_profit + arbitrage_profit + options_profit + futures_profit",
    },
]


# ── 业务词典：中文/英文短语 → 表全称列表（被命中的表得到主题加分）────────────
# 写法说明：key 是问题里可能出现的中/英文片段，value 是相关表的 full name 列表。
# 同一片段可指向多张表（按相关性排序）；scoring 阶段以**第一张**为最相关，往后递减。
LEXICON = {
    # 注册 / 邀请 / 代理
    "注册": ["ohx_dwd.dwd_user_reg", "ohx_ads.ads_operation_report_daily"],
    "新增用户": ["ohx_ads.ads_operation_report_daily", "ohx_dwd.dwd_user_reg"],
    "邀请": ["ohx_dwd.dwd_user_reg"],
    "代理": ["ohx_dwd.dwd_user_reg", "ohx_ads.ads_operation_report_daily"],
    "散户": ["ohx_ads.ads_operation_report_daily"],
    "渠道": ["ohx_ads.ads_operation_report_daily"],
    # 活跃 / 留存
    "活跃": ["ohx_ads.ads_operation_report_daily"],
    "DAU": ["ohx_ads.ads_operation_report_daily"],
    # 充值 / 提现
    "充值": ["ohx_dwd.dwd_user_deposit", "ohx_ads.ads_operation_report_daily"],
    "入金": ["ohx_dwd.dwd_user_deposit", "ohx_ads.ads_operation_report_daily"],
    "首充": ["ohx_ads.ads_operation_report_daily"],
    "提现": ["ohx_ads.ads_operation_report_daily"],
    "出金": ["ohx_ads.ads_operation_report_daily"],
    "净充值": ["ohx_ads.ads_operation_report_daily"],
    # 交易（合约 / 现货）
    "合约交易量": ["ohx_dwd.dwd_user_deal", "ohx_ads.ads_operation_report_daily"],
    "合约交易": ["ohx_dwd.dwd_user_deal", "ohx_ads.ads_operation_report_daily"],
    "现货交易量": ["ohx_dwd.dwd_user_deal", "ohx_ads.ads_operation_report_daily"],
    "现货交易": ["ohx_dwd.dwd_user_deal", "ohx_ads.ads_operation_report_daily"],
    "手续费": ["ohx_ads.ads_operation_report_daily"],
    "盈亏": ["ohx_ads.ads_operation_report_daily", "ohx_ads.ads_platform_balance"],
    "PnL": ["ohx_ads.ads_operation_report_daily"],
    # 余额 / 资产
    "余额": ["ohx_ads.ads_platform_balance", "ohx_dwd.dwd_perpetual_log_slice_balance_new", "ohx_dwd.dwd_trade_log_slice_balance_new"],
    "总余额": ["ohx_ads.ads_platform_balance"],
    "平台资金": ["ohx_ads.ads_platform_balance"],
    "Cobo": ["ohx_ads.ads_platform_balance"],
    "理财": ["ohx_ads.ads_platform_balance", "ohx_ads.ads_gen_ying_bao_detail_record_daily"],
    # 做市
    "做市": ["ohx_ads.ads_future_market", "ohx_ads.ads_spot_market", "ohx_dwd.static_future_user_list", "ohx_dwd.static_spot_user_list"],
    "做市账号": ["ohx_dwd.static_future_user_list", "ohx_dwd.static_spot_user_list"],
    # 价格
    "价格": ["ohx_dwd.dwd_sign_price_history"],
    "币价": ["ohx_dwd.dwd_sign_price_history"],
    "标记价格": ["ohx_dwd.dwd_sign_price_history"],
    # 套利 / 折扣购 / 金鹰宝 / 结构化
    "套利": ["ohx_ads.ads_arbitrage_tool_record_daily", "ohx_ads.ads_struct_arbitrage_record_daily"],
    "套利工具": ["ohx_ads.ads_arbitrage_tool_record_daily"],
    "结构化": ["ohx_ads.ads_struct_arbitrage_record_daily"],
    "期权": ["ohx_ads.ads_struct_arbitrage_record_daily"],
    "折扣购": ["ohx_ads.ads_discount_buy_record_daily"],
    "PUSD": ["ohx_ads.ads_discount_buy_record_daily", "ohx_ads.ads_arbitrage_tool_record_daily"],
    "100XT": ["ohx_ads.ads_arbitrage_tool_record_daily", "ohx_ads.ads_discount_buy_record_daily"],
    "金鹰宝": ["ohx_ads.ads_gen_ying_bao_detail_record_daily"],
    # 周/月聚合（命中即提级到 weekly/monthly 表）
    "周报": ["ohx_ads.ads_operation_report_weekly"],
    "月报": ["ohx_ads.ads_operation_report_monthly"],
    "本周": ["ohx_ads.ads_operation_report_weekly", "ohx_ads.ads_operation_report_daily"],
    "上周": ["ohx_ads.ads_operation_report_weekly", "ohx_ads.ads_operation_report_daily"],
    "本月": ["ohx_ads.ads_operation_report_monthly", "ohx_ads.ads_operation_report_daily"],
    "上月": ["ohx_ads.ads_operation_report_monthly", "ohx_ads.ads_operation_report_daily"],
}


# ── 业务规则常量（供 prompt / few-shot 引用）────────────────────────────────
BUSINESS_RULES = """## OHX 业务规则（必须遵守）

### 时区与时间字段
- DWD 事件表均有 `sta_time`（UTC）和 `sta_time_bjt`（北京时间 UTC+8）。**默认用 sta_time_bjt**。
- 业务日切日时间：UTC+8 14:00。即"今日"= [今日 14:00, 明日 14:00)，例如 4 月 27 日的业务日 = '2026-04-27 14:00:00' ≤ sta_time_bjt < '2026-04-28 14:00:00'。
- ADS 表用 `sta_date`（DATE / VARCHAR）：日报 DATE、周报 'YYYY-Www'、月报 'YYYY-MM'。

### 真实用户范围 & 测试号排除
- 真实用户：`user_id >= 10001000 AND user_id < 100000000`
- 排除测试号：`AND user_id <> 10056103`
- 凡涉及奖励/活动/真实业务结果时，以上三条 WHERE **必须同时存在**。

### 默认资产
- 涉及"充值/提现金额"或"净充值"未指明币种时，加 `asset = 'USDT'`。

### 表分层选择
- 单一聚合指标（"昨天注册多少人"、"上月 GMV"、"本周新用户数"）→ 直接走 `ads_operation_report_{daily,weekly,monthly}`。
- 需要列出 user_id / 用户明细 → 走 `dwd_user_*`。
- "余额 / 总资金" → `ads_platform_balance`（按 sta_date 取最新一天）。
- 套利 / 折扣购 / 金鹰宝 / 结构化 → 各自的 `ads_*_record_daily`。

### 字段命名提示
- `future_*` 前缀 = 合约相关；`spot_*` 前缀 = 现货相关
- `*_user_num` = 用户数；`*_match_amt` = 交易量；`*_fee` = 手续费；`*_pnl` = 已实现盈亏
- `first_*` = 首次（如 first_deposit_user_num = 首充用户数）
"""


def get_table_full_names() -> list:
    return [f"{t['db']}.{t['table']}" for t in TABLES]


def get_table_meta(full_name: str) -> dict:
    """通过 'db.table' 取元数据，无匹配返回 None。"""
    for t in TABLES:
        if f"{t['db']}.{t['table']}" == full_name or t["table"] == full_name:
            return t
    return None
