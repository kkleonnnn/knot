"""knot/services/semantic/fragment_guard.py — LogicForm 片段级注入校验（v0.8.0 B6.1 · 安全承重）。

编译器把 **LLM 产出**的 7 类片段逐字拼进 SQL：having / qualify / lf.filters /
window partition_by / window arg / window 内层 order_by[].field / window as_name。全句
`_is_safe_sql`（adapters/db/doris.py）by-design 放行**只读**子查询 / session 函数 / 注释截断
（只读闸门不保证 bounded-cost / scope；见 doris.py `_is_safe_sql` docstring）。本 leaf 在 splice **前**
做片段级校验，堵住 `_is_safe_sql` 结构上覆盖不到的注入面（B6.1 安全必修）。

## 纯 leaf（Contract 9 semantic-compile-acyclic）
仅 import `sqlglot` + stdlib，**0 semantic-sibling import**。故抛**自有 `FragmentUnsafe`**（不 import
`compile_helpers.CompileError` → 免 sibling import 破 acyclic）；`compiler.py` 在 splice 点 catch 翻译成
`CompileError` → 混合架构 R-SL-14 回退 LLM ReAct（**fail-closed**；相对 flag-off baseline 0 能力损失）。
`.importlinter` Contract 9 `source_modules` 含本模块（CI 守无环）。

## 规则（G0–G6；Stage 3 守护者终审 + 执行者 5 路 sqlglot 30.11.0 POC 复核后终态）
- **G0 注释 prescan（全片段）**：原始串含 `-- / # / /* / */` → raise。sqlglot 30.11.0 **不剥注释**、
  roundtrip 成 `/* */`（存 node.comments）→ 逐字拼串后注释会截断编译器自身 GROUP BY/LIMIT → 须 parse 前扫原始串。
- **G1 standalone parse（全片段）**：`sqlglot.parse_one(dialect="mysql")` **孤立**解析（**不包裹** ——
  `SELECT..WHERE(<frag>)` 包裹会引入自身外层 Select → 100% 误命中 G2）；解析失败 → raise。
- **G2 结构（全片段）**：AST 含 `Select`/`Subquery`/`Union`/`Intersect`/`Except` → raise（堵注入只读子查询/UNION）。
  单纯括号 `(...)` = `exp.Paren` 非 Subquery → 不误杀。
- **G3 未识别函数（全片段）**：`exp.Anonymous`（sqlglot 不识别）→ raise，**例外 benign 白名单**（`UNIX_TIMESTAMP`
  等 —— POC 证 20 常见函数唯它 Anonymous 且合法；version-pinned，requirements.txt sqlglot>=30,<31 承重）。
  覆盖 SLEEP/BENCHMARK/LOAD_FILE/USER/CONNECTION_ID（皆 Anonymous）。
- **G4 typed 危险 denylist（全片段）**：`CurrentUser`/`CurrentVersion`/`CurrentSchema`/`SessionUser`/`GroupConcat`
  （G3 抓不到的专有节点）→ raise。
- **G3.5 写/DDL（全片段，defense-in-depth）**：Insert/Update/Delete/Drop/Create/Alter/Command → raise（_is_safe_sql 亦兜）。
- **G5 别名 + 限定符（仅别名类：having/qualify/window partition·arg）**：每个 Column 须**无限定符**
  （`.table==.db==.catalog==""` —— 堵 `otherdb.users.revenue` 末段命中白名单的跨库读）且 name ∈ 作用域可见别名集。
- **G6 无函数调用（仅别名类）**：别名类片段严禁任何真函数调用。**放行仅布尔连接词** `And`/`Or`/`Xor`
  （基类 `exp.Connector` —— sqlglot 30.11.0 把它们归 `exp.Func`，非语义上的函数调用）；**19 个 `exp.Func∩exp.Binary`**
  （`RegexpLike`/`JSONExtract`/`Pow` 等）与所有普通函数一并拒（守护者 final R-F1：旧「排 exp.Binary」误放行这 19 个）。
  比较（`GT`/`LT`/`EQ`）/算术（`Add`/`Div`）是 `exp.Binary` **非** `exp.Func` → `find_all(Func)` 天然不 yield →
  不受影响（`gmv/dau>0.5` OK）。corpus-safe（别名类 having/qualify/partition/arg 0 函数）+ 真·零函数（闭 ReDoS 残余）。

**lf.filters（物理 WHERE）：仅 G0–G4 + G3.5**，不施 G5/G6（物理列无 catalog 列源 + parser 对 filters 0 func
约束 → 列/func 白名单必误杀 DATE/CAST/LIKE/UNIX_TIMESTAMP）。调用方外科作用域：只校验 lf.filters 切片，
严禁碰信任的 metric.filters / caliber（require_tenant_admin gated —— **租户** admin 对**自己租户**的 SQL 面，见 §残余风险）。

## 残余风险（接受 + 记录，Stage 3 §C）
- admin caliber / metric filters 信任面 scope 外（require_tenant_admin + OOS-1v2 锁）；caliber 内只读跨表子查询按设计不防。
  ⚠️ v0.9.5：该信任面的准确表述是「**租户** admin 只对**自己租户**的 SQL 面被信任」——
  跨租户由 per-tenant **文件边界**挡住（不是靠这层信任）；平台身份不进此面（out-of-band 平行路径）。
- 合法字符串字面量含 `--/#`（如 `o.note LIKE '%--%'`）→ G0 误杀 → 回退 LLM（罕见、非用户错）。
- 裸 `SESSION_USER`（无括号）parse 成 Column：别名类由 G5 挡；filters 内视为列名（低危，非函数）。
- benign-Anonymous / typed 危险划分 sqlglot-版本相关 → requirements.txt `>=30,<31` pin 承重；升级须重跑攻击语料。
"""
from __future__ import annotations

