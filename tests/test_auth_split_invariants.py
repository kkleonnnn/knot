"""闸门：v0.9.5 鉴权拆分的承重不变量（`require_tenant_admin` 改名 + role 值域 + BI bypass 契约）。

## 本文件守什么
v0.9.5 把 `require_admin` 拆成「**租户** admin」语义（platform admin 走**平行**认证路径，
out-of-band 共享密钥 —— E1）。三条不变量：
1. **旧名不得复活**（否则「名字诚实」这个本片的全部意义就没了，且会出现两套并存的守护）。
2. **`role` 值域钉住 `{"admin","analyst"}`** —— 封住 E1 的第二条放弃路径（见下）。
3. **BI RBAC 的 admin bypass 契约** —— 全仓后果最大的一处体内角色分流。

## ⭐ E1 有两条放弃路径，本文件封第二条
platform admin 之所以**不是**租户内的一个角色，靠两件事：
- 路径 A（建 `platform_admins` 表）→ `tests/test_tenant_isolation.py::test_iso4_platform_db_only_tenants_table`
  已断言 `platform.db` 表集 == `{tenants}`，**建表即红** ✅（既有守护，本片不动）。
- 路径 B（**往 `role` 值域塞 `platform_admin`**）→ **本片之前是敞的**：`role` 是
  `TEXT DEFAULT 'analyst'` **无 DB CHECK**（`repositories/schema.sql:9`），
  且 `_VALID_ROLES` **零测钉住**（实测 `grep -rn "_VALID_ROLES" tests/` 零命中）
  ⇒ 加一个值是**一行、零 CI 反应**。本文件的 `test_VALID_ROLES_pinned` 封它。

⚠️ **精确定性（别读重）**：**单加一个 role 值本身 fail-closed 无害** —— 所有
`role == "admin"` 比较都不匹配，那个用户什么都做不了。**危险在紧随其后的放宽**：
有人发现「不工作」就把 `require_tenant_admin` 或 `bi_permission_service._is_tenant_admin`
改成 `role in ("admin", "platform_admin")` —— **那一刻**全仓 12 处体内角色分流才真变缺口
（平台 admin 在**租户内**绕过整套 BI RBAC + 看未脱敏 SQL/表名）。
本文件第 2、3 条测就是那两个「紧随其后」的动作各自的红灯。
"""
import ast
import pathlib
import subprocess

import pytest

_REPO = pathlib.Path(__file__).resolve().parents[1]


def _tracked_py() -> list:
    out = subprocess.run(["git", "ls-files", "*.py"], cwd=_REPO,
                         capture_output=True, text=True, check=True).stdout.split()
    return [_REPO / f for f in out]


def test_old_require_admin_name_is_gone_everywhere():
    """⭐ 全仓 `.py` 不得再出现旧名 `require_` + `admin`（词边界）。

    **只扫 `.py`**：`CHANGELOG.md` / `docs/plans/**` 里合法引用旧名（历史记录 + 评审留痕），
    扫它们会因历史而红 —— 那是「让守护逼着改历史」，反了。

    ⚠️⚠️ **用 AST 只看标识符，不做文本匹配** —— 这是本测第二版。
    第一版用「运行期拼 needle + 逐 token 比对」，自以为躲开了自匹配，结果**仍然自匹配**：
    本文件的 docstring / 注释里以 prose 形式提到旧名（`` `旧名` `` 带反引号），
    而 tokenizer 会 strip 反引号 ⇒ 命中自己两处（实测 full suite 转红）。
    更难看的是第一版的 docstring **正引用了 v0.9.4 `test_R17` 匹配到自己 docstring 的教训**，
    然后犯了同一个错。⇒ **结论：讨论一个名字的文件必然含有那个名字；判「标识符是否存在」只能用 AST。**
    （本仓第三次「文本匹配 → 改 AST」：v0.9.3 载体名 · v0.9.4 `test_R17` · 本次。）
    「复活」的定义因此也更准：**存在一个叫这个名字的标识符**（import / 调用 / 定义 / 参数），
    而不是「源码里出现过这串字符」。
    取材=revert：把任一处改回旧名 → 本测红并点名 `file:line`。
    """
    needle = "require_" + "admin"          # 仍构造式：避免本行自己成为一个「字面」被将来的 grep 误判
    hits = []
    for p in _tracked_py():
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, SyntaxError):
            continue
        for n in ast.walk(tree):
            found = (
                (isinstance(n, ast.Name) and n.id == needle)
                or (isinstance(n, ast.Attribute) and n.attr == needle)
                or (isinstance(n, ast.alias) and needle in (n.name, n.asname))
                or (isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef) and n.name == needle)
                or (isinstance(n, ast.arg) and n.arg == needle)
                or (isinstance(n, ast.keyword) and n.arg == needle)
            )
            if found:
                hits.append(f"{p.relative_to(_REPO)}:{getattr(n, 'lineno', '?')}")
    assert not hits, (
        f"旧名 `{needle}` 复活于：\n  " + "\n  ".join(hits)
        + "\n\nv0.9.5 已把它改名为 `require_tenant_admin`（platform admin 走平行认证路径 —— E1）。"
          "\n两套并存的守护 = 读者无法判断某条路由属于哪一域 = 本片要治的病。"
    )


