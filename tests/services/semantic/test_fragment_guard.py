"""tests/services/semantic/test_fragment_guard.py — B6.1 片段级注入校验（v0.8.0 安全承重）。

攻击语料（全 raise FragmentUnsafe）源自 Stage 3 守护者 + 执行者 5 路 sqlglot 30.11.0 POC 实证；
合法语料（全 pass）源自 test_compiler.py 既有片段形状 + parser prompt 允许的 filters 自由式。
"""
from __future__ import annotations

import pytest

from knot.services.semantic.fragment_guard import (
    FragmentUnsafe,
    assert_alias_ref,
    assert_as_name,
    assert_predicate,
)

# 别名类可见集（having/qualify 作用域样例：metric gmv/dau + 维度 city/date + window as_name rk）
ALIASES = frozenset({"gmv", "dau", "city", "date", "rk"})


# ───────────────────────── 攻击语料（全部须 raise） ─────────────────────────

@pytest.mark.parametrize("frag", [
    "gmv > 0 OR EXISTS (SELECT 1 FROM secret)",      # G2 子查询
    "gmv IN (SELECT id FROM users)",                  # G2 子查询
    "gmv > (SELECT MAX(bal) FROM otherdb.wallets)",   # G2 跨库标量子查询
])
def test_g2_subquery_rejected(frag):
    with pytest.raises(FragmentUnsafe):
        assert_predicate(frag, alias_based=True, aliases=ALIASES)


@pytest.mark.parametrize("frag", [
    "gmv > 0 -- ",          # G0 行注释截断（尾 -- ）
    "gmv > 0 # foo",        # G0 # 注释
    "gmv > 0 /* x */",      # G0 块注释
])
def test_g0_comment_rejected(frag):
    with pytest.raises(FragmentUnsafe):
        assert_predicate(frag, alias_based=True, aliases=ALIASES)


@pytest.mark.parametrize("frag", [
    "otherdb.users.revenue > 0",   # 3 段跨库（末段 revenue 命中 name 白名单也须拒）
    "o.status = 1",                # 表限定符（别名类严禁）
    "info.x > 0",
])
def test_g5_qualifier_rejected(frag):
    with pytest.raises(FragmentUnsafe):
        assert_predicate(frag, alias_based=True, aliases=ALIASES | {"revenue", "status", "x"})


@pytest.mark.parametrize("frag", [
    "SLEEP(5) > 0",                        # G3 Anonymous DoS
    "BENCHMARK(1000000, MD5('a')) > 0",    # G3 Anonymous DoS
    "LOAD_FILE('/etc/passwd') IS NOT NULL",# G3 Anonymous 文件读
    "USER() = 'x'",                        # G3 Anonymous
    "CONNECTION_ID() > 0",                 # G3 Anonymous
])
def test_g3_anonymous_dangerous_rejected(frag):
    with pytest.raises(FragmentUnsafe):
        assert_predicate(frag, alias_based=False, aliases=frozenset())  # 即便 filters 宽松路径也须拒


@pytest.mark.parametrize("frag", [
    "GROUP_CONCAT(gmv) > 0",   # G4 typed exfil-into-one-cell
    "CURRENT_USER() = 'x'",    # G4 typed
    "VERSION() > '5'",         # G4 typed
    "DATABASE() = 'x'",        # G4 typed
])
def test_g4_typed_dangerous_rejected(frag):
    with pytest.raises(FragmentUnsafe):
        assert_predicate(frag, alias_based=False, aliases=frozenset())


def test_g6_no_function_in_alias_based():
    # 别名类严禁任何函数调用（即便非危险）——bare aliases + operators only
    with pytest.raises(FragmentUnsafe):
        assert_predicate("ROUND(gmv) > 5", alias_based=True, aliases=ALIASES)


def test_g5_unknown_alias_rejected():
    with pytest.raises(FragmentUnsafe):
        assert_predicate("total_volume > 0", alias_based=True, aliases=ALIASES)  # 幻觉列（Q19 类）


@pytest.mark.parametrize("name", [
    "rn, (SELECT MAX(bal) FROM otherdb.wallets)",  # B-1 as_name 子查询 exfil
    "rn -- ",                                       # as_name 注释截断
    "rn AS x",                                      # 逗号/空格逃逸
    "a b",
    "1abc",                                         # 非法标识符
])
def test_as_name_non_identifier_rejected(name):
    with pytest.raises(FragmentUnsafe):
        assert_as_name(name)


def test_order_ref_hallucination_rejected():
    with pytest.raises(FragmentUnsafe):
        assert_alias_ref("total_volume", ALIASES)   # 内层 order 幻觉列
    with pytest.raises(FragmentUnsafe):
        assert_alias_ref("otherdb.t.c", ALIASES)     # 限定符


# ───────────────────────── 合法语料（全部须 pass，byte-equal 承重） ─────────────────────────

@pytest.mark.parametrize("frag", [
    "gmv > 10000",       # test_compiler having
    "gmv >= 10000",
    "rk <= 3",           # qualify（rk = window as_name ∈ ALIASES）
    "gmv / dau > 0.5",   # 算术 having（Div 非 Func）
    "gmv > 0 AND dau > 0",
])
def test_alias_based_legit_pass(frag):
    assert_predicate(frag, alias_based=True, aliases=ALIASES)  # 不 raise


@pytest.mark.parametrize("frag", [
    "gmv",     # window partition_by 元素 / arg（bare 别名）
    "city",
    "dau",
])
def test_alias_based_bare_ident_pass(frag):
    assert_predicate(frag, alias_based=True, aliases=ALIASES)


@pytest.mark.parametrize("frag", [
    "o.status = 'paid'",                       # 物理列过滤（filters 只结构校验）
    "o.amount > 0 AND o.name LIKE '%btc%'",
    "DATE(o.created_at) = '2026-01-01'",       # 合法函数（filters 不施 G3-benign 外的 func 白名单）
    "CAST(o.x AS SIGNED) > 0",
    "COALESCE(o.a, 0) > 0",
    "UNIX_TIMESTAMP(o.t) > 0",                 # benign-Anonymous 白名单（否则误杀）
    "o.status IN ('a', 'b')",
])
def test_filters_physical_legit_pass(frag):
    assert_predicate(frag, alias_based=False, aliases=frozenset())  # 不 raise


@pytest.mark.parametrize("name", ["rn", "rk", "x", "ma", "row_num_2026"])
def test_as_name_identifier_pass(name):
    assert_as_name(name)  # 不 raise


def test_order_ref_legit_pass():
    assert_alias_ref("gmv", ALIASES)
    assert_alias_ref("date", ALIASES)
