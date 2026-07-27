"""v0.9.4 step 4 — interim token 的 ctx-free 前缀契约 + 单一组合入口（R-12 / R-13 / D4''-c）。

守护者 I-1/I-2/Q1 定稿的三件事，本文件逐条钉住：
1. **单一组合入口**（Q1）：两段均模块私有，对外只有 `interim_session`。⇒ 「验了签但没验吊销」的
   半成品 payload **没有任何 public API 交得出来** ⇒ 「忘记验吊销」不是一个能犯的错。
   `test_R12_*` 两测守此结构（AST + 全仓引用），**不是**靠人记得。
2. **顺序 `① ② ③ ⑤ ④`**（I-1，限流提到吊销之前）：`test_order_*` 三测用**可观察的状态码**钉顺序
   （429 vs 401 谁先出），不看代码行号。
3. **ctx-free 前缀恰为 [验签, 取 tid]**（I-2）：`test_entry_clears_ctx_*` 证明入口清 ctx 后
   前缀内任何依赖 ctx 的调用会**当场崩**（R-13 运行期自执行），不靠静态清单猜传递闭包。

fixtures：`tmp_db_path`（conftest）已建 platform.db + seed tenant#1(db_dir='.')；autouse 设 tenant#1 ctx。
"""
import ast
import pathlib

import jwt
import pytest
from fastapi import HTTPException

from knot.api import totp as totp_mod
from knot.api.deps import JWT_ALGORITHM, _get_secret
from knot.core import tenant_context as tc
from knot.core.tenant_context import TenantContextError

_REPO = pathlib.Path(__file__).resolve().parents[1]
_TOTP_SRC = _REPO / "knot" / "api" / "totp.py"

# 两段私有函数名 —— 哨兵的目标集**从这里派生**，但下方 test_R12_stage_names_exist 会核实
# 它们真的存在（防将来改名后哨兵扫 0 处仍绿 = 假绿）。
_STAGE1 = "_verify_interim_signature"
_STAGE2 = "_assert_interim_not_revoked"
_COMBINED = "interim_session"


def _mk_interim(user_id=1, ver=1, tid=1, **extra):
    """直接造 interim payload（绕过 `create_interim_token`，以便造出它造不出的畸形形状）。"""
    from datetime import datetime, timedelta
    payload = {"sub": str(user_id), "totp_pending": True, "ver": ver,
               "exp": datetime.utcnow() + timedelta(minutes=5)}
    if tid is not None:
        payload["tid"] = tid
    payload.update(extra)
    return jwt.encode(payload, _get_secret(), algorithm=JWT_ALGORITHM)


def _enclosing_funcs(tree):
    """{Call 节点 → **最内层**包裹它的 def 名}（哨兵用：判「谁调了第一段」）。

    刻意不用 `ast.walk`：walk 自外向内、无嵌套信息，嵌套 def 会把归属算到外层 def 上
    ⇒ 「把第一段的调用藏进 verify 端点里的内嵌函数」这种绕过会被误判成合规。
    这里显式递归、进 def 就换 owner，嵌套多深都归到最内层那个 def。
    """
    out = {}

    def rec(node, owner):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                rec(child, child.name)
            else:
                if isinstance(child, ast.Call):
                    out[child] = owner
                rec(child, owner)

    rec(tree, None)
    return out


# ─── 1. R-12 单一组合入口（结构性守护） ──────────────────────────────────


def test_R12_stage_names_exist():
    """先钉「目标集非空」—— 否则两段一改名，下方哨兵扫 0 处**仍绿** = 假绿。

    （v0.9.3 教训：哨兵最常见的失效方式不是判错，而是**目标集变空而无人察觉**。）
    """
    for name in (_STAGE1, _STAGE2, _COMBINED):
        assert hasattr(totp_mod, name), f"{name} 不存在 —— 改名了？哨兵目标集已失效，须同步本文件"


