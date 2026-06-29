"""tests/services/semantic/test_compiler.py — v0.7.1 C2 单对象确定性编译器守护。

R-SL-17 确定性（同 lf+time_ctx → byte-equal）· R-SL-18 单对象 · R-SL-21 catalog 隔离 ·
R-SL-22 cartesian 守护 wiring（非空转）· 保守 raise（未定义/多对象/无物理表/http/无日期列/未知 time/越界维度）·
caliber alias `o`。`_build_sql` 纯 stdlib（不依赖 DB/LLM）；compile_logicform 经 monkeypatch list_metrics。
"""
from types import SimpleNamespace

import pytest

from knot.services.semantic.compile_helpers import _resolve_date_col, _resolve_metric_date_col
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


# ─── v0.7.11 多 base 标量聚合（标量子查询入 SELECT · 0 JOIN）R-SL-98~103 ──────
# R-SL-102 语义变更：v0.7.11 前 test_multi_base_aggregation_fallback（无维度 gmv+uc → CompileError）；
# 现无维度多 base → 确定性编译（capability upgrade）；多 base + 维度/非标量 → 仍 fallback（守护边界）。

def test_multi_base_scalar_aggregation():
    """R-SL-98/99/100：多 base 标量 → 标量子查询入 SELECT（0 JOIN，保序，按构造 1 行）。"""
    sql = _build_sql(LogicForm(metrics=["gmv", "uc"]), {"gmv": _GMV, "uc": _UC}, _TABLES2, _time_ctx())
    assert sql == ("SELECT (SELECT SUM(o.pay_amount) FROM shop.orders o WHERE o.status='paid') AS gmv, "
                   "(SELECT COUNT(o.id) FROM shop.users o) AS uc LIMIT 1000")
    assert " JOIN " not in sql                           # 0 JOIN（标量子查询入 SELECT 而非 JOIN）


def test_multi_base_scalar_metrics_order_preserved():
    """R-SL-99：lf.metrics 保序 = SELECT 列序（uc 先则 uc 列在前；非 base 排序）。"""
    sql = _build_sql(LogicForm(metrics=["uc", "gmv"]), {"gmv": _GMV, "uc": _UC}, _TABLES2, _time_ctx())
    assert sql.index("AS uc") < sql.index("AS gmv")


def test_multi_base_non_common_dimension_fallback():
    """R-SL-107（v0.7.12）：维度非共同（city ∈ gmv[orders] ∉ uc[users dims=region]）→ CompileError 回退。
    （v0.7.11 此 case 是「多 base+维度一律 fallback」；v0.7.12 共同维度可编 → 仅非共同维度 fallback。）"""
    with pytest.raises(CompileError):
        _build_sql(LogicForm(metrics=["gmv", "uc"], dimensions=["city"]), {"gmv": _GMV, "uc": _UC}, _TABLES2, _time_ctx())


def test_multi_base_non_scalar_fallback():
    """⭐ R-SL-101 全矩阵 raise（守护者 Stage 3 — 非 assert）：多 base + having/window/qualify/filters 任一 → 回退。"""
    m = {"gmv": _GMV, "uc": _UC}
    for extra in ({"having": ["gmv > 1"]}, {"window": [{"func": "rank", "as_name": "r"}]},
                  {"qualify": ["r <= 1"]}, {"filters": ["o.x = 1"]}):
        with pytest.raises(CompileError):
            _build_sql(LogicForm(metrics=["gmv", "uc"], **extra), m, _TABLES2, _time_ctx())


def test_multi_base_time_base_without_date_fallback():
    """R-SL-101：多 base + time 但某 base（uc dims=[region]）无日期列 → CompileError 回退。"""
    with pytest.raises(CompileError):
        _build_sql(LogicForm(metrics=["gmv", "uc"], time="this_month_to_latest"),
                   {"gmv": _GMV, "uc": _UC}, _TABLES2, _time_ctx())


def test_multi_base_scalar_with_time_per_base():
    """多 base 标量 + time：各 base 子查询各注入**自己 base** 的日期窗。"""
    uc_dated = dict(_UC); uc_dated["dimensions"] = '["date","region"]'    # users 带 date
    sql = _build_sql(LogicForm(metrics=["gmv", "uc"], time="this_month_to_latest"),
                     {"gmv": _GMV, "uc": uc_dated}, _TABLES2, _time_ctx())
    assert "FROM shop.orders o WHERE o.status='paid' AND o.date BETWEEN '2026-06-01' AND '2026-06-21'" in sql
    assert "FROM shop.users o WHERE o.date BETWEEN '2026-06-01' AND '2026-06-21'" in sql


def test_multi_base_scalar_passes_safety_gates():
    """R-SL-100/103：标量多 base（FROM-less + 嵌套 Subquery）过 is_cartesian + _is_safe_sql DQL-only。"""
    from knot.adapters.db.doris import _is_safe_sql
    from knot.services.sql_validator import is_cartesian
    sql = _build_sql(LogicForm(metrics=["gmv", "uc"]), {"gmv": _GMV, "uc": _UC}, _TABLES2, _time_ctx())
    assert is_cartesian(sql)[0] is False                 # 0 JOIN / 无 comma-FROM → 不误判（R-SL-100）
    assert _is_safe_sql(sql)[0] is True                  # Select 根 + 嵌套 Subquery ∈ allowed_roots（R-SL-103）


