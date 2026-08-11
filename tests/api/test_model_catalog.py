"""tests/api/test_model_catalog.py — v0.6.0.6 F-D 模型 catalog 守护测试。

覆盖：
- /api/admin/models 返回 max_context 字段（OR entries 有；direct provider 为 None）
- /api/admin/or-catalog 空表返 items=[]
- model_catalog_repo.upsert 幂等（同 model_id 触发覆盖）
- DEFAULT_MODEL 仍在 cfg.MODELS（F-D-7 守 R-PA-5 兼容性）
- google/gemini-pro-1.5 已从 MODELS dict 删除（F-D-4 OR 已下架）
- OR API 拉取失败 → 503（unit test 用 monkeypatch 模拟）
"""
from __future__ import annotations


def test_admin_models_returns_max_context(client, auth_headers):
    """/api/admin/models 响应每条含 max_context；OR entries 非 None，direct 为 None。"""
    r = client.get("/api/admin/models", headers=auth_headers)
    assert r.status_code == 200
    models = r.json()
    or_entries = [m for m in models if m["provider"].lower() == "openrouter"]
    direct_entries = [m for m in models if m["provider"].lower() != "openrouter"]
    # OR entries 全部含 max_context（F-D-1）
    for m in or_entries:
        assert m["max_context"] is not None, f"OR entry {m['id']} 必须含 max_context"
    # direct provider 无 max_context（保留兼容）
    for m in direct_entries:
        assert m["max_context"] is None or isinstance(m["max_context"], int)


def test_gemini_pro_1_5_removed_from_models(client, auth_headers):
    """F-D-4: OR 已下架 google/gemini-pro-1.5，dict 必须删除（防 404 + 计费失真）。"""
    from knot import config as cfg
    assert "google/gemini-pro-1.5" not in cfg.MODELS


def test_pricing_corrections_applied(client, auth_headers):
    """F-D-3: OR live API 实测 pricing 已与 dict 对齐（守护者 M-D6 数据准确性）。"""
    from knot import config as cfg
    # 选 5 个修正点验证
    assert cfg.MODELS["anthropic/claude-haiku-4.5"]["input_price"] == 1.00
    assert cfg.MODELS["anthropic/claude-haiku-4.5"]["output_price"] == 5.00
    assert cfg.MODELS["deepseek/deepseek-chat"]["input_price"] == 0.32
    assert cfg.MODELS["deepseek/deepseek-r1"]["output_price"] == 2.50
    assert cfg.MODELS["qwen/qwen-plus"]["input_price"] == 0.26


def test_default_model_fallback_is_or_path():
    """v0.6.0.8 MUST-2: 检查 settings.py 源码 fallback 已切到 OR-only key。

    实际 cfg.DEFAULT_MODEL 受 env DEFAULT_MODEL 覆盖（本地 dev / 测试 env 各异），
    所以本测试用源码字面 grep 校验 fallback 默认值已修正。
    """
    from pathlib import Path
    settings_src = Path("knot/config/settings.py").read_text(encoding="utf-8")
    assert 'os.getenv("DEFAULT_MODEL", "anthropic/claude-haiku-4.5")' in settings_src, (
        "MUST-2 违规：settings.py:51 fallback 必须为 'anthropic/claude-haiku-4.5'"
    )


def test_or_only_no_direct_keys(client, auth_headers):
    """v0.6.5.4 OR-only 不变量：直连 provider key 已删，cfg.MODELS 全 OR（带 "/"）。

    旧 test_legacy_direct_key_still_in_dict 的 "Day 28+ 保留直连" 语义已被资深 OR-only 决策推翻。
    """
    from knot import config as cfg
    assert "claude-haiku-4-5-20251001" not in cfg.MODELS, "直连 key 应已删（OR-only）"
    assert "anthropic/claude-haiku-4.5" in cfg.MODELS, "OR Claude Haiku 4.5 保留"
    assert all("/" in k for k in cfg.MODELS), f"cfg.MODELS 必全 OR（带 /）；违例: {[k for k in cfg.MODELS if '/' not in k]}"


