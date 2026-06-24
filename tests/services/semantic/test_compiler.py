"""tests/services/semantic/test_compiler.py — v0.7.1 C2 单对象确定性编译器守护。

R-SL-17 确定性（同 lf+time_ctx → byte-equal）· R-SL-18 单对象 · R-SL-21 catalog 隔离 ·
R-SL-22 cartesian 守护 wiring（非空转）· 保守 raise（未定义/多对象/无物理表/http/无日期列/未知 time/越界维度）·
caliber alias `o`。`_build_sql` 纯 stdlib（不依赖 DB/LLM）；compile_logicform 经 monkeypatch list_metrics。
"""
from types import SimpleNamespace

import pytest

from knot.services.semantic.compiler import CompileError, _build_sql, compile_logicform
from knot.services.semantic.logicform import LogicForm


def _time_ctx():
    return SimpleNamespace(
        this_month_to_latest=("2026-06-01", "2026-06-21"),
        this_month=("2026-06-01", "2026-06-30"),
    )


_GMV = {"name": "gmv", "caliber": "SUM(o.pay_amount)", "base_object": "shop.orders",
        "filters": '["o.status=\'paid\'"]', "dimensions": '["date","city"]'}
_DAU = {"name": "dau", "caliber": "COUNT(DISTINCT o.user_id)", "base_object": "shop.orders",
        "filters": '[]', "dimensions": '["date","city"]'}
_TABLES = [{"db": "shop", "table": "orders", "source_type": "db"}]


# ─── R-SL-17 确定性 + 结构 + alias o ─────────────────────────────────

def test_deterministic_same_lf_byte_equal():
    lf = LogicForm(metrics=["gmv"], dimensions=["city"], time="this_month_to_latest", limit=10)
    m = {"gmv": _GMV}
    assert _build_sql(lf, m, _TABLES, _time_ctx()) == _build_sql(lf, m, _TABLES, _time_ctx())


def test_sql_structure_and_alias_o():
    lf = LogicForm(metrics=["gmv"], dimensions=["city"], time="this_month_to_latest", limit=10)
    sql = _build_sql(lf, {"gmv": _GMV}, _TABLES, _time_ctx())
    assert "FROM shop.orders o" in sql
    assert "SUM(o.pay_amount) AS gmv" in sql
    assert "o.city" in sql and "GROUP BY o.city" in sql
    assert "o.date BETWEEN '2026-06-01' AND '2026-06-21'" in sql
    assert "o.status='paid'" in sql              # metric 口径内置 filter 注入
    assert sql.endswith("LIMIT 10")


def test_no_time_no_dims_default_limit():
    sql = _build_sql(LogicForm(metrics=["gmv"]), {"gmv": _GMV}, _TABLES, _time_ctx())
    assert "GROUP BY" not in sql and "BETWEEN" not in sql
    assert sql.endswith("LIMIT 1000")           # _DEFAULT_LIMIT 兜底


# ─── 保守 raise（→ F4 回退）─────────────────────────────────────────

def test_multi_object_raises():
    bad = dict(_DAU); bad["base_object"] = "shop.users"
    with pytest.raises(CompileError):
        _build_sql(LogicForm(metrics=["gmv", "dau"]), {"gmv": _GMV, "dau": bad}, _TABLES, _time_ctx())


def test_undefined_metric_raises():
    with pytest.raises(CompileError):
        _build_sql(LogicForm(metrics=["nope"]), {"gmv": _GMV}, _TABLES, _time_ctx())


def test_base_object_not_in_tables_raises():
    with pytest.raises(CompileError):
        _build_sql(LogicForm(metrics=["gmv"]), {"gmv": _GMV}, [], _time_ctx())


def test_http_table_raises():
    with pytest.raises(CompileError):
        _build_sql(LogicForm(metrics=["gmv"]), {"gmv": _GMV},
                   [{"db": "shop", "table": "orders", "source_type": "http"}], _time_ctx())


def test_time_set_no_date_col_raises():
    nodate = dict(_GMV); nodate["dimensions"] = '["city"]'
    with pytest.raises(CompileError):
        _build_sql(LogicForm(metrics=["gmv"], time="this_month_to_latest"), {"gmv": nodate}, _TABLES, _time_ctx())


def test_unknown_time_raises():
    with pytest.raises(CompileError):
        _build_sql(LogicForm(metrics=["gmv"], time="last_decade"), {"gmv": _GMV}, _TABLES, _time_ctx())