# ─── v0.7.12 多 base + 维度「聚合后 JOIN」维度并集驱动（Option U）R-SL-105~108 ──
# 共同维度 fixtures（gmv@orders + dau@users 共享 city）
_GMV_C = {"name": "gmv", "caliber": "SUM(o.pay_amount)", "base_object": "shop.orders",
          "filters": "[]", "dimensions": '["date","city"]'}
_DAU_C = {"name": "dau", "caliber": "COUNT(o.id)", "base_object": "shop.users",
          "filters": "[]", "dimensions": '["city"]'}


def test_multi_base_dimensional_union_driver():
    """R-SL-106：维度并集驱动 — UNION driver + LEFT JOIN 各 metric agg + ON dim.dim=t{i}.dim（对称不丢）。"""
    sql = _build_sql(LogicForm(metrics=["gmv", "dau"], dimensions=["city"]),
                     {"gmv": _GMV_C, "dau": _DAU_C}, _TABLES2, _time_ctx())
    assert sql.startswith("SELECT dim.city, t0.gmv, t1.dau FROM (SELECT DISTINCT o.city FROM shop.orders o "
                          "UNION SELECT DISTINCT o.city FROM shop.users o) dim")
    assert "LEFT JOIN (SELECT o.city, SUM(o.pay_amount) AS gmv FROM shop.orders o GROUP BY o.city) t0 ON dim.city = t0.city" in sql
    assert "LEFT JOIN (SELECT o.city, COUNT(o.id) AS dau FROM shop.users o GROUP BY o.city) t1 ON dim.city = t1.city" in sql
    assert sql.endswith("LIMIT 1000")


def test_multi_base_dimensional_per_metric_filters():
    """⭐ R-SL-106 守护者 Stage 3 bug 守护：同 base 两 metric 不同 filter → 各 agg **自己的 filter**（非共用 names[0]）。"""
    paid = {"name": "paid_gmv", "caliber": "SUM(o.pay_amount)", "base_object": "shop.orders",
            "filters": '["o.status=\'paid\'"]', "dimensions": '["city"]'}
    allg = {"name": "all_gmv", "caliber": "SUM(o.pay_amount)", "base_object": "shop.orders",
            "filters": "[]", "dimensions": '["city"]'}
    sql = _build_sql(LogicForm(metrics=["paid_gmv", "all_gmv", "dau"], dimensions=["city"]),
                     {"paid_gmv": paid, "all_gmv": allg, "dau": _DAU_C}, _TABLES2, _time_ctx())
    assert "SUM(o.pay_amount) AS paid_gmv FROM shop.orders o WHERE o.status='paid' GROUP BY o.city" in sql  # paid 有 filter
    assert "SUM(o.pay_amount) AS all_gmv FROM shop.orders o GROUP BY o.city" in sql      # all_gmv 无 WHERE（未被 paid 污染）


def test_multi_base_dimensional_passes_safety_gates():
    """R-SL-108：维度并集驱动（UNION + LEFT JOIN）过 is_cartesian（LEFT-with-ON 不误判）+ _is_safe_sql（Union∈allowed_roots）。"""
    from knot.adapters.db.doris import _is_safe_sql
    from knot.services.sql_validator import is_cartesian
    sql = _build_sql(LogicForm(metrics=["gmv", "dau"], dimensions=["city"]),
                     {"gmv": _GMV_C, "dau": _DAU_C}, _TABLES2, _time_ctx())
    assert is_cartesian(sql)[0] is False                 # LEFT JOIN 有 ON（非 CROSS）+ UNION 分支无 join → 不误判
    assert _is_safe_sql(sql)[0] is True                  # Select 根 + Union + 嵌套 Subquery ∈ allowed_roots


def test_multi_base_dimensional_time_per_metric_base():
    """R-SL-109：多 base 维度 + time → 维度域 UNION 分支 + agg 各注入自己 base 的日期窗（共同维度 date）。"""
    gmv_d = dict(_GMV_C); dau_d = dict(_DAU_C); dau_d["dimensions"] = '["date","city"]'
    sql = _build_sql(LogicForm(metrics=["gmv", "dau"], dimensions=["date"], time="this_month_to_latest"),
                     {"gmv": gmv_d, "dau": dau_d}, _TABLES2, _time_ctx())
    assert "SELECT DISTINCT o.date FROM shop.orders o WHERE o.date BETWEEN '2026-06-01' AND '2026-06-21'" in sql
    assert "FROM shop.orders o WHERE o.date BETWEEN '2026-06-01' AND '2026-06-21' GROUP BY o.date) t0" in sql


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


# ─── v0.7.9 窗口函数（排名/同环比/累计）两层 R-SL-84~88 ──────────────────

