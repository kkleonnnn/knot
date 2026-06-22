"""tests/services/semantic/test_logicform.py — v0.7.1 C1 LogicForm schema 守护。

确定性序列化（R-SL-17 基础）：同内容 LogicForm → byte-equal canonical_json；
metrics 顺序语义相关（不同序 → 不同 canonical）；order_by dict key 序无关；from_dict 兜底。
纯 stdlib（无 fastapi/LLM）→ 本机 + CI 同跑。
"""
import json

import pytest

from knot.services.semantic.logicform import LogicForm


def test_canonical_json_deterministic_same_content():
    """同内容 LogicForm → byte-equal canonical_json（确定性基础）。"""
    a = LogicForm(metrics=["gmv", "dau"], dimensions=["city"], time="this_month_to_latest",
                  order_by=[{"field": "gmv", "dir": "desc"}], limit=10)
    b = LogicForm(metrics=["gmv", "dau"], dimensions=["city"], time="this_month_to_latest",
                  order_by=[{"field": "gmv", "dir": "desc"}], limit=10)
    assert a.to_canonical_json() == b.to_canonical_json()


def test_canonical_json_order_by_dict_key_order_irrelevant():
    """order_by 内 dict key 写入序不同 → canonical 后 byte-equal（key 排序确定性）。"""
    a = LogicForm(metrics=["gmv"], order_by=[{"field": "gmv", "dir": "desc"}])
    b = LogicForm(metrics=["gmv"], order_by=[{"dir": "desc", "field": "gmv"}])
    assert a.to_canonical_json() == b.to_canonical_json()


def test_canonical_json_metric_order_preserved():
    """metrics 顺序语义相关（SELECT 列序）→ 不同序 → 不同 canonical（不归一）。"""
    a = LogicForm(metrics=["gmv", "dau"])
    b = LogicForm(metrics=["dau", "gmv"])
    assert a.to_canonical_json() != b.to_canonical_json()


def test_from_dict_defaults_on_missing_keys():
    """缺键 → 默认（dimensions/filters/order_by=[]，time=""，limit=0）。"""
    lf = LogicForm.from_dict({"metrics": ["gmv"]})
    assert lf.metrics == ["gmv"]
    assert lf.dimensions == [] and lf.filters == [] and lf.time == "" and lf.order_by == [] and lf.limit == 0


def test_from_dict_roundtrip_canonical():
    """from_dict → to_canonical_json → json.loads → from_dict 往返 byte-equal。"""
    d = {"metrics": ["gmv"], "dimensions": ["city"], "filters": ["o.status='paid'"],
         "time": "this_month", "order_by": [{"field": "gmv", "dir": "desc"}], "limit": 5}
    lf = LogicForm.from_dict(d)
    lf2 = LogicForm.from_dict(json.loads(lf.to_canonical_json()))
    assert lf.to_canonical_json() == lf2.to_canonical_json()


def test_from_dict_rejects_non_dict():
    """非 dict 输入 → ValueError（解析失败兜底）。"""
    with pytest.raises(ValueError):
        LogicForm.from_dict("not a dict")
