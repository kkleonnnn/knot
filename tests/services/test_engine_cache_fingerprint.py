"""⭐ 验收：引擎缓存的连接指纹（v0.9.23 R10'-A）。

## 它证什么
多副本下，副本 A 改了数据源，**副本 B 的进程内缓存收不到 `invalidate_*`**
⇒ 此前最多 1 小时（`_TTL_SEC`）继续用旧凭据 / 旧库清单。
本片让**键包含真正被用来建连接的那些值** ⇒ 值变了键必变 ⇒ **陈旧在结构上不可能**。

## ⚠️ 判据形状是评审逼出来的，别改回去
- **oracle = 对象身份**（`create_engine` stub 每次返新 `object()`）——
  「有没有重建」这件事**直接可观测**，不必数调用次数、不必猜走了哪条分支
  （lens B-O1：原方案那条「行为不变」是**散文**、不可执行，且在「永不缓存」实现下全绿）。
- **每格都配 no-op 负对照**（同一测内先证「该命中时真命中」）——
  否则「永不缓存」这种全坏实现会让所有「改一格就重建」的断言**全部通过**。
- **必须逐字段参数化**，不能只测密码（lens A-P1-4 / B-O6 独立同结论）：
  `create_engine` 只用 `primary`，而 `databases` 由**组内全部源**合并
  ⇒ 只对 primary 取指纹的实现，**改 secondary 仍陈旧** ⇒ 那一格才是判别力所在。
- **`get_engine_for_source`（site 3）必须单独覆盖**：它原先键里**零连接参数**，是三个站点里最严重的一个。
"""
from __future__ import annotations

import pytest

from knot.core.tenant_context import reset_active_tenant, set_active_tenant

_T1 = {"id": 1, "db_dir": "tenants/1"}


@pytest.fixture(autouse=True)
def _in_t1():
    tok = set_active_tenant(_T1)
    yield
    reset_active_tenant(tok)


def _src(**kw):
    base = {"id": 3, "is_active": 1, "db_type": "doris", "db_host": "h", "db_port": 9030,
            "db_user": "u", "db_password": "p", "db_database": "x"}
    return {**base, **kw}


def _stub(monkeypatch, ec, rows: dict, schema="schema-v1"):
    """把 get_user_engine 的 DB 依赖换成内存字典；`create_engine` 每次返**新对象**（= 身份 oracle）。"""
    monkeypatch.setattr(ec.data_source_repo, "get_user_source_ids", lambda uid: sorted(rows))
    monkeypatch.setattr(ec.data_source_repo, "get_datasource", rows.get)  # rows 原地改 ⇒ 绑定 .get 仍取最新值
    monkeypatch.setattr(ec.db_connector, "create_engine", lambda *a, **k: object())
    monkeypatch.setattr(ec.db_connector, "test_connection", lambda e: (True, ""))
    monkeypatch.setattr(ec.db_connector, "check_readonly_grants", lambda e: ("unknown", ""))
    monkeypatch.setattr(ec.db_connector, "get_schema", lambda e, **k: schema)


#: 「改这一格 ⇒ 必须重建」的字段矩阵。⚠️ `db_host`/`db_port`/`db_user` **本来就在 group_key 里**
#: （改它们此前就会重建）—— 仍列入，因为指纹**不得让它们退化**。
_MUTATIONS = [
    ("db_password", "p2"),          # ⭐ 此前**不在键里** —— 凭据轮换
    ("db_database", "x2"),          # ⭐ 此前**不在键里** —— 查询范围
    ("db_host", "h2"),
    ("db_port", 9031),
    ("db_user", "u2"),
]
# ⚠️ **`is_active` 刻意不在这张矩阵里**（实施期踩到）：我最初写了 `("is_active", 1)`，
#    而 base 本来就是 `1` ⇒ **改动压根没发生**，却断言「必重建」⇒ 测自己红了（六问②：
#    注入产生不了它要测的后果）。`is_active` 的真实效果是**把该源从 `sources` 里过滤掉**
#    （`engine_cache` 在分组前按 `is_active` 过滤）⇒ 它属于「组成员集合变了」这一类，
#    已在 `test_site1_rebuilds_when_a_secondary_source_changes` 里覆盖。


