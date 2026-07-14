"""tests/api/test_admin_share.py — v0.8.14 分享 admin 配置：IM 凭据 mask + 白名单 CRUD + 权限门。"""


def _analyst_headers(client, auth_headers, uname="cfg_analyst"):
    client.post("/api/admin/users", json={"username": uname, "password": "p", "role": "analyst"},
                headers=auth_headers)
    tok = client.post("/api/auth/login", json={"username": uname, "password": "p"}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


def test_im_config_mask_and_should_update(client, auth_headers):
    # 写机密 + 明文
    r = client.put("/api/admin/share/config", json={
        "telegram_bot_token": "123456:REAL-SECRET", "lark_app_secret": "app-sec-REAL",
        "lark_app_id": "cli_public", "lark_region": "feishu",
    }, headers=auth_headers)
    assert r.status_code == 200

    got = client.get("/api/admin/share/config", headers=auth_headers).json()
    # 机密 masked（不漏明文）
    assert "REAL-SECRET" not in got["telegram_bot_token"] and got["telegram_bot_token"].endswith("CRET")
    assert "app-sec-REAL" not in got["lark_app_secret"]
    # 明文原样
    assert got["lark_app_id"] == "cli_public" and got["lark_region"] == "feishu"

    # 回传 mask 占位 → 保留原值（不被覆盖成 mask 串）
    client.put("/api/admin/share/config", json={"telegram_bot_token": got["telegram_bot_token"]},
               headers=auth_headers)
    from knot.repositories import settings_repo
    assert settings_repo.get_app_setting("telegram_bot_token") == "123456:REAL-SECRET"


def test_share_target_crud(client, auth_headers):
    tg = client.post("/api/admin/share/targets",
                     json={"name": "运营TG", "platform": "tg", "chat_id": "-100abc"},
                     headers=auth_headers)
    assert tg.status_code == 200
    lark = client.post("/api/admin/share/targets",
                       json={"name": "日报Lark", "platform": "lark", "chat_id": "oc_x", "region": "feishu"},
                       headers=auth_headers)
    assert lark.status_code == 200

    lst = client.get("/api/admin/share/targets", headers=auth_headers).json()
    names = {t["name"] for t in lst}
    assert {"运营TG", "日报Lark"} <= names

    tid = tg.json()["id"]
    assert client.delete(f"/api/admin/share/targets/{tid}", headers=auth_headers).status_code == 200
    lst2 = client.get("/api/admin/share/targets", headers=auth_headers).json()
    assert tid not in {t["id"] for t in lst2}


def test_share_target_bad_platform_400(client, auth_headers):
    r = client.post("/api/admin/share/targets",
                    json={"name": "x", "platform": "slack", "chat_id": "c"}, headers=auth_headers)
    assert r.status_code == 400


def test_share_target_bad_lark_region_400(client, auth_headers):
    r = client.post("/api/admin/share/targets",
                    json={"name": "x", "platform": "lark", "chat_id": "oc", "region": "qq"},
                    headers=auth_headers)
    assert r.status_code == 400


def test_share_config_analyst_403(client, auth_headers):
    ah = _analyst_headers(client, auth_headers)
    assert client.get("/api/admin/share/config", headers=ah).status_code == 403
    assert client.get("/api/admin/share/targets", headers=ah).status_code == 403
    assert client.post("/api/admin/share/targets",
                       json={"name": "x", "platform": "tg", "chat_id": "c"}, headers=ah).status_code == 403
