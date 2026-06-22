"""tests/repositories/test_semantic_audit_repo — v0.7.3 C1 LogicForm 审计侧表守护。

覆盖：OOS-1 死线（0 tenant_id/project_id）+ R-SL-40 catalog_id 落盘 + CRUD + 命中/near-miss +
catalog 隔离（list_audit catalog_id 过滤）+ get_by_message（engine 派生）+ 修正行（is_corrected/parent）。
"""
from knot.repositories import semantic_audit_repo as sar
from knot.repositories.base import get_conn


# ─── OOS-1 死线 + schema ──────────────────────────────────────────────

def test_schema_no_tenant_and_has_catalog_id(tmp_db_path):
    conn = get_conn()
    cols = {r[1] for r in conn.execute("PRAGMA table_info(semantic_query_audit)").fetchall()}
    conn.close()
    assert "tenant_id" not in cols and "project_id" not in cols, "OOS-1 死线：侧表严禁 tenant_id/project_id"
    assert "catalog_id" in cols, "R-SL-40：须存解析时 catalog_id"
    assert cols == {
        "id", "message_id", "catalog_id", "logicform_json",
        "compile_error_reason", "is_corrected", "parent_message_id", "created_at",
    }


# ─── CRUD + 命中 / near-miss ──────────────────────────────────────────

def test_create_hit_and_get(tmp_db_path):
    aid = sar.create_audit(message_id=10, catalog_id=1,
                           logicform_json='{"metrics":["gmv"]}')
    a = sar.get_audit(aid)
    assert a["message_id"] == 10 and a["catalog_id"] == 1
    assert a["logicform_json"] == '{"metrics":["gmv"]}'
    assert a["compile_error_reason"] == "" and a["is_corrected"] == 0


def test_create_near_miss_with_error(tmp_db_path):
    aid = sar.create_audit(message_id=11, catalog_id=2,
                           logicform_json='{"metrics":["gmv"],"dimensions":["region"]}',
                           compile_error_reason="对象无唯一 JOIN 路径 → 回退")
    a = sar.get_audit(aid)
    assert a["compile_error_reason"].startswith("对象无唯一")   # near-miss 诊断存得下


def test_get_by_message_engine_derivation(tmp_db_path):
    assert sar.get_by_message(99) is None                       # 无行 = LLM 路径
    sar.create_audit(message_id=99, catalog_id=1, logicform_json='{"metrics":["dau"]}')
    assert sar.get_by_message(99) is not None                   # 有行 = semantic 路径


# ─── catalog 隔离（R-SL-39/40）────────────────────────────────────────

def test_list_audit_by_catalog(tmp_db_path):
    sar.create_audit(message_id=1, catalog_id=1, logicform_json="a")
    sar.create_audit(message_id=2, catalog_id=2, logicform_json="b")
    assert len(sar.list_audit()) == 2                           # 全部
    c1 = sar.list_audit(catalog_id=1)
    assert len(c1) == 1 and c1[0]["message_id"] == 1            # catalog 隔离


def test_list_audit_desc_recent_first(tmp_db_path):
    sar.create_audit(message_id=1, catalog_id=1)
    sar.create_audit(message_id=2, catalog_id=1)
    rows = sar.list_audit()
    assert rows[0]["message_id"] == 2 and rows[1]["message_id"] == 1   # 最近优先


# ─── 修正行（F4 审计血缘）─────────────────────────────────────────────

def test_correction_row_lineage(tmp_db_path):
    aid = sar.create_audit(message_id=20, catalog_id=1,
                           logicform_json='{"metrics":["gmv"],"dimensions":["channel"]}',
                           is_corrected=1, parent_message_id=10)
    a = sar.get_audit(aid)
    assert a["is_corrected"] == 1 and a["parent_message_id"] == 10   # 修正链：新行指向原 message
