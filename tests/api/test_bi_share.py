"""tests/api/test_bi_share.py — v0.8.14 分享端点：权限门 + body 校验 + fail-fast → 状态码。

R-BI-SHARE-1 权限门（require_report_perm("share")）+ base64/size 校验 + ShareValidationError→400。
真 IM 投递 mock（share_svc.share_report）避免外发。
"""
import base64

_PNG = base64.b64encode(b"\x89PNG\r\n\x1a\nfake-image-bytes").decode()


def _analyst_headers(client, auth_headers, uname="share_analyst"):
    client.post("/api/admin/users", json={"username": uname, "password": "p", "role": "analyst"},
                headers=auth_headers)
    tok = client.post("/api/auth/login", json={"username": uname, "password": "p"}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


def _make_report(client, auth_headers):
    return client.post("/api/bi/reports", json={"title": "日报", "sql_text": "SELECT 1 AS a"},
                       headers=auth_headers).json()["id"]


def test_share_admin_happy_path(client, auth_headers, monkeypatch):
    from knot.api import bi_share
    monkeypatch.setattr(bi_share.share_svc, "share_report",
                        lambda png, ids, cap: [{"id": i, "name": f"t{i}", "ok": True} for i in ids])
    rid = _make_report(client, auth_headers)
    r = client.post(f"/api/bi/reports/{rid}/share",
                    json={"image_png": _PNG, "target_ids": [1, 2], "caption": "本月"},
                    headers=auth_headers)
    assert r.status_code == 200, r.text
    assert r.json()["ok_count"] == 2 and r.json()["total"] == 2


def test_share_bad_base64_400(client, auth_headers):
    rid = _make_report(client, auth_headers)
    r = client.post(f"/api/bi/reports/{rid}/share",
                    json={"image_png": "not@@base64!!", "target_ids": [1]}, headers=auth_headers)
    assert r.status_code == 400


def test_share_empty_targets_400(client, auth_headers):
    rid = _make_report(client, auth_headers)
    r = client.post(f"/api/bi/reports/{rid}/share",
                    json={"image_png": _PNG, "target_ids": []}, headers=auth_headers)
    assert r.status_code == 400


def test_share_too_many_targets_400(client, auth_headers):
    rid = _make_report(client, auth_headers)
    r = client.post(f"/api/bi/reports/{rid}/share",
                    json={"image_png": _PNG, "target_ids": list(range(1, 30))}, headers=auth_headers)
    assert r.status_code == 400


def test_share_oversize_png_413(client, auth_headers):
    rid = _make_report(client, auth_headers)
    big = base64.b64encode(b"x" * (9 * 1024 * 1024)).decode()  # >8MB 原始
    r = client.post(f"/api/bi/reports/{rid}/share",
                    json={"image_png": big, "target_ids": [1]}, headers=auth_headers)
    assert r.status_code == 413


def test_share_nonexistent_report_404(client, auth_headers):
    r = client.post("/api/bi/reports/999999/share",
                    json={"image_png": _PNG, "target_ids": [1]}, headers=auth_headers)
    assert r.status_code == 404


def test_share_analyst_without_grant_403(client, auth_headers):
    rid = _make_report(client, auth_headers)
    ah = _analyst_headers(client, auth_headers)
    r = client.post(f"/api/bi/reports/{rid}/share",
                    json={"image_png": _PNG, "target_ids": [1]}, headers=ah)
    assert r.status_code == 403


def test_share_bad_target_id_400(client, auth_headers):
    """target_id ∉ 白名单 → service fail-fast ShareValidationError → 端点 400（无真发）。"""
    rid = _make_report(client, auth_headers)
    # 不建任何白名单目标 → target_id=1 必 miss
    r = client.post(f"/api/bi/reports/{rid}/share",
                    json={"image_png": _PNG, "target_ids": [1]}, headers=auth_headers)
    assert r.status_code == 400


def _make_target(client, auth_headers, name="运营TG", platform="tg", chat_id="-100xyz", region=None):
    body = {"name": name, "platform": platform, "chat_id": chat_id}
    if region:
        body["region"] = region
    return client.post("/api/admin/share/targets", json=body, headers=auth_headers).json()["id"]


def test_picker_admin_lists_targets_without_chat_id(client, auth_headers):
    """admin 可枚举投递目标；DTO 仅 id/name/platform（**绝不含 chat_id/凭据** — R-BI-SHARE-3）。"""
    _make_target(client, auth_headers)
    lst = client.get("/api/bi/share/targets", headers=auth_headers).json()
    assert any(t["name"] == "运营TG" and t["platform"] == "tg" for t in lst)
    for t in lst:
        assert set(t.keys()) == {"id", "name", "platform"}, "选择器 DTO 不得泄 chat_id/region/凭据"


def test_picker_analyst_without_share_grant_empty(client, auth_headers):
    """对抗复核 v0.8.15 #LOW：无 share 权用户枚举 → []（不泄内部 IM 群名）。"""
    _make_target(client, auth_headers)
    ah = _analyst_headers(client, auth_headers, uname="picker_nogrant")
    assert client.get("/api/bi/share/targets", headers=ah).json() == []


def test_picker_analyst_with_share_grant_sees_targets(client, auth_headers):
    """持任一报表 share 权的 analyst → 可枚举（选择器可用）。"""
    _make_target(client, auth_headers)
    uid = client.post("/api/admin/users", json={"username": "picker_grant", "password": "p", "role": "analyst"},
                      headers=auth_headers).json()["id"]
    rid = _make_report(client, auth_headers)
    client.put("/api/bi/permissions", json={"user_id": uid, "report_id": rid, "can_share": True},
               headers=auth_headers)
    tok = client.post("/api/auth/login", json={"username": "picker_grant", "password": "p"}).json()["token"]
    ah = {"Authorization": f"Bearer {tok}"}
    lst = client.get("/api/bi/share/targets", headers=ah).json()
    assert any(t["name"] == "运营TG" for t in lst)


def test_share_caption_too_long_422(client, auth_headers):
    """#sub-LOW：caption 服务端硬界 max_length=500（直调 API 亦不放行超长文案入 IM）。"""
    rid = _make_report(client, auth_headers)
    r = client.post(f"/api/bi/reports/{rid}/share",
                    json={"image_png": _PNG, "target_ids": [1], "caption": "x" * 501}, headers=auth_headers)
    assert r.status_code == 422


def test_share_unexpected_error_audits_and_502(client, auth_headers, monkeypatch):
    """对抗复核 confirmed fix：意外异常（非 ShareValidationError）→ 502 且 bi_report.share 审计仍写（不跳）。"""
    from knot.api import bi_share
    monkeypatch.setattr(bi_share.share_svc, "share_report",
                        lambda png, ids, cap: (_ for _ in ()).throw(RuntimeError("decrypt boom")))
    audited = []
    monkeypatch.setattr(bi_share, "audit", lambda *a, **k: audited.append(k))
    rid = _make_report(client, auth_headers)
    r = client.post(f"/api/bi/reports/{rid}/share",
                    json={"image_png": _PNG, "target_ids": [1]}, headers=auth_headers)
    assert r.status_code == 502
    assert any(k.get("action") == "bi_report.share" and (k.get("detail") or {}).get("ok_count") == 0
               for k in audited), "意外错误路径须仍审计 bi_report.share（出境尝试留痕）"