def test_window_empty_byte_equal():
    """R-SL-84：window 空 → 单层 SQL byte-equal（不退化包子查询；现有查询 0 漂移）。"""
    m = {"gmv": _GMV}
    base = _build_sql(LogicForm(metrics=["gmv"], dimensions=["city"]), m, _TABLES, _time_ctx())
    win0 = _build_sql(LogicForm(metrics=["gmv"], dimensions=["city"], window=[]), m, _TABLES, _time_ctx())
    assert base == win0 and "OVER" not in win0 and ") sub" not in win0   # 单层不退化


def test_window_ranking_two_level():
    """R-SL-87：两层 —— 外层 SELECT sub.* + 窗口列 + 整个 _order_limit；内层聚合（无 LIMIT）。"""
    lf = LogicForm(metrics=["gmv"], dimensions=["city"], limit=10,
                   window=[{"func": "row_number", "partition_by": ["city"],
                            "order_by": [{"field": "gmv", "dir": "desc"}], "as_name": "rk"}])
    sql = _build_sql(lf, {"gmv": _GMV}, _TABLES, _time_ctx())
    assert sql.startswith("SELECT sub.*, ROW_NUMBER() OVER (PARTITION BY city ORDER BY gmv DESC) AS rk FROM (")
    assert "GROUP BY o.city) sub LIMIT 10" in sql        # 内层 GROUP BY（无 LIMIT）+ 外层 LIMIT


def test_window_multi_object_alias_based():
    """⭐ R-SL-86：多对象窗口 OVER 引 **alias**（gmv）—— 内层 caliber 重写 t0，外层 OVER 引子查询 alias 列。"""
    lf = LogicForm(metrics=["gmv"], dimensions=["region"],
                   window=[{"func": "rank", "partition_by": ["region"],
                            "order_by": [{"field": "gmv", "dir": "desc"}], "as_name": "rk"}])
    sql = _build_sql(lf, {"gmv": _GMV, "uc": _UC}, _TABLES2, _time_ctx(), _REL_N1)
    assert "RANK() OVER (PARTITION BY region ORDER BY gmv DESC) AS rk" in sql   # 外层 OVER 引 alias gmv（非 t0.）
    assert "SUM(t0.pay_amount) AS gmv" in sql            # 内层 caliber 重写 t0
    assert "FROM (" in sql and ") sub" in sql            # 两层包裹


def test_window_func_whitelist_real_sql_names():
    """R-SL-85：func key 映射**真实 SQL 函数**（dense_rank→DENSE_RANK 非 RANK_DENSE）+ 带参 lag/sum/avg。"""
    def col(func, arg=None):
        w = {"func": func, "order_by": [{"field": "gmv", "dir": "desc"}], "as_name": "x"}
        if arg:
            w["arg"] = arg
        return _build_sql(LogicForm(metrics=["gmv"], dimensions=["city"], window=[w]),
                          {"gmv": _GMV}, _TABLES, _time_ctx())
    assert "DENSE_RANK() OVER" in col("dense_rank")      # dense_rank → DENSE_RANK（非 Stage2 笔误 RANK_DENSE）
    assert "ROW_NUMBER() OVER" in col("row_number")
    assert "LAG(gmv) OVER" in col("lag", "gmv")          # 带参
    assert "SUM(gmv) OVER" in col("sum", "gmv")
    assert "AVG(gmv) OVER" in col("avg", "gmv")          # avg 保留（Stage2 误删）


def test_window_unknown_func_raises():
    """R-SL-85：未知 func（如 Stage2 笔误 rank_dense）→ CompileError 回退（非静默生成不存在函数）。"""
    lf = LogicForm(metrics=["gmv"], dimensions=["city"],
                   window=[{"func": "rank_dense", "order_by": [{"field": "gmv", "dir": "desc"}], "as_name": "x"}])
    with pytest.raises(CompileError):
        _build_sql(lf, {"gmv": _GMV}, _TABLES, _time_ctx())


def test_canonical_window_omitted_when_empty():
    """R-SL-88：window 空 → canonical 省略键（存量 byte-equal）；非空 → window 末位（having 后）。"""
    assert '"window"' not in LogicForm(metrics=["gmv"]).to_canonical_json()
    j = LogicForm(metrics=["gmv"], window=[{"func": "row_number", "as_name": "rk"}]).to_canonical_json()
    assert '"window"' in j and j.endswith("}")


# ─── v0.7.10 分区 top-N（窗口结果过滤）三层 R-SL-91~96 ──────────────────

_W_RK = [{"func": "row_number", "partition_by": ["city"],
          "order_by": [{"field": "gmv", "dir": "desc"}], "as_name": "rk"}]


def test_qualify_empty_byte_equal_two_level():
    """R-SL-93：window + qualify 空 → 两层 byte-equal（不退化加第三层；v0.7.9 0 漂移）。"""
    m = {"gmv": _GMV}
    two = _build_sql(LogicForm(metrics=["gmv"], dimensions=["city"], window=_W_RK), m, _TABLES, _time_ctx())
    q0 = _build_sql(LogicForm(metrics=["gmv"], dimensions=["city"], window=_W_RK, qualify=[]), m, _TABLES, _time_ctx())
    assert two == q0 and ") win WHERE" not in q0      # qualify 空不加第三层


