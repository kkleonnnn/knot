"""v0.6.1.4 commit 5 — HTTP planner + URL allowlist + executor 守护测试（最小集）

加速版策略：覆盖 3 核心红线 + happy path，其他推 v0.6.1.5 followup。

覆盖红线：
- R-PB2-3  env / URL allowlist 缺失 fail-fast
- R-PB2-4  跨源 JOIN catalog 守护（当前 demo 阶段：lexicon 多源命中优先 HTTP，
            不立即 raise；测验证 pick_http_route 行为）
- R-PB2-10 PII redact + truncate(20)

红线 R-PB2-1/5/6/11/15 由 commit 1/4 的 smoke test 已覆盖。
"""
from __future__ import annotations

import pytest


# ─── R-PB2-3: env / URL allowlist fail-fast ─────────────────────────────


def test_executor_base_url_env_missing_raises_auth_error(monkeypatch):
    """env <BASE_URL_ENV> 缺失 → HTTPAuthError (R-PB2-3 sustained)."""
    monkeypatch.delenv("KNOT_TEST_API_BASE_URL", raising=False)
    monkeypatch.setenv("KNOT_HTTP_ALLOWED_HOSTS", "api.example.com")
    monkeypatch.setenv("KNOT_TEST_API_AUTH_HEADER", "key")
    monkeypatch.setenv("KNOT_TEST_API_AUTH_VALUE", "test-token-value")

    from knot.adapters.http import HTTPAuthError, execute

    spec = {
        "method": "GET",
        "url_template": "{base_url}/v1/items",
        "base_url_env": "KNOT_TEST_API_BASE_URL",
        "auth_header_env": "KNOT_TEST_API_AUTH_HEADER",
        "auth_value_env": "KNOT_TEST_API_AUTH_VALUE",
        "response_path": "data.records",
    }

    with pytest.raises(HTTPAuthError, match=r"KNOT_TEST_API_BASE_URL.*R-PB2-3"):
        execute(spec, {"q": "test"})


def test_url_allowlist_secure_by_default(monkeypatch):
    """KNOT_HTTP_ALLOWED_HOSTS 未设 → 全拒绝（R-PB2-3 secure by default）."""
    monkeypatch.delenv("KNOT_HTTP_ALLOWED_HOSTS", raising=False)

    from knot.adapters.http.url_allowlist import get_allowed_hosts, is_url_allowed

    assert get_allowed_hosts() == set()
    assert is_url_allowed("http://api.example.com/some/path") is False
    assert is_url_allowed("http://internal-api.example.com/x") is False


def test_url_allowlist_host_match(monkeypatch):
    """env 设了 host → 该 host 通过；其他 host 仍拒绝."""
    monkeypatch.setenv(
        "KNOT_HTTP_ALLOWED_HOSTS",
        "api.example.com,api2.example.com",
    )

    from knot.adapters.http.url_allowlist import get_allowed_hosts, is_url_allowed

    assert get_allowed_hosts() == {"api.example.com", "api2.example.com"}
    assert is_url_allowed("http://api.example.com/v1/x") is True
    assert is_url_allowed("http://api2.example.com/v1/y") is True
    # 其他 host 拒绝
    assert is_url_allowed("http://attacker.com/x") is False
    assert is_url_allowed("http://internal-secret.local/dump") is False


def test_url_allowlist_check_raises(monkeypatch):
    """check_url_allowed 不在 allowlist → HTTPAuthError."""
    monkeypatch.setenv("KNOT_HTTP_ALLOWED_HOSTS", "api.example.com")

    from knot.adapters.http import HTTPAuthError
    from knot.adapters.http.url_allowlist import check_url_allowed

    # 通过
    check_url_allowed("http://api.example.com/x")
    # 不通过
    with pytest.raises(HTTPAuthError, match=r"KNOT_HTTP_ALLOWED_HOSTS"):
        check_url_allowed("http://attacker.com/x")


# ─── R-PB2-10: PII redact + truncate ────────────────────────────────────


def test_redact_pii_strips_email_and_phone():
    """PII 字段（email/phone/mobile/id_card/...）→ REDACTED."""
    from knot.services.http_planner import redact_pii

    rows = [
        {"user_id": 12345, "email": "test@a.com", "phone": "13800000000", "amount": "0.0002"},
        {"user_id": 67890, "Email": "x@y.com", "mobile": "13900000000", "ok": True},
    ]
    result = redact_pii(rows)

    assert result[0]["email"] == "[REDACTED]"
    assert result[0]["phone"] == "[REDACTED]"
    assert result[0]["user_id"] == 12345    # user_id 不脱敏（业务字段）
    assert result[0]["amount"] == "0.0002"  # 金融字段保留

    # 大小写不敏感（Email 也命中）
    assert result[1]["Email"] == "[REDACTED]"
    assert result[1]["mobile"] == "[REDACTED]"


def test_redact_pii_empty_input():
    """空 rows 不崩."""
    from knot.services.http_planner import redact_pii

    assert redact_pii([]) == []
    assert redact_pii([{}]) == [{}]


