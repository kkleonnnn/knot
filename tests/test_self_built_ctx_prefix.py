"""v0.9.4 step 12 — R-13：自建-ctx 端点的**入口不变量**静态哨兵（目标集与禁列**双向派生**）。

## 不变量
凡「自建 tenant ctx」的函数（= 调用 `clear_active_tenant()` 的函数），从该调用到第一次
`set_active_tenant(...)` 之间的**前缀**里，**禁止任何依赖 tenant ctx 的调用** —— 含任何
`get_conn` 型仓库调用 / `audit()` / `create_token` / catalog_state / engine·upload 缓存。
**不是**只禁 `tenant_cache_key` / `_tenant_authed_key` 两族（那太窄，是 R-13 明确点名的写窄陷阱）。

## 为什么静态哨兵是必要的（草案 R-13 要求；本 PATCH step 5~7 曾只做运行期自执行）
运行期确实自执行：ctx 被清成 None ⇒ 前缀内误用 ctx 会 `TenantContextError` **当场崩**。
**但那只在该路径被测覆盖时才生效** —— 新增一个自建-ctx 端点、前缀里多一句仓库调用、又没写测，
就带着 500 上线。静态哨兵在**没有测**的时候也能拦。

## 两处都是**派生**的，没有需要人肉同步的清单
1. **目标集**（查谁）：全仓所有调用 `clear_active_tenant()` 的函数 —— 谁自建 ctx 谁自证，
   将来新增端点自动纳入。与被 #258 否掉的「端点路径白名单」本质不同（那种会漏端点）。
2. **禁列**（禁什么）：从若干**种子**（真正碰租户库/ctx 的函数）在 `knot/` 内做**传递闭包**算出
   —— 任何（间接）调到种子的函数自动进禁列。
   ⇒ 不需要枚举内建/纯函数白名单（那种清单会一直膨胀，且 `get` 这类名字太泛，
   `session.get(url)` 与 `dict.get(k)` 同名 ⇒ 白名单必然误放）。
   失败模式是**保守的**：名字撞车导致误报 → 作者去核实，而不是漏放。
"""
import ast
import pathlib

_REPO = pathlib.Path(__file__).resolve().parents[1]
_KNOT = _REPO / "knot"

_MARKER = "clear_active_tenant"
_SET = "set_active_tenant"

# 种子 = 真正「碰当前租户」的收敛点。加项只会让禁列更大（更严），不会放松。
_SEEDS = frozenset({
    "get_conn",              # 租户库连接（repositories/base）—— 一切仓库调用的收敛点
    "current_tenant",        # ctx 直读（fail-closed）
    "tenant_cache_key",      # 进程内缓存的租户键（v0.9.1 MF4 choke point）
    "_tenant_authed_key",    # 限流的租户桶键
    "get_upload_engine",     # per-tenant uploads 引擎（v0.9.2）
    "get_state",             # catalog per-tenant 载体槽（v0.9.3）
    "audit",                 # 审计写租户库
    "create_token",          # 签发要读 ctx 取 tid（v0.9.4 D1）
    "create_interim_token",  # 同上
})


def _iter_funcs(tree):
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield n


def _calls_in(node):
    """node 子树里所有被调用的名字（`f()`→'f'；`a.b()`→'b'），带行号。"""
    out = []
    for n in ast.walk(node):
        if isinstance(n, ast.Call):
            f = n.func
            if isinstance(f, ast.Name):
                out.append((f.id, n.lineno))
            elif isinstance(f, ast.Attribute):
                out.append((f.attr, n.lineno))
    return out


# ⚠️ **不作为闭包「边」的名字**：与内建/标准库对象方法同名，裸名聚合下必然误连。
# 实测（非猜测）：仓内**真有** `def get(...)` 与 `def execute(...)` 且它们（间接）碰 `get_conn`
# ⇒ 全仓每个 `payload.get(...)` / `conn.execute(...)` 都被当成指向它们的边，
# 连**只读平台库**的 `resolve_tenant_by_slug` / `get_platform_conn` 都被污染成「依赖租户 ctx」
# （3 条误报实测复现）。排除它们只损失「恰好取这些名字的自定义函数」的边，
# **不影响** `get_conn` / `audit` / `create_token` 这些真正的收敛点。
_AMBIGUOUS_METHOD_NAMES = frozenset({
    "get", "set", "add", "pop", "keys", "values", "items", "update", "copy", "clear",
    "execute", "executescript", "commit", "close", "fetchone", "fetchall", "rollback",
    "append", "extend", "insert", "remove", "sort", "reverse", "count", "index",
    "read", "write", "seek", "flush", "send", "recv", "run", "start", "stop", "join",
    "encode", "decode", "strip", "lstrip", "rstrip", "split", "rsplit", "format",
    "replace", "lower", "upper", "title", "startswith", "endswith", "isdigit", "isalpha",
})