def test_R12_first_stage_only_called_inside_combined_entry():
    """⭐ 第一段（验了签但没验吊销）**只能**在组合入口内被调用。

    revert-to-bad：在 verify 端点里直接调 `_verify_interim_signature` → 本测转红。
    """
    tree = ast.parse(_TOTP_SRC.read_text(encoding="utf-8"))
    encl = _enclosing_funcs(tree)
    bad = []
    found = 0
    for node, owner in encl.items():
        if isinstance(node.func, ast.Name) and node.func.id == _STAGE1:
            found += 1
            if owner != _COMBINED:
                bad.append(f"{owner or '<模块级>'}():{node.lineno}")
    assert found >= 1, f"哨兵在 totp.py 里扫到 0 处 {_STAGE1} 调用 —— 目标集失效"
    assert not bad, (
        f"{_STAGE1} 只允许在 {_COMBINED}() 内调用（R-12）；越界处：{bad}。\n"
        f"它返回的是「验了签但没验吊销」的半成品 —— 绕过组合入口 = 复活 #259 修掉的洞。"
    )


def test_R12_no_external_reference_to_private_stages():
    """两段私有函数**不得被 totp.py 之外的生产码引用**（含 import / 属性访问）。"""
    bad = []
    for py in (_REPO / "knot").rglob("*.py"):
        if py == _TOTP_SRC:
            continue
        src = py.read_text(encoding="utf-8")
        for name in (_STAGE1, _STAGE2):
            if name in src:
                bad.append(f"{py.relative_to(_REPO)} 提及 {name}")
    assert not bad, f"两段私有函数外泄（R-12）：{bad}"


# ─── 2. ctx-free 前缀 + 入口清 ctx（R-13 运行期自执行） ──────────────────


def test_entry_clears_ctx_before_signature_verification(tmp_db_path, monkeypatch):
    """⭐ ① 入口清 ctx：进入组合入口后、③ set 之前，**任何依赖 ctx 的调用都会当场崩**。

    这是 R-13 的**运行期**证明（不是静态清单）：外层 ctx 明明是 tenant#1，但第一段里读 ctx 就 raise
    ⇒ 「入口到 set-ctx 之间误用 middleware 留下的 ctx（可能属于**别的公司**）」不可能静默发生。

    revert-to-bad：删掉 `clear_active_tenant()` 那行 → 第一段里读到 tenant#1 → 本测转红。
    """
    seen = {}
    real = totp_mod._verify_interim_signature

    def spy(token):
        try:
            seen["ctx"] = tc.current_tenant()["id"]
        except TenantContextError:
            seen["ctx"] = "RAISED"
        return real(token)

    monkeypatch.setattr(totp_mod, _STAGE1, spy)
    assert tc.current_tenant()["id"] == 1, "前置：外层 ctx 应是 autouse 的 tenant#1"
    with totp_mod.interim_session(_mk_interim(tid=1)):
        pass
    assert seen["ctx"] == "RAISED", (
        f"ctx-free 前缀被破：第一段里读到 ctx={seen['ctx']} —— 入口未清 ctx，"
        f"前缀内的代码会静默用上游租户的 ctx"
    )


def test_ctx_restored_after_block(tmp_db_path):
    """作用域化：`with` 退出后外层 ctx 原样（不把租户 ctx 泄给后续代码）。"""
    before = tc.current_tenant()
    with totp_mod.interim_session(_mk_interim(tid=1)) as (payload, uid):
        assert uid == 1 and payload["tid"] == 1
    assert tc.current_tenant() is before, "退出后 ctx 未复原（泄漏）"


def test_ctx_restored_even_when_block_raises(tmp_db_path):
    """异常路径同样复原（`finally` 承重 —— verify 失败会 raise HTTPException）。"""
    before = tc.current_tenant()
    with pytest.raises(RuntimeError, match="boom"):
        with totp_mod.interim_session(_mk_interim(tid=1)):
            raise RuntimeError("boom")
    assert tc.current_tenant() is before, "异常路径未复原 ctx"


# ─── 3. 顺序契约 ① ② ③ ⑤ ④（守护者 I-1） ─────────────────────────────


def _fill_verify_bucket(user_id=1, n=5):
    """把 totp-verify 桶打满（桶是 **tenant-scoped**，须在目标租户 ctx 内调）。"""
    from knot.api import _rate_limit as rl
    for _ in range(n):
        rl.enforce_totp_verify_rate_limit(user_id)


