"""tests/eval/conftest.py — pytest fixtures: 加载 cases.yaml 并把 bi_agent/core 加进 sys.path。

v0.2.3 起 fake_schema 改用 OHX 真实 18 张表的简化版（来自
/Users/kk/Documents/work_space/ohx_doris 的 DDL）。
"""
import sys
from pathlib import Path

import yaml
import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "bi_agent" / "core"))

CASES_FILE = Path(__file__).parent / "cases.yaml"


def load_cases():
    with open(CASES_FILE, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("cases", [])


_OHX_SCHEMA = """## ohx_dwd.dwd_user_reg
- sta_time (DATETIME) 注册时间(UTC)
- sta_time_bjt (DATETIME) 注册时间(北京时间, UTC+8)
- user_id (BIGINT)
- register_ip (VARCHAR)
- invitees_id (BIGINT) 邀请人 user_id
- root_id (BIGINT) 代理 user_id
- nick_name (VARCHAR) 代理昵称

## ohx_dwd.dwd_user_deposit
- sta_time (DATETIME)
- sta_time_bjt (DATETIME) 北京时间
- user_id (BIGINT)
- asset (VARCHAR) 币种
- deposit (DECIMAL) 充值金额

## ohx_dwd.dwd_user_deal
- sta_time (DATETIME)
- sta_time_bjt (DATETIME) 北京时间
- user_id (BIGINT)
- future_match_amt (DECIMAL) 合约交易量
- spot_match_amt (DECIMAL) 现货交易量

## ohx_dwd.dwd_perpetual_log_slice_balance_new
- id (LARGEINT)
- user_id (LARGEINT)
- asset (VARCHAR)
- market (VARCHAR)
- type (SMALLINT)
- balance (DECIMAL) 合约余额

## ohx_dwd.dwd_trade_log_slice_balance_new
- id (LARGEINT)
- user_id (LARGEINT)
- account (LARGEINT)
- asset (VARCHAR)
- t (SMALLINT)
- balance (DECIMAL) 现货余额
- update_time (DECIMAL)

## ohx_dwd.dwd_sign_price_history
- sta_date (DATE)
- asset (VARCHAR)
- price (DECIMAL) 参照合约日均价

## ohx_dwd.static_future_user_list
- user_id (BIGINT) 合约做市账号
- asset_usdt (VARCHAR) 交易对
- usdt_initial (DECIMAL) 期初USDT

## ohx_dwd.static_spot_user_list
- user_id (BIGINT) 现货做市账号
- asset_usdt (VARCHAR) 交易对
- token_initial (DECIMAL) 期初Token
- usdt_initial (DECIMAL) 期初USDT

## ohx_ads.ads_operation_report_daily
- sta_date (DATE)
- reg_user_num (BIGINT) 注册用户数
- reg_user_num_agent (BIGINT) 代理渠道注册数
- reg_user_num_normal (BIGINT) 散户注册数
- invitees_num (BIGINT) 注册代理渠道数
- active_user_num (BIGINT) 活跃用户数
- active_agent_num (BIGINT) 活跃代理渠道数
- first_deposit_user_num (BIGINT) 首充用户数
- deposit_user_num (BIGINT) 充值用户数
- deposit (DECIMAL) 充值金额
- withdraw_user_num (BIGINT) 提现用户数
- withdraw (DECIMAL) 提现金额
- withdraw_fee (DECIMAL) 提现手续费
- net_deposit (DECIMAL) 净充值
- first_future_user_num (BIGINT) 首次合约交易用户数
- future_user_num (BIGINT) 合约交易用户数
- future_match_amt (DECIMAL) 合约交易量
- future_fee (DECIMAL) 合约手续费
- future_commisson (DECIMAL) 合约返佣
- future_pnl (DECIMAL) 合约已实现盈亏
- first_spot_user_num (BIGINT) 首次现货交易用户数
- spot_user_num (BIGINT) 现货交易用户数
- spot_match_amt (DECIMAL) 现货交易量
- spot_fee (DECIMAL) 现货手续费
- spot_pnl (DECIMAL) 现货已实现盈亏
- platform_pnl (DECIMAL) 平台总盈亏

## ohx_ads.ads_operation_report_weekly
- sta_date (VARCHAR) 形如 '2026-W17'
- (其余列与日报相同)

## ohx_ads.ads_operation_report_monthly
- sta_date (VARCHAR) 形如 '2026-04'
- (其余列与日报相同)

## ohx_ads.ads_platform_balance
- sta_date (DATE)
- asset (VARCHAR)
- price (DECIMAL)
- balance (DECIMAL)
- spot_balance (DECIMAL) 现货余额
- future_balance (DECIMAL) 合约余额
- earn_balance (DECIMAL) 理财余额
- total_balance (DECIMAL) 总余额
- total_balance_usdt (DECIMAL) 总余额折合USDT
- spot_pnl (DECIMAL) 现货已实现盈亏
- spot_fee (DECIMAL) 现货手续费
- future_pnl (DECIMAL) 合约已实现盈亏
- future_fee (DECIMAL) 合约手续费
- cobo_balance (DECIMAL)
- cobo_balance_usdt (DECIMAL)

## ohx_ads.ads_future_market
- sta_date (DATE)
- user_id (BIGINT)
- asset_usdt (VARCHAR)
- usdt_initial (DECIMAL)
- balance_new (DECIMAL)
- usdt_change (DECIMAL)

## ohx_ads.ads_spot_market
- sta_date (DATE)
- user_id (BIGINT)
- asset_usdt (VARCHAR)
- token_initial (DECIMAL)
- usdt_initial (DECIMAL)
- token_new (DECIMAL)
- usdt_new (DECIMAL)
- token_change (DECIMAL)
- usdt_change (DECIMAL)
- change_cost (DECIMAL)

## ohx_ads.ads_arbitrage_tool_record_daily
- sta_date (DATE)
- target_token_name (VARCHAR)
- order_num (BIGINT) 订单数
- settle_order_num (BIGINT) 结算订单数
- amount (DECIMAL)
- token_amount (DECIMAL) 投入USDT
- discount_token_amount (DECIMAL) 折扣PUSD
- lock_token_amount (DECIMAL) 锁定100XT
- settle_token_amount (DECIMAL)
- settle_discount_token_amount (DECIMAL)
- unlock_token_amount (DECIMAL)

## ohx_ads.ads_discount_buy_record_daily
- sta_date (DATE)
- target_token_name (VARCHAR)
- order_num (BIGINT)
- settle_order_num (BIGINT)
- amount (DECIMAL) 购买金额
- token_amount (DECIMAL)
- discount_token_amount (DECIMAL)
- lock_token_amount (DECIMAL)
- user_profit (DECIMAL) 用户收益

## ohx_ads.ads_gen_ying_bao_detail_record_daily
- sta_date (DATE)
- product_name (VARCHAR)
- order_num (BIGINT)
- order_user_num (BIGINT)
- total_amount (DECIMAL)
- lock_amount (DECIMAL)
- buy_fees (DECIMAL)
- obtained_interest (DECIMAL) 结算利息
- settle_amount (DECIMAL)
- profit_amount (DECIMAL)
- pay_amount (DECIMAL)

## ohx_ads.ads_struct_arbitrage_record_daily
- sta_date (DATE)
- order_num (BIGINT)
- settle_order_num (BIGINT)
- token_amount (DECIMAL)
- lock_token_amount (DECIMAL)
- total_profit (DECIMAL)
- arbitrage_profit (DECIMAL)
- options_profit (DECIMAL)
- futures_profit (DECIMAL)
"""


@pytest.fixture(scope="session")
def fake_schema():
    return _OHX_SCHEMA
