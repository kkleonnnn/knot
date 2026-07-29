"""v0.9.4 R-13 —— 自建-ctx 端点**入口不变量**静态哨兵（限定名解析版 · 守护者 MF2 重写）。

## 不变量
凡「自建 tenant ctx」的函数（= 调用 `set_active_tenant()` 的函数），从函数入口（若有
`clear_active_tenant()` 则从它）到**第一次** `set_active_tenant(...)` 之间的**前缀**里，
**禁止任何依赖 tenant ctx 的调用** —— 含任何 `get_conn` 型仓库调用 / `audit` / `audit_service.log` /
`create_token` / catalog_state / engine·upload 缓存。

## 为什么要静态哨兵（运行期自执行不够）
ctx 清成 None ⇒ 前缀内误用 ctx 会 `TenantContextError` 当场崩 —— **但只在该路径被测覆盖时才生效**，
且 **MF3 实证过一个反例**：`audit_service.log` 曾把 `TenantContextError` fail-soft 吞掉 ⇒
「响亮崩掉」在那条路径上根本不成立（已修，但正说明不能只靠运行期）。

## 两处都是**派生**的（无人肉清单）
1. **目标集（查谁）** = 全仓 `set_active_tenant()` 的调用者。
   ⚠️ **MF2① 修**：旧版只认 `clear_active_tenant()` 调用点 ⇒ 「**set 了但没 clear**」的端点对哨兵
   **完全不可见**，而那恰是最危险的形状（沿用上游 ctx 却自认在建自己的）。改用 set 作标记 = 覆盖两种变体。
2. **禁列（禁什么）** = 从若干**种子**（真正碰租户库/ctx 的收敛点）做**反向传递闭包**。

## ⭐ MF2②③④ 的根治：按 import 语句解析**限定名**，不再用歧义名清单
旧版按**裸名**聚合调用边，为压制误连又硬编了一份「歧义方法名」排除清单。守护者证明它同时坏两头
（我已逐条复现）：
- **③ 切断真链**：`audit_service.log` → `audit_repo.insert`（`insert` 在排除清单里）→ `get_conn`
  ⇒ `log` 永远进不了禁列 ⇒ **审计写者不被守**。实测：`log` / `get_owned` / `update_owned` 三者都不在旧禁列。
- **④ 判定侧误报**：`get` 留在禁列、而排除清单**只作用于闭包边、没作用于违规判定**
  ⇒ 前缀里一个普通 `payload.get("x")` 就误报（实测 `'get' in dep == True`）。
- **② 别名绕过**：`import knot.core.tenant_context as _tc` 后 `_tc.set_active_tenant(...)` 逃出裸名匹配。

**现设计**：每个文件按自己的 import 语句把被调名解析成**限定名**（`knot.x.y.f`）：
  · `payload.get("x")` —— `payload` 是局部变量、非模块绑定 ⇒ **解析不出 ⇒ 自然忽略**（不需要任何清单）
  · `audit_repo.insert(...)` —— `audit_repo` 由 `from knot.repositories import audit_repo` 绑为模块
    ⇒ 解析为 `knot.repositories.audit_repo.insert` ⇒ **真链保住**
  · `_tc.set_active_tenant(...)` —— 别名同样解析 ⇒ **② 关闭**
函数内的**延迟 import**（本仓大量使用）也一并收集、文件级生效（过近似 = 更严，安全方向）。
"""
import ast
import pathlib

_REPO = pathlib.Path(__file__).resolve().parents[1]
_KNOT = _REPO / "knot"

_MARKER_SET = "knot.core.tenant_context.set_active_tenant"
_MARKER_CLEAR = "knot.core.tenant_context.clear_active_tenant"

# 种子 = 真正「碰当前租户」的收敛点，**写全限定名**（`test_R13_seeds_all_resolve` 断言它们真存在）。
# 加项只会让禁列更大（更严）。
_SEEDS = frozenset({
    "knot.repositories.base.get_conn",                    # 租户库连接 —— 一切仓库调用的收敛点
    "knot.core.tenant_context.current_tenant",            # ctx 直读（fail-closed）
    "knot.core.tenant_context.tenant_cache_key",          # 进程内缓存的租户键（v0.9.1 MF4 choke point）
    "knot.api._rate_limit._tenant_authed_key",            # 限流的租户桶键
    "knot.services.upload_engine.get_upload_engine",      # per-tenant uploads 引擎（v0.9.2）
    "knot.services.agents.catalog_state.get_state",       # catalog per-tenant 载体槽（v0.9.3）
    "knot.api._audit_helpers.audit",                      # 审计（端点侧 helper）
    "knot.services.audit_service.log",                    # 审计（服务侧本体 —— MF2③ 点名的漏网者）
    "knot.api.deps.create_token",                         # 签发要读 ctx 取 tid（v0.9.4 D1）
    "knot.api.totp.create_interim_token",                 # 同上（第二条签发路径）
})