@pytest.mark.parametrize(("field", "newval"), _MUTATIONS)
def test_site1_rebuilds_when_any_connection_field_changes(monkeypatch, field, newval):
    """⭐ 验收 #1（site 1）：改任一连接字段 ⇒ **必重建**；不改 ⇒ **必命中**（同测内负对照）。

    注入：把指纹从键里去掉 ⇒ `db_password` / `db_database` 两格转红
    （其余格因 group_key 本就含它们而仍绿 —— 这正说明**只有那两格有判别力**）。
    """
    import knot.services.engine_cache as ec
    ec._engine_cache.clear()
    rows = {3: _src()}
    _stub(monkeypatch, ec, rows)
    user = {"id": 7}

    e_a, _ = ec.get_user_engine(user)
    e_b, _ = ec.get_user_engine(user)
    assert e_a is e_b, "⚠️ 负对照失败：行未动 + TTL 内**必须命中缓存** —— 否则下面的断言在测「永不缓存」"

    rows[3] = _src(**{field: newval})
    e_c, _ = ec.get_user_engine(user)
    assert e_c is not e_b, f"改了 {field} 却仍命中旧 engine —— 多副本下该副本会继续用旧连接参数"


def test_site1_rebuilds_when_a_secondary_source_changes(monkeypatch):
    """⭐⭐ 验收 #1 最关键的一格：**改组内非 primary 成员**（两个 lens 独立指出）。

    `create_engine` 只用 `primary=gsources[0]`，而 `databases` 由**组内全部源**合并
    ⇒ `group_key`（host:port:user）不变 ⇒ **只对 primary 取指纹的实现在这里仍然陈旧**。
    注入：把 `group_fingerprint([...全部源...])` 改成只喂 primary 那一行 ⇒ 本测红，而上面那些格照绿。
    """
    import knot.services.engine_cache as ec
    ec._engine_cache.clear()
    rows = {3: _src(id=3, db_database="a"), 4: _src(id=4, db_database="b")}  # 同 host:port:user ⇒ 同组
    _stub(monkeypatch, ec, rows)
    user = {"id": 7}

    e_a, _ = ec.get_user_engine(user)
    assert ec.get_user_engine(user)[0] is e_a, "负对照失败：未改动应命中"

    rows[4] = _src(id=4, db_database="b-CHANGED")          # 改 secondary
    assert ec.get_user_engine(user)[0] is not e_a, (
        "改了组内 secondary 源的 db_database 却仍命中 —— `databases` 是**组内合并**的，"
        "该副本会用旧的库清单查数（数据范围错，比连接失败更隐蔽）"
    )

    # ⭐ `is_active` 的正确测法：flip secondary 的 is_active ⇒ 它被**过滤出** `sources`
    #    ⇒ 参与合并的组成员从 [3,4] 变成 [3]（而 group_key 仍不变）⇒ 必须重建
    rows[4] = _src(id=4, db_database="b", is_active=0)
    e_flip = ec.get_user_engine(user)[0]
    assert e_flip is not e_a, "flip secondary 的 is_active 却仍命中旧 engine（该源已不该参与合并）"

    # ⚠️⚠️ **这里刻意有一条「不该重建」的负对照**（实施期我先写错了才发现）：
    #    把**已经 inactive** 的那行删掉 ⇒ 参与合并的组成员**没变**（仍是 [3]）⇒ **必须命中**。
    #    我最初断言「组成员集合变了 ⇒ 必重建」是错的：`engine_cache` 在分组**之前**就按
    #    `is_active` 过滤（`get_user_engine` 里的 `if s["is_active"]`）⇒ inactive 行从来到不了指纹。
    #    ⇒ 代码是对的，是我的判据错了。留这条负对照，免得下一个人也这么想。
    del rows[4]
    assert ec.get_user_engine(user)[0] is e_flip, (
        "删掉一个**本来就 inactive** 的源却重建了 —— 说明指纹把 inactive 行也算进去了（无谓 churn）"
    )