def test_qualify_partition_topn_single_object():
    """R-SL-92：三层 —— 外层 SELECT * FROM (<两层>) win WHERE <qualify> + 最外层 _order_limit（只一次）。"""
    lf = LogicForm(metrics=["gmv"], dimensions=["city"], limit=20, window=_W_RK, qualify=["rk <= 3"])
    sql = _build_sql(lf, {"gmv": _GMV}, _TABLES, _time_ctx())
    assert sql.startswith(
        "SELECT * FROM (SELECT sub.*, ROW_NUMBER() OVER (PARTITION BY city ORDER BY gmv DESC) AS rk FROM (")
    assert ") sub) win WHERE rk <= 3 LIMIT 20" in sql   # 第三层 WHERE + 最外层 LIMIT（非内层）
    assert sql.count("LIMIT") == 1                       # R-SL-92 _order_limit 只在最外层一次


def test_qualify_partition_topn_multi_object_alias_based():
    """⭐ R-SL-95：多对象三层 qualify 引 alias（rk）—— 内层 caliber 重写 t0，窗口 OVER 引 alias，qualify 引窗口 as_name。"""
    lf = LogicForm(metrics=["gmv"], dimensions=["region"], qualify=["rk <= 5"],
                   window=[{"func": "rank", "partition_by": ["region"],
                            "order_by": [{"field": "gmv", "dir": "desc"}], "as_name": "rk"}])
    sql = _build_sql(lf, {"gmv": _GMV, "uc": _UC}, _TABLES2, _time_ctx(), _REL_N1)
    assert "SUM(t0.pay_amount) AS gmv" in sql            # 内层 caliber 重写 t0
    assert "RANK() OVER (PARTITION BY region ORDER BY gmv DESC) AS rk" in sql  # 窗口 OVER 引 alias gmv（非 t0.）
    assert ") win WHERE rk <= 5 LIMIT" in sql            # 第三层 qualify 引窗口 as_name rk（alias-based）
    assert sql.startswith("SELECT * FROM (")             # 三层包裹


def test_qualify_without_window_raises():
    """R-SL-94：qualify 非空但 window 空 → CompileError 回退（严禁静默丢弃 → 否则返全量非 top-N 错答案）。"""
    with pytest.raises(CompileError):
        _build_sql(LogicForm(metrics=["gmv"], dimensions=["city"], qualify=["rk <= 3"]),
                   {"gmv": _GMV}, _TABLES, _time_ctx())


def test_qualify_three_level_passes_is_safe_sql():
    """R-SL-96：三层（嵌套 Subquery）过 _is_safe_sql DQL-only 收口（单 + 多对象）——外层 Select 根 + Subquery ∈ allowed_roots。"""
    from knot.adapters.db.doris import _is_safe_sql
    single = _build_sql(LogicForm(metrics=["gmv"], dimensions=["city"], window=_W_RK, qualify=["rk <= 3"]),
                        {"gmv": _GMV}, _TABLES, _time_ctx())
    multi = _build_sql(LogicForm(metrics=["gmv"], dimensions=["region"], qualify=["rk <= 5"],
                                 window=[{"func": "rank", "partition_by": ["region"],
                                          "order_by": [{"field": "gmv", "dir": "desc"}], "as_name": "rk"}]),
                       {"gmv": _GMV, "uc": _UC}, _TABLES2, _time_ctx(), _REL_N1)
    assert _is_safe_sql(single)[0] is True
    assert _is_safe_sql(multi)[0] is True               # 非-DQL 收口（不守 alias 正确性 — 两个门别混 R-SL-95/96）


def test_canonical_qualify_omitted_when_empty():
    """R-SL-91：qualify 空 → canonical 省略键（存量 byte-equal）；非空 → qualify 末位（window 后）。"""
    assert '"qualify"' not in LogicForm(metrics=["gmv"]).to_canonical_json()
    j = LogicForm(metrics=["gmv"], window=[{"func": "row_number", "as_name": "rk"}],
                  qualify=["rk <= 3"]).to_canonical_json()
    assert j.endswith('"qualify":["rk <= 3"]}')          # 末位（window 后）+ 非空才出现


# ─── v0.7.13 抽 multi_base.py 纯重构 — CompileError re-export identity 哨兵 R-SL-115 ──

def test_v0713_compile_error_reexport_identity():
    """R-SL-115：CompileError 单定义 compile_helpers + compiler/multi_base re-export **同一类对象**
    → `except compiler.CompileError` 捕获 multi_base raise（5+ 生产 except 不破；Contract 9 只查 no-import 不查 identity）。"""
    from knot.services.semantic import compile_helpers, compiler, multi_base
    assert compiler.CompileError is compile_helpers.CompileError       # compiler re-export 同对象
    assert multi_base.CompileError is compile_helpers.CompileError     # multi_base import 同对象


def test_v0713_multi_base_routes_through_build_sql():
    """R-SL-117：多 base 走 multi_base.build_multi_base_sql（compiler `_build_sql` 包 _guard）byte-equal。"""
    sql = _build_sql(LogicForm(metrics=["gmv", "uc"]), {"gmv": _GMV, "uc": _UC}, _TABLES2, _time_ctx())
    assert sql.startswith("SELECT (SELECT SUM(o.pay_amount)")          # 标量多 base SQL 不变（纯移动）
    assert " JOIN " not in sql