def _module_of(py: pathlib.Path) -> str:
    m = str(py.relative_to(_REPO).with_suffix("")).replace("/", ".")
    return m[: -len(".__init__")] if m.endswith(".__init__") else m


def _all_modules() -> set:
    return {_module_of(py) for py in _KNOT.rglob("*.py")}


def _bindings(tree, modules: set) -> tuple[dict, dict]:
    """本文件的 import 绑定 → ({本地名: 模块限定名}, {本地名: 函数限定名})。

    走**整棵树**（含函数内延迟 import —— 本仓大量使用）：文件级生效是过近似，方向偏严、安全。
    """
    mod_b, fn_b = {}, {}
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for a in n.names:                       # import knot.x.y [as z]
                local = a.asname or a.name.split(".")[0]
                mod_b[local] = a.name if a.asname else a.name.split(".")[0]
        elif isinstance(n, ast.ImportFrom) and n.module:
            for a in n.names:                       # from knot.x import y [as z]
                local = a.asname or a.name
                cand = f"{n.module}.{a.name}"
                if cand in modules:
                    mod_b[local] = cand             # y 是子模块
                else:
                    fn_b[local] = cand              # y 是函数/类
    return mod_b, fn_b


def _resolved_calls(module: str, tree, modules: set, bindings=None):
    """[(限定名 | None, 行号)]：解析不出的一律 None（**这正是取代歧义名清单的机制**）。"""
    mod_b, fn_b = bindings if bindings else _bindings(tree, modules)
    local_defs = {n.name for n in ast.walk(tree)
                  if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    out = []
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call):
            continue
        f, q = n.func, None
        if isinstance(f, ast.Name):
            if f.id in fn_b:
                q = fn_b[f.id]
            elif f.id in local_defs:
                q = f"{module}.{f.id}"
        elif isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name):
            base = mod_b.get(f.value.id)            # 仅当 receiver 是**模块绑定**才解析
            if base:
                q = f"{base}.{f.attr}"
        out.append((q, n.lineno))
    return out


def _file_state(py: pathlib.Path, modules: set):
    """(module, tree, bindings, local_defs) —— 绑定与 local_defs 须按**整文件**算，
    否则只遍历某个函数子树时会丢掉文件顶部的 import 与同模块兄弟函数。"""
    tree = ast.parse(py.read_text(encoding="utf-8"))
    module = _module_of(py)
    mod_b, fn_b = _bindings(tree, modules)
    file_defs = {n.name for n in ast.walk(tree)
                 if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    return module, tree, (mod_b, fn_b), file_defs


def _calls_in_node(module, node, bindings, file_defs):
    """在给定节点里解析调用，但用**文件级**绑定与 defs。"""
    mod_b, fn_b = bindings
    out = []
    for n in ast.walk(node):
        if not isinstance(n, ast.Call):
            continue
        f, q = n.func, None
        if isinstance(f, ast.Name):
            if f.id in fn_b:
                q = fn_b[f.id]
            elif f.id in file_defs:
                q = f"{module}.{f.id}"
        elif isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name):
            base = mod_b.get(f.value.id)
            if base:
                q = f"{base}.{f.attr}"
        out.append((q, n.lineno))
    return out


def _callee_map():
    """{函数限定名 → 它调用的限定名集合}（解析不出的调用不产生边）。"""
    modules = _all_modules()
    m = {}
    for py in _KNOT.rglob("*.py"):
        try:
            module, tree, bindings, file_defs = _file_state(py, modules)
        except SyntaxError:
            continue
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            inner = {q for q, _ln in _calls_in_node(module, fn, bindings, file_defs) if q}
            m.setdefault(f"{module}.{fn.name}", set()).update(inner)
    return m


def _ctx_dependent():
    """反向传递闭包：任何（间接）调到种子的函数都算「依赖 tenant ctx」。"""
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
    """**目标集**：调用 `set_active_tenant()` 的函数（MF2①：覆盖「set 而不 clear」的变体）。"""
    modules = _all_modules()
    for py in _KNOT.rglob("*.py"):
        if "set_active_tenant" not in py.read_text(encoding="utf-8"):
            continue
        try:
            module, tree, bindings, file_defs = _file_state(py, modules)
        except SyntaxError:
            continue
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            calls = _calls_in_node(module, fn, bindings, file_defs)
            if any(q == _MARKER_SET for q, _ in calls):
                yield py, fn, calls


def _prefix(calls):
    """前缀 = 「入口（或 clear 处）→ 首个 set」之间的调用。"""
    set_line = min((ln for q, ln in calls if q == _MARKER_SET), default=None)
    if set_line is None:
        return []
    clear_line = min((ln for q, ln in calls if q == _MARKER_CLEAR), default=None)
    start = clear_line if clear_line is not None else -1
    return [(q, ln) for q, ln in calls if start < ln < set_line]


