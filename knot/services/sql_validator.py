"""knot/services/sql_validator.py — v0.5.1 SQL AST 笛卡尔积硬防御。

入口：is_cartesian(sql) -> tuple[bool, str]

D1 独立模块（与 sql_planner._is_fan_out v0.4.1.1 互补）；
D3 fail-open（sqlglot 缺包/解析失败/超长/超深 → 落 logger.warning 不阻断）；
R-90 纯函数 — 禁 import knot.adapters.db / knot.repositories；
R-92 建设性 reason — 必须含表名 / 可定位线索。
"""
from __future__ import annotations

import re

from knot.core.logging_setup import logger

# R-89 输入预检上限
_MAX_SQL_LEN = 100_000
_MAX_PAREN_DEPTH = 100

# C1 文本侧：sqlglot 30.x 把 `FROM a, b` 与 `FROM a JOIN b`（缺 ON）解析为完全
# 一致 AST，无法仅靠 AST 区分。故 C1 用文本正则；C2/C3/C4 用 AST。任意嵌套位置
# 都拒（含 CTE/子查询）。
_COMMA_FROM_RE = re.compile(
    r"\bfrom\s+(?:\w+\.)?\w+(?:\s+(?:as\s+)?\w+)?\s*,\s*(?:\w+\.)?\w+",
    re.IGNORECASE,
)

_REASON_TEMPLATES = {
    "comma": (
        "Implicit comma-join: tables [{t}] in FROM without explicit JOIN. "
        "Rewrite as `FROM {a} JOIN {b} ON <key>` (see RELATIONS for the keys)."
    ),
    "cross": (
        "Cartesian product: tables [{t}] joined via CROSS JOIN. "
        "Use `JOIN ... ON <key>` instead unless cross-product is truly intended."
    ),
    "missing_on": (
        "Cartesian product: tables [{t}] joined without ON/USING condition. "
        "Add `ON <key>` (see RELATIONS for the keys)."
    ),
    "tautological": (
        "Tautological ON expression: {extra} (effectively a cross join over [{t}]). "
        "Replace with the real join key (see RELATIONS)."
    ),
}


def is_cartesian(sql: str) -> tuple[bool, str]:
    """检测 4 类笛卡尔积反模式 (C1~C4)，命中 → (True, reason) 拒收。

    R-80 fail-open / R-83 CTE 子查询递归 / R-89 输入预检 / R-92 建设性 reason。
    """
    if not sql or not sql.strip():
        return False, ""

    if len(sql) > _MAX_SQL_LEN:
        logger.warning(f"sql_validator: SQL 过长 ({len(sql)} > {_MAX_SQL_LEN}) — fail-open")
        return False, ""

    depth = max_depth = 0
    for ch in sql:
        if ch == "(":
            depth += 1
            max_depth = max(max_depth, depth)
        elif ch == ")":
            depth -= 1
    if max_depth > _MAX_PAREN_DEPTH:
        logger.warning(f"sql_validator: 括号过深 ({max_depth} > {_MAX_PAREN_DEPTH}) — fail-open")
        return False, ""

    # C1 旧式逗号 join — 文本侧（任意嵌套位置都拒）
    m = _COMMA_FROM_RE.search(sql)
    if m:
        return True, _reason("comma", _extract_comma_tables(m.group(0)))

    try:
        import sqlglot
        from sqlglot import expressions as exp
    except ImportError:
        logger.warning("sql_validator: sqlglot 不可用 — fail-open")
        return False, ""

    try:
        tree = sqlglot.parse_one(sql.strip().rstrip(";"), dialect="mysql")
    except Exception as e:
        logger.warning(f"sql_validator: 解析失败 ({str(e)[:80]}) — fail-open")
        return False, ""

    if tree is None:
        return False, ""

    # R-83 递归：每个 Select（含 CTE / 子查询）
    for select in tree.find_all(exp.Select):
        from_ = select.args.get("from")
        main_t = _tname(from_.this, exp) if from_ and from_.this else "?"
        for join in select.args.get("joins") or []:
            join_t = _tname(join.this, exp) if join.this else "?"
            kind = (join.kind or "").upper()
            on = join.args.get("on")
            using = join.args.get("using")

            if kind == "CROSS":
                return True, _reason("cross", [main_t, join_t])
            if on is None and not using:
                return True, _reason("missing_on", [main_t, join_t])
            if on is not None and _is_tautological(on, exp):
                return True, _reason("tautological", [main_t, join_t], on.sql())

    return False, ""


def _tname(node, exp) -> str:
    """从 Table/Subquery 节点提取表名（reason 用）。"""
    if isinstance(node, exp.Table):
        return node.name or "?"
    return type(node).__name__.lower()


def _is_tautological(on, exp) -> bool:
    """识别恒真 ON：Boolean True / 字面量=字面量 且相等。"""
    if isinstance(on, exp.Boolean):
        return bool(on.this)
    if isinstance(on, exp.EQ):
        l_, r_ = on.left, on.right
        if isinstance(l_, exp.Literal) and isinstance(r_, exp.Literal):
            return l_.is_string == r_.is_string and l_.name == r_.name
    return False


def _extract_comma_tables(snippet: str) -> list[str]:
    m = re.search(
        r"from\s+((?:\w+\.)?\w+)(?:\s+(?:as\s+)?\w+)?\s*,\s*((?:\w+\.)?\w+)",
        snippet, re.IGNORECASE,
    )
    return [m.group(1), m.group(2)] if m else ["?", "?"]


def _reason(kind: str, tables: list[str], extra: str = "") -> str:
    """R-92 建设性 reason — 含表名 + 修复指引。"""
    t = ", ".join(tables) if tables else "?"
    tmpl = _REASON_TEMPLATES.get(kind)
    if not tmpl:
        return f"Cartesian product detected ({kind}) over [{t}]"
    return tmpl.format(
        t=t,
        a=tables[0] if tables else "a",
        b=tables[1] if len(tables) > 1 else "b",
        extra=extra,
    )
