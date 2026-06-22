"""knot/services/semantic/joingraph.py — RELATIONS 关系图 + JOIN 路径（v0.7.2 C1）。

catalog RELATIONS（`list[tuple/list]`，**len≥4**：left_t, left_c, right_t, right_c, [semantics], [cardinality]）
当无向图（表=节点，关系=边）。`find_join_path` 找连接所有引用对象的最小 JOIN 子树（≤3 表阈值 D1）。

保守 + 确定性（R-SL-23/24/25）：歧义（多 join 键 / 多 bridge / 三角环）/ 无路径 / 超阈（>3 表）→ None
→ 编译器回退 LLM。R-SL-32：`len(r) >= 4` + **按位置索引读，禁解包**（DB 路径 list / 文件路径 tuple，变长）。
纯 stdlib（无 DB/LLM）→ 本机 + CI 同跑。
"""
from __future__ import annotations

from dataclasses import dataclass

_MAX_JOIN_TABLES = 3  # D1 阈值（含 bridge 表）；≤3 表 = ≤2 JOIN


@dataclass(frozen=True)
class JoinEdge:
    left_table: str
    left_col: str
    right_table: str
    right_col: str
    cardinality: str  # n:1 / 1:1 / 1:n / n:n / unknown（R-SL-31 基数 gate 用；C3）


@dataclass
class JoinPath:
    tables: list[str]       # 有序（FROM t0 JOIN t1 JOIN t2 — 每表连接前序表）
    edges: list[JoinEdge]   # JOIN 边（len = len(tables) - 1）


def _parse_edges(relations) -> list[JoinEdge]:
    """RELATIONS → JoinEdge（R-SL-32：len>=4 按位置索引；card 索引 5 可选，缺省 unknown）。"""
    out: list[JoinEdge] = []
    for r in relations or []:
        if not isinstance(r, (list, tuple)) or len(r) < 4:
            continue
        card = str(r[5]).strip().lower() if len(r) >= 6 and r[5] else "unknown"
        out.append(JoinEdge(str(r[0]), str(r[1]), str(r[2]), str(r[3]), card))
    return out


def _between(edges: list[JoinEdge], a: str, b: str) -> list[JoinEdge]:
    return [e for e in edges if {e.left_table, e.right_table} == {a, b}]


def _neighbors(edges: list[JoinEdge], t: str) -> set[str]:
    ns: set[str] = set()
    for e in edges:
        if e.left_table == t:
            ns.add(e.right_table)
        elif e.right_table == t:
            ns.add(e.left_table)
    return ns


def find_join_path(objects, relations) -> JoinPath | None:
    """连接所有 objects 的最小 JOIN 子树（≤3 表）。None = 无路径/超阈/歧义（→ 回退 R-SL-25）。"""
    objs = sorted({str(o) for o in objects if o})
    if not objs:
        return None
    if len(objs) == 1:
        return JoinPath([objs[0]], [])          # 单对象（v0.7.1 路径，无 JOIN）
    if len(objs) > _MAX_JOIN_TABLES:
        return None                              # >3 对象 → 超 ≤3 表阈值
    edges = _parse_edges(relations)

    # ── 2 对象：直连（1 JOIN）或经唯一 bridge（2 JOIN, 3 表）──
    if len(objs) == 2:
        a, b = objs
        direct = _between(edges, a, b)
        if len(direct) == 1:
            return JoinPath([a, b], [direct[0]])
        if len(direct) >= 2:
            return None                          # 多 join 键 → 歧义
        bridges = sorted(b_ for b_ in (_neighbors(edges, a) & _neighbors(edges, b)) - {a, b}
                         if len(_between(edges, a, b_)) == 1 and len(_between(edges, b_, b)) == 1)
        if len(bridges) == 1:
            x = bridges[0]
            return JoinPath([a, x, b], [_between(edges, a, x)[0], _between(edges, x, b)[0]])
        return None                              # 0 或 ≥2 bridge → 无路径/歧义

    # ── 3 对象：须 {a,b,c} 恰 2 边连成树（无多键 / 无三角环）──
    pairs: dict[frozenset, list[JoinEdge]] = {}
    for e in edges:
        key = frozenset((e.left_table, e.right_table))
        if len(key) == 2 and key <= set(objs):
            pairs.setdefault(key, []).append(e)
    if any(len(v) >= 2 for v in pairs.values()):
        return None                              # 某对多 join 键 → 歧义
    uniq = [v[0] for v in pairs.values()]
    if len(uniq) != 2:                           # 须恰 2 边（<2 不连通 / 3 三角环歧义）
        return None
    return _order_three(objs, uniq)


def _child_on_one_side(edge: JoinEdge, child: str) -> bool:
    """edge 中 child（远离 base 侧）须在「1」侧 → base（多侧）不被乘。R-SL-31 基数 gate 核心。"""
    card = edge.cardinality
    if card == "1:1":
        return True
    if card == "n:1":              # left=n, right=1 → 「1」侧 = right_table
        return child == edge.right_table
    if card == "1:n":              # left=1, right=n → 「1」侧 = left_table
        return child == edge.left_table
    return False                   # n:n / unknown → 不安全


def cardinality_safe(base: str, path: JoinPath) -> bool:
    """从 base BFS，每非-base 表经其指向 base 的边须在「1」侧（base 不乘）→ True；否则 False。

    R-SL-31：单 base 聚合的 grain 不被 JOIN 乘 → 聚合不膨胀。1:n/n:n/unknown 边 → False（回退）。
    """
    if len(path.tables) <= 1:
        return True                # 单对象，无 JOIN
    if base not in path.tables:
        return False
    visited = {base}
    frontier = [base]
    while frontier:
        nxt: list[str] = []
        for parent in frontier:
            for e in path.edges:
                child = (e.right_table if e.left_table == parent
                         else e.left_table if e.right_table == parent else None)
                if child and child not in visited:
                    if not _child_on_one_side(e, child):
                        return False   # 该非-base 表在「多」侧 → base 被乘 → 不安全
                    visited.add(child)
                    nxt.append(child)
        frontier = nxt
    return len(visited) == len(path.tables)


def _order_three(objs: list[str], uniq: list[JoinEdge]) -> JoinPath | None:
    """3 表 2 边 → BFS 从排序首表排序，验连通 + 每表连接前序（FROM/JOIN 有效序）。"""
    start = objs[0]
    ordered = [start]
    path_edges: list[JoinEdge] = []
    remaining = list(uniq)
    while remaining:
        progressed = False
        for e in sorted(remaining, key=lambda x: (x.left_table, x.right_table)):
            for cur in ordered:
                other = (e.right_table if e.left_table == cur
                         else e.left_table if e.right_table == cur else None)
                if other and other not in ordered:
                    ordered.append(other)
                    path_edges.append(e)
                    remaining.remove(e)
                    progressed = True
                    break
            if progressed:
                break
        if not progressed:
            return None                          # 剩余边接不上 → 不连通
    if len(ordered) != 3:
        return None
    return JoinPath(ordered, path_edges)