# ─── v0.7.14 CTE 结果再聚合（outer-aggregate）R-SL-118~123 ──────────────────

def _compile_outer(monkeypatch, lf):
    """经 compile_logicform 编译（outer wrap 在 compile_logicform 非 _build_sql；monkeypatch metric_repo）。"""
    import knot.repositories.metric_repo as mr
    monkeypatch.setattr(mr, "list_metrics", lambda cid: [_GMV])
    return compile_logicform(lf, {"catalog_id": 1, "tables": _TABLES}, _time_ctx())


def test_outer_count_groups_no_limit(monkeypatch):
    """⭐ R-SL-122：outer count + limit=0 → CTE body **无 LIMIT**（count groups 不被 cap = 正确标量答案；守护者 Stage 3 必纠）。"""
    sql = _compile_outer(monkeypatch, LogicForm(metrics=["gmv"], dimensions=["city"],
                                                having=["gmv > 10000"], outer={"func": "count"}))
    assert sql.startswith("WITH r AS (") and sql.endswith("SELECT COUNT(*) AS result FROM r")
    assert "HAVING gmv > 10000" in sql        # 复用 v0.7.8 HAVING 作 body
    assert "LIMIT" not in sql                 # ⭐ inner 无 LIMIT（修复：count groups 不被 cap）


def test_outer_sum_topn_keeps_limit(monkeypatch):
    """R-SL-122：outer sum + 显式 limit=5（top-N）→ inner 保 LIMIT 5（top-5 后聚合 intentional）。"""
    lf = LogicForm(metrics=["gmv"], dimensions=["city"], limit=5,
                   order_by=[{"field": "gmv", "dir": "desc"}], outer={"func": "sum", "arg": "gmv"})
    sql = _compile_outer(monkeypatch, lf)
    assert "LIMIT 5) SELECT SUM(gmv) AS result FROM r" in sql   # inner 保 top-5 LIMIT + 外层 SUM


def test_outer_empty_byte_equal(monkeypatch):
    """R-SL-119：outer 空 → 无 CTE wrap，与 _build_sql 输出 byte-equal（存量 0 漂移）。"""
    lf = LogicForm(metrics=["gmv"], dimensions=["city"])
    via_compile = _compile_outer(monkeypatch, lf)
    direct = _build_sql(lf, {"gmv": _GMV}, _TABLES, _time_ctx())
    assert via_compile == direct and "WITH r" not in via_compile


def test_outer_unknown_func_raises(monkeypatch):
    """R-SL-120：未知 outer func → CompileError 回退。"""
    with pytest.raises(CompileError):
        _compile_outer(monkeypatch, LogicForm(metrics=["gmv"], dimensions=["city"], outer={"func": "median"}))


def test_outer_arg_not_in_columns_raises(monkeypatch):
    """R-SL-120：outer arg ∉ metrics∪dimensions（raw o.col/越界）→ CompileError（alias-based 守护，同 having R-SL-80）。"""
    with pytest.raises(CompileError):
        _compile_outer(monkeypatch, LogicForm(metrics=["gmv"], dimensions=["city"],
                                              outer={"func": "sum", "arg": "o.pay_amount"}))


def test_outer_passes_safety_gates(monkeypatch):
    """R-SL-121：CTE（WITH）过 _is_safe_sql（With∈allowed_roots）+ is_cartesian（CTE body guarded + outer 无 join）。"""
    from knot.adapters.db.doris import _is_safe_sql
    from knot.services.sql_validator import is_cartesian
    sql = _compile_outer(monkeypatch, LogicForm(metrics=["gmv"], dimensions=["city"], outer={"func": "count"}))
    assert is_cartesian(sql)[0] is False
    assert _is_safe_sql(sql)[0] is True


def test_canonical_outer_omitted_when_empty():
    """R-SL-118：outer 空 → canonical 省略键（存量 byte-equal）；非空 → outer 末位（qualify 后）。"""
    assert '"outer"' not in LogicForm(metrics=["gmv"]).to_canonical_json()
    j = LogicForm(metrics=["gmv"], outer={"func": "count"}).to_canonical_json()
    assert j.endswith('"outer":{"func":"count"}}')


# ─── v0.7.15 自定义窗口 frame（ROWS BETWEEN 移动平均）R-SL-125~129 ───────────

def _win_frame(frame, func="avg", order=True):
    w = {"func": func, "arg": "gmv", "as_name": "ma", "frame": frame}
    if order:
        w["order_by"] = [{"field": "date", "dir": "asc"}]
    return LogicForm(metrics=["gmv"], dimensions=["date"], window=[w])


def test_window_frame_moving_average():
    """R-SL-126/127：avg + order_by + frame → `AVG(gmv) OVER (ORDER BY date ASC ROWS BETWEEN 6 PRECEDING AND CURRENT ROW)`。"""
    sql = _build_sql(_win_frame({"preceding": 6, "following": 0}), {"gmv": _GMV}, _TABLES, _time_ctx())
    assert "AVG(gmv) OVER (ORDER BY date ASC ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) AS ma" in sql