def test_truncate_rows_below_limit():
    """rows < 阈值 → 原样返 + truncated=False."""
    from knot.services.http_planner import truncate_rows

    rows = [{"i": i} for i in range(5)]
    result, was_truncated = truncate_rows(rows)
    assert len(result) == 5
    assert was_truncated is False


def test_truncate_rows_above_limit():
    """rows > 20 → 截到 20 + truncated=True."""
    from knot.services.http_planner import truncate_rows

    rows = [{"i": i} for i in range(50)]
    result, was_truncated = truncate_rows(rows)
    assert len(result) == 20
    assert was_truncated is True


# ─── R-PB2-4: 跨源守护（当前 demo 阶段：lexicon 多源命中优先 HTTP）────────


def test_pick_http_route_no_http_match():
    """问题不含 HTTP lexicon 关键词 → 返 None（走 SQL 路径）."""
    from knot.services import http_planner

    # 假设 SQL 问题（'GMV' / '订单' 在通用 catalog 但非 HTTP）
    result = http_planner.pick_http_route("昨天的 GMV 是多少")
    assert result is None


def test_pick_http_route_user_pending_when_user_id():
    """问题含 user_id 数字 + 持仓关键词 → entity-aware 选 user_pending."""
    from knot.services import http_planner
    from knot.services.agents import catalog

    catalog.reload()
    if not catalog.is_http_table("futures_admin.futures_user_pending"):
        pytest.skip("当前部署 catalog 未含 futures_user_pending HTTP 表")

    result = http_planner.pick_http_route("用户 1000260 当前 BTCUSDT 持仓")
    assert result is not None
    table_name, spec = result
    assert table_name == "futures_admin.futures_user_pending"
    assert spec.get("method") == "GET"
    assert "user/position/pending" in spec.get("url_template", "")


def test_pick_http_route_position_list_when_no_user_id():
    """问题无 user_id → entity-aware 选平台视图 position_list."""
    from knot.services import http_planner
    from knot.services.agents import catalog

    catalog.reload()
    if not catalog.is_http_table("futures_admin.futures_position_list"):
        pytest.skip("当前部署 catalog 未含 futures_position_list HTTP 表")

    result = http_planner.pick_http_route("BTC 多头持仓总量")
    assert result is not None
    table_name, _spec = result
    assert table_name == "futures_admin.futures_position_list"


# ─── 参数提取（regex MVP）─────────────────────────────────────────────


def test_extract_params_user_id():
    """\"用户 12345\" → user_id=12345."""
    from knot.services.http_planner import extract_params_for_endpoint

    params = extract_params_for_endpoint("用户 1000260 当前持仓")
    assert params.get("user_id") == 1000260


def test_extract_params_market_full_form():
    """BTCUSDT 全大写 → market=BTCUSDT."""
    from knot.services.http_planner import extract_params_for_endpoint

    params = extract_params_for_endpoint("BTCUSDT 空头持仓")
    assert params.get("market") == "BTCUSDT"


def test_extract_params_market_short_form():
    """'BTC' 短名 → market=BTCUSDT（拼 USDT）."""
    from knot.services.http_planner import extract_params_for_endpoint

    params = extract_params_for_endpoint("BTC 多头持仓总量")
    assert params.get("market") == "BTCUSDT"


def test_extract_params_side_long():
    """'多头' → side=2."""
    from knot.services.http_planner import extract_params_for_endpoint

    params = extract_params_for_endpoint("BTC 多头持仓")
    assert params.get("side") == 2


def test_extract_params_side_short():
    """'空头' → side=1."""
    from knot.services.http_planner import extract_params_for_endpoint

    params = extract_params_for_endpoint("BTC 空头持仓")
    assert params.get("side") == 1


def test_extract_params_pagination_default_for_list_endpoint():
    """endpoint_key 含 '_list' → 自动 page=1, page_size=10."""
    from knot.services.http_planner import extract_params_for_endpoint

    params = extract_params_for_endpoint("BTC 多头持仓", endpoint_key="futures_position_list")
    assert params.get("page") == 1
    assert params.get("page_size") == 10


# ─── HTTPEndpointSpec 契约稳定性（R-PB2-1）─────────────────────────────


def test_http_endpoint_spec_fields_stable():
    """R-PB2-1：HTTPEndpointSpec TypedDict 字段稳定 — 变更必须三方共识."""
    from knot.adapters.http.base import HTTPEndpointSpec

    # TypedDict __annotations__ 暴露字段
    expected_fields = {
        "method", "url_template", "base_url_env",
        "auth_header_env", "auth_value_env",
        "response_path", "param_schema", "timeout_sec",
    }
    actual_fields = set(HTTPEndpointSpec.__annotations__.keys())
    assert actual_fields == expected_fields, (
        f"HTTPEndpointSpec 字段变更检测：actual={actual_fields} "
        f"missing={expected_fields - actual_fields} "
        f"extra={actual_fields - expected_fields}"
    )