import re

import sqlglot
from sqlglot import expressions as exp


class FragmentUnsafe(Exception):
    """片段级注入校验失败。compiler splice 点 catch → 翻译成 CompileError → 回退 LLM（R-SL-14）。"""


# G0：注释 token（sqlglot 不剥、roundtrip /* */ → parse 前扫原始串）
_COMMENT_TOKENS = ("--", "#", "/*", "*/")

# G2：注入结构节点
_INJECTION_NODES = (exp.Select, exp.Subquery, exp.Union, exp.Intersect, exp.Except)

# G3.5：写/DDL（defense-in-depth；_is_safe_sql 亦兜）
_WRITE_NODES = (exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Create, exp.Alter, exp.Command)

# G3：benign-Anonymous 白名单（sqlglot 30.11.0 parse 成 Anonymous 但合法；version-pinned）
_BENIGN_ANONYMOUS = frozenset({"UNIX_TIMESTAMP"})

# G4：typed 危险函数（专有节点，G3 Anonymous 检查抓不到）
_DANGEROUS_TYPED = (exp.CurrentUser, exp.CurrentVersion, exp.CurrentSchema, exp.SessionUser, exp.GroupConcat)

# G5/as_name：纯 SQL 标识符（R-F3：`\A..\Z` 非 `^..$` —— Python `$` 匹配尾换行前 → `'rn\n'` 会漏；
# `re.ASCII` 使 `\w` 限 ASCII → 挡 `rñ` 类命名过宽，非注入向量但收紧标识符面）
_IDENT_RE = re.compile(r"\A[A-Za-z_]\w*\Z", re.ASCII)


def _parse(frag: str) -> exp.Expression:
    """G0（注释 prescan）+ G1（standalone parse）。失败 → FragmentUnsafe。"""
    raw = str(frag)
    for tok in _COMMENT_TOKENS:                      # G0：sqlglot 不剥注释 → parse 前扫原始串
        if tok in raw:
            raise FragmentUnsafe(f"片段含注释 token {tok!r}（截断风险）：{raw!r}")
    try:
        node = sqlglot.parse_one(raw, dialect="mysql")   # G1：孤立解析（不包裹，避 self-FP）
    except Exception as e:                           # noqa: BLE001 — 任何 parse 异常 → fail-closed
        raise FragmentUnsafe(f"片段解析失败 → 回退：{raw!r}（{str(e)[:80]}）")
    if node is None:
        raise FragmentUnsafe(f"片段解析为空 → 回退：{raw!r}")
    return node