def test_window_frame_unbounded():
    """R-SL-126：unbounded 边界枚举正确编译。"""
    sql = _build_sql(_win_frame({"preceding": "unbounded", "following": 0}), {"gmv": _GMV}, _TABLES, _time_ctx())
    assert "ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW" in sql


def test_window_frame_injection_safe_raises():
    """⭐ R-SL-126：frame 边界非「非负 int/unbounded」（恶意串/负/bool）→ CompileError（0 裸拼）。"""
    for bad in ["6; DROP TABLE x", -1, True]:
        with pytest.raises(CompileError):
            _build_sql(_win_frame({"preceding": bad, "following": 0}), {"gmv": _GMV}, _TABLES, _time_ctx())


def test_window_frame_ranking_raises():
    """R-SL-127：ranking/lag/lead + frame → CompileError（frame 仅 sum/avg 聚合窗口）。"""
    for func in ("row_number", "rank", "lag"):
        with pytest.raises(CompileError):
            _build_sql(_win_frame({"preceding": 6, "following": 0}, func=func), {"gmv": _GMV}, _TABLES, _time_ctx())


def test_window_frame_needs_order_by_raises():
    """R-SL-127：frame 无 ORDER BY → CompileError。"""
    with pytest.raises(CompileError):
        _build_sql(_win_frame({"preceding": 6, "following": 0}, order=False), {"gmv": _GMV}, _TABLES, _time_ctx())


def test_window_no_frame_byte_equal():
    """R-SL-128：window 无 frame → v0.7.9 两层 SQL byte-equal（frame additive，存量 0 漂移）。"""
    w_noframe = LogicForm(metrics=["gmv"], dimensions=["city"],
                          window=[{"func": "rank", "partition_by": ["city"],
                                   "order_by": [{"field": "gmv", "dir": "desc"}], "as_name": "rk"}])
    sql = _build_sql(w_noframe, {"gmv": _GMV}, _TABLES, _time_ctx())
    assert "ROWS BETWEEN" not in sql and "RANK() OVER (PARTITION BY city ORDER BY gmv DESC) AS rk" in sql


def test_window_frame_passes_safety_gates():
    """R-SL-129：ROWS BETWEEN（OVER window spec）过 _is_safe_sql DQL-only + is_cartesian。"""
    from knot.adapters.db.doris import _is_safe_sql
    from knot.services.sql_validator import is_cartesian
    sql = _build_sql(_win_frame({"preceding": 6, "following": 0}), {"gmv": _GMV}, _TABLES, _time_ctx())
    assert is_cartesian(sql)[0] is False and _is_safe_sql(sql)[0] is True


def test_canonical_frame_recursive_sort():
    """R-SL-125：window frame 嵌套 dict 递归排 → 语义相等 frame 不同键序 **等 canonical**（与 order_by 对齐）。"""
    w1 = LogicForm(metrics=["g"], window=[{"func": "avg", "frame": {"preceding": 6, "following": 0}}]).to_canonical_json()
    w2 = LogicForm(metrics=["g"], window=[{"func": "avg", "frame": {"following": 0, "preceding": 6}}]).to_canonical_json()
    assert w1 == w2                                              # 不同键序 → 等 canonical
    assert '"frame":{"following":0,"preceding":6}' in w1         # frame 内递归排（f<p）


# ─── v0.7.16 派生指标模型（占比/人均 = metric÷metric · 标量+单层）R-SL-132~139 ──
# 派生 fixtures：arpu = gmv÷dau（gmv@orders + dau@users 跨 base 标量；派生 base_object 空 + lineage object）
_GMV_D = {"name": "gmv", "caliber": "SUM(o.pay_amount)", "base_object": "shop.orders",
          "filters": "[]", "dimensions": '["date"]', "lineage": ""}
_DAU_D = {"name": "dau", "caliber": "COUNT(DISTINCT o.user_id)", "base_object": "shop.users",
          "filters": "[]", "dimensions": '["date"]', "lineage": ""}
_ARPU = {"name": "arpu", "caliber": "", "base_object": "",
         "lineage": '{"op":"divide","left":"gmv","right":"dau"}'}
_DERIVED_MBN = {"gmv": _GMV_D, "dau": _DAU_D, "arpu": _ARPU}


def test_derived_scalar_divide_nullif():
    """R-SL-132~135：派生 arpu=gmv÷dau → `(left subq) / NULLIF(right subq, 0) AS arpu`（FROM-less 0 JOIN + 除零防护）。"""
    sql = _build_sql(LogicForm(metrics=["arpu"]), _DERIVED_MBN, _TABLES2, _time_ctx())
    assert sql == ("SELECT (SELECT SUM(o.pay_amount) FROM shop.orders o) / "
                   "NULLIF((SELECT COUNT(DISTINCT o.user_id) FROM shop.users o), 0) AS arpu")
    assert " JOIN " not in sql                                   # 0 JOIN（标量子查询算术，免疫基数坑）


