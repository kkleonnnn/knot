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


# ⛔ `test_executor_base_url_env_missing_raises_auth_error` 已于 v0.9.7 删除（B-3 ②）：
#    它测的是「spec 带 env 名 → executor 读进程 env → env 缺失则抛」这条路，而**那条路已退役**
#    （进程 env 是租户盲的 ⇒ 跨租户数据出境）。删测不是降覆盖 —— 替代守护更强：
#    `tests/adapters/test_http_spec_requires_source_id.py` 断言 env 形态 spec
#    **结构上不可表达**（走到能力处就被拒，且零出网），而不只是「env 没配时会抛」。


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
    """check_url_allowed 不在 allowlist → HTTPAuthError.

    ⚠️ v0.9.7 D11：`match=` 从 `KNOT_HTTP_ALLOWED_HOSTS` 改为新消息 —— 消息**不再点名 env**
    （allowlist 已 per-tenant：起源租户回退 env，其余读平台库列 ⇒ 点名单一机制对非起源租户是误导），
    也**不再枚举允许集**（见 `test_SEC_allowlist_refusal_does_not_enumerate_allowlist`）。
    """
    monkeypatch.setenv("KNOT_HTTP_ALLOWED_HOSTS", "api.example.com")

    from knot.adapters.http import HTTPAuthError
    from knot.adapters.http.url_allowlist import check_url_allowed

    # 通过
    check_url_allowed("http://api.example.com/x")
    # 不通过
    with pytest.raises(HTTPAuthError, match=r"不在本租户的出网白名单内"):
        check_url_allowed("http://attacker.com/x")


def test_SEC_allowlist_refusal_does_not_enumerate_allowlist(monkeypatch):
    """⭐ must #12 / D11：allowlist 拒绝消息**不得枚举白名单**、不得点名 env（#262 同类）。

    **既有缺陷，v0.9.7 修**：原实现 `f"(allowed: {sorted(allowed)})"` 把**整份白名单**插进异常，
    而该异常经 `http_planner.run_http_step` 的 `except Exception` → `result["error"]` →
    `api/query.py` **原样 yield 给客户端** ⇒ 租户 admin 就能读出部署方整份 egress allowlist
    = `KNOT_HTTP_ALLOWED_HOSTS` 的 **env 值**进了响应（#262 泄的是 JWT_SECRET / KNOT_MASTER_KEY）。

    ⚠️ **判据是内容级、不是计数**：断言「**一个确实配置进去的 host 字面**不出现在消息里」——
    这样「换个写法继续枚举」（改成逗号连接 / 只报第一条 / 报 host 的一部分）同样会红。
    ⚠️ 刻意**不**断言「消息不含数字」：调用方自己给的 host 合法含数字（`api2.example.com`），
    那条断言会误伤（v0.9.6 `:312` 的 `isdigit` 判据不能照搬到这条消息上）。
    取材=revert：把消息改回含 `(allowed: {sorted(allowed)})` → 本测红。
    """
    secret_host = "internal-secret-9x.corp.local"
    monkeypatch.setenv("KNOT_HTTP_ALLOWED_HOSTS", f"api.example.com,{secret_host}")

    from knot.adapters.http import HTTPAuthError
    from knot.adapters.http.url_allowlist import check_url_allowed

    try:
        check_url_allowed("http://attacker.com/x")
    except HTTPAuthError as e:
        msg = str(e)
    else:
        pytest.fail(
            "不在 allowlist 的 URL **未被拒绝** —— egress 守护失效。\n"
            "本测的前提是「拒绝时抛 HTTPAuthError」；若它不再抛，`executor.execute` 出网前就没有门了。"
        )

    assert secret_host not in msg, (
        f"拒绝消息枚举了 allowlist 内容（泄漏 {secret_host!r}）：{msg!r}\n"
        "⚠️ 这条消息会经 run_http_step → result['error'] → api/query.py **原样回到客户端** ——\n"
        "  即 #262 那条缝。allowlist 是部署方内网 API 主机清单，泄漏 = 内网侦察面。\n"
        "  诊断信息请放**日志**（只记来源机制，不记内容）。"
    )
    assert "KNOT_" not in msg, f"拒绝消息点名了 env（allowlist 已 per-tenant，点名是误导）：{msg!r}"


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
        "method", "url_template", "source_id",
        "response_path", "param_schema", "timeout_sec",
    }
    actual_fields = set(HTTPEndpointSpec.__annotations__.keys())
    assert actual_fields == expected_fields, (
        f"HTTPEndpointSpec 字段变更检测：actual={actual_fields} "
        f"missing={expected_fields - actual_fields} "
        f"extra={actual_fields - expected_fields}"
    )
    # ⭐ v0.9.7 B-3 ②：三个 env 字段**必须缺席** —— 把「删掉了」变成一条守护，而不只是改期望值。
    # 上面的 `==` 已隐含这点，但**单独点名**是因为「加回来」是一个有具体动机的动作
    # （「给某个表配个临时 env 就好了」），届时读者应当直接看到为什么不行。
    retired = {"base_url_env", "auth_header_env", "auth_value_env"}
    assert not (actual_fields & retired), (
        f"env 引用形态被加回来了：{sorted(actual_fields & retired)}\n\n"
        "⛔ 这条路让 adapter 读**进程 env** = **租户盲** ⇒ 租户#2 能用租户#1 的凭据读其实时接口\n"
        "  = 跨租户数据出境（R-T-GATE 清单 B-3 ②，v0.9.7 关闭）。\n"
        "凭据一律经 `source_id` → **本租户库** data_sources 行（Fernet）。\n"
        "若确有「不绑数据源」的需求，请先过评审：docs/plans/v0.9.7-http-per-tenant-credentials-egress.md §7"
    )
