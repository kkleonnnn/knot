"""路由策略分类的**唯一实现**（测与再生成脚本共用 —— 防两处判据漂移）。

## 扫描面**派生**，期望值**字面**（R-C2 · D1'）
本模块只负责「**从 app 派生今天的实际策略**」。期望值在 `tests/fixtures/route_policy.json`，
是**字面快照**。⚠️ 二者的区别是本片的核心设计，务必分清：
- **扫描面派生** = 遍历 `flatten_app_routes(app)` 全量 ⇒ 新增路由**自动纳入**，不需要人往清单里加；
- **期望值字面** = 快照钉住 ⇒ 漂移才有的可比。
  **从被检对象派生期望 = 自我实现的 tautology，测永远绿**（v0.9.4 MF11①）。
> 与 v0.9.4 MF2 被否掉的「漂移清单」**不同形**：MF2 的坑在**扫描面**硬编（漏一个端点就漏检）；
> 这里硬编的是**期望值**，而期望值本就必须被钉住，否则无从检测漂移。

## 守护者身份用 `is` 比较，不用 `__name__`（D2'）
`weak.__name__ = "require_admin"` 一行即可骗过名字匹配（实测：名字匹配 True / `is` 比较 False）。
⇒ 一律 `dep.call is <函数对象>`。
⚠️ **`is` 比较不代表对 `dependency_overrides` 免疫** —— dependant 树在**注册期**构建、持的是原对象，
override 在**请求期**解析。实测：override 后本模块仍报 `ADMIN`，而实际执行的是 `weak`。
⇒ 那条旁路由 `test_route_policy.py::test_D7_named_guards_not_overridden` 独立守；**二者正交，谁也替代不了谁**。
"""
from __future__ import annotations

import pathlib
import sys

_TESTS = pathlib.Path(__file__).resolve().parent
if str(_TESTS) not in sys.path:
    sys.path.insert(0, str(_TESTS))

# 四类策略（D1'）
PUBLIC_OR_OUT_OF_BAND = "PUBLIC_OR_OUT_OF_BAND"
AUTHENTICATED = "AUTHENTICATED"
ADMIN = "ADMIN"
REPORT_PERMISSION = "REPORT_PERMISSION"

FIXTURE = _TESTS / "fixtures" / "route_policy.json"


def _dep_calls(route) -> list:
    """递归收集一条路由 dependant 树上的所有 `call` **对象**（带 `seen` 防环 —— MF2）。"""
    out, stack, seen = [], [getattr(route, "dependant", None)], set()
    while stack:
        d = stack.pop()
        if d is None or id(d) in seen:
            continue
        seen.add(id(d))
        if getattr(d, "call", None) is not None:
            out.append(d.call)
        stack.extend(getattr(d, "dependencies", ()) or ())
    return out


def _report_perm_code():
    """`require_report_perm` 产出的 `_dep` 闭包的 **code 对象**（编译期唯一）。

    ⭐ **实施期发现的 LOCKED 设计洞（Stage 4 请核）**：`require_report_perm(action)` 是**依赖工厂**，
    每条路由拿到的是**不同的 `_dep` 闭包对象** ⇒ **D2' 规定的 `dep.call is X` 对它按构造不可能成立**
    （实测 `factory("a") is factory("b")` → False）。评审双方给的类名 `require_report_permission`
    在仓里**不存在**，真名是 `require_report_perm`。
    **解法仍守 D2' 的实质（身份而非名字）**：比 **`__code__` 身份** —— 同一工厂产出的所有闭包共享
    同一个 code 对象（实测 `factory("a").__code__ is factory("b").__code__` → True），
    而它**不可被 `__name__` 伪装**（实测：把 `weak.__name__` 改成 `_dep` 后 `weak.__code__` 仍不同）。
    """
    from knot.api.bi_reports import require_report_perm
    return require_report_perm("__probe__").__code__


def _classify(calls: list) -> str:
    """按依赖**对象身份**定策略。顺序承重：ADMIN 最强，故先判。"""
    from knot.api.deps import get_current_user, require_admin

    if any(c is require_admin for c in calls):
        return ADMIN
    rp = _report_perm_code()
    if any(getattr(c, "__code__", None) is rp for c in calls):
        return REPORT_PERMISSION
    if any(c is get_current_user for c in calls):
        return AUTHENTICATED
    return PUBLIC_OR_OUT_OF_BAND


def build_actual_policy_map() -> dict:
    """{"METHOD /path": POLICY} —— 从 app **派生**（含全部 `APIRoute`）。

    **返回 list-based 中间态再折叠**：先收集 `(method, path)` 列表并断唯一，
    避免 `set` 静默折叠重复（MF6）。重复由调用方（测/脚本）报错，不在此处静默。
    """
    from _route_count import flatten_app_routes
    from fastapi.routing import APIRoute

    from knot.main import app

    pairs = []
    for r in flatten_app_routes(app):
        if not isinstance(r, APIRoute):
            continue
        policy = _classify(_dep_calls(r))
        for m in sorted(r.methods or ()):
            pairs.append((f"{m} {r.path}", policy))

    dupes = sorted({k for k, _ in pairs if [x for x, _ in pairs].count(k) > 1})
    if dupes:
        raise AssertionError(
            f"发现重复的 (method, path)：{dupes}\n"
            "快照以 (method, path) 为键；重复会被静默折叠成一条 ⇒ 其中一条的策略漂移检测不到（MF6）。"
        )
    return dict(pairs)


def unclassified_websocket_routes() -> list:
    """`APIWebSocketRoute` 一律未分类（本快照只覆盖 `APIRoute`）—— D3' 断言其为空。

    今天 0 条；将来若新增，必须显式决定它的策略并扩本模块，**而不是让它静默逃出策略表**。
    """
    from _route_count import flatten_app_routes
    from fastapi.routing import APIWebSocketRoute

    from knot.main import app

    return [getattr(r, "path", str(r)) for r in flatten_app_routes(app)
            if isinstance(r, APIWebSocketRoute)]


def load_expected() -> dict:
    import json
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def diff(expected: dict, actual: dict) -> dict:
    """三类差集（D1'）—— 不是「90 != 91」这种不可行动的数字。"""
    ek, ak = set(expected), set(actual)
    return {
        "added": sorted(ak - ek),
        "removed": sorted(ek - ak),
        "policy_changed": sorted(
            f"{k}: {expected[k]} → {actual[k]}" for k in (ek & ak) if expected[k] != actual[k]
        ),
    }
