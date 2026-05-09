"""tests/api/test_settings_masked.py — v0.4.5 commit #4 守护测试（R-39）。

API 边界 mask + PATCH 空值/mask 占位保留。
守护者强调 §：mask 在 api 序列化最外层做（不污染 repo / service）。
"""


# ─── R-39 GET 返 masked ────────────────────────────────────────────────

def test_R39_get_api_keys_returns_masked(client, auth_headers):
    """admin GET /api/admin/api-keys 见 ••••••••last4，不见明文。"""
    client.put("/api/admin/api-keys",
               json={"openrouter_api_key": "sk-or-real-secret-LAST"},
               headers=auth_headers)
    r = client.get("/api/admin/api-keys", headers=auth_headers)
    assert r.status_code == 200
    val = r.json()["openrouter_api_key"]
    assert val.startswith("•" * 8), "R-39：GET 必须 mask"
    assert val.endswith("LAST"), "保留 last4 让用户识别"
    assert "sk-or-real" not in val, "明文中段不得泄漏"


def test_R39_short_secret_fully_masked(client, auth_headers):
    """守护者补：长度 ≤ 4 字符的 key 应全 mask（不暴露 last4）。"""
    client.put("/api/admin/api-keys",
               json={"openrouter_api_key": "abc"},  # 短于 4
               headers=auth_headers)
    r = client.get("/api/admin/api-keys", headers=auth_headers)
    assert r.json()["openrouter_api_key"] == "••••", "短 key 应全 mask"


def test_R39_empty_secret_returns_empty(client, auth_headers):
    """空 key → 返空串（不是 8 个圆点 — 避免误导未配置）。"""
    r = client.get("/api/admin/api-keys", headers=auth_headers)
    # 默认未配置 → ""
    assert r.json()["openrouter_api_key"] == ""


# ─── R-39 PATCH 空值/mask 占位 → 保留原值 ─────────────────────────────

def test_R39_patch_empty_api_key_preserves_original(client, auth_headers):
    """PATCH 空字符串 → 原值不变（编辑表单空白 != 清空）。"""
    client.put("/api/admin/api-keys",
               json={"openrouter_api_key": "sk-or-original-LAST"},
               headers=auth_headers)
    # 误传空串
    client.put("/api/admin/api-keys",
               json={"openrouter_api_key": ""},
               headers=auth_headers)
    # 验证：repo 拿到的明文仍是原值
    from knot.repositories import settings_repo
    assert settings_repo.get_app_setting("openrouter_api_key") == "sk-or-original-LAST"


def test_R39_patch_mask_placeholder_preserves_original(client, auth_headers):
    """PATCH 见 mask 占位（开头 8 个 U+2022）→ 保留原值（前端误回传兜底）。"""
    client.put("/api/admin/api-keys",
               json={"openrouter_api_key": "sk-or-keep-this-LAST"},
               headers=auth_headers)
    # 前端误把 GET 的 masked 值回传
    client.put("/api/admin/api-keys",
               json={"openrouter_api_key": "•" * 8 + "LAST"},
               headers=auth_headers)
    from knot.repositories import settings_repo
    assert settings_repo.get_app_setting("openrouter_api_key") == "sk-or-keep-this-LAST"


def test_R39_patch_new_value_overwrites(client, auth_headers):
    """新明文 → 正常更新（加密落盘）。"""
    client.put("/api/admin/api-keys",
               json={"openrouter_api_key": "old-value"},
               headers=auth_headers)
    client.put("/api/admin/api-keys",
               json={"openrouter_api_key": "sk-or-NEW-VALUE-2026"},
               headers=auth_headers)
    from knot.repositories import settings_repo
    assert settings_repo.get_app_setting("openrouter_api_key") == "sk-or-NEW-VALUE-2026"


# ─── 守护者补：admin list 不漏明文 ────────────────────────────────────

def test_R39_admin_list_users_does_not_leak_secrets(client, auth_headers):
    """admin 视角看用户列表 — 不得返 api_key / openrouter_api_key / doris_password 明文。"""
    r = client.get("/api/admin/users", headers=auth_headers)
    assert r.status_code == 200
    rows = r.json()
    for u in rows:
        for forbidden in ("api_key", "openrouter_api_key", "embedding_api_key", "doris_password"):
            assert forbidden not in u or not u[forbidden] or u[forbidden].startswith("•"), \
                f"R-39：admin/users 列表泄漏 {forbidden}={u.get(forbidden)!r}"


def test_R39_admin_list_datasources_does_not_leak_db_password(client, auth_headers):
    """admin 视角看 datasources 列表 — 不得返 db_password 明文。"""
    r = client.get("/api/admin/datasources", headers=auth_headers)
    assert r.status_code == 200
    for s in r.json():
        assert "db_password" not in s or not s["db_password"] or s["db_password"].startswith("•")


def test_R39_mask_helper_unit():
    """单元测试 mask_secret helper（边界）。"""
    from knot.api._secret import mask_secret
    assert mask_secret("") == ""
    assert mask_secret(None) == ""
    assert mask_secret("abc") == "••••"
    assert mask_secret("abcd") == "••••"
    assert mask_secret("abcde") == "•" * 8 + "bcde"
    assert mask_secret("sk-ant-real-secret-LAST4") == "•" * 8 + "AST4"


def test_R39_should_update_secret_helper_unit():
    """单元测试 should_update_secret 四种输入分类。"""
    from knot.api._secret import should_update_secret
    # None → 字段缺失
    assert should_update_secret(None, "old") == (False, "old")
    # "" 空白 → 保留
    assert should_update_secret("", "old") == (False, "old")
    # mask 占位 → 保留
    assert should_update_secret("•" * 8 + "LAST", "old") == (False, "old")
    # 新明文 → 更新
    assert should_update_secret("new-value", "old") == (True, "new-value")
