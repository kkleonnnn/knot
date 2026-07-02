"""tests/repositories/test_catalog_repo — v0.6.2.5 段 4 (A1) commit 2 守护测试（TDD）。

覆盖：
- R-PB-A1-1 OOS-1 死线：catalogs 表 + users.active_catalog_id 0 tenant_id/project_id
- R-PB-A1-6 迁移幂等：init_db 跑两次 catalogs 行数恒定 + seed 仅空时
- catalog_repo CRUD（list/get/create/update）+ update 仅 6 字段（防 tenant 注入）
- per-user active 解析：get_user_active_catalog_id（NULL → 兜底 id=1）+ set_user_active_catalog
- Stage 2 修订 3 兜底熔断：catalogs 空 → get_active_catalog MetadataError（ε2 fail-fast）
"""
import pytest

from knot.models.errors import MetadataError
from knot.repositories import catalog_repo
from knot.repositories.base import get_conn, init_db


# ─── R-PB-A1-1 OOS-1 死线：0 tenant_id/project_id ────────────────────

def test_A1_1_catalogs_schema_no_tenant(tmp_db_path):
    conn = get_conn()
    cols = {r[1] for r in conn.execute("PRAGMA table_info(catalogs)").fetchall()}
    conn.close()
    assert "tenant_id" not in cols, "OOS-1 死线：catalogs 严禁 tenant_id"
    assert "project_id" not in cols, "OOS-1 死线：catalogs 严禁 project_id"
    # 10 列契约（v0.7.27 +field_labels）
    assert cols == {
        "id", "name", "description", "tables", "lexicon",
        "business_rules", "relations", "field_labels", "created_at", "updated_at",
    }


def test_A1_1_users_active_catalog_id_no_tenant(tmp_db_path):
    conn = get_conn()
    cols = {r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()}
    acols = {r[1] for r in conn.execute("PRAGMA table_info(audit_log)").fetchall()}
    conn.close()
    assert "active_catalog_id" in cols, "users.active_catalog_id 必备"
    assert "tenant_id" not in cols and "project_id" not in cols, "OOS-1 死线：users 0 tenant"
    assert "catalog_id" in acols, "audit_log.catalog_id 必备（R-PB-A1-5 ③）"


# ─── R-PB-A1-6 迁移幂等 + seed ───────────────────────────────────────

def test_A1_6_seed_catalog_id_1(tmp_db_path):
    """fresh init_db → catalog id=1 '默认 Catalog'（app_settings 空 → 空内容）。"""
    cat = catalog_repo.get_catalog(1)
    assert cat is not None
    assert cat["name"] == "默认 Catalog"
    assert cat["tables"] == "" and cat["lexicon"] == ""


def test_A1_6_migration_idempotent(tmp_db_path):
    """init_db 再跑一次 → catalogs 行数不变（seed 仅空时）。"""
    n1 = len(catalog_repo.list_catalogs())
    init_db()
    n2 = len(catalog_repo.list_catalogs())
    assert n1 == n2 == 1


def test_A1_6_seed_byte_equal_from_app_settings(tmp_db_path):
    """既有 app_settings 4-key → seed 搬入 catalog id=1（byte-equal）。"""
    conn = get_conn()
    conn.execute("DELETE FROM catalogs")  # 模拟迁移前
    for k, v in [
        ("catalog.tables", '[{"db":"ohx","table":"t1"}]'),
        ("catalog.lexicon", '{"GMV":["t1"]}'),
        ("catalog.business_rules", "rule X"),
        ("catalog.relations", '[["a","b","c","d"]]'),
    ]:
        conn.execute("INSERT OR REPLACE INTO app_settings(key, value) VALUES (?, ?)", (k, v))
    conn.commit()
    conn.close()
    init_db()  # seed 应搬运
    cat = catalog_repo.get_catalog(1)
    assert cat["tables"] == '[{"db":"ohx","table":"t1"}]'
    assert cat["lexicon"] == '{"GMV":["t1"]}'
    assert cat["business_rules"] == "rule X"
    assert cat["relations"] == '[["a","b","c","d"]]'


# ─── CRUD ────────────────────────────────────────────────────────────

def test_crud_create_get_list(tmp_db_path):
    cid = catalog_repo.create_catalog("业务方 B", description="B 的 catalog", tables="[]")
    assert cid > 1
    cat = catalog_repo.get_catalog(cid)
    assert cat["name"] == "业务方 B" and cat["description"] == "B 的 catalog"
    names = {c["name"] for c in catalog_repo.list_catalogs()}
    assert {"默认 Catalog", "业务方 B"} <= names


