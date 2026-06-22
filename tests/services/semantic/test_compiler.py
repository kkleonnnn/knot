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
