"""闸门：catalog 载体注册表的**派生**（D4'/D5'）+ **结构守护**（D6'）+ 重复清单提醒（D8'）。

## 两层，作用不同，缺一不可
- **派生（D4'/D5'）只治「抄写漂移」**：6 个载体名此前抄在 4 处，改一漏一不会红。
- **结构守护（D6'）治「登记漂移」**：所有 oracle 都从注册表派生之后，
  **任何没进注册表的新载体对全部守护不可见** ⇒ 单靠派生会把「4 个弱守护」变成
  「**1 个强但盲的守护**」，MUTANT-E 换个形态（新加载体但不登记）照样逃逸。
  ⇒ **D6' 才是本片真正的安全性来源**（守护者 §II-1 认账其 v0.9.3 §IV-1 处方的不足）。
> §6 自检末条：**不因为「派生了」就认为完备。**

## MUTANT-E 背景（v0.9.3 §IV-1）
加第 7 个载体名 + 在 `reload()` 里 `global` 它 → **26 测全绿逃逸**，PEP 562 代理对该名静默死、
per-tenant 槽闲置、跨租户串供照旧。`FIELD_LABELS` 自 v0.7.27 起长期在哨兵之外正是同机制。
v0.9.3 修了**实例**（补 `FIELD_LABELS`）**未修机制** —— 本文件修机制。
"""
import ast
import inspect
import pathlib
import sys

import pytest

_REPO = pathlib.Path(__file__).resolve().parents[1]
_TESTS = _REPO / "tests"
if str(_TESTS) not in sys.path:
    sys.path.insert(0, str(_TESTS))

_CATALOG_PY = _REPO / "knot" / "services" / "agents" / "catalog.py"
_STATE_PY = _REPO / "knot" / "services" / "agents" / "catalog_state.py"


# ─── D4'/D5'：注册表是唯一真相源，派生**活**（不冻结） ────────────────────


def test_D4_carrier_names_is_live_not_frozen():
    """⭐ `carrier_names()` 必须**每次现算** —— 冻结的话 D5' 的注入测按设计不可能通过。

    这是 Codex R3 / 守护者实验坐实的那条：`tuple(_ATTR_TO_SLOT)` 在 **import 期**求值，
    运行期往注册表注入第 7 名后它仍只有 6 个 ⇒ 依赖它的回归测**静默地绿**。
    取材=revert：把 `carrier_names()` 改回 `CARRIER_NAMES = tuple(...)` 模块级常量 → 本测红。
    """
    from knot.services.agents import catalog_state

    before = catalog_state.carrier_names()
    catalog_state._ATTR_TO_SLOT["XPROBE_LIVE"] = "xprobe_live"
    try:
        after = catalog_state.carrier_names()
    finally:
        catalog_state._ATTR_TO_SLOT.pop("XPROBE_LIVE", None)
    assert "XPROBE_LIVE" not in before and "XPROBE_LIVE" in after, (
        f"`carrier_names()` 未反映运行期注入（before={len(before)} after={len(after)}）"
        " —— 它被冻结了（eager tuple / import 期求值），D5' 的注入测将永远绿。"
    )


def test_IV4c_publish_signature_is_driven_by_registry():
    """⭐ IV-4 (c)：`publish()` 的 **keyword-only 参数集 == 注册表 values**。

    **定性：这是廉价的纵深，不是补洞。** 守护者穷举过六种漂移组合：
    ① 只改注册表 / ④ 注册表+签名漏 dict → 不变量红 · ③ 只改 dict 字面 → `NameError` ·
    ⑤ 注册表+dict 漏签名 → `TypeError` · ⑥ 三处齐改 → 正确。
    **唯一漏网的是「只加 publish 签名参数」，而那是良性的死参数**（无人消费）。
    ⇒ 本测买的就是那个良性情形，顺手让**注册表成为 publish 形状的唯一权威**。
    ⚠️ **不要把它当成在守一个真洞** —— 否则你会不敢碰 `publish` 的形状。
    ⚠️ 也**不要**为消除「签名 + dict 字面」这处重复而把 `publish` 改成 `**kwargs`：
    keyword-only 是 v0.9.3 **刻意**的防错设计（防位置参数把 lexicon 灌进 tables）。

    取材=revert：给 `publish()` 加一个未登记的 keyword-only 参数 → 本测红。
    """
    from knot.services.agents.catalog_state import _ATTR_TO_SLOT, publish

    kw = {p.name for p in inspect.signature(publish).parameters.values()
          if p.kind is inspect.Parameter.KEYWORD_ONLY}
    assert kw == set(_ATTR_TO_SLOT.values()), (
        f"publish 的 keyword-only 参数集与注册表 values 不一致：\n"
        f"  publish  = {sorted(kw)}\n  registry = {sorted(set(_ATTR_TO_SLOT.values()))}\n"
        "注册表是 publish 形状的唯一权威；改 slot 集合请同时改两处（本测就是那个提醒）。"
    )