def test_derived_dispatch_before_metric_bases():
    """⭐ R-SL-136：派生 base_object 空 → dispatch **先于** _metric_bases（否则空 base 被误 raise）。"""
    sql = _build_sql(LogicForm(metrics=["arpu"]), _DERIVED_MBN, _TABLES2, _time_ctx())
    assert "AS arpu" in sql                                      # 派生 base_object='' 不触发 _metric_bases 空 base raise


def test_derived_ops_no_nullif_except_divide():
    """R-SL-133：×/+/− op → 对应 SQL 运算符；**仅 divide 包 NULLIF**（其余裸算术）。"""
    for op, sym in (("multiply", "*"), ("add", "+"), ("subtract", "-")):
        m = dict(_ARPU); m["lineage"] = f'{{"op":"{op}","left":"gmv","right":"dau"}}'
        sql = _build_sql(LogicForm(metrics=["arpu"]), {**_DERIVED_MBN, "arpu": m}, _TABLES2, _time_ctx())
        assert f" {sym} " in sql and "NULLIF" not in sql


def test_derived_unknown_op_raises():
    """⭐ R-SL-133 注入安全：op ∉ 白名单（divide/multiply/add/subtract）→ CompileError（0 裸拼运算符）。"""
    m = dict(_ARPU); m["lineage"] = '{"op":"powerrr","left":"gmv","right":"dau"}'
    with pytest.raises(CompileError):
        _build_sql(LogicForm(metrics=["arpu"]), {**_DERIVED_MBN, "arpu": m}, _TABLES2, _time_ctx())


def test_derived_dep_not_in_registry_raises():
    """R-SL-134：派生 left/right ∉ 注册表 → CompileError 回退（无 gmv/dau 定义）。"""
    with pytest.raises(CompileError):
        _build_sql(LogicForm(metrics=["arpu"]), {"arpu": _ARPU}, _TABLES2, _time_ctx())


def test_derived_nested_single_level_raises():
    """⭐ R-SL-135 单层防循环：left/right 须**原子** metric；嵌套派生（left=派生）→ CompileError（免 DFS 循环）。"""
    nested = {"name": "x", "caliber": "", "base_object": "",
              "lineage": '{"op":"divide","left":"arpu","right":"dau"}'}   # left=arpu(派生)
    with pytest.raises(CompileError):
        _build_sql(LogicForm(metrics=["x"]), {**_DERIVED_MBN, "x": nested}, _TABLES2, _time_ctx())


def test_derived_non_scalar_fallback():
    """R-SL-137：派生仅标量 — dimensions/having/window/qualify/outer/filters 任一 → CompileError（维度派生留后续）。"""
    for extra in ({"dimensions": ["city"]}, {"having": ["arpu>1"]},
                  {"filters": ["o.x=1"]}, {"limit": 0, "outer": {"func": "count"}}):
        with pytest.raises(CompileError):
            _build_sql(LogicForm(metrics=["arpu"], **extra), _DERIVED_MBN, _TABLES2, _time_ctx())


def test_derived_time_per_dep_injection():
    """⭐ R-SL-138（守护者修订 1）：本月 arpu → time **per-dep 注入**两子查询（gmv@orders.date + dau@users.date 各自窗）。"""
    sql = _build_sql(LogicForm(metrics=["arpu"], time="this_month_to_latest"), _DERIVED_MBN, _TABLES2, _time_ctx())
    assert "FROM shop.orders o WHERE o.date BETWEEN '2026-06-01' AND '2026-06-21'" in sql
    assert "FROM shop.users o WHERE o.date BETWEEN '2026-06-01' AND '2026-06-21'" in sql


def test_derived_passes_safety_gates():
    """R-SL-139：派生标量（FROM-less + 嵌套 Subquery 算术）过 is_cartesian（0 JOIN 不误判）+ _is_safe_sql DQL-only。"""
    from knot.adapters.db.doris import _is_safe_sql
    from knot.services.sql_validator import is_cartesian
    sql = _build_sql(LogicForm(metrics=["arpu"]), _DERIVED_MBN, _TABLES2, _time_ctx())
    assert is_cartesian(sql)[0] is False                         # FROM-less + 0 JOIN → 不误判
    assert _is_safe_sql(sql)[0] is True                          # Select 根 + 嵌套 Subquery ∈ allowed_roots


# ─── v0.7.17 metric 显式 date_column + 两遍 _resolve_date_col（修 sta_date gap）R-SL-140~146 ──
# OHX 风格：显式 date_column=sta_date（维度无 regex-匹配日期列）+ 无 date_column 靠 sta_date 维度兜底
_GMV_DC = {"name": "gmv", "caliber": "SUM(o.pay_amount)", "base_object": "shop.orders",
           "filters": "[]", "dimensions": '["symbol","city"]', "date_column": "sta_date"}
_GMV_STA = {"name": "gmv", "caliber": "SUM(o.pay_amount)", "base_object": "shop.orders",
            "filters": "[]", "dimensions": '["sta_date","city"]', "date_column": ""}


