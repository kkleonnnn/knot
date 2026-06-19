"""v0.6.5.2 F6 — SPA index.html no-cache 守护（防发版换 hash bundle 白屏回归）.

白屏根因：spa() 裸 FileResponse(index.html) 无 Cache-Control → 浏览器启发式缓存旧
index.html → 引用已删旧 hash bundle → /assets/index-<旧hash>.js 404 → 整屏白屏。
修复：仅 index.html 套 no-cache（must-revalidate）；favicon/icons/assets 沿用默认 etag。
"""


def test_F6_root_index_html_no_cache(client):
    """根路径 / → index.html 必带 no-cache。"""
    r = client.get("/")
    assert r.status_code == 200
    cc = r.headers.get("cache-control", "")
    assert "no-cache" in cc, f"/ 的 index.html 必 no-cache；实际 Cache-Control={cc!r}"


def test_F6_spa_fallback_no_cache(client):
    """非文件 SPA 路由 → fallback index.html 必带 no-cache。"""
    r = client.get("/some-spa-route-that-is-not-a-file")
    assert r.status_code == 200
    cc = r.headers.get("cache-control", "")
    assert "no-cache" in cc, f"SPA fallback index.html 必 no-cache；实际 {cc!r}"


def test_F6_top_level_asset_not_no_cache(client):
    """顶层非-index 文件（favicon.svg）不被误套 no-cache（仅 index.html 套）。"""
    r = client.get("/favicon.svg")
    assert r.status_code == 200
    cc = r.headers.get("cache-control", "")
    assert "no-cache" not in cc, \
        f"favicon.svg 不应套 index.html 的 no-cache（守护者：header 仅套 index.html 不泛化）；实际 {cc!r}"