def test_VALID_ROLES_pinned():
    """⭐ must-fix #3：`role` 值域钉死 `{"admin","analyst"}`（封 E1 的路径 B）。

    `role` 列**无 DB CHECK**，此前该集合**零测钉住** ⇒ 加 `"platform_admin"` 一行、零 CI 反应。
    取材=injection：往 `knot/api/admin/users.py` 的 `_VALID_ROLES` 加一个值 → 本测红。
    """
    from knot.api.admin.users import _VALID_ROLES

    assert _VALID_ROLES == {"admin", "analyst"}, (
        f"`role` 值域变了：{sorted(_VALID_ROLES)}\n\n"
        "⚠️ 若你在加 `platform_admin` 之类的值 —— **停一下**：v0.9.5 的 E1 决策是\n"
        "  platform admin **不是**租户内的角色，走 out-of-band 共享密钥的**平行认证路径**\n"
        "  （`knot/api/platform_admin.py`），正因为 `get_current_user` 结构性要求 `tid`。\n"
        "加值本身 fail-closed 无害，但**下一步**必然是把 `require_tenant_admin` 或\n"
        "`bi_permission_service._is_tenant_admin` 放宽成 `role in (...)` —— **那一刻**\n"
        "全仓 12 处体内角色分流全变缺口（平台 admin 在租户内绕过整套 BI RBAC + 看未脱敏 SQL）。\n"
        "⇒ 见 `docs/plans/v0.9.5-auth-split-platform-tenant-admin.md` D10' 条件式，先走评审。"
    )


# ─── D10'：BI RBAC 的 admin bypass 契约（全仓后果最大的一处体内角色分流）──────


@pytest.mark.parametrize("role,expect_bypass", [
    ("admin", True),            # 租户 admin：恒全权（v0.8.12 设计）
    ("analyst", False),         # 普通用户：走 grant 解析
    ("platform_admin", False),  # ⭐ 未来值：**不得**获得 bypass（fail-closed）
])
def test_bi_permission_admin_bypass_contract(role, expect_bypass, monkeypatch):
    """⭐ D10'：`bi_permission_service` 的 admin bypass 语义被钉住，**四个入口全覆盖**。

    这是 v0.9.5 唯一被**强制**改名的体内分流点（`_is_admin` → `_is_tenant_admin`）——
    因为它的后果最大：命中即**绕过整套 BI RBAC**（4 个入口 `effective` / `can` /
    `can_share_anything` / `can_folder` 全部 `if _is_tenant_admin(user): return 全权`）。

    ⭐ `platform_admin` 那一格是**前瞻守护**：它今天不是合法 role 值（`test_VALID_ROLES_pinned` 钉住），
    本格断言的是「**即便有人塞进这个值，也不得拿到 bypass**」。
    取材=injection：把 `_is_tenant_admin` 放宽成 `role in ("admin","platform_admin")` → 本格红。
    """
    from knot.services import bi_permission_service as svc

    # grant 全空 ⇒ 非 bypass 路径必然全 False（把「有没有 bypass」与「grant 内容」解耦）
    monkeypatch.setattr(svc.repo, "get_folder_grant", lambda *a, **k: None)
    monkeypatch.setattr(svc.repo, "get_report_grant", lambda *a, **k: None)
    monkeypatch.setattr(svc.repo, "user_has_any_share_grant", lambda *a, **k: False)

    user = {"id": 7, "role": role}
    report = {"id": 1, "folder_id": 3}

    got = {
        "effective": all(svc.effective(user, report).values()),
        "can": svc.can(user, report, "edit"),
        "can_share_anything": svc.can_share_anything(user),
        "can_folder": svc.can_folder(user, 3, "edit"),
    }
    assert all(v is expect_bypass for v in got.values()), (
        f"role={role!r} 的 bypass 契约破了：{got}（期望四个入口全部 {expect_bypass}）\n"
        "⚠️ 若你放宽了 `_is_tenant_admin` 的条件 —— 那正是 D10' 条件式点名的危险动作："
        "平台身份在**租户内**绕过整套 BI RBAC。"
    )
