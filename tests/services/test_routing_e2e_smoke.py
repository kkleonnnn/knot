"""v0.6.2.1 commit 4 — F4.4 e38de5e76703 类链路 e2e 回归 smoke

生产 bug 链路回归（2026-05-25 demo 后业务方反馈）：
  1. catalog 重建后丢 source_type → pick_http_route 静默 fallback SQL（C1 修）
  2. "历史持仓" 误路由 HTTP 当前持仓表（C2 Layer 3 修）
  3. sql_planner 输出非 SQL 中文 fail-open 当 SQL 给 presenter（C3 修）

NRP-C3：e2e mock 边界明示 — 用 monkeypatch 模拟 catalog + DataSource，
不依赖真实业务方 admin API（防 CI 间歇失败）。
"""
from unittest.mock import patch

from knot.services import http_planner
from knot.services.agents import catalog as catalog_loader
from knot.services.agents.sql_planner_tools import (
    _VALID_SQL_OPENERS,
    _get_first_sql_keyword,
)

# ─── e2e Bug 1 — catalog source_type 推断兜底（C1）────────────────


def test_e2e_bug1_catalog_infers_http_after_rebuild():
    """e38de5e76703 Bug 1：catalog 表丢 source_type → C1 从 DataSource 推断兜底。

    模拟 admin UI 重建 catalog（丢 source_type 字段）→ _infer_source_types_from_datasources
    从 db_type='http' DataSource 推断回 source_type='http'。
    """
    tables = [
        {"db": "futures_admin", "table": "futures_position_list", "topics": ["持仓"]},
    ]
    mock_ds = [{"db_type": "http", "db_database": "futures_admin"}]
    with patch("knot.repositories.data_source_repo.list_datasources", return_value=mock_ds):
        result = catalog_loader._infer_source_types_from_datasources(tables)
    assert result[0]["source_type"] == "http", \
        "Bug 1 回归：catalog 重建丢 source_type → 从 DataSource db_type=http 推断兜底"


# ─── e2e Bug 2 — 历史持仓不再误路由 HTTP（C2 Layer 3）────────────


def test_e2e_bug2_history_position_routes_sql_not_http(monkeypatch):
    """e38de5e76703 Bug 2："历史持仓" → Layer 3 exclusion → SQL（非 HTTP 当前持仓表）。"""
    mock_lex = {"持仓": ["futures_admin.futures_position_list",
                        "ohx_dwd.dwd_user_position_history"]}
    http_tables = {"futures_admin.futures_position_list"}
    monkeypatch.setattr(catalog_loader, "reload", lambda strict=False: "mock")
    monkeypatch.setattr(catalog_loader, "LEXICON", mock_lex)
    monkeypatch.setattr(catalog_loader, "is_http_table", lambda t: t in http_tables)
    monkeypatch.setattr(catalog_loader, "get_http_spec",
                        lambda t: {"url_template": "x", "method": "GET"} if t in http_tables else None)

    # 历史持仓 → SQL（不走 HTTP 当前持仓表）
    assert http_planner.pick_http_route("用户 1000260 历史持仓") is None
    # 当前持仓 → HTTP（对照组）
    result = http_planner.pick_http_route("用户 1000260 当前持仓")
    assert result is not None and result[0] == "futures_admin.futures_position_list"


# ─── e2e Bug 3 — sql_planner 非 SQL 中文拒识（C3）────────────────


def test_e2e_bug3_chinese_non_sql_rejected():
    """e38de5e76703 Bug 3：LLM 输出"无法直接 SQL 查询 HTTP 虚拟表"中文 → 拒识（不当 SQL）。"""
    # 生产实际 LLM 输出原文（demo 后业务方反馈截图）
    llm_output = "无法直接使用 SQL 查询 HTTP 虚拟表。查询用户当前持仓挂单情况需要通过其他方式获取数据，请联系相关人员。"
    opener = _get_first_sql_keyword(llm_output)
    assert opener not in _VALID_SQL_OPENERS, \
        "Bug 3 回归：中文非 SQL 输出必拒识（不 fail-open 当 SQL 给 presenter）"


def test_e2e_bug3_valid_sql_still_accepted():
    """对照组：合法 SELECT/WITH 仍正常接受（C3 不误杀正常 SQL）。"""
    assert _get_first_sql_keyword("SELECT id FROM users WHERE active=1") in _VALID_SQL_OPENERS
    assert _get_first_sql_keyword("WITH t AS (SELECT 1) SELECT * FROM t") in _VALID_SQL_OPENERS


# ─── 三层联动 e2e — 完整路由决策链 ───────────────────────────────