def test_site3_rebuilds_when_credentials_change(monkeypatch):
    """⭐ 验收 #1（site 3 `get_engine_for_source`）—— 三站点里此前**最严重**的一个。

    它的键原先是 `(tid, "source", source_id)`：**零连接参数** ⇒ 连密码都陈旧至 TTL。
    """
    import knot.services.engine_cache as ec
    ec._engine_cache.clear()
    row = {"v": _src()}
    monkeypatch.setattr(ec.data_source_repo, "get_datasource", lambda sid: row["v"])
    monkeypatch.setattr(ec.db_connector, "create_engine", lambda *a, **k: object())
    monkeypatch.setattr(ec.db_connector, "test_connection", lambda e: (True, ""))

    e_a = ec.get_engine_for_source(3)
    assert ec.get_engine_for_source(3) is e_a, "负对照失败：未改动应命中"
    row["v"] = _src(db_password="rotated")
    assert ec.get_engine_for_source(3) is not e_a, "site 3 改了密码仍命中旧 engine（该站点键里原本零连接参数）"


def test_ttl_still_governs_remote_schema_on_site1(monkeypatch):
    """⭐ 验收 #2：**TTL 没被指纹取代** —— 数据源行不变、但远端 schema 变了 ⇒ 跨 TTL 后拿到新 schema。

    ⚠️ **刻意放在 site 1，不能放 site 3**（lens B-O7 实读）：`get_engine_for_source` 的缓存条目
    只有 `{"engine","ts"}`、**不含 schema** ⇒ 在那里「TTL 管 schema 陈旧」这个理由为假。
    ⚠️ 断的是**返回的 schema 串真换成了 v2**，不是「重建了」—— 后者对「永不缓存」也成立。
    """
    import knot.services.engine_cache as ec
    ec._engine_cache.clear()
    rows = {3: _src()}
    _stub(monkeypatch, ec, rows, schema="schema-v1")
    user = {"id": 7}

    _, s1 = ec.get_user_engine(user)
    assert s1 == "schema-v1"
    monkeypatch.setattr(ec.db_connector, "get_schema", lambda e, **k: "schema-v2")
    _, s_cached = ec.get_user_engine(user)
    assert s_cached == "schema-v1", "负对照失败：TTL 内应仍返缓存里的旧 schema"

    monkeypatch.setattr(ec, "_TTL_SEC", -1)                # 让所有条目立即过期
    _, s2 = ec.get_user_engine(user)
    assert s2 == "schema-v2", "跨 TTL 后仍返旧 schema —— TTL 那一半（管远端 schema 陈旧）失效了"


def test_old_fingerprint_entry_is_evicted_and_disposed(monkeypatch):
    """⭐⭐ 验收 #3/#4：换指纹时旧条目被**移除**且其 engine 被 **`dispose()`**。

    ⚠️ **为什么这条承重**：指纹进键后，改一次凭据就多一条键；旧条目若留着，
    它持有的连接池里是用**已撤销口令**认证的**活连接** ⇒ 「凭据轮换生效」只完成了一半。
    生产码此前 `.dispose()` **0 处**。
    ⚠️ 顺带证 #4：同前缀恒只有一条 ⇒ `get_user_databases`（首个命中即返回）不可能返回旧那条。
    """
    import knot.services.engine_cache as ec
    ec._engine_cache.clear()
    disposed = []

    class _Eng:
        def __init__(self, tag): self.tag = tag
        def dispose(self): disposed.append(self.tag)

    seq = iter(range(100))
    rows = {3: _src(db_database="d1")}
    _stub(monkeypatch, ec, rows)
    monkeypatch.setattr(ec.db_connector, "create_engine", lambda *a, **k: _Eng(next(seq)))
    user = {"id": 7}

    ec.get_user_engine(user)
    keys_before = [k for k in ec._engine_cache if k[:2] == (1, 7)]
    assert len(keys_before) == 1 and disposed == [], f"起始态不对: keys={keys_before} disposed={disposed}"

    rows[3] = _src(db_database="d2")
    ec.get_user_engine(user)

    keys_after = [k for k in ec._engine_cache if k[:2] == (1, 7)]
    assert len(keys_after) == 1, (
        f"同前缀应恒只有一条，实际 {len(keys_after)} 条: {keys_after} —— "
        "旧指纹条目没被淘汰 ⇒ 旧连接池长存，且 `get_user_databases` 会返回最老那条的 databases"
    )
    assert disposed == [0], f"旧 engine 未被 dispose（实际 {disposed}）—— 已撤销口令的活连接仍在池里"
    assert ec.get_user_databases(7) == ["d2"], f"get_user_databases 返回了旧那条: {ec.get_user_databases(7)}"
