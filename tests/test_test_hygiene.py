"""tests/test_test_hygiene.py — 「关于测的测」：封住已知的**假绿面**。

本仓已有元哨兵先例 `test_core_purity.py`（AST 扫 `knot/core` 的 import 边界）。
本文件同形，但**对象是测本身** —— 因为一条测可以「绿着却什么都没验」，而那种绿最贵。

═══ 为什么需要它（v0.9.12 Stage 4 §IV 守护者建议）═══
本仓 logger 是 **loguru**（`core/logging_setup`），而 pytest 的 `caplog` **只抓 stdlib logging**
⇒ **loguru 的日志根本不进 `caplog`**。后果分两个方向，**只有一个方向危险**：
- **正向断言**（`"x" in caplog.text`）：抓不到 ⇒ 测**响亮地红** ⇒ 安全，会被立刻发现。
- **反向断言**（`"x" not in caplog.text` / `not caplog.records` / `caplog.text == ""`）：
  **对空集恒真** ⇒ 测**静默地绿**，而它其实什么都没验。

这条已经被踩过**三次**，而前两次的教训只写在两条 docstring 里
（`test_tenant_resolution.py` 的 `_loguru_sink` · `test_catalog_tenant_isolation.py`）——
**「散文规则没有守护」正是 v0.9.10-.12 这条弧在治的形状**，所以这次给它一条真守护。

⚠️ **刻意不一律禁用 `caplog`**：`adapters/http/url_allowlist.py` 确实用 stdlib `logging`
（v0.9.7 实读），所以 `caplog` 有**合法用法**。⇒ 判据只卡危险的那个方向。
"""
from __future__ import annotations

import ast
import pathlib

_TESTS = pathlib.Path("tests")

# 「断言缺席」的三种形态 —— 三种在 loguru 下**都恒真**：
#   ① `X not in caplog.text`      ② `not caplog.records`      ③ `caplog.text == ""`
_ABSENCE_HINT = (
    "「断言某内容不在日志里」在 loguru 下**恒真**（caplog 只抓 stdlib logging）。\n"
    "    ⇒ 同一个测函数里必须**先证明 caplog 真的能看到东西**（一条正向断言），\n"
    "       否则这条反向断言是在**空集上**通过的。\n"
    "    修法二选一：\n"
    "      (a) 该日志确实走 stdlib logging ⇒ 同函数先加 `assert caplog.records`（或一条正向 in 断言）；\n"
    "      (b) 该日志走 loguru ⇒ **别用 caplog** —— 挂 loguru sink，\n"
    "          范式见 `tests/test_tenant_resolution.py::_loguru_sink`。"
)


def _is_caplog_absence_assert(node: ast.Assert) -> bool:
    """判本条 assert 是否属「断言 caplog 里缺席」的三种形态之一。"""
    t = node.test
    # ② `assert not <...caplog...>`
    if isinstance(t, ast.UnaryOp) and isinstance(t.op, ast.Not):
        return "caplog" in ast.unparse(t.operand)
    if isinstance(t, ast.Compare):
        left = ast.unparse(t.left)
        rights = [ast.unparse(c) for c in t.comparators]
        # ① `X not in caplog...`
        if any(isinstance(o, ast.NotIn) for o in t.ops) and any("caplog" in r for r in rights):
            return True
        # ③ `caplog.text == ""` / `len(caplog.records) == 0`
        if any(isinstance(o, ast.Eq) for o in t.ops) and "caplog" in left:
            if any(r in ('""', "''", "0") for r in rights):
                return True
    return False


def _has_positive_caplog_assert(fn: ast.FunctionDef) -> bool:
    """同函数内是否有一条**正向** caplog 断言（= 证明 caplog 真能看到东西）。"""
    for node in ast.walk(fn):
        if not isinstance(node, ast.Assert) or _is_caplog_absence_assert(node):
            continue
        if "caplog" in ast.unparse(node.test):
            return True
    return False


def test_caplog_absence_assertions_must_prove_caplog_is_nonempty():
    """任何「caplog 里没有 X」的断言，同函数内必须先有一条**正向** caplog 断言。

    ⚠️ **现状实测 0 处违规 —— 本哨兵是预防性的，不是在修现存缺陷。**
    值得现在装的理由：我自己在 v0.9.12 的 Sb7 初版**差点写出**这个形态，
    救我的正是「先断必须有命中」那一行；而本仓此前已踩过三次，教训只在 docstring 里。
    ⭐ 它同时是「跑 revert 前四问」第 **③ 条（oracle 会不会恒定）**的一个高频具体形态：
    **「X 不在 Y 里」的断言必须先证明 Y 非空。**

    revert-to-bad：在任一测函数里加一条裸 `assert "zzz" not in caplog.text`
    （且不加正向断言）⇒ 本测转红并点名那个函数。
    """
    offenders: list[str] = []
    for path in sorted(_TESTS.rglob("test_*.py")):
        if path.name == pathlib.Path(__file__).name:
            continue                                  # 本文件在**讨论**这些形态（R-SENTINEL-AST 自匹配）
        src = path.read_text(encoding="utf-8")
        if "caplog" not in src:
            continue
        for fn in (n for n in ast.walk(ast.parse(src)) if isinstance(n, ast.FunctionDef)):
            absences = [a for a in ast.walk(fn)
                        if isinstance(a, ast.Assert) and _is_caplog_absence_assert(a)]
            if absences and not _has_positive_caplog_assert(fn):
                offenders.append(
                    f"{path}:{absences[0].lineno} {fn.name}（{len(absences)} 条反向断言，0 条正向）"
                )
    assert not offenders, (
        "以下测函数只对 caplog 做了**反向**断言，没有任何正向断言：\n    "
        + "\n    ".join(offenders) + "\n\n" + _ABSENCE_HINT
    )


