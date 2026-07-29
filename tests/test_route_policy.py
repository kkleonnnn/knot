"""闸门：**每条路由的授权策略**必须与钉住的快照一致（D1'~D3' + D7'）。

## 为什么需要它
v0.9.5 要动 **90 处** `require_admin` 依赖。此前全仓的路由守护只有**条数**断言
（`== 144` / `== 53` / `>= 80`）+ **8 条**行为 403 spot check，**0 处** introspect 路由的依赖身份
⇒ **没有任何测能断言「某条路由仍受 `require_admin` 守护」，漏一个不会红。**

## 两条最容易被后人「好心修坏」的地方（D11'）
1. **期望值必须是字面**（`tests/fixtures/route_policy.json`）。
   **从被检对象派生期望 = 自我实现的 tautology，测永远绿**。若你想「让测自动跟上代码」——
   那正是本测要防的事。改动路由/守护后请跑 `scripts/gen_route_policy_snapshot.py`，
   **把 diff 当 review 材料**。
2. **v0.9.5 拆 `require_admin`（platform admin / tenant admin）时本测会按设计必红。**
   那是**强制显式重登记** —— 每条路由都要重新回答「它属于哪一类」。
   **严禁**用「放宽成子串 / 名字匹配 / 从 app 派生期望」来把它弄绿。

## 与 v0.9.4 MF2 被否掉的「漂移清单」不同形
MF2 的坑在**扫描面**硬编（漏一个端点就漏检）；这里硬编的是**期望值**，
而期望值本就必须被钉住，否则无从检测漂移。**扫描面仍是派生的**（全量路由 + introspect 依赖）。
"""
import json
import sys
from pathlib import Path

import pytest

_TESTS = Path(__file__).resolve().parent
if str(_TESTS) not in sys.path:
    sys.path.insert(0, str(_TESTS))

from _route_policy import (  # noqa: E402
    ADMIN,
    AUTHENTICATED,
    PUBLIC_OR_OUT_OF_BAND,
    REPORT_PERMISSION,
    build_actual_policy_map,
    diff,
    load_expected,
    unclassified_websocket_routes,
)

_REGEN = "PYTHONPATH=. python3 scripts/gen_route_policy_snapshot.py"