def _callee_map():
    """{函数名 → 它调用的名字集合}，跨 `knot/` 全仓按**裸名**聚合（排除歧义方法名）。

    裸名聚合把不同模块的同名函数合并 = **过近似**（更严），对守护是安全方向 ——
    但歧义方法名（见上）会让过近似**失控到不可用**，故显式排除。
    """
    m = {}
    for py in _KNOT.rglob("*.py"):
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for fn in _iter_funcs(tree):
            m.setdefault(fn.name, set()).update(
                name for name, _ in _calls_in(fn) if name not in _AMBIGUOUS_METHOD_NAMES
            )
    return m


def _ctx_dependent_names():
    """从种子做**反向传递闭包**：任何（间接）调到种子的函数都算「依赖 tenant ctx」。"""
    m = _callee_map()
    dep = set(_SEEDS)
    changed = True
    while changed:
        changed = False
        for fname, callees in m.items():
            if fname not in dep and (callees & dep):
                dep.add(fname)
                changed = True
    return dep


def _self_built_ctx_functions():
    """**目标集从标记派生**：全仓所有调用 `clear_active_tenant()` 的函数。"""
    for py in _KNOT.rglob("*.py"):
        src = py.read_text(encoding="utf-8")
        if _MARKER not in src:
            continue
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        for fn in _iter_funcs(tree):
            if any(n == _MARKER for n, _ in _calls_in(fn)):
                yield py, fn


def _prefix_calls(fn):
    """「`clear_active_tenant()` 之后、首个 `set_active_tenant()` 之前」的调用（按行号切）。

    按行号而非结构遍历：marker 与 set 常分处 try/finally 的不同层级（结构上不连续），
    但源码行号次序清晰、且与人读代码的直觉一致。
    """
    marker_line = set_line = None
    for name, lineno in _calls_in(fn):
        if name == _MARKER and marker_line is None:
            marker_line = lineno
        elif name == _SET and marker_line is not None and lineno > marker_line and set_line is None:
            set_line = lineno
    if marker_line is None:
        return None, []
    end = set_line if set_line is not None else 10 ** 9   # 无 set → 整个函数都无 ctx
    return marker_line, [(n, ln) for n, ln in _calls_in(fn) if marker_line < ln < end]


# ─── 哨兵三条（两条守目标集/禁列非空，一条守不变量本身） ──────────────────


def test_R13_marker_target_set_is_not_empty():
    """先钉「目标集非空」—— marker 一改名，下方哨兵扫 0 处**仍绿** = 假绿。

    （v0.9.3 教训：哨兵最常见的失效方式不是判错，而是**目标集变空而无人察觉**。）
    """
    names = {fn.name for _py, fn in _self_built_ctx_functions()}
    assert names, (
        f"全仓 0 处调用 {_MARKER}() —— 自建-ctx 端点的入口不变量失去载体（改名了？）。"
        f"若确实不再需要该原语，请连同本哨兵一起删并在 CHANGELOG 说明。"
    )
    assert {"login", "interim_session"} <= names, (
        f"预期覆盖 login / interim_session（v0.9.4 的两个自建-ctx 端点），实得 {names}"
    )


def test_R13_denylist_closure_is_populated():
    """钉「禁列非空且真的传递开了」—— 否则不变量测退化为同义反复（禁列空 ⇒ 恒不命中 ⇒ 恒绿）。"""
    dep = _ctx_dependent_names()
    assert _SEEDS <= dep, "种子自身应在禁列内"
    # 闭包必须把「经仓库函数间接碰 get_conn」的常见入口拉进来，否则说明闭包没跑通
    for probe in ("get_user_by_username", "authenticate", "list_datasources"):
        assert probe in dep, (
            f"{probe} 未被闭包覆盖 —— 禁列没传递开（改了 _SEEDS 名字？仓库层重构了？）："
            f"此时不变量测会漏放大量真正依赖 ctx 的调用"
        )
    assert len(dep) > 50, f"禁列仅 {len(dep)} 项，疑似闭包未展开"


def test_R13_prefix_contains_no_ctx_dependent_call():
    """⭐ 前缀内不得出现禁列里的调用。

    revert-to-bad：往 `api/auth.login` 前缀插一句 `get_user_by_username(...)` → 本测转红。
    **自动覆盖**：将来任何新的自建-ctx 函数（只要它调 `clear_active_tenant`）无需改本测即被纳入；
    任何新的「间接碰租户库」的 helper 也自动进禁列。
    """
    dep = _ctx_dependent_names()
    violations = []
    for py, fn in _self_built_ctx_functions():
        _marker, calls = _prefix_calls(fn)
        for called, lineno in calls:
            if called in dep:
                violations.append(
                    f"{py.relative_to(_REPO)}:{lineno} {fn.name}() 的 ctx-free 前缀里调了 {called}()"
                )
    assert not violations, (
        "R-13 破：自建-ctx 端点在「清 ctx → 建 ctx」之间调了依赖 tenant ctx 的东西 ——\n  "
        + "\n  ".join(violations)
        + "\n\n处置：把该调用移到 `set_active_tenant(...)` 之后（绝大多数情况是正解）。"
          "\n若确信它其实 ctx-free（禁列因**裸名聚合**过近似而误报），在本文件说明理由后"
          "把该名字排除 —— 但先想清楚：前缀里调依赖 ctx 的东西 = 运行期 500，"
          "或（若哪天 fail-closed 被回退）**静默串到别家公司的库**。"
    )