def test_D5_mutant_E_real_slot_is_detected_everywhere(monkeypatch):
    """⭐ MUTANT-E 回归：注入**真 slot**（不得别名到既有 slot）→ 三处 oracle **自动**覆盖它。

    「必须是真 slot」承重：v0.9.3 的原始 MUTANT-E 是 `"XLEX": "lexicon"`（**别名**到既有 slot），
    照抄就**触及不到 slot-schema 漂移** —— 见下方 `test_D5_alias_mutant_is_weaker` 的对照。
    取材=注入（第 7 名是尚不存在的未来状态）。

    ⚠️ **注入必须走 `_cat.__dict__` 的 setitem，不得用 `monkeypatch.setattr(_cat, ...)`**：
    后者即使 `raising=False` 也会先 `getattr` 探一次 → 命中 PEP 562 代理 →
    `get_state()["xnew_slot"]` **裸下标** → `KeyError: 'xnew_slot'`（实测，写本测时踩到）。
    **副产物（已报 Stage 4，本片刻意不修）**：注册表登记了而 publish 没产出的 slot，被读到时
    抛的是 `KeyError` 而非 `AttributeError` ⇒ `hasattr(catalog, X)` 会**炸**而不是返回 False。
    今天不可能发生（注册表 values == publish 参数，由 `test_IV4c_*` 守），故只记不修；
    但它顺带说明了漂移组合 ① 未被拦住时的**运行期症状**是个语焉不详的 `KeyError`。
    """
    from knot.services.agents import catalog_state

    monkeypatch.setitem(catalog_state._ATTR_TO_SLOT, "XNEW", "xnew_slot")

    # ① 派生的载体名集合自动含它
    assert "XNEW" in catalog_state.carrier_names()

    # ② 生产的复活检测自动覆盖它（把它复活进 catalog 命名空间 → 必须 raise）
    from knot.services.agents import catalog as _cat
    monkeypatch.setitem(_cat.__dict__, "XNEW", "resurrected")     # 见上：不得用 setattr
    with pytest.raises(AssertionError, match="XNEW"):
        catalog_state.assert_no_resurrected_globals()
    monkeypatch.delitem(_cat.__dict__, "XNEW")

    # ③ **slot-schema 漂移被 IV-4(c) 抓到** —— 这是「真 slot」才买得到的
    kw = {p.name for p in inspect.signature(catalog_state.publish).parameters.values()
          if p.kind is inspect.Parameter.KEYWORD_ONLY}
    assert kw != set(catalog_state._ATTR_TO_SLOT.values()), (
        "注入了真 slot 却仍与 publish 签名一致 —— IV-4(c) 抓不到 slot-schema 漂移"
    )


def test_D5_alias_mutant_is_weaker(monkeypatch):
    """**对照组**：别名形 mutant（`"XLEX": "lexicon"`）**触及不到** slot-schema 漂移。

    存在意义 = 把「D5' 的 mutant 必须是真 slot」这条要求的**理由**变成可执行的证明，
    而不是一句注释（否则后人照抄 v0.9.3 的别名形，测照样绿、以为覆盖了）。
    """
    from knot.services.agents import catalog_state

    monkeypatch.setitem(catalog_state._ATTR_TO_SLOT, "XLEX", "lexicon")   # 别名到既有 slot
    assert "XLEX" in catalog_state.carrier_names(), "载体名侧仍能覆盖（这半是有效的）"
    kw = {p.name for p in inspect.signature(catalog_state.publish).parameters.values()
          if p.kind is inspect.Parameter.KEYWORD_ONLY}
    assert kw == set(catalog_state._ATTR_TO_SLOT.values()), (
        "别名形 mutant 竟然触发了 slot-schema 断言 —— 那本测的前提（别名更弱）不成立，须重写 D5'"
    )


# ─── D6'：与注册表**无关**的结构守护（本片真正的安全来源） ─────────────────


def _module_level_mutables(tree) -> list:
    """catalog.py 模块级的**可变容器**赋值（含 `AnnAssign` 与 `dict()/list()/set()` 调用形）。

    刻意允许 `ContextVar(...)` —— 它是**请求作用域**状态、不是进程级载体（`_active_catalog_ctx`）。
    """
    out = []
    _MUT_CALLS = {"dict", "list", "set", "defaultdict", "OrderedDict", "Counter"}
    for n in tree.body:
        tg, val = None, None
        if isinstance(n, ast.Assign) and len(n.targets) == 1:
            tg, val = n.targets[0], n.value
        elif isinstance(n, ast.AnnAssign):
            tg, val = n.target, n.value
        if not isinstance(tg, ast.Name) or val is None:
            continue
        bad = isinstance(val, (ast.Dict, ast.List, ast.Set)) or (
            isinstance(val, ast.Call) and getattr(val.func, "id", "") in _MUT_CALLS
        )
        if bad:
            out.append(f"{n.lineno}: {tg.id}")
    return out