def test_e2e_full_routing_decision_chain(monkeypatch):
    """完整三层路由决策链：当前持仓→HTTP / 历史持仓→SQL / 无关问题→SQL（None）。"""
    mock_lex = {"持仓": ["futures_admin.futures_position_list",
                        "ohx_dwd.dwd_user_position_history"]}
    http_tables = {"futures_admin.futures_position_list"}
    monkeypatch.setattr(catalog_loader, "reload", lambda strict=False: "mock")
    monkeypatch.setattr(catalog_loader, "LEXICON", mock_lex)
    monkeypatch.setattr(catalog_loader, "is_http_table", lambda t: t in http_tables)
    monkeypatch.setattr(catalog_loader, "get_http_spec",
                        lambda t: {"url_template": "x", "method": "GET"} if t in http_tables else None)

    # Layer 1：当前持仓 → HTTP
    assert http_planner.pick_http_route("平台 BTC 当前持仓") is not None
    # Layer 3：历史持仓 → SQL
    assert http_planner.pick_http_route("平台 BTC 历史持仓") is None
    # 无 lexicon 命中：注册用户 → SQL（None）
    assert http_planner.pick_http_route("今天注册用户数") is None


# ─── v0.7.20 B — http_table_in_sql 检测 HTTP 虚拟表 SQL 误引用 ────────────


def test_http_table_in_sql_detects_virtual_table(monkeypatch):
    """v0.7.20 B（守护者 Stage 3 LOCKED）：pick_http_route 漏路由 → sql_planner 误把 HTTP
    虚拟表当真库写 `SELECT … FROM futures_admin.X` → http_table_in_sql 检测到 → query.py
    失败分支改报友好 data_unavailable（替代原始 Unknown database + 防 presenter 幻觉）。"""
    monkeypatch.setattr(
        http_planner.catalog_loader, "is_http_table",
        lambda n: n == "futures_admin.futures_position_list",
    )
    # 命中：误对 HTTP 虚拟表写的 SQL → 返虚拟表全名（"db.table"，与 is_http_table 入参一致）
    assert http_planner.http_table_in_sql(
        "SELECT market, side FROM futures_admin.futures_position_list WHERE side = 2"
    ) == "futures_admin.futures_position_list"
    # 不误伤：普通 SQL 表（problem 2 Unknown column 走 ② 原样透传）
    assert http_planner.http_table_in_sql(
        "SELECT market, SUM(profit_real) FROM ohx_dwd.dwd_user_position_history GROUP BY market"
    ) is None
    # fail-open：畸形 SQL / 空 不崩（R-SL-155）
    assert http_planner.http_table_in_sql("SELECT FROM WHERE 注：乱七八糟") is None
    assert http_planner.http_table_in_sql("") is None


def test_failure_error_meta_three_cases(monkeypatch):
    """v0.7.20 R-SL-155（守护者 Stage 3）：查询失败 3 子case 元数据（纯函数·可单测）。"""
    monkeypatch.setattr(
        http_planner.catalog_loader, "is_http_table",
        lambda n: n == "futures_admin.futures_position_list",
    )
    # ① HTTP 虚拟表（优先 — 即便 has_db_error=True，如 Unknown database 'futures_admin'）→ data_unavailable + 指引
    k, m = http_planner.failure_error_meta(
        "SELECT * FROM futures_admin.futures_position_list", has_db_error=True)
    assert k == "data_unavailable" and "当前" in m and "实时持仓" in m
    # ② ReAct 放弃（无 SQL 无错）→ sql_invalid + 兜底（防失败分支空白）
    k, m = http_planner.failure_error_meta("", has_db_error=False)
    assert k == "sql_invalid" and "未能生成有效查询" in m
    # ③ 普通 DB 错（非 http）→ 原样透传 (None, None)（不误伤 problem 2 Unknown column）
    k, m = http_planner.failure_error_meta(
        "SELECT market FROM ohx_dwd.dwd_user_future_deal", has_db_error=True)
    assert k is None and m is None


def test_should_run_presenter_gate_four_cases():
    """v0.7.20 A gate（守护者 Stage 3 + adversarial 复核纠正）：present iff success AND not error。
    ⭐ 核心：单 `not success` 会漏「有 SQL 但执行失败」(success=True/error set) = problem 1/2 本身
    （execute_query 出错返 ([], err) 非 None → success 恒 True）。本测锁住纠正后的 predicate 防回归。"""
    from knot.services.query_steps import should_run_presenter
    assert should_run_presenter(True, "") is True                                   # 成功（含真空 rows=[]）→ present（真空说「无数据」合法）
    assert should_run_presenter(True, "字段不存在: Unknown column 'market'") is False    # ⭐ DB 错 success=True/error set → 跳（problem 2 核心）
    assert should_run_presenter(True, "Unknown database 'futures_admin'") is False    # ⭐ problem 1
    assert should_run_presenter(False, "") is False                                 # ReAct 放弃（无 SQL）→ 跳
    assert should_run_presenter(False, "boom") is False
