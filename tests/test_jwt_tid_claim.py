"""v0.9.4 D1/B-3/R-8 — JWT `tid` claim 守护：两条签发路径 + 静态哨兵。

⭐ **为何要静态哨兵**：签发路径有**两条且不共码**（`deps.create_token` / `totp.create_interim_token`
—— 不同文件、`ver` 来源不同），漏加 `tid` **不会崩、只会静默失能**。哨兵从 AST 派生目标集
（扫全仓 `jwt.encode` 调用），故**将来出现第三条签发路径时自动覆盖** —— 不是一份需要人同步的清单
（v0.9.3 教训 7「修机制不修实例」）。
"""
from __future__ import annotations

import ast
from pathlib import Path

import jwt
import pytest

from knot.core import tenant_context as tc
from knot.core.tenant_context import reset_active_tenant, set_active_tenant

_REPO = Path(__file__).resolve().parents[1]


def _jwt_aliases(tree) -> tuple[set, set]:
    """从**本文件的 import 语句派生** jwt 的别名集 —— 不硬编名字 `jwt`。

    ⚠️ 初版只匹配字面 `jwt.encode(...)` ⇒ `import jwt as _j` + `_j.encode(...)` **直接绕过**
    （revert 实测：新增一条用别名的签发路径，哨兵毫无反应）。这与守护者两次点名的同类问题
    （setattr 哨兵别名绕过 / 端点清单硬编）是同一形状：**匹配名字而非匹配来源**。
    → 返 (模块别名集, 直接 import 的 encode 名集)。
    """
    mods, funcs = set(), set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for a in n.names:
                if a.name == "jwt" or a.name.startswith("jwt."):
                    mods.add(a.asname or a.name.split(".")[0])
        elif isinstance(n, ast.ImportFrom) and n.module == "jwt":
            for a in n.names:
                if a.name == "encode":
                    funcs.add(a.asname or a.name)
    return mods, funcs


def _jwt_encode_calls():
    """全仓所有 JWT 签发调用（AST 派生 + **别名感知**）→ (相对路径, 行号, 首参 AST)。"""
    for py in (_REPO / "knot").rglob("*.py"):
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        mods, funcs = _jwt_aliases(tree)
        if not mods and not funcs:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            # ⚠️ **MF8**：`jwt.encode(payload={...}, key=...)` 是**关键字形**，旧版只看 `node.args`
            # ⇒ 关键字调用整条逃出哨兵。首参取「位置首参 **或** `payload=` 关键字」。
            first = node.args[0] if node.args else next(
                (kw.value for kw in node.keywords if kw.arg == "payload"), None)
            if first is None:
                continue
            fn = node.func
            hit = (
                (isinstance(fn, ast.Attribute) and fn.attr == "encode"
                 and isinstance(fn.value, ast.Name) and fn.value.id in mods)
                or (isinstance(fn, ast.Name) and fn.id in funcs)
            )
            if hit:
                yield py.relative_to(_REPO), node.lineno, first


def test_R8_every_jwt_encode_payload_declares_tid():
    """⭐ R-8 哨兵：全仓**每一处** `jwt.encode` 的 payload 字面必须含 `tid` 键。

    目标集从 AST 派生 ⇒ 第三条签发路径出现时自动纳入守护。
    revert（任一路径去掉 `"tid"`）→ 本测转红。
    """
    found, offenders = 0, []
    for rel, lineno, payload in _jwt_encode_calls():
        found += 1
        if not isinstance(payload, ast.Dict):
            offenders.append(f"{rel}:{lineno} payload 非字面 dict（哨兵无法静态验证 tid，请改字面）")
            continue
        keys = {k.value for k in payload.keys if isinstance(k, ast.Constant)}
        if "tid" not in keys:
            offenders.append(f"{rel}:{lineno} payload 缺 tid，实有 {sorted(keys)}")
    assert found >= 2, f"应扫到 ≥2 处签发路径（create_token / create_interim_token）；实际 {found} —— 哨兵可能失效"
    assert not offenders, (
        "JWT 签发路径漏带 tid ⇒ 多租户下该 token 无租户身份（**静默失能**，不会崩）：\n  "
        + "\n  ".join(offenders)
    )


@pytest.fixture
def _t7(tmp_path, monkeypatch):
    """tenant#7 ctx（刻意非 1，防「恰好等于默认值」的假通过）。"""
    from knot.repositories import base, tenant_repo
    anchor = tmp_path / "knot.db"
    monkeypatch.setattr(base, "SQLITE_DB_PATH", str(anchor))
    monkeypatch.setattr(tenant_repo, "SQLITE_DB_PATH", str(anchor))
    tok = set_active_tenant({"id": 7, "db_dir": "."})
    base.init_db()
    yield 7
    reset_active_tenant(tok)


def _decode(token):
    from knot.api.deps import _get_secret
    return jwt.decode(token, _get_secret(), algorithms=["HS256"])


def test_create_token_carries_current_tenant_id(_t7):
    """`create_token` 的 tid = 当前 ctx 的租户 id（用 tid=7 而非 1，防默认值假通过）。"""
    from knot.api.deps import create_token
    p = _decode(create_token(1))
    assert p["tid"] == 7, p
    assert type(p["tid"]) is int, f"tid 须为 int（R-9 严格类型）；实际 {type(p['tid'])}"


def test_create_interim_token_carries_current_tenant_id(_t7):
    """`create_interim_token` 同样带 tid，且**由内部取 ctx**（F-4）——
    调用方只传 user_id/token_version，签名里没有 tid 参数可漏传。"""
    import inspect

    from knot.api.totp import create_interim_token
    assert "tid" not in inspect.signature(create_interim_token).parameters, (
        "F-4：tid 不得作为参数由调用方传（那种签名风格让漏传变成静默）"
    )
    p = _decode(create_interim_token(1, 1))
    assert p["tid"] == 7 and p["totp_pending"] is True, p


@pytest.mark.parametrize("factory", ["create_token", "create_interim_token"])
def test_both_signing_paths_fail_closed_without_ctx(_t7, factory):
    """两条签发路径在**无 tenant ctx** 时都必须 raise —— 绝不签出无 tid 的 token（fail-closed）。

    这正是 F-4 裁定的收益：`create_interim_token` 此前不依赖 ctx ⇒ 漏改是静默的；改为内部取 ctx 后
    变成**响亮崩溃**。revert（tid 由参数传且默认 None）→ 本测转红。
    """
    fn = (__import__("knot.api.deps", fromlist=["x"]).create_token if factory == "create_token"
          else __import__("knot.api.totp", fromlist=["x"]).create_interim_token)
    tok = tc._active_tenant_ctx.set(None)
    try:
        with pytest.raises(tc.TenantContextError):
            fn(1) if factory == "create_token" else fn(1, 1)
    finally:
        tc._active_tenant_ctx.reset(tok)