def test_or_catalog_empty_initially(client, auth_headers):
    """GET /api/admin/or-catalog 初始空表返 items=[] total=0。"""
    r = client.get("/api/admin/or-catalog", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert "items" in data and "total" in data
    # 测试环境 fresh DB → 空表
    assert data["total"] == 0


def test_model_catalog_repo_upsert_idempotent(client, auth_headers):
    """F-D-6: model_catalog_repo.upsert 同 model_id 触发覆盖（非重复行）。"""
    from knot.repositories import model_catalog_repo
    model_catalog_repo.upsert(
        model_id="test/dummy-model",
        context_length=128000,
        input_price=1.50, output_price=3.00,
    )
    model_catalog_repo.upsert(
        model_id="test/dummy-model",
        context_length=256000,  # 改了
        input_price=2.00, output_price=4.00,  # 改了
    )
    rows = model_catalog_repo.list_all()
    matches = [r for r in rows if r["model_id"] == "test/dummy-model"]
    assert len(matches) == 1, f"UPSERT 应只有 1 行；得到 {len(matches)}"
    assert matches[0]["context_length"] == 256000
    assert matches[0]["input_price"] == 2.00


def test_sync_or_catalog_requires_admin(client):
    """POST /api/admin/sync-or-catalog 无 token → 401/403。"""
    r = client.post("/api/admin/sync-or-catalog")
    assert r.status_code in (401, 403)


def test_sync_or_catalog_network_failure_returns_503(client, auth_headers, monkeypatch):
    """OR API 失败时端点应 503 不写表（守护者数据准确性原则 — 不刷写错误数据）。"""
    import urllib.error
    import urllib.request

    def _fail_open(*args, **kwargs):
        raise urllib.error.URLError("simulated network failure")

    # ⭐ v0.9.22：patch 目标从 `urllib.request.urlopen` 改为 `_OPENER.open`。
    # ⚠️ **不改会静默变成空操作** —— 生产码改走 `_OPENER`（不跟随重定向的 opener）之后，
    #    patch `urlopen` 谁都不影响 ⇒ 本测会**真打 openrouter.ai**（而不是模拟失败）
    #    ⇒ 「因错误的理由而绿」或因真实网络状况而 flaky。
    # ⚠️ `URLError` 仍是**正确的**模拟：`_OPENER.open` 的异常谱系与 `urlopen` 相同
    #    （这正是选「保留 urllib + 自定义 opener」而不是「换 requests」省下来的东西）。
    from knot.api.admin.or_catalog import _OPENER
    monkeypatch.setattr(_OPENER, "open", _fail_open)
    r = client.post("/api/admin/sync-or-catalog", headers=auth_headers)
    assert r.status_code == 503
    assert "OpenRouter" in r.json()["detail"]


def test_sync_or_catalog_upstream_302_is_fail_closed(client, auth_headers, monkeypatch):
    """⭐ 验收 #2：上游回 **302** ⇒ 端点 503 且**零 upsert**（`_NoRedirect` 的端点层后果）。

    ⚠️ **oracle 不能只用「模型表行数不变」**（Stage 2 lens A 的 P0-2，我认同）：
    OpenRouter 式错误体 `{"error": {...}}` 经 `payload.get("data") or []` 得空
    ⇒ **0 行 upsert** ⇒ 「行数不变」在「fail-open 了」与「fail-closed 了」**两种情况下都真**
    ⇒ 那是个恒绿判据。⇒ 本测断 **状态码 + `upserted_count` 不存在于响应**。

    ⚠️ **下游为什么必须 fail-closed**（lens A 指出，记录在案）：`Admin.jsx` 只在 catch 里报失败，
    200 走 `已同步 ${r.upserted_count} 条` ⇒ 若上游失败被吞成 200，admin 会看到**绿色 toast
    「已同步 0 条」**，而 `upsert` 从不删行 ⇒ **「同步成功无变化」与「上游挂了」不可区分**。
    """
    import urllib.error

    from knot.api.admin.or_catalog import _OPENER

    def _redirect(*a, **k):
        # `_NoRedirect.redirect_request` 返 None ⇒ urllib 落到 `http_error_default` ⇒ HTTPError
        raise urllib.error.HTTPError("https://openrouter.ai/x", 302, "Found",
                                     {"Location": "https://evil.example.com/x"}, None)

    monkeypatch.setattr(_OPENER, "open", _redirect)
    r = client.post("/api/admin/sync-or-catalog", headers=auth_headers)
    assert r.status_code == 503, f"上游 302 必须 fail-closed，实际 {r.status_code}: {r.text[:200]}"
    assert "upserted_count" not in r.text, (
        f"⛔ 上游 302 被吞成了「同步结果」：{r.text[:200]} —— "
        "前端会显示绿色「已同步 0 条」，admin 无法区分「无变化」与「上游挂了」。"
    )


def test_sync_or_catalog_200_still_syncs(client, auth_headers, monkeypatch):
    """⭐ 验收 #7 **正对照**：200 路径照常同步 —— 防「一律拒绝」式假通过。

    ⚠️ 没有这一条，「禁重定向」可以用「把整个端点弄坏」来通过上面那些测。
    """
    import io
    import json

    from knot.api.admin.or_catalog import _OPENER

    body = json.dumps({"data": [{
        "id": "vendor/probe-model", "name": "Probe", "context_length": 4096,
        "pricing": {"prompt": "0.000001", "completion": "0.000002"},
    }]}).encode()

    class _Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(_OPENER, "open", lambda *a, **k: _Resp(body))
    r = client.post("/api/admin/sync-or-catalog", headers=auth_headers)
    assert r.status_code == 200, f"200 路径被打坏了: {r.status_code} {r.text[:200]}"
    assert r.json().get("upserted_count", 0) >= 1, f"未同步任何模型: {r.json()}"
