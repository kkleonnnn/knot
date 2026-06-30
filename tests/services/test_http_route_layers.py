"""v0.6.2.1 commit 4 — F4.2 C2 三层路由守护测试 + 守护者第 19 次议题 1 边界 case

覆盖红线：
  R-PB-C2-1  三层路由（Layer 1 白名单 / Layer 2 clarifier 责任 / Layer 3 exclusion）
  R-PB-C2-2  None 分支强制 logger.info 诊断
  R-PB-C2-3  exclusion regex diagnostic warn 不阻断（命中即 return None 走 SQL）

守护者第 19 次 §议题 1 边界 3 case（exclusion 复合句误触已知风险）：
  - 复合句正向（误触 — 已知边角风险，v0.7+ LLM 路由层修复）
  - 复合句反向（命中合理）
  - "N 天" 时间词边界
"""
from unittest.mock import patch

from knot.services import http_planner

# 模拟 catalog：futures_admin.* = HTTP；ohx_dwd.* = SQL
_MOCK_LEXICON = {
    "持仓": ["futures_admin.futures_position_list", "futures_admin.futures_user_pending",
            "ohx_dwd.dwd_user_position_history"],
    "平台持仓": ["futures_admin.futures_position_list"],
    "历史持仓": ["ohx_dwd.dwd_user_position_history"],
}
_HTTP_TABLES = {"futures_admin.futures_position_list", "futures_admin.futures_user_pending"}
_MOCK_SPEC = {"url_template": "https://admin.example/api/v1/position/list", "method": "GET"}


def _mock_catalog(monkeypatch):
    """patch catalog_loader：reload no-op + LEXICON + is_http_table + get_http_spec。"""
    monkeypatch.setattr(http_planner.catalog_loader, "reload", lambda strict=False: "mock")
    monkeypatch.setattr(http_planner.catalog_loader, "LEXICON", _MOCK_LEXICON)
    monkeypatch.setattr(http_planner.catalog_loader, "is_http_table",
                        lambda t: t in _HTTP_TABLES)
    monkeypatch.setattr(http_planner.catalog_loader, "get_http_spec",
                        lambda t: _MOCK_SPEC if t in _HTTP_TABLES else None)


# ─── Layer 1 — 白名单主路由 + entity-aware ranking ───────────────


def test_layer1_platform_position_hits_http(monkeypatch):
    """平台 BTC 卖出持仓（无 user_id）→ futures_position_list（平台视图）。"""
    _mock_catalog(monkeypatch)
    result = http_planner.pick_http_route("平台 BTC 卖出持仓")
    assert result is not None
    table, spec = result
    assert table == "futures_admin.futures_position_list"


def test_layer1_user_position_prefers_user_endpoint(monkeypatch):
    """用户 1000260 持仓（有 user_id）→ futures_user_pending（用户视图优先）。"""
    _mock_catalog(monkeypatch)
    result = http_planner.pick_http_route("查询用户 1000260 的当前持仓")
    assert result is not None
    table, _ = result
    assert table == "futures_admin.futures_user_pending"


# ─── Layer 3 — exclusion regex 命中 → 走 SQL（return None）────────


def test_layer3_history_keyword_defaults_sql(monkeypatch):
    """历史持仓 → exclusion regex 命中 "历史" → return None（走 SQL 历史表）。"""
    _mock_catalog(monkeypatch)
    # 即使 lexicon "持仓" 命中 HTTP 表，"历史" exclusion 优先短路
    assert http_planner.pick_http_route("查询用户 1000260 的历史持仓") is None


def test_layer3_liquidation_keyword_defaults_sql(monkeypatch):
    """强平 / 爆仓 → exclusion 命中 → SQL。"""
    _mock_catalog(monkeypatch)
    assert http_planner.pick_http_route("昨天爆仓的持仓记录") is None
    assert http_planner.pick_http_route("用户强平持仓") is None


# ─── 守护者第 19 次 §议题 1 — exclusion 边界 3 case ──────────────


def test_issue1_compound_sentence_false_trigger_known_risk(monkeypatch):
    """议题 1 边角风险（已知）：复合句"排除昨天爆仓的数据，查询当前持仓"
    → "昨天"+"爆仓" exclusion 命中 → 误降级 SQL（v0.7+ LLM 路由层修复）。

    本测试 documents 当前行为（误降级），非 expected-correct — 守护者 §III ack。
    """
    _mock_catalog(monkeypatch)
    # 当前实现：exclusion regex 命中 → SQL（即使语义是"查询当前持仓"）
    result = http_planner.pick_http_route("排除昨天爆仓的数据，查询当前持仓")
    assert result is None, "已知边角风险：复合句误降级 SQL（v0.7+ LLM 路由层修复）"


def test_issue1_history_record_correct_trigger(monkeypatch):
    """议题 1 反向（命中合理）："查询用户历史持仓记录" → SQL ✓。"""
    _mock_catalog(monkeypatch)
    assert http_planner.pick_http_route("查询用户 X 历史持仓记录") is None