def test_get_catalog_missing_returns_none(tmp_db_path):
    assert catalog_repo.get_catalog(999) is None


def test_update_catalog(tmp_db_path):
    cid = catalog_repo.create_catalog("X")
    catalog_repo.update_catalog(cid, name="X2", business_rules="new rule")
    cat = catalog_repo.get_catalog(cid)
    assert cat["name"] == "X2" and cat["business_rules"] == "new rule"


def test_field_labels_crud(tmp_db_path):
    # v0.7.27：field_labels 在 _COLS（get 可读）+ _UPDATABLE（update 可写）+ create 透传
    cid = catalog_repo.create_catalog("FL", field_labels='{"market":"交易对"}')
    assert catalog_repo.get_catalog(cid)["field_labels"] == '{"market":"交易对"}'
    catalog_repo.update_catalog(cid, field_labels='{"market":"交易对","sta_date":"日期"}')
    assert catalog_repo.get_catalog(cid)["field_labels"] == '{"market":"交易对","sta_date":"日期"}'
    catalog_repo.update_catalog(cid, field_labels="")   # 空 → 清覆盖
    assert catalog_repo.get_catalog(cid)["field_labels"] == ""


def test_update_catalog_ignores_non_whitelisted_fields(tmp_db_path):
    """OOS-1：update 忽略 tenant_id 等非白名单字段（不抛、不写）。"""
    cid = catalog_repo.create_catalog("X")
    catalog_repo.update_catalog(cid, tenant_id=42, name="X3")  # tenant_id 应被忽略
    cat = catalog_repo.get_catalog(cid)
    assert cat["name"] == "X3"
    assert "tenant_id" not in cat


def test_delete_catalog(tmp_db_path):
    cid = catalog_repo.create_catalog("ToDelete")
    catalog_repo.delete_catalog(cid)
    assert catalog_repo.get_catalog(cid) is None


def test_delete_catalog_dangling_active_falls_back(tmp_db_path):
    """删除某用户 active catalog → get_active_catalog 优雅兜底 id=1（dangling 不崩）。"""
    admin_id = get_conn().execute("SELECT id FROM users WHERE username='admin'").fetchone()[0]
    cid = catalog_repo.create_catalog("ToDelete")
    catalog_repo.set_user_active_catalog(admin_id, cid)
    catalog_repo.delete_catalog(cid)
    assert catalog_repo.get_active_catalog(admin_id)["id"] == 1


# ─── per-user active 解析 ────────────────────────────────────────────

def test_active_id_fallback_to_1_when_null(tmp_db_path):
    """seed admin active_catalog_id 默认 NULL → 兜底 1。"""
    admin_id = get_conn().execute("SELECT id FROM users WHERE username='admin'").fetchone()[0]
    assert catalog_repo.get_user_active_catalog_id(admin_id) == 1


def test_set_user_active_catalog(tmp_db_path):
    admin_id = get_conn().execute("SELECT id FROM users WHERE username='admin'").fetchone()[0]
    cid = catalog_repo.create_catalog("业务方 C")
    catalog_repo.set_user_active_catalog(admin_id, cid)
    assert catalog_repo.get_user_active_catalog_id(admin_id) == cid


def test_set_user_active_catalog_ghost_raises(tmp_db_path):
    admin_id = get_conn().execute("SELECT id FROM users WHERE username='admin'").fetchone()[0]
    with pytest.raises(MetadataError):
        catalog_repo.set_user_active_catalog(admin_id, 9999)


def test_get_active_catalog_resolves(tmp_db_path):
    admin_id = get_conn().execute("SELECT id FROM users WHERE username='admin'").fetchone()[0]
    cat = catalog_repo.get_active_catalog(admin_id)
    assert cat["id"] == 1  # NULL active → 兜底 1


# ─── Stage 2 修订 3 兜底熔断（ε2 fail-fast）─────────────────────────

def test_get_active_catalog_fail_fast_empty(tmp_db_path):
    """catalogs 表清空 → 真空期 → MetadataError（拒绝静默服务空 catalog）。"""
    admin_id = get_conn().execute("SELECT id FROM users WHERE username='admin'").fetchone()[0]
    conn = get_conn()
    conn.execute("DELETE FROM catalogs")
    conn.commit()
    conn.close()
    with pytest.raises(MetadataError):
        catalog_repo.get_active_catalog(admin_id)
