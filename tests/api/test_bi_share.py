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