def test_loguru_sink_pattern_is_discoverable():
    """`_loguru_sink` 范式必须存在且可被找到 —— 否则上一条的修法 (b) 指向空气。

    ⭐ 这是「声明 vs 生产者」（v3.1-B #6）：上一条测的失败消息**推荐**一个范式，
    那个范式就必须真的存在。范式没了 ⇒ 建议变成死指针 ⇒ 本测红。
    """
    ref = _TESTS / "test_tenant_resolution.py"
    src = ref.read_text(encoding="utf-8")
    assert "def _loguru_sink" in src, (
        f"{ref} 里找不到 `_loguru_sink` —— 而 test_caplog_absence_assertions... 的失败消息"
        "正指向它作为 loguru 场景的修法范式。若范式被移动，请同步那条消息。"
    )
    assert "logger.add" in src or "_lg.add" in src, (
        f"{ref} 的 `_loguru_sink` 应真的挂一个 loguru sink（`logger.add`），否则它不是可用范式"
    )


# ─── 正则字面不得内联进 f-string（本弧第 4 次同一机制 ⇒ 值得机械化）──────────

_RE_FNS = frozenset({"findall", "search", "match", "fullmatch", "sub", "subn",
                     "split", "compile", "finditer"})


def test_no_regex_literal_inlined_in_fstring():
    """禁止把正则调用嵌进 f-string —— 那是**双重转义**的高发地。

    ⚠️⚠️ **本弧犯了 4 次，机制完全相同**：在 f-string 里写 `\\d` / `\\.`，
    而 raw string 里 `\\d` 是**反斜杠 + d**、`\\.` 是**反斜杠 + 点** ⇒ **永不匹配** ⇒
    正则恒返空 ⇒ **诊断行恒报 `[]`，红是红了，但它在撒谎**。
    - v0.9.10：`test_static_bundle_version_synced_with_version_js` 的诊断行；
    - v0.9.12（本片）：`test_deploy_md_top_version_synced_with_main` 的诊断行
      —— **在同一个文件里、而当时的注释就写着上一次的教训**。
    ⇒ 「教训写成注释」= 无守护的散文规则，**正是 v0.9.10-.12 这条弧在治的形状** ⇒ 给它机械守护。

    **判据 = 结构性的**：正则调用**出现在 f-string 内部**这件事本身就是气味
    （在字符串模板里拼正则，转义层数必然容易数错）。⇒ 把 pattern 提为模块级常量即可。
    ⚠️ **诊断代码只在失败路径上运行 ⇒ 它只能靠真的把它弄红来测试**
    ⇒ 这也是为什么「revert-to-bad 的验收产物是失败消息的原文，不是『转红了』三个字」。

    ⚠️ **现状实测 0 处违规**（修掉本片那处之后）⇒ 预防性，且无需任何豁免。
    revert-to-bad：把某个诊断行的 pattern 内联回 f-string ⇒ 本测转红并点名位置。
    """
    offenders: list[str] = []
    roots = [pathlib.Path("knot"), _TESTS, pathlib.Path("scripts")]
    for root in roots:
        for path in sorted(root.rglob("*.py")):
            if path.name == pathlib.Path(__file__).name:
                continue                      # 本文件在**讨论**这个形态（R-SENTINEL-AST 自匹配）
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            for js in (n for n in ast.walk(tree) if isinstance(n, ast.JoinedStr)):
                for call in (c for c in ast.walk(js) if isinstance(c, ast.Call)):
                    fn = call.func
                    name = (fn.attr if isinstance(fn, ast.Attribute)
                            else fn.id if isinstance(fn, ast.Name) else "")
                    if name in _RE_FNS:
                        offenders.append(f"{path}:{js.lineno}  `{name}(...)` 嵌在 f-string 内")
    assert not offenders, (
        "以下位置把正则调用内联进了 f-string：\n    " + "\n    ".join(offenders) + "\n\n"
        "    在 f-string 里手写 `\\d` / `\\.` 极易变成**反斜杠+字符**（永不匹配）⇒ 正则恒返空\n"
        "    ⇒ 若这是诊断消息，它会**恒报空结果**：红是红了，但说的是假话。\n"
        "    修：把 pattern 提为模块级 `re.compile(...)` 常量，f-string 里只放结果变量。"
    )