def test_order_rate_limit_precedes_revocation(tmp_db_path):
    """⭐ ⑤ 限流 早于 ④ 吊销（I-1）：桶满 + **已吊销** interim → 应 **429**（不是 401）。

    意义：持「已吊销但签名有效」interim 的攻击者不再能靠反复尝试**每次都触发一次 DB 读**。
    revert-to-bad：把 ⑤④ 两行调换 → 得 401 INTERIM_TOKEN_REVOKED → 本测转红。
    """
    _fill_verify_bucket()                              # 桶：与组合入口同一 tenant#1 ctx
    revoked = _mk_interim(ver=999, tid=1)              # ver 与 DB 不符 = 已吊销
    with pytest.raises(HTTPException) as ei:
        with totp_mod.interim_session(revoked):
            pass
    assert ei.value.status_code == 429, (
        f"顺序破：应先撞限流(429)，实得 {ei.value.status_code} {ei.value.detail}"
    )


def test_order_signature_precedes_rate_limit(tmp_db_path):
    """② 验签 早于 ⑤ 限流：桶满 + **签名无效** → 应 **401**（不是 429）。

    意义：无效 token 不消耗/不受限流影响 —— 且证明验签确实在 ctx 与桶之前（ctx-free 前缀）。
    """
    _fill_verify_bucket()
    with pytest.raises(HTTPException) as ei:
        with totp_mod.interim_session("garbage.not.a.jwt"):
            pass
    assert ei.value.status_code == 401, f"应先验签(401)，实得 {ei.value.status_code}"


# ─── 4. tid 消费：严格类型 + fail-closed（R-10 D9 / D8） ─────────────────


def test_legacy_interim_without_tid_rejected(tmp_db_path):
    """D8：升级前签发的 interim **无 tid** → 401（判别式是 **tid 有无**，不是 ver）。

    用户重登一次即可；`Recreate` 部署下新旧版本不同时 serving ⇒ 无抖动循环（§3.1）。
    """
    with pytest.raises(HTTPException) as ei:
        with totp_mod.interim_session(_mk_interim(tid=None)):
            pass
    assert ei.value.status_code == 401


@pytest.mark.parametrize("bad_tid", ["1", True, 0, -1, 1.0, [1]])
def test_interim_tid_strict_types(tmp_db_path, bad_tid):
    """R-10 D9 严格化：`type(tid) is int and tid > 0`，否则 401。

    - `"1"` → **禁 SQLite 隐式类型转换参与租户解析**（字符串 '1' 在 SQLite 里能匹配整型 1）
    - `True` → `bool` 是 `int` 子类且 `True == 1`，宽松写法会让它当成 tenant#1
    - `0` / `-1` → 非法 id
    """
    with pytest.raises(HTTPException) as ei:
        with totp_mod.interim_session(_mk_interim(tid=bad_tid)):
            pass
    assert ei.value.status_code == 401, f"tid={bad_tid!r} 应被拒"


def test_suspended_tenant_tid_rejected_without_fallback(tmp_db_path):
    """⭐ ③ fail-closed：tid 指向的租户**已停用** → 401，**不回退**到任何默认租户。

    回退 = 静默跨租户供数（OOS-1v2）。本测同时覆盖 B-2（`resolve_tenant_by_id` 必须过滤 status）。
    revert-to-bad：把 ③ 换成 `get_tenant(tid)`（不过滤 status）→ 停用租户被解析出来 → 本测转红。
    """
    from knot.repositories import tenant_repo
    conn = tenant_repo.get_platform_conn()
    conn.execute("UPDATE tenants SET status='suspended' WHERE id=1")
    conn.commit()
    conn.close()
    with pytest.raises(HTTPException) as ei:
        with totp_mod.interim_session(_mk_interim(tid=1)):
            pass
    assert ei.value.status_code == 401


def test_unknown_tenant_tid_rejected(tmp_db_path):
    """③ fail-closed：tid 指向**不存在**的租户 → 401（不回退）。"""
    with pytest.raises(HTTPException) as ei:
        with totp_mod.interim_session(_mk_interim(tid=4242)):
            pass
    assert ei.value.status_code == 401
