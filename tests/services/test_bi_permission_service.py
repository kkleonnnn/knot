"""tests/services/test_bi_permission_service.py — v0.8.12 BI RBAC 解析 + admin bypass。

覆盖：admin 全权 / 无 grant 默认拒 / 归档报表继承目录 grant / 未分组报表逐张 grant /
全 0 权限删 grant / 未知 action False。
"""
from knot.repositories import bi_permission_repo as prepo
from knot.services import bi_permission_service as psvc

_ADMIN = {"id": 1, "role": "admin"}
_ANALYST = {"id": 2, "role": "analyst"}


def test_admin_full(tmp_db_path):
    rep = {"id": 10, "folder_id": None}
    assert psvc.effective(_ADMIN, rep) == {a: True for a in psvc.ACTIONS}
    assert psvc.can(_ADMIN, rep, "edit") is True


def test_analyst_no_grant_denied(tmp_db_path):
    assert psvc.effective(_ANALYST, {"id": 10, "folder_id": 5}) == {a: False for a in psvc.ACTIONS}
    assert psvc.can(_ANALYST, {"id": 10, "folder_id": 5}, "export") is False


def test_filed_report_inherits_folder_grant(tmp_db_path):
    prepo.set_folder_grant("analyst", 5, {"can_edit": 1, "can_export": 1}, created_by=1)
    eff = psvc.effective(_ANALYST, {"id": 10, "folder_id": 5})
    assert eff["edit"] and eff["export"] and not eff["schedule"] and not eff["share"]
    assert psvc.can(_ANALYST, {"id": 11, "folder_id": 6}, "edit") is False   # 另一目录无 grant → 拒


def test_ungrouped_report_per_report_grant(tmp_db_path):
    prepo.set_report_grant("analyst", 10, {"can_share": 1}, created_by=1)
    eff = psvc.effective(_ANALYST, {"id": 10, "folder_id": None})
    assert eff["share"] and not eff["edit"]
    assert psvc.can(_ANALYST, {"id": 99, "folder_id": None}, "share") is False  # 另一未分组报表无 grant → 拒


def test_filed_report_ignores_report_grant(tmp_db_path):
    # 归档报表只看目录 grant，不看同 id 的报表级 grant（解析分叉正确性）
    prepo.set_report_grant("analyst", 10, {"can_edit": 1}, created_by=1)
    assert psvc.can(_ANALYST, {"id": 10, "folder_id": 7}, "edit") is False


def test_all_zero_perms_deletes_grant(tmp_db_path):
    prepo.set_folder_grant("analyst", 5, {"can_edit": 1}, created_by=1)
    assert prepo.get_folder_grant("analyst", 5) is not None
    prepo.set_folder_grant("analyst", 5, {}, created_by=1)   # 全 0 → 删（默认拒）
    assert prepo.get_folder_grant("analyst", 5) is None


def test_cascade_delete(tmp_db_path):
    prepo.set_folder_grant("analyst", 5, {"can_edit": 1}, created_by=1)
    prepo.set_report_grant("analyst", 10, {"can_share": 1}, created_by=1)
    prepo.delete_for_folder(5)
    prepo.delete_for_report(10)
    assert prepo.get_folder_grant("analyst", 5) is None
    assert prepo.get_report_grant("analyst", 10) is None


def test_unknown_action_false(tmp_db_path):
    assert psvc.can(_ANALYST, {"id": 10, "folder_id": None}, "bogus") is False