def test_date_col_two_pass_byte_equal_order_drift():
    """⭐ R-SL-142（守护者 Stage 3 order-drift 守护）：多日期列 pass1 旧 exact 逐字 → `["created_date","dt"]` 返 `dt`（非 _date$ 列抢占）。"""
    assert _resolve_date_col(sorted(["created_date", "dt"])) == "dt"          # exact 'dt' 赢 _date$ 'created_date'
    assert _resolve_date_col(sorted(["amount_date", "stat_date"])) == "stat_date"  # pass1 保留 stat_date
    assert _resolve_date_col(["date", "city"]) == "date"                      # 存量 byte-equal


def test_date_col_two_pass_fills_sta_date():
    """R-SL-143：pass2 `.endswith("_date")` 兜底 → `sta_date` 命中（修 OHX gap；单 regex re.match 锚首失效）。"""
    assert _resolve_date_col(["sta_date", "symbol"]) == "sta_date"
    assert _resolve_date_col(["symbol", "sta_date"]) == "sta_date"            # pass2 与序无关（pass1 全 miss）


def test_date_col_no_overmatch():
    """R-SL-143：无 `_date` 后缀不过匹配（守护者盲刺）→ None（→ time raise → 回退）。"""
    assert _resolve_date_col(["city"]) is None
    assert _resolve_date_col(["city_candidate", "update_state"]) is None


def test_resolve_metric_date_col_explicit_wins():
    """R-SL-141/144：显式 date_column 绝对优先（即使维度无匹配列）；空白串 strip→fallback。"""
    assert _resolve_metric_date_col(_GMV_DC) == "sta_date"                    # 显式赢，dims=[symbol,city] 无 _date
    assert _resolve_metric_date_col(_GMV_DC, ["symbol"]) == "sta_date"        # fallback_dims 无关，显式赢
    assert _resolve_metric_date_col(_GMV_STA) == "sta_date"                   # 未声明 → dims 兜底
    assert _resolve_metric_date_col({"date_column": "  ", "dimensions": '["date"]'}) == "date"  # 空白 strip→fallback


def test_metric_date_column_explicit_injects():
    """R-SL-144：metric date_column=sta_date + time → SQL 含 `o.sta_date BETWEEN`（维度无 _date 列仍注入）。"""
    sql = _build_sql(LogicForm(metrics=["gmv"], time="this_month_to_latest"), {"gmv": _GMV_DC}, _TABLES, _time_ctx())
    assert "o.sta_date BETWEEN '2026-06-01' AND '2026-06-21'" in sql


def test_metric_date_column_regex_fallback_injects():
    """R-SL-143：metric 无 date_column + 维度含 sta_date → 两遍 pass2 命中 → 注入（修 OHX gap）。"""
    sql = _build_sql(LogicForm(metrics=["gmv"], time="this_month_to_latest"), {"gmv": _GMV_STA}, _TABLES, _time_ctx())
    assert "o.sta_date BETWEEN '2026-06-01' AND '2026-06-21'" in sql


def test_metric_no_date_column_byte_equal_existing():
    """R-SL-142 byte-equal：未声明 date_column + 维度 `["date","city"]`（_GMV 存量）→ 编译 SQL 与 v0.7.16 exact ==。"""
    lf = LogicForm(metrics=["gmv"], dimensions=["city"], time="this_month_to_latest", limit=10)
    assert _build_sql(lf, {"gmv": _GMV}, _TABLES, _time_ctx()) == (
        "SELECT o.city, SUM(o.pay_amount) AS gmv FROM shop.orders o "   # 单对象 SELECT = 维度 + caliber
        "WHERE o.status='paid' AND o.date BETWEEN '2026-06-01' AND '2026-06-21' "
        "GROUP BY o.city LIMIT 10")


# ─── v0.7.19 DATETIME 日期列半开区间（修 dwd sta_time 全天漏空）──────────────
def test_v0719_datetime_col_half_open_range():
    """⭐ v0.7.19：DATETIME 列（sta_time/update_time）→ 半开区间 `>= start 00:00:00 AND < (end+1) 00:00:00`
    覆盖全天（旧 `BETWEEN 'date' AND 'date'` 在 datetime 列只匹配午夜瞬间 → 全天漏空 NULL，实测 dwd 今天返空）。
    DATE 列（sta_date）保 BETWEEN（存量 byte-equal）。"""
    from types import SimpleNamespace
    tc = SimpleNamespace(today=("2026-06-29", "2026-06-29"))
    m_dt = {"name": "x", "caliber": "SUM(o.amt)", "base_object": "shop.orders",
            "filters": "[]", "dimensions": "[]", "date_column": "sta_time"}
    sql = _build_sql(LogicForm(metrics=["x"], time="today"), {"x": m_dt}, _TABLES, tc)
    assert "BETWEEN" not in sql                                                    # datetime 不用 BETWEEN
    assert "o.sta_time >= '2026-06-29 00:00:00' AND o.sta_time < '2026-06-30 00:00:00'" in sql  # 半开覆盖全天
    # DATE 列对照：仍 BETWEEN（存量不变）
    m_d = {**m_dt, "date_column": "sta_date"}
    sql2 = _build_sql(LogicForm(metrics=["x"], time="today"), {"x": m_d}, _TABLES, tc)
    assert "o.sta_date BETWEEN '2026-06-29' AND '2026-06-29'" in sql2