def test_dimension_not_allowed_raises():
    with pytest.raises(CompileError):
        _build_sql(LogicForm(metrics=["gmv"], dimensions=["channel"]), {"gmv": _GMV}, _TABLES, _time_ctx())


# ─── R-SL-22 cartesian 守护 wiring（非空转）+ R-SL-21 catalog 隔离 ───

def test_cartesian_guard_wired(monkeypatch):
    import knot.services.semantic.compiler as comp
    monkeypatch.setattr(comp, "is_cartesian", lambda sql: (True, "forced"))
    with pytest.raises(CompileError):
        _build_sql(LogicForm(metrics=["gmv"]), {"gmv": _GMV}, _TABLES, _time_ctx())


def test_compile_logicform_isolates_active_catalog(monkeypatch):
    captured = {}
    def fake_list(cid):
        captured["cid"] = cid
        return [_GMV]
    import knot.repositories.metric_repo as mr
    monkeypatch.setattr(mr, "list_metrics", fake_list)
    compile_logicform(LogicForm(metrics=["gmv"]), {"catalog_id": 7, "tables": _TABLES}, _time_ctx())
    assert captured["cid"] == 7                  # 传 active catalog_id（非 None 全取）


# ─── C2 alias 分配 + caliber 重写（R-SL-26/28）────────────────────────

def test_assign_aliases_single_object_o():
    from knot.services.semantic.compiler import _assign_aliases
    assert _assign_aliases(["orders"]) == {"orders": "o"}            # R-SL-28 v0.7.1 兼容


def test_assign_aliases_multi_deterministic_sorted():
    from knot.services.semantic.compiler import _assign_aliases
    assert _assign_aliases(["orders", "users"]) == {"orders": "t0", "users": "t1"}
    assert _assign_aliases(["users", "orders"]) == {"orders": "t0", "users": "t1"}  # 乱序同结果（确定性）


def test_rewrite_caliber_single_o_unchanged():
    from knot.services.semantic.compiler import _rewrite_caliber
    assert _rewrite_caliber("SUM(o.pay_amount)", "o") == "SUM(o.pay_amount)"        # byte-equal v0.7.1


def test_rewrite_caliber_multi_alias():
    from knot.services.semantic.compiler import _rewrite_caliber
    assert _rewrite_caliber("SUM(o.pay_amount)", "t0") == "SUM(t0.pay_amount)"
    assert _rewrite_caliber("COUNT(DISTINCT o.user_id)", "t1") == "COUNT(DISTINCT t1.user_id)"
    assert _rewrite_caliber("SUM(o.a) / COUNT(o.b)", "t0") == "SUM(t0.a) / COUNT(t0.b)"  # 多 ref


def test_rewrite_caliber_word_boundary_no_false_hit():
    from knot.services.semantic.compiler import _rewrite_caliber
    assert _rewrite_caliber("SUM(foo.x)", "t0") == "SUM(foo.x)"     # foo. 不误伤（o 非词首）
    assert _rewrite_caliber("SUM(info.amt)", "t0") == "SUM(info.amt)"


# ─── C3 跨对象维度 JOIN + 基数 gate（R-SL-30/31）──────────────────────

_UC = {"name": "uc", "caliber": "COUNT(o.id)", "base_object": "shop.users",
       "filters": "[]", "dimensions": '["region"]'}                 # users 对象（供 region 维度）
_TABLES2 = [{"db": "shop", "table": "orders", "source_type": "db"},
            {"db": "shop", "table": "users", "source_type": "db"}]
_REL_N1 = [["shop.orders", "user_id", "shop.users", "id", "订单用户", "n:1"]]


def test_single_object_still_uses_o_alias_r_sl_28():
    """R-SL-28：单对象（维度全在 base）→ 走 v0.7.1 路径 alias `o`（byte-equal，非 t0）。"""
    sql = _build_sql(LogicForm(metrics=["gmv"], dimensions=["city"]), {"gmv": _GMV}, _TABLES, _time_ctx())
    assert "FROM shop.orders o" in sql and "SUM(o.pay_amount) AS gmv" in sql  # alias o 不漂


def test_cross_object_dimension_join():
    """metrics gmv(orders) + 维度 region(users) → JOIN orders→users(n:1)；caliber 重写 + region 归 users alias。"""
    sql = _build_sql(LogicForm(metrics=["gmv"], dimensions=["region"]),
                     {"gmv": _GMV, "uc": _UC}, _TABLES2, _time_ctx(), _REL_N1)
    assert "JOIN shop.users" in sql and "ON" in sql
    assert "AS gmv" in sql and "region" in sql and "GROUP BY" in sql
    assert " o " not in sql.replace("FROM", "")  # 多对象不用裸 alias o（用 t0/t1）