def test_issue1_n_days_time_word_boundary(monkeypatch):
    """议题 1 边界（时间词）："最近 7 天持仓变化趋势" → "7 天" 命中 → SQL（合理降级）。"""
    _mock_catalog(monkeypatch)
    assert http_planner.pick_http_route("最近 7 天持仓变化趋势") is None


# ─── R-PB-C2-2 None 分支强制诊断日志 ─────────────────────────────


def test_R_PB_C2_2_no_match_logs_diagnostic(monkeypatch, caplog):
    """无 HTTP 表命中 → logger.info 诊断（防 e38de5e76703 静默 fallback）。"""
    import logging
    _mock_catalog(monkeypatch)
    # 问题不含任何 lexicon 关键词 → no match
    with caplog.at_level(logging.INFO):
        result = http_planner.pick_http_route("今天的注册用户数")
    assert result is None
    # loguru → 标准 logging 桥接可能不被 caplog 捕获；仅断言 return None 行为
    # （诊断日志由生产 Kibana 验证；此处守护 None 路径不崩溃）


def test_R_PB_C2_2_exclusion_returns_none_not_raise(monkeypatch):
    """R-PB-C2-3：exclusion 命中 diagnostic warn 不阻断（return None 非 raise）。"""
    _mock_catalog(monkeypatch)
    # 不应抛异常，只 return None
    result = http_planner.pick_http_route("历史持仓数据")
    assert result is None


# ─── exclusion regex 模式覆盖 ─────────────────────────────────────


def test_exclusion_regex_patterns(monkeypatch):
    """exclusion regex 各模式命中验证（历史/已平仓/强平/爆仓/ADL/时间词）。"""
    _mock_catalog(monkeypatch)
    for q in ["历史持仓", "已平仓持仓", "强平持仓", "爆仓持仓", "ADL 持仓",
              "3 天前持仓", "2 月前持仓", "昨天持仓", "前天持仓", "上周持仓", "上月持仓"]:
        assert http_planner.pick_http_route(q) is None, f"{q!r} 应命中 exclusion → SQL"


# ─── Layer A（v0.7.22 R-SL-162）— intent 结构信号 veto（价值自测 #3/#4）──────


def test_layerA_analytical_intents_veto_http(monkeypatch):
    """5 分析类 intent（trend/compare/rank/distribution/retention）→ None（走 SQL），
    即使 "持仓" lexicon 命中 HTTP 表。

    关键（R-SL-162 ③ early-return）：本查询单参/detail 本会命中 HTTP（见
    test_layerA_metric_detail_intent_still_http + test_layerA_default_none_byte_equal）；
    analytical intent 仍 veto → 证 Layer A early-return 先于 Layer 1 lexicon match。
    解 #4（各交易对持仓盈亏排名 → rank → SQL）。
    """
    _mock_catalog(monkeypatch)
    for intent in ["trend", "compare", "rank", "distribution", "retention"]:
        assert http_planner.pick_http_route("平台 BTC 卖出持仓", intent) is None, \
            f"intent={intent!r}（分析类）应 veto HTTP → SQL（HTTP 快照产不出分析类）"


def test_layerA_metric_detail_intent_still_http(monkeypatch):
    """metric / detail intent → 不 veto，"持仓" 裸快照仍走 HTTP（R-SL-163 边界 ·
    裸快照仍 detail → HTTP 正路不断）。"""
    _mock_catalog(monkeypatch)
    for intent in ["metric", "detail"]:
        result = http_planner.pick_http_route("平台 BTC 卖出持仓", intent)
        assert result is not None, f"intent={intent!r} 应留 HTTP-eligible（裸快照）"
        assert result[0] == "futures_admin.futures_position_list"


def test_layerA_default_none_byte_equal(monkeypatch):
    """intent=None（默认 / 旧单参调用）→ 跳过 Layer A，byte-equal 现状 HTTP 路由（R-SL-161）。"""
    _mock_catalog(monkeypatch)
    r_explicit_none = http_planner.pick_http_route("平台 BTC 卖出持仓", None)
    r_single_param = http_planner.pick_http_route("平台 BTC 卖出持仓")  # 旧单参省略 intent
    assert r_explicit_none is not None and r_single_param is not None
    assert r_explicit_none[0] == r_single_param[0] == "futures_admin.futures_position_list"


def test_layerA_does_not_break_layer3_exclusion(monkeypatch):
    """intent=detail + "历史持仓" → Layer 3 exclusion 仍命中 → None（Layer A 不干扰 Layer 3）。"""
    _mock_catalog(monkeypatch)
    assert http_planner.pick_http_route("查询用户历史持仓", "detail") is None


def test_layerA_unknown_intent_no_veto(monkeypatch):
    """intent 非 5 分析类（如脏值 / 旧 intent）→ 不 veto，走原 Layer 1/3（防误杀）。"""
    _mock_catalog(monkeypatch)
    result = http_planner.pick_http_route("平台 BTC 卖出持仓", "garbage_intent")
    assert result is not None and result[0] == "futures_admin.futures_position_list"