# ─── 守护（先钉「哨兵自身没失效」，再钉不变量） ──────────────────────────


def test_R13_seeds_all_resolve():
    """每个种子必须真的对应一个 `knot/` 里的定义 —— 否则闭包建在沙上、不变量测恒绿。"""
    missing = sorted(_SEEDS - set(_callee_map()))
    assert not missing, f"种子解析不到定义（改名/搬迁了？）：{missing}"


def test_R13_target_set_covers_known_self_built_ctx():
    """目标集非空，且含三个已知者。

    `tenant_context_middleware` 也在内 —— 它是**正常**的 ctx 建立者，同样受入口不变量约束
    （若有人在 `resolve_for_request` 之前插一句碰租户库的调用，就该红）。
    """
    names = {fn.name for _py, fn, _c in _self_built_ctx_functions()}
    assert names, "全仓 0 处 set_active_tenant —— 标记失效（改名了？）"
    for expect in ("login", "interim_session", "tenant_context_middleware"):
        assert expect in names, f"目标集漏了 {expect}；实得 {sorted(names)}"


def test_R13_denylist_reaches_the_writers_guardian_named():
    """⭐ MF2③ 回归：几个**真租户库写者**必须在禁列内（旧裸名版把它们全漏了）。"""
    dep = _ctx_dependent()
    for q in ("knot.services.audit_service.log",
              "knot.repositories.audit_repo.insert",
              "knot.repositories.user_repo.get_user_by_username",
              "knot.services.saved_report_service.get_owned",
              "knot.services.saved_report_service.update_owned"):
        assert q in dep, f"{q} 不在禁列 —— 闭包没传递开（MF2③ 回归）"
    assert len(dep) > 60, f"禁列仅 {len(dep)} 项，疑似闭包未展开"


def test_R13_plain_dict_get_is_not_a_violation():
    """⭐ MF2④ 回归：局部变量上的 `.get()` / `.execute()` **不得**被判为违规。

    旧版把 `get` 留在禁列、又只在闭包边侧排除歧义名 ⇒ 前缀里一个普通 `payload.get("x")` 就误报。
    现设计不靠清单：receiver 不是模块绑定 ⇒ **解析不出 ⇒ 不产生边、也不参与判定**。
    """
    src = (
        "from knot.core.tenant_context import clear_active_tenant, set_active_tenant\n"
        "def f(payload, conn):\n"
        "    tok = clear_active_tenant()\n"
        "    x = payload.get('sub')\n"
        "    y = conn.execute('SELECT 1')\n"
        "    t = set_active_tenant({'id': 1})\n"
        "    return x, y, t\n"
    )
    calls = _resolved_calls("probe", ast.parse(src), _all_modules())
    assert len([1 for q, _ in calls if q is None]) == 2, f"局部变量方法调用应解析不出：{calls}"
    dep = _ctx_dependent()
    assert not [q for q, _ln in _prefix(calls) if q in dep], f"误报：{_prefix(calls)}"


def test_R13_alias_import_cannot_escape():
    """⭐ MF2② 回归：`import knot.core.tenant_context as _tc` + `_tc.set_active_tenant()` 必须被认出，
    且同一前缀里的别名形审计调用必须被抓。"""
    src = (
        "import knot.core.tenant_context as _tc\n"
        "from knot.services import audit_service as _a\n"
        "def sneaky(u):\n"
        "    _a.log(actor=None, action='x', resource_type='y')\n"
        "    tok = _tc.set_active_tenant({'id': 1})\n"
        "    return tok\n"
    )
    calls = _resolved_calls("probe", ast.parse(src), _all_modules())
    assert _MARKER_SET in {q for q, _ in calls}, f"别名形 set_active_tenant 未被认出：{calls}"
    bad = [q for q, _ln in _prefix(calls) if q in _ctx_dependent()]
    assert bad == ["knot.services.audit_service.log"], f"别名形前缀违规未被抓：{calls}"


def test_R13_prefix_contains_no_ctx_dependent_call():
    """⭐ 不变量本体：前缀内不得出现禁列里的调用。"""
    dep = _ctx_dependent()
    violations = []
    for py, fn, calls in _self_built_ctx_functions():
        for q, ln in _prefix(calls):
            if q in dep:
                violations.append(f"{py.relative_to(_REPO)}:{ln} {fn.name}() 前缀调了 {q}()")
    assert not violations, (
        "R-13 破：自建-ctx 函数在「入口 → set ctx」之间调了依赖 tenant ctx 的东西 ——\n  "
        + "\n  ".join(violations)
        + "\n\n处置：把该调用移到 `set_active_tenant(...)` 之后（绝大多数情况是正解）。"
          "\n⚠️ 别只是把它挪出前缀了事 —— 前缀内调依赖 ctx 的东西 = 运行期 500，"
          "或（若该路径像 MF3 那样 fail-soft 吞掉）**安全记录静默丢失 / 静默串到别家公司的库**。"
    )