# ═══════════════════════════════════════════════════════════════════════════════
# D10' 意图复核 —— **23 条挂 admin 守护却在 `/api/admin/` 之外**的路由，逐条一行理由
#
# 为什么必须逐条过：**快照会把今天的状态祝福成正确；钉住之后就查不出来了。**
# 分布实测：ADMIN 90 = `/api/admin/` 内 67 + **外 23**。
# 复核结论：**23 条全部有正当理由，无一条误挂**。理由归三类：
#   (A) 改的是**全体用户共享的结构** → 单人改动影响所有人；
#   (B) 改的是**喂给 LLM 的内容** → prompt 注入面，影响每个用户的每次查询；
#   (C) 拿的是**凭据/第二因子**这类高权面。
#
# 【/api/bi】7 —— (A) 文件夹树与排序是**全站共享导航结构**
#   POST/PUT/DELETE /api/bi/folders[/{id}]     建/改/删文件夹 = 改所有人看到的树
#   PUT /api/bi/reorder/{folders,reports}      改**全局显示顺序**（对比：改单份报表内容只需 report perm，
#                                              因为那只影响该报表；排序影响所有人 ⇒ 不对称是有意的）
#   GET/PUT /api/bi/permissions                RBAC 授权面**本身** —— 能改它就能给自己发权限
# 【/api/db】1
#   POST /api/db/test                          (C) 带**调用方提供的凭据**去连任意主机 = 凭据探测 + 出网面
#                                              （对比 `/api/db/{status,schema}` 只读**已配置**源 ⇒ 仅需登录）
# 【/api/few-shots】5 —— (B) few-shot 直接进 sql_planner prompt
#   GET/POST/PUT/DELETE /api/few-shots[/{fid}] + POST /upload
#   GET 也是 admin：few-shot 正文含**业务口径**（与 `/api/prompts` GET 同口径，非疏漏）
# 【/api/knowledge】3 —— (B) 知识文档进 RAG 检索 → 同样影响每次查询
#   POST /api/knowledge/upload · GET /api/knowledge · DELETE /api/knowledge/{doc_id}
# 【/api/prompts】5 —— (B) **3 个 agent 的 system prompt 本体** = 杠杆最高的 prompt 面
#   GET /api/prompts · GET/PUT/DELETE /api/prompts/{agent_name} · POST /api/prompts/upload
# 【/api/templates】1
#   GET /api/templates/{kind}                  下载 few-shots/knowledge 的**上传模板** xlsx。
#                                              乍看「下个空模板为何要 admin」→ 它是**仅 admin 可用的上传端点的
#                                              配套物**，非 admin 拿到也无处可用 ⇒ 同权限是自洽的，非过严。
# 【/api/totp】1
#   POST /api/totp/reset                       (C) admin 清除**他人的第二因子**。权限正确，但请注意这是
#                                              admin 能力里最接近「绕过 2FA」的一条（本就内含于 admin 权力，
#                                              记此一笔是为让读者别把它当普通 CRUD）。
#
# ── 镜像面也扫了（同一个「祝福」风险的反面：**本该 admin 却只要登录**的）──
# 结论：**无新发现**，一条已登记的开放项：
#   `POST /api/catalog/switch` 无 catalog 级 RBAC —— 任意登录用户可把自己的 active catalog 切到
#   本租户内**任一** catalog。这是**自述的** OOS-2 设计缺口（`knot/api/catalog.py:253`），
#   且**不是租户隔离洞**（catalog_id = 租户内水平切分；跨租户由 v0.9.3 的 per-tenant 文件边界结构性挡住）。
#   ⚠️ 唯一陈旧处是它的版本指针「留 v0.7+」（现已 v0.9 仍未做）→ 已登记 backlog，本片不改代码。
#   （差点误判：CLAUDE.md 说 v0.8 上了「**目录** RBAC」—— 实为 folder/report 粒度 grant
#     （`bi_reports.set_permission` 只收 `folder_id`/`report_id`），**不是** catalog 粒度 ⇒ 那句自述仍准确。）
#
# ⚠️⚠️ **读快照的人必须知道的分类器局限**：本快照只看**依赖层**（`Depends(...)`）守护。
# **函数体内**的守护对它完全不可见 —— 例如 `DELETE /api/saved-reports/{id}` 标 `AUTHENTICATED`，
# 但真正的归属检查在体内（`saved_reports.py:113` `delete_owned(...)` → 不属于你就 404）。
# ⇒ **`AUTHENTICATED` 不等于「任何登录用户能动任何行」**。反过来也成立：本快照转绿
# **不代表**体内授权没被改坏；那是各自的行为测在守。
# ═══════════════════════════════════════════════════════════════════════════════

# D3'：**无用户 JWT 依赖**的路由（原名「无鉴权」不实 —— 它们各有认证来源，只是不经
# `get_current_user`）。每条必须写明认证来源；新增一条即红，强制显式决策。
_NO_USER_JWT_DEPENDENCY = {
    # 本端点**就是**认证入口：凭 username/password（+ 可选公司代号 `company`）
    "POST /api/auth/login",
    # 从**请求体**的 interim_token 认证（不经 Authorization ⇒ 刻意不经 get_current_user；
    # 校验全在 `api/totp.interim_session` —— v0.9.4 R-12 唯一入口）
    "POST /api/totp/verify",
    # **共享密钥** `KNOT_SCHEDULER_TOKEN`（constant-time 比对；未配置 → 503 = 安全默认）
    "POST /api/bi/scheduler/tick",
    # SPA catch-all：只回静态壳，**不碰 DB**（v0.9.4 实测无 ctx 也不 5xx）
    "GET /{full_path:path}",
}