def test_cross_object_cardinality_1n_unsafe_fallback():
    """orders→users 1:n（base orders 会被乘）→ CompileError 回退（R-SL-31）。"""
    rel_1n = [["shop.orders", "user_id", "shop.users", "id", "x", "1:n"]]
    with pytest.raises(CompileError):
        _build_sql(LogicForm(metrics=["gmv"], dimensions=["region"]),
                   {"gmv": _GMV, "uc": _UC}, _TABLES2, _time_ctx(), rel_1n)


def test_cross_object_cardinality_unknown_fallback():
    """orders→users 无基数（unknown）→ 回退（R-SL-31 严禁静默膨胀）。"""
    rel_unk = [["shop.orders", "user_id", "shop.users", "id"]]      # len 4 → unknown
    with pytest.raises(CompileError):
        _build_sql(LogicForm(metrics=["gmv"], dimensions=["region"]),
                   {"gmv": _GMV, "uc": _UC}, _TABLES2, _time_ctx(), rel_unk)


def test_cross_object_dim_no_owner_fallback():
    """维度无归属对象 → CompileError 回退（R-SL-30）。"""
    with pytest.raises(CompileError):
        _build_sql(LogicForm(metrics=["gmv"], dimensions=["nonexistent"]),
                   {"gmv": _GMV, "uc": _UC}, _TABLES2, _time_ctx(), _REL_N1)


def test_multi_base_aggregation_fallback():
    """metrics 跨 2 base（gmv on orders + uc on users 都聚合）→ CompileError 回退（R-SL-31 多 base 不支持）。"""
    with pytest.raises(CompileError):
        _build_sql(LogicForm(metrics=["gmv", "uc"]), {"gmv": _GMV, "uc": _UC}, _TABLES2, _time_ctx(), _REL_N1)


# ─── v0.7.8 HAVING（聚合后过滤）R-SL-78~81 ────────────────────────────

def test_having_empty_byte_equal():
    """R-SL-78：having 空 → SQL byte-equal（无 HAVING；现有查询 0 漂移）。"""
    m = {"gmv": _GMV}
    base = _build_sql(LogicForm(metrics=["gmv"], dimensions=["city"]), m, _TABLES, _time_ctx())
    empty = _build_sql(LogicForm(metrics=["gmv"], dimensions=["city"], having=[]), m, _TABLES, _time_ctx())
    assert base == empty and "HAVING" not in empty


def test_having_single_object():
    """单对象 HAVING：GROUP BY 后 / LIMIT 前，引 metric alias。"""
    sql = _build_sql(LogicForm(metrics=["gmv"], dimensions=["city"], having=["gmv > 10000"]),
                     {"gmv": _GMV}, _TABLES, _time_ctx())
    assert "GROUP BY o.city HAVING gmv > 10000 LIMIT" in sql


def test_having_multi_object_alias_based():
    """⭐ R-SL-80：多对象 HAVING 用 **alias**（gmv）编对 —— caliber 重写 t0 但 HAVING 引 SELECT alias（非 raw o.）。"""
    sql = _build_sql(LogicForm(metrics=["gmv"], dimensions=["region"], having=["gmv > 10000"]),
                     {"gmv": _GMV, "uc": _UC}, _TABLES2, _time_ctx(), _REL_N1)
    assert "HAVING gmv > 10000" in sql                    # alias-based（非 raw o.pay_amount）
    assert "SUM(t0.pay_amount) AS gmv" in sql             # caliber 重写 t0 + alias gmv（HAVING 引此 alias）
    assert sql.index("GROUP BY") < sql.index("HAVING") < sql.index("LIMIT")   # 子句序：GROUP BY → HAVING → LIMIT


def test_canonical_having_omitted_when_empty():
    """R-SL-81：having 空 → canonical 省略键（与存量 canonical byte-equal）；非空 → having 末位。"""
    assert '"having"' not in LogicForm(metrics=["gmv"]).to_canonical_json()
    j = LogicForm(metrics=["gmv"], having=["gmv > 100"]).to_canonical_json()
    assert j.endswith('"having":["gmv > 100"]}')          # 末位 + 非空才出现
