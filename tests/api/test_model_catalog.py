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


def test_default_model_is_or_path_and_in_dict(client, auth_headers):
    """v0.6.0.8 MUST-2: DEFAULT_MODEL 默认切到 OR-only key。

    旧 direct provider key 'claude-haiku-4-5-20251001' 仍在 MODELS dict（不删保兼容），
    但 fallback 默认值改为 OR 路径 'anthropic/claude-haiku-4.5'。
    """
    from knot import config as cfg
    assert cfg.DEFAULT_MODEL == "anthropic/claude-haiku-4.5"
    # 该 key 必须在 MODELS dict
    assert cfg.DEFAULT_MODEL in cfg.MODELS
    # 守 R-PA-5: 旧 direct key 不删（admin 已配置的 agent_models 保兼容）
    assert "claude-haiku-4-5-20251001" in cfg.MODELS


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
    import urllib.request
    import urllib.error

    def _fail_open(*args, **kwargs):
        raise urllib.error.URLError("simulated network failure")

    monkeypatch.setattr(urllib.request, "urlopen", _fail_open)
    r = client.post("/api/admin/sync-or-catalog", headers=auth_headers)
    assert r.status_code == 503
    assert "OpenRouter" in r.json()["detail"]