def test_D1_route_policy_matches_snapshot():
    """⭐ 全 138 条路由的授权策略 == 钉住的快照；差集报 added / removed / policy-changed。

    验收（R-C3 取材=revert）：去掉某条 admin 路由的 `Depends(require_admin)` → 本测红且**点名该路由**。
    """
    actual = build_actual_policy_map()
    expected = load_expected()
    d = diff(expected, actual)
    if any(d.values()):
        block = json.dumps(actual, ensure_ascii=False, indent=1, sort_keys=True)
        pytest.fail(
            "路由授权策略与快照不一致：\n"
            f"  ➕ added（新增路由，须显式登记策略）: {d['added'] or '—'}\n"
            f"  ➖ removed（路由消失）: {d['removed'] or '—'}\n"
            f"  ⚠️ policy-changed（**守护被改动**）: {d['policy_changed'] or '—'}\n\n"
            "若改动是有意的：跑 `" + _REGEN + "` 重生成，并把 diff 当 review 材料逐条过。\n"
            "⚠️ policy-changed 里出现 ADMIN → 其它 = 有路由**失去了 admin 守护**，先确认这是有意的。\n"
            "—— 可直接粘贴的新快照 ——\n" + block
        )


def test_D1_policy_class_counts_are_pinned():
    """各策略类的**条数**也钉住 —— 便于人一眼看出「哪一类被整体挪动了」。

    单靠逐条比对已足够严；本测是给**人**看的摘要（失败信息里直接给出四类分布）。
    """
    actual = build_actual_policy_map()
    import collections
    got = collections.Counter(actual.values())
    want = {ADMIN: 90, REPORT_PERMISSION: 10, AUTHENTICATED: 34, PUBLIC_OR_OUT_OF_BAND: 4}
    assert dict(got) == want, (
        f"策略类分布漂移：\n  实际 {dict(sorted(got.items()))}\n  期望 {dict(sorted(want.items()))}\n"
        f"若有意：跑 `{_REGEN}` 并同步本测的 want。"
    )


def test_D2_guard_identity_not_name_based():
    """⭐ 守护者身份用 **`is` / `__code__` 比较**，不用 `__name__`（一行即可伪装）。

    本测直接检验分类器**不被伪装骗**：造一个 `weak`，把 `__name__` 伪装成 `require_admin`，
    看它是否被分类成 ADMIN。
    验收（取材=revert）：把 `_route_policy._classify` 改成按 `__name__` 匹配 → 本测红。
    """
    from _route_policy import _classify

    from knot.api.deps import get_current_user, require_admin

    def weak():
        ...

    weak.__name__ = "require_admin"          # 一行伪装
    assert _classify([weak]) != ADMIN, "按名字匹配被伪装骗过 —— 必须用对象身份（is / __code__）"
    assert _classify([weak, get_current_user]) == AUTHENTICATED
    assert _classify([require_admin]) == ADMIN, "真 require_admin 必须被认出"


def test_D2_factory_produced_dep_is_matched_by_code_identity():
    """⭐ 依赖**工厂**产出的闭包：`is` 比较按构造不可能成立 ⇒ 比 `__code__` 身份。

    `require_report_perm(action)` 每次返回**不同**的 `_dep` 闭包（实测 `is` 为 False），
    但同一工厂产出的闭包**共享同一 code 对象**（编译期唯一）。
    `__code__` 同样**不可被 `__name__` 伪装**（伪装后 `__code__` 仍不同）—— 故仍守 D2' 的实质。
    ⚠️ 这是**实施期发现的 LOCKED 设计洞**：D2' 原文只写了 `dep.call is X`，对工厂形态不适用；
    若照字面实现，**10 条有 RBAC 细粒度权限的报表路由会被错标成 `AUTHENTICATED`**。
    """
    from _route_policy import _classify

    from knot.api.bi_reports import require_report_perm

    a, b = require_report_perm("edit"), require_report_perm("view")
    assert a is not b, "前提：工厂每次产出不同对象（否则本测在验一个不存在的问题）"
    assert a.__code__ is b.__code__, "前提：同一工厂的闭包共享 code 对象"
    assert _classify([a]) == REPORT_PERMISSION and _classify([b]) == REPORT_PERMISSION

    def weak():
        ...

    weak.__name__ = "_dep"                   # 伪装成内层闭包名
    assert _classify([weak]) != REPORT_PERMISSION, "`__code__` 比较不得被 `__name__` 伪装绕过"


