"""tests/services/semantic/test_joingraph.py — v0.7.2 C1 BFS JOIN 路径守护。

R-SL-23 确定性 + 唯一性 / R-SL-24 ≤3 表阈值 / R-SL-25 歧义/无路径 → None / R-SL-32 len≥4 + card 解析。
纯 stdlib（无 DB/LLM）→ 本机 + CI 同跑。
"""
from knot.services.semantic.joingraph import JoinPath, find_join_path

# RELATIONS 边：[left_t, left_c, right_t, right_c, semantics?, cardinality?]
_AB = ["orders", "user_id", "users", "id", "订单注册用户", "n:1"]
_BC = ["users", "city_id", "cities", "id", "用户城市", "n:1"]
_AC = ["orders", "city_id", "cities", "id", "订单城市", "n:1"]
_AB4 = ["orders", "user_id", "users", "id"]  # len 4（无 semantics/card → unknown）


def test_single_object_no_join():
    p = find_join_path(["orders"], [_AB])
    assert p == JoinPath(["orders"], [])


def test_two_objects_direct_edge():
    p = find_join_path(["orders", "users"], [_AB, _BC])
    assert p.tables == ["orders", "users"]
    assert len(p.edges) == 1 and p.edges[0].cardinality == "n:1"


def test_two_objects_len4_relation_unknown_cardinality():
    """R-SL-32：len 4 边照解析（card → unknown）。"""
    p = find_join_path(["orders", "users"], [_AB4])
    assert p.tables == ["orders", "users"]
    assert p.edges[0].cardinality == "unknown"


def test_two_objects_via_unique_bridge():
    # orders↔cities 无直连；经 users bridge（orders-users, users-cities）
    p = find_join_path(["orders", "cities"], [_AB, _BC])
    assert p is not None and set(p.tables) == {"orders", "users", "cities"}  # ≤3 表（含 bridge）
    assert len(p.edges) == 2
    # FROM/JOIN 有效序：每表（首表后）连接前序表（序起于排序首表，确定性）
    seen = {p.tables[0]}
    for i, e in enumerate(p.edges):
        assert (e.left_table in seen) or (e.right_table in seen)
        seen.add(p.tables[i + 1])


def test_two_objects_multiple_direct_edges_ambiguous():
    dup = ["orders", "uid2", "users", "id2", "另一键", "n:1"]
    assert find_join_path(["orders", "users"], [_AB, dup]) is None  # 多 join 键歧义


def test_two_objects_no_path():
    assert find_join_path(["orders", "products"], [_AB, _BC]) is None


def test_three_objects_chain():
    p = find_join_path(["orders", "users", "cities"], [_AB, _BC])  # orders-users-cities 链
    assert p is not None and set(p.tables) == {"orders", "users", "cities"}
    assert len(p.edges) == 2
    # FROM/JOIN 有效序：每表（首表后）连接前序表
    seen = {p.tables[0]}
    for i, e in enumerate(p.edges):
        nxt = p.tables[i + 1]
        assert nxt in (e.left_table, e.right_table)
        assert (e.left_table in seen) or (e.right_table in seen)
        seen.add(nxt)


def test_three_objects_triangle_ambiguous():
    # A-B, B-C, A-C 三角 → 多 spanning tree → 歧义 → None
    assert find_join_path(["orders", "users", "cities"], [_AB, _BC, _AC]) is None


def test_three_objects_disconnected():
    assert find_join_path(["orders", "users", "cities"], [_AB]) is None  # 仅 A-B，C 不连通


def test_four_objects_exceeds_threshold():
    rels = [_AB, _BC, _AC, ["cities", "x", "regions", "y", "", "n:1"]]
    assert find_join_path(["orders", "users", "cities", "regions"], rels) is None  # >3 对象


def test_deterministic_same_input_same_path():
    a = find_join_path(["cities", "orders"], [_AB, _BC])  # 乱序输入
    b = find_join_path(["orders", "cities"], [_BC, _AB])  # 乱序输入 + 边
    assert a.tables == b.tables and [e.left_table for e in a.edges] == [e.left_table for e in b.edges]


def test_malformed_relation_skipped():
    # len<4 / 非 list 跳过（不崩）
    p = find_join_path(["orders", "users"], [["orders", "user_id"], "garbage", _AB])
    assert p.tables == ["orders", "users"]


# ─── C3 基数 gate cardinality_safe（R-SL-31）──────────────────────────

from knot.services.semantic.joingraph import cardinality_safe  # noqa: E402


def test_cardinality_safe_single_object():
    p = find_join_path(["orders"], [])
    assert cardinality_safe("orders", p) is True          # 无 JOIN → 安全


def test_cardinality_safe_n_to_1_base_many_side():
    # orders(n)→users(1) n:1；base=orders（多侧），joined users 在 1 侧 → 安全
    p = find_join_path(["orders", "users"], [_AB])
    assert cardinality_safe("orders", p) is True


def test_cardinality_unsafe_base_on_one_side():
    # base=users（1 侧），joined orders 在「多」侧 → users 被乘 → 不安全
    p = find_join_path(["orders", "users"], [_AB])
    assert cardinality_safe("users", p) is False


def test_cardinality_unsafe_1_to_n_edge():
    # orders(1)→items(n) 1:n；base=orders，joined items 在「多」侧 → 不安全
    o2i = ["orders", "id", "items", "order_id", "订单明细", "1:n"]
    p = find_join_path(["orders", "items"], [o2i])
    assert cardinality_safe("orders", p) is False


def test_cardinality_unsafe_unknown():
    unk = ["orders", "user_id", "users", "id"]               # len 4 → card unknown
    p = find_join_path(["orders", "users"], [unk])
    assert cardinality_safe("orders", p) is False            # unknown → 不安全 → 回退