def test_D6_catalog_module_has_no_global_statement():
    """⭐ **`catalog.py` 全文件禁任何 `global`** —— 不只禁注册表内那 6 名。

    **这条才是本片真正的安全来源**（守护者 §II-1）：派生只保证「已登记的名字」被守护；
    `global <任何新名>` 会把一个**未登记**的载体复活进模块命名空间 ⇒ PEP 562 代理对它静默死，
    而所有从注册表派生的 oracle **看不见它**。
    ⇒ 故本测**不看名字是否在注册表里**，只看「有没有 `global`」。基线：0 处（实测）。

    **随迁自 v0.9.3 R-9 哨兵②**（原 `test_catalog_loaders.py`，按名过滤版，已移交至此）：
    - 失效机制经**最小复刻模块**实测：PEP 562 `__getattr__` 只在常规属性查找**失败**时触发。
    - **时序真相**：`reload()` 在**启动期与每次 query** 都跑 ⇒ 一旦跑过就**永久落在静默支**；
      `NameError` 那支只存在于首次 reload 之前，**反而是幸运情况**（会炸，看得见）。
    取材=注入：往 `catalog.py` 任意函数里加 `global <随便什么名>` → 本测红。
    """
    tree = ast.parse(_CATALOG_PY.read_text(encoding="utf-8"))
    hits = [f"{n.lineno}: global {', '.join(n.names)}"
            for n in ast.walk(tree) if isinstance(n, ast.Global)]
    assert not hits, (
        "`catalog.py` 出现 `global` 语句：\n  " + "\n  ".join(hits)
        + "\n\n`global X; X = ...` 会把名字复活进模块 `__dict__` ⇒ PEP 562 `__getattr__` **永不触发**"
          "（它只在常规属性查找失败时才被调用）⇒ per-tenant 槽闲置、跨租户串供复发，**且不报错**。"
          "\nreload 必须「局部变量构造 + `catalog_state.publish(...)`」，不得 `global`。"
    )


def test_D6_catalog_module_has_no_module_level_mutable_state():
    """⭐ D6' 后半：`catalog.py` 不得新增**模块级可变容器**（新载体的另一种进场方式）。

    `global` 之外，直接在模块级写 `NEW_THING = {}` 同样造出一个进程级、租户盲的载体，
    而它**不在注册表里** ⇒ 所有派生 oracle 看不见。
    基线：0 处（唯一模块级赋值是 `_active_catalog_ctx = ContextVar(...)`，**请求作用域**，刻意允许）。
    取材=注入：在 `catalog.py` 模块级加 `_CACHE = {}` → 本测红。
    """
    tree = ast.parse(_CATALOG_PY.read_text(encoding="utf-8"))
    hits = _module_level_mutables(tree)
    assert not hits, (
        "`catalog.py` 出现模块级可变容器：\n  " + "\n  ".join(hits)
        + "\n\n它是进程级、租户盲的状态，且**不在载体注册表里** ⇒ 从注册表派生的守护全部看不见它。"
          "\n若确需 per-tenant 状态：加进 `catalog_state` 的槽（并登记进 `_ATTR_TO_SLOT`）；"
          "若确需请求作用域：用 `ContextVar`。"
    )


# ─── D8'：重复清单提醒（阈值 4 · 非完备性保证） ───────────────────────────


def test_D8_no_duplicated_carrier_name_list():
    """载体名字面清单只允许存在于**注册表**一处（阈值 **4** 个名字即视为「抄了一份」）。

    ⚠️ **这是防重复清单的提醒，不是完备性保证** —— 完备性由 `test_D6_*` 两条承担。
    阈值取 4 的理由（守护者裁定）：≥3 会误伤只验三个属性的正当测；≥3 也能拆成两个二元组绕过
    ⇒ 既然注定只是提醒，就该**优先减少误报** —— 噪音大的提醒会被关掉。
    取材=注入：在 `tests/` 里写一份含 **4** 个载体名的字面元组 → 本测红；含 **3** 个 → **不红**（边界）。
    """
    from knot.services.agents.catalog_state import _ATTR_TO_SLOT

    names = set(_ATTR_TO_SLOT)
    hits = []
    for root in ("knot", "tests", "scripts"):
        for py in sorted((_REPO / root).rglob("*.py")):
            try:
                tree = ast.parse(py.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, (ast.Set, ast.Tuple, ast.List)):
                    lits = {e.value for e in node.elts
                            if isinstance(e, ast.Constant) and isinstance(e.value, str)}
                elif isinstance(node, ast.Dict):
                    lits = {k.value for k in node.keys
                            if isinstance(k, ast.Constant) and isinstance(k.value, str)}
                else:
                    continue
                overlap = lits & names
                if len(overlap) >= 4:
                    rel = str(py.relative_to(_REPO))
                    # 注册表本身是唯一允许的一份
                    if rel == str(_STATE_PY.relative_to(_REPO)):
                        continue
                    hits.append(f"{rel}:{node.lineno} 含 {sorted(overlap)}")
    assert not hits, (
        "发现重复的载体名字面清单（唯一允许的一份是 `catalog_state._ATTR_TO_SLOT`）：\n  "
        + "\n  ".join(hits)
        + "\n\n改用 `catalog_state.carrier_names()` 派生。"
          "\n（本测是**提醒**：阈值 4，可被「拆成两个二元组」绕过 —— 完备性由 `test_D6_*` 承担。）"
    )
