"""tests/services/semantic/test_semantic_byte_equal_corpus.py — B6.1 guard 端到端 corpus（v0.8.0）。

⭐ N-1（守护者 second pass）：test_compiler.py 82/99 走 `_build_sql` **绕过** guard（guard 在
`compile_logicform` choke point）。本 corpus **强制走 compile_logicform** → 真 exercise guard on
window/having/qualify/filters/as_name 全片段面：
- 合法 corpus（编译七刀 + filters + as_name）→ 0 FragmentUnsafe（guard 不误杀 = byte-equal 承重）；
- 攻击 corpus → CompileError（端到端经真入口拦截，补 test_fragment_guard 的孤立单测）；
- 括号（§1.5 Option A）在真编译路径生效（parenthesized WHERE/HAVING/qualify）。
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from knot.services.semantic.compiler import CompileError, compile_logicform
from knot.services.semantic.logicform import LogicForm

# ── 与 test_compiler 一致的 fixtures（单对象 orders + 多 base users） ──
_GMV = {"name": "gmv", "caliber": "SUM(o.pay_amount)", "base_object": "shop.orders",
        "filters": '["o.status=\'paid\'"]', "dimensions": '["date","city"]'}
_UC = {"name": "uc", "caliber": "COUNT(o.id)", "base_object": "shop.users",
       "filters": '[]', "dimensions": '["region"]'}
_CATALOG = {"catalog_id": 1, "tables": [{"db": "shop", "table": "orders", "source_type": "db"},
                                        {"db": "shop", "table": "users", "source_type": "db"}]}


def _tc():
    return SimpleNamespace(this_month_to_latest=("2026-06-01", "2026-06-21"))


@pytest.fixture
def _mr(monkeypatch):
    """metric_repo.list_metrics → 全 fixtures（compile_logicform 经此取 catalog metric）。"""
    import knot.repositories.metric_repo as mr
    monkeypatch.setattr(mr, "list_metrics", lambda cid: [_GMV, _UC])
    return mr


_W_RK = {"func": "row_number", "partition_by": ["city"],
         "order_by": [{"field": "gmv", "dir": "desc"}], "as_name": "rk"}

# 合法 corpus：编译七刀 + filters + as_name（全须经 compile_logicform 0 FragmentUnsafe）
_LEGIT = {
    "plain":            LogicForm(metrics=["gmv"], dimensions=["city"], time="this_month_to_latest"),
    "having":           LogicForm(metrics=["gmv"], dimensions=["city"], having=["gmv > 10000"]),
    "having_arith":     LogicForm(metrics=["gmv"], dimensions=["city"], having=["gmv / 2 > 100"]),
    "window":           LogicForm(metrics=["gmv"], dimensions=["city"], window=[_W_RK]),
    "qualify_topn":     LogicForm(metrics=["gmv"], dimensions=["city"], limit=20, window=[_W_RK], qualify=["rk <= 3"]),
    "lf_filters":       LogicForm(metrics=["gmv"], dimensions=["city"], filters=["o.amount > 0"]),
    "lf_filters_func":  LogicForm(metrics=["gmv"], dimensions=["city"], filters=["UNIX_TIMESTAMP(o.t) > 0"]),
    "multi_base_scalar":LogicForm(metrics=["gmv", "uc"]),
    "outer_cte":        LogicForm(metrics=["gmv"], dimensions=["city"], having=["gmv > 10000"], outer={"func": "count"}),
    "window_frame":     LogicForm(metrics=["gmv"], dimensions=["date"],
                                  window=[{"func": "sum", "arg": "gmv", "order_by": [{"field": "date", "dir": "asc"}],
                                           "frame": {"preceding": 6, "following": 0}, "as_name": "ma"}]),
}


@pytest.mark.parametrize("name", list(_LEGIT))
def test_legit_corpus_compiles_via_choke_point(name, _mr):
    """N-1：合法 corpus 经 compile_logicform（guard 真跑）→ 0 FragmentUnsafe/CompileError + 非空 SQL。"""
    sql = compile_logicform(_LEGIT[name], _CATALOG, _tc())
    assert isinstance(sql, str) and sql.strip()


def test_parenthesization_in_real_path(_mr):
    """§1.5 Option A：真编译路径括每片段（WHERE/HAVING/qualify）。"""
    having = compile_logicform(_LEGIT["having"], _CATALOG, _tc())
    assert "WHERE (o.status='paid')" in having and "HAVING (gmv > 10000)" in having
    topn = compile_logicform(_LEGIT["qualify_topn"], _CATALOG, _tc())
    assert "win WHERE (rk <= 3)" in topn


# 攻击 corpus：经真入口 compile_logicform → CompileError（end-to-end，补孤立单测）
_ATTACK = {
    "having_subquery":  LogicForm(metrics=["gmv"], dimensions=["city"], having=["gmv > (SELECT MAX(x) FROM secret)"]),
    "filter_subquery":  LogicForm(metrics=["gmv"], dimensions=["city"], filters=["o.id IN (SELECT id FROM otherdb.secret)"]),
    "filter_comment":   LogicForm(metrics=["gmv"], dimensions=["city"], filters=["o.amount > 0 -- "]),
    "filter_sleep":     LogicForm(metrics=["gmv"], dimensions=["city"], filters=["SLEEP(5) > 0"]),
    "qualify_3part":    LogicForm(metrics=["gmv"], dimensions=["city"], window=[_W_RK],
                                  qualify=["otherdb.users.rk <= 3"]),
    "as_name_exfil":    LogicForm(metrics=["gmv"], dimensions=["city"],
                                  window=[{"func": "row_number", "order_by": [{"field": "gmv", "dir": "desc"}],
                                           "as_name": "rn, (SELECT MAX(bal) FROM otherdb.wallets)"}]),
}


@pytest.mark.parametrize("name", list(_ATTACK))
def test_attack_corpus_blocked_via_choke_point(name, _mr):
    """攻击 corpus 经真入口 → FragmentUnsafe→CompileError（回退 LLM）。"""
    with pytest.raises(CompileError):
        compile_logicform(_ATTACK[name], _CATALOG, _tc())