def test_D3_no_user_jwt_dependency_set_is_pinned():
    """⭐ **无用户 JWT 依赖**的路由集合钉住（每条的认证来源见本文件常量注释）。

    此前只有「这些路径不得 5xx」的**行为**测（v0.9.4），**没有**结构断言
    ⇒ 新增一条无用户 JWT 依赖的路由**静默通过**。
    验收（取材=注入，须走真实注册 API）：`app.get(...)` 新增一条无依赖路由 → 本测红。
    """
    actual = build_actual_policy_map()
    got = {k for k, v in actual.items() if v == PUBLIC_OR_OUT_OF_BAND}
    added, removed = sorted(got - _NO_USER_JWT_DEPENDENCY), sorted(_NO_USER_JWT_DEPENDENCY - got)
    assert not added and not removed, (
        "无用户 JWT 依赖的路由集合变了 —— 这是**认证面**的改动，必须显式决策：\n"
        f"  ➕ 新增（须在本文件常量里写明认证来源）: {added or '—'}\n"
        f"  ➖ 消失: {removed or '—'}"
    )


def test_D3_no_unclassified_websocket_routes():
    """`APIWebSocketRoute` 不在策略表覆盖范围内 ⇒ 必须为 0，否则它会**静默逃出策略表**。

    今天 0 条（实测）⇒ 本条是**防御性**加固，无现存坏例。
    验收（取材=注入，须走真实注册 API）：`app.add_api_websocket_route(...)` → 本测红。
    ⚠️ 不得手搓 route 对象塞 `app.routes` —— 那样红是因为「对象形状不对」而非「有 WebSocket 路由」，
    是个假证明（R-C3 附加条件 2）。
    """
    ws = unclassified_websocket_routes()
    assert not ws, (
        f"发现未分类的 WebSocket 路由：{ws}\n"
        "策略表只覆盖 APIRoute。请显式决定它的授权策略并扩 `tests/_route_policy.py`，"
        "**而不是**让它逃出策略表。"
    )


def test_D7_named_guards_not_overridden():
    """⭐ 具名守护函数**不得**出现在 `app.dependency_overrides`（D1' 对此**免疫不了**）。

    ⚠️ **D2'/D7' 正交，谁也替代不了谁**（实测）：dependant 树在**注册期**构建、持的是原对象；
    override 在**请求期**解析 ⇒ override 之后 D1' **仍报 ADMIN**，而实际执行的是替身。
    ⇒ **「用了 `is` 比较所以对 override 免疫」是错的。** 本测就是那条正交性的守护，
    `test_D7_orthogonal_to_D1` 进一步钉住它 —— **删掉本测 = 打开一条静默换守护的旁路**。

    只针对**具名守护函数**，不断言整个 overrides 字典为空 —— 测自己会合法用 override（D7' 硬条件）。
    """
    from knot.api.deps import get_current_user, require_admin
    from knot.main import app

    overridden = [f.__name__ for f in (require_admin, get_current_user)
                  if f in app.dependency_overrides]
    assert not overridden, (
        f"具名守护被 override：{overridden}\n"
        "这会让路由策略快照**仍然绿**而实际守护已被替换（注册期 vs 请求期）。\n"
        "若某条测需要 override，请用局部 fixture 并在结束时复原"
        "（根 conftest 的 `_restore_dependency_overrides` 已提供 per-test 复原）。"
    )


def test_D7_orthogonal_to_D1(monkeypatch):
    """⭐ **正交性证明**：override 之后 D7' 红而 D1' **仍绿** ⇒ 二者不可互相替代。

    守护者 Stage 1' 复核指出：这条测**比两个守护本身更值钱** —— 它防的是后人删掉 D7'
    （「D1' 已经用 `is` 比较了，D7' 多余」是个很容易犯的误推）。
    取材=注入（override 是未来状态，不是某个已做的修）。
    """
    from knot.api.deps import require_admin
    from knot.main import app

    def weak():
        return {"id": 1, "role": "analyst"}

    weak.__name__ = "require_admin"                      # 连名字一起伪装
    monkeypatch.setitem(app.dependency_overrides, require_admin, weak)

    # D1' 侧：策略快照**察觉不到** override
    actual = build_actual_policy_map()
    assert actual.get("GET /api/admin/users") == ADMIN, (
        "前提不成立：D1' 本应对 override **无感**（注册期持原对象）。"
        "若此断言红，说明 FastAPI 行为变了 —— 正交性论证需重做。"
    )
    # D7' 侧：能察觉
    assert require_admin in app.dependency_overrides