def _assert_structural(node: exp.Expression, raw: str) -> None:
    """G2 + G3 + G4 + G3.5（全片段通用结构 / 函数拦截）。"""
    for n in node.walk():
        if isinstance(n, _INJECTION_NODES):
            raise FragmentUnsafe(f"片段含子查询/UNION（{type(n).__name__}）→ 回退：{raw!r}")
        if isinstance(n, _WRITE_NODES):
            raise FragmentUnsafe(f"片段含写/DDL（{type(n).__name__}）→ 回退：{raw!r}")
        if isinstance(n, exp.Anonymous) and (n.name or "").upper() not in _BENIGN_ANONYMOUS:
            raise FragmentUnsafe(f"片段含未识别函数 {n.name!r}（非 benign 白名单）→ 回退：{raw!r}")
        if isinstance(n, _DANGEROUS_TYPED):
            raise FragmentUnsafe(f"片段含危险函数 {type(n).__name__} → 回退：{raw!r}")


def assert_predicate(frag: str, *, alias_based: bool, aliases=frozenset()) -> None:
    """校验谓词/标量片段（having / qualify / lf.filters / window arg / window partition_by 元素）。

    G0–G4 + G3.5 全片段施；`alias_based=True`（having/qualify/window）另施 G5（无限定符 + 列 ∈ aliases）+
    G6（无函数调用）。`alias_based=False`（lf.filters 物理列）止于结构校验。不安全 → raise FragmentUnsafe。
    """
    raw = str(frag)
    node = _parse(raw)
    _assert_structural(node, raw)
    if not alias_based:
        return
    allowed = frozenset(aliases)
    for col in node.find_all(exp.Column):            # G5：别名类严禁限定符 + 列须 ∈ 可见别名集
        if col.table or col.db or col.catalog:
            raise FragmentUnsafe(f"别名类片段含限定符列 {col.sql()!r}（严禁跨对象/跨库引用）→ 回退：{raw!r}")
        if col.name not in allowed:
            raise FragmentUnsafe(f"别名类片段列 {col.name!r} ∉ 可见别名 {sorted(allowed)} → 回退：{raw!r}")
    for fn in node.find_all(exp.Func):               # G6：别名类严禁真函数调用（真·零函数）。
        # ⚠️ sqlglot 30.11.0 把布尔连接词 And/Or/Xor 归 exp.Func（基类 exp.Connector）——仅放行这些连接词。
        # 真函数（Round/Anonymous/TsOrDsToDate + 19 个 Func∩Binary 如 RegexpLike/JSONExtract/Pow）→ 拒。
        # 比较（GT/LT/EQ）/算术（Add/Div）是 exp.Binary 但**非** exp.Func → find_all(Func) 不 yield → 不受影响。
        # （R-F1 守护者 final：旧「排 exp.Binary」会误放行 19 个 Func∩Binary → 收窄为 exp.Connector。）
        if isinstance(fn, exp.Connector):
            continue
        raise FragmentUnsafe(f"别名类片段含函数调用 {type(fn).__name__} → 回退：{raw!r}")


def assert_alias_ref(field: str, aliases=frozenset()) -> None:
    """校验 window 内层 order_by[].field（引子查询输出列）：纯标识符 + ∈ 内层可见别名集。"""
    name = str(field)
    if not _IDENT_RE.match(name):
        raise FragmentUnsafe(f"window order_by 字段 {name!r} 非纯标识符 → 回退")
    if name not in frozenset(aliases):
        raise FragmentUnsafe(f"window order_by 字段 {name!r} ∉ 内层可见别名 {sorted(aliases)} → 回退")


def assert_as_name(name: str) -> None:
    """校验 window as_name（B6.1 第 7 类 splice）：**别名声明**须纯标识符（非表达式）。

    堵 `as_name='rn, (SELECT MAX(bal) FROM otherdb.wallets)'`（POC 证 _is_safe_sql 放行该跨库 exfil）。
    """
    n = str(name)
    if not _IDENT_RE.match(n):
        raise FragmentUnsafe(f"window as_name {n!r} 非纯标识符（^[A-Za-z_]\\w*$）→ 回退")
