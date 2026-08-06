"""v0.9.15 commit 4：`tenant_provisioning.create_tenant` 承重测。

覆盖 Stage 1' 的三条承重设计 + 守护者四问的裁定：
- §1.1 `db_dir` 服务端生成的不透明串（**不派生自 slug**）
- §1.2 幂等/续做四分支（判据 = **库文件是否存在**）
- §1.3 第二个 ctx 生产者 ⇒ **ctx 绝不泄漏**（成功 + 异常两条路径）
- Q1 `token_hex` 纯小写 hex ⇒ 对大小写不敏感文件系统结构性免疫
- Q2「库已存在则不续做」= 唯一不猜的分支
- Q3 ctx 判据用**直接比对 contextvar**，不用「后续请求」
"""

from __future__ import annotations

import re

import bcrypt
import pytest

from knot.core import tenant_context as tc
from knot.repositories import base, tenant_repo
from knot.repositories import tenant_provisioning as tp

_HOSTS = "api.example.com"


def _audit_rows():
    conn = tenant_repo.get_platform_conn()
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM platform_audit ORDER BY id")]
    finally:
        conn.close()


# ── §1.1 db_dir：服务端生成、不透明、不派生自 slug ────────────────────────

def test_db_dir_is_opaque_lowercase_hex_and_not_derived_from_slug(tmp_db_path):
    """`db_dir` 必须是 `tenants/<小写 hex>`，且**与 slug 无关**。

    ⭐ 草案曾提案 `tenants/<slug>`，被 Stage 3 判 blocking：`slug` 由调用方传且**零格式校验**
    ⇒ 「服务端派生」是空的（`slug='../evil'` 会把主库路径逃逸经 API 复现）。
    ⭐ 纯小写 hex 还顺带关掉一个洞（守护者 Q1）：macOS/Windows 文件系统**大小写不敏感**，
    而 SQLite `UNIQUE(slug)` **大小写敏感** ⇒ `AcmeCo` 与 `acmeco` 会是两个租户**共用一个目录**。
    """
    out = tp.create_tenant(slug="acmeco", name="Acme", allowed_http_hosts=_HOSTS)
    db_dir = out["tenant"]["db_dir"]

    assert re.fullmatch(r"tenants/[0-9a-f]{16}", db_dir), (
        f"db_dir={db_dir!r} 不是 `tenants/<16 位小写 hex>` —— "
        "不透明性/大小写免疫性任一条被破坏都会让文件边界失效。"
    )
    assert "acmeco" not in db_dir.lower(), "db_dir 含 slug 片段 ⇒ 它又变成调用方可影响的了"

    # ⭐⭐ **结构级判据**（v3.1-B #7「顶班」）：d2'' 的 slug 校验会**替本测挡住**恶意 slug
    # ⇒ 若只靠「传个恶意 slug 看 db_dir」，`_new_db_dir` 退化成派生式时**没人会红**。
    # ⇒ 独立断言它**根本不接受任何输入** —— slug 影响不了它，是**构造上**不可能，而非碰巧。
    import inspect
    assert list(inspect.signature(tp._new_db_dir).parameters) == [], (
        "`_new_db_dir` 开始接受参数了 —— 那意味着 `db_dir` 又变成**可被输入影响**的了。\n"
        "  ⇒ 它必须是零输入的服务端生成；调用方对它的影响面应当是**空**。"
    )


def test_hostile_slug_cannot_reach_the_filesystem(tmp_db_path):
    """`slug='../evil'` 也只能得到不透明 `db_dir`，且数据根外**零产物**。

    ⚠️ 属性是「什么没发生」⇒ **无条件**断言数据根外为空，不依赖「抛没抛异常」。

    ⚠️ **v0.9.15 Stage 4 #2 之后本测的门变早了**：d2'' 的 slug 校验现在**先**拒掉 `../evil`
    ⇒ 本测不再能测到「万一它过了，`db_dir` 也不受它影响」那一层深度。
    ⇒ **那一层改由上一条测的「`_new_db_dir` 零参数」结构断言守**（两层各自独立，见 v3.1-B #7 顶班）。
    本测保留的性质是：**恶意 slug 一路下来，数据根外零产物**（无论被哪一层挡住）。
    """
    root = base._tenant_db_path().parent.resolve()      # autouse tenant#1，db_dir='.' ⇒ 数据根
    raised = None
    try:
        tp.create_tenant(slug="../evil", name="X", allowed_http_hosts="")
    except Exception as e:                              # noqa: BLE001 —— 属性断言必须无条件执行
        raised = e
    # ① 真属性（**无条件**）：数据根外零产物
    assert not (root.parent / "evil").exists(), "数据根外出现了 evil —— 恶意 slug 摸到了文件系统"
    # ② 其次才是「被挡住了、且说得清」
    assert raised is not None, "`../evil` 竟被接受"
    assert "不合法" in str(raised), f"拒绝了但消息不可操作：{raised!r}"


# ── §1.3 ctx 绝不泄漏（Q3：直接比对 contextvar，成功 + 异常两条路径）────────

def test_ctx_is_restored_exactly_on_success(tmp_db_path):
    """成功路径：调用前后 `_active_tenant_ctx` **逐字相等**。

    ⚠️ **判据刻意不是「后续请求看到的 ctx」**（守护者 Q3）：本仓 conftest 有 autouse 的
    tenant#1 ctx，且中间件每请求自己 set ⇒ 泄漏会被**掩盖**（v0.9.4 记过的盲区）。
    """
    before = tc._active_tenant_ctx.get()
    tp.create_tenant(slug="t-ok", name="OK", allowed_http_hosts=_HOSTS)
    assert tc._active_tenant_ctx.get() == before, "成功路径后 ctx 未复原 —— 第二个生产者泄漏了"


def test_ctx_is_restored_exactly_on_exception(tmp_db_path, monkeypatch):
    """⭐ 异常路径：建库中途炸掉时 ctx 也必须复原。

    这是 §1.3 里**最静默**的一处（守护者点名）：建库那步跑在一个从 **suspended 行**造出来的
    ctx 里；若中途失败而未 reset，后续请求会带着一个**不可服务租户**的 ctx。
    """
    before = tc._active_tenant_ctx.get()

    def _boom():
        raise RuntimeError("建库中途炸了")

    monkeypatch.setattr(base, "init_db", _boom)
    with pytest.raises(RuntimeError, match="建库中途炸了"):
        tp.create_tenant(slug="t-boom", name="Boom", allowed_http_hosts=_HOSTS)

    assert tc._active_tenant_ctx.get() == before, (
        "异常路径后 ctx 未复原 —— 后续请求会带着一个不可服务租户的 ctx（fail-closed 被虚化）"
    )


def test_failed_db_build_leaves_the_discoverable_state(tmp_db_path, monkeypatch):
    """⭐ §2-10 的顺序性质：建库失败后「**行在 + 审计有记录 + 库没建**」。

    这正是「不选策略、选留痕的失败模式」要的形状 —— 而 §1.2 的续做分支据此可重试。
    """
    monkeypatch.setattr(base, "init_db", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    with pytest.raises(RuntimeError):
        tp.create_tenant(slug="t-half", name="Half", allowed_http_hosts=_HOSTS)

    row = tenant_repo.get_tenant_by_slug("t-half")
    assert row is not None, "行不在 ⇒ 失败没留痕，运维无从发现"
    assert row["status"] == "suspended"
    assert any(a["tenant_slug"] == "t-half" for a in _audit_rows()), "审计无记录 ⇒ 同事务性质破了"
    assert not tp._tenant_db_exists(row), "库竟已建好 —— 与本测前提矛盾"


# ── §1.2 四分支 ───────────────────────────────────────────────────────────

def test_resume_when_row_exists_but_db_missing(tmp_db_path, monkeypatch):
    """有行 + suspended + **库不存在** → 续做，且返回**全新**口令（库是全新的）。

    ⛔⛔ **绝不能用 `monkeypatch.undo()` 来「只撤掉我这一个补丁」** ——
    `monkeypatch` 是**函数级共享**的 fixture，`undo()` 会把 **`tmp_db_path` 打的
    `SQLITE_DB_PATH` 补丁一起撤掉** ⇒ 后续调用打到**真实的 `knot/data/platform.db`**。
    实测代价：本测初版据此在**真库**里建了一行 `t-resume` 租户 + 一个真实的租户目录
    （靠 `status='suspended'` 才没把线上打挂 —— active 数仍是 1，R-T-GATE 未触发）。
    ⇒ 要「先失败再成功」，用**按调用次数**失败的 stub，不要 `undo()`。
    """
    _calls = {"n": 0}
    _real_init = base.init_db

    def _flaky_init():
        _calls["n"] += 1
        if _calls["n"] == 1:
            raise RuntimeError("boom")
        return _real_init()

    monkeypatch.setattr(base, "init_db", _flaky_init)

    with pytest.raises(RuntimeError, match="boom"):
        tp.create_tenant(slug="t-resume", name="R", allowed_http_hosts=_HOSTS)

    out = tp.create_tenant(slug="t-resume", name="R", allowed_http_hosts=_HOSTS)
    assert out["resumed"] is True
    assert out["initial_password"]
    assert tp._tenant_db_exists(out["tenant"]), "续做后库仍不存在"


def test_refuse_when_row_and_db_both_exist(tmp_db_path):
    """有行 + suspended + **库已存在** → 拒绝，且消息指向一条**真能走的**出口。

    ⚠️ Q2：此时无法区分「建库后被中断」与「真实在用但被停用的租户」
    ⇒ 续做会重置一个**可能在用**的租户的凭据 ⇒ 拒绝是**唯一不猜的**分支。
    """
    tp.create_tenant(slug="t-dup", name="D", allowed_http_hosts=_HOSTS)
    with pytest.raises(tp.TenantProvisioningError) as ei:
        tp.create_tenant(slug="t-dup", name="D", allowed_http_hosts=_HOSTS)
    msg = str(ei.value)
    assert "不续做" in msg
    assert "reset_admin_password" in msg and "--tenant" in msg, (
        f"拒绝消息没给出可走的恢复出口：\n{msg}"
    )


def test_refuse_active_tenant(tmp_db_path):
    """有行 + **active** → 拒绝（不碰在服务的租户）。"""
    with pytest.raises(tp.TenantProvisioningError, match="正在服务中"):
        tp.create_tenant(slug="default", name="X", allowed_http_hosts=_HOSTS)   # tenant#1 是 active


# ── status / 口令 / 审计 ──────────────────────────────────────────────────

def test_new_tenant_is_suspended_and_invisible_to_both_resolvers(tmp_db_path):
    """⭐ **行为级**断言（不只断 status 字面）：新租户对**请求路径**与**登录路径**都不可见。

    只断 `status == 'suspended'` 表示不了「解析器是否真的过滤」——
    而那两条解析器才是 R-T-GATE 与登录的实际入口。
    """
    out = tp.create_tenant(slug="t-hidden", name="H", allowed_http_hosts=_HOSTS)
    tid = out["tenant"]["id"]

    assert out["tenant"]["status"] == "suspended"
    assert tenant_repo.resolve_tenant_by_id(tid) is None, "请求路径能解析到 suspended 租户"
    assert tenant_repo.resolve_tenant_by_slug("t-hidden") is None, "登录路径能解析到 suspended 租户"
    assert tenant_repo.get_tenant(tid) is not None, "get_* 应当仍能取到（它刻意不过滤）"


def test_initial_password_actually_works_and_forces_change(tmp_db_path):
    """⭐ **反向守护**：返回的口令**真的**是那个租户 admin 的口令，且 `must_change_password=1`。

    没有这条，「一律拒绝/随便写个哈希」也能让上面各条通过 = 把功能删掉还绿。
    """
    out = tp.create_tenant(slug="t-pwd", name="P", allowed_http_hosts=_HOSTS)
    tok = tc.set_active_tenant(out["tenant"])
    try:
        conn = base.get_conn()
        row = conn.execute(
            "SELECT password_hash, must_change_password FROM users WHERE username='admin'"
        ).fetchone()
        conn.close()
    finally:
        tc.reset_active_tenant(tok)

    assert row is not None, "新租户库里没有 admin"
    assert bcrypt.checkpw(out["initial_password"].encode(), row["password_hash"].encode()), (
        "返回的初始口令**对不上**库里的哈希 —— 运维拿到的口令登不进去"
    )
    assert row["must_change_password"] == 1


def test_two_tenants_get_different_initial_passwords(tmp_db_path):
    """⭐ kk② 的正面证明：两个租户的初始口令**不同**（全局共享口令是被消除的那个东西）。"""
    a = tp.create_tenant(slug="t-a", name="A", allowed_http_hosts=_HOSTS)
    b = tp.create_tenant(slug="t-b", name="B", allowed_http_hosts=_HOSTS)
    assert a["initial_password"] != b["initial_password"]
    assert a["tenant"]["db_dir"] != b["tenant"]["db_dir"]


def test_initial_password_never_lands_in_audit(tmp_db_path):
    """口令**绝不**进平台审计（`GET /api/platform/audit` 会返回 detail）。"""
    out = tp.create_tenant(slug="t-secret", name="S", allowed_http_hosts="internal.corp")
    pwd = out["initial_password"]
    blob = "\n".join(str(a) for a in _audit_rows())
    assert pwd not in blob, "初始口令泄漏进了平台审计"
    assert "internal.corp" not in blob, (
        "allowed_http_hosts 的**内容**泄漏进了审计 —— 那是部署方内网主机清单（v0.9.8 已立禁令）"
    )


def test_allowed_http_hosts_empty_string_is_preserved_not_nulled(tmp_db_path):
    """`''` 必须原样存下 —— v0.9.7 三态里它是「部署方明确的**禁**」，与 `NULL`（未配置）不同。"""
    out = tp.create_tenant(slug="t-deny", name="D", allowed_http_hosts="")
    assert out["tenant"]["allowed_http_hosts"] == "", (
        "空串被写成了 NULL ⇒ 「明确禁止」被静默变成「未配置」（起源租户会回退 env）"
    )


# ── d2''：slug 格式校验（v0.9.15 Stage 4 #2）───────────────────────────────

@pytest.mark.parametrize("bad", [
    "Acme",             # ⭐ 大写 —— 决定性理由：UNIQUE 区分大小写而登录链接肉眼相同
    "ACME",
    "a",                # 太短（<2）
    "a" * 32,           # 太长（>31）
    "-acme",            # 首字符不能是 `-`
    "ac me",            # 空格
    "ac/me",            # `/` —— 它进 URL
    "ac&me", "ac#me",
    "会员",              # 非 ASCII（slug 是 URL 组件，须转写）
    "../evil",          # 路径穿越形态（隔离性质已由不透明 db_dir 兜住，但仍不该收）
])
def test_d2pp_invalid_slug_is_refused(bad, tmp_db_path):
    """非法 slug ⇒ 拒绝，且**零副作用**（不建行、不建库）。

    ⭐ **仅小写的决定性理由是大小写，不是整洁**（守护者 Q4）：SQLite `UNIQUE` 对 TEXT
    **区分**大小写 ⇒ `Acme` 与 `acme` 会是**两个租户**，而登录链接 `?c=Acme` / `?c=acme`
    **肉眼完全一样** ⇒ 混淆/钓鱼面。
    ⚠️ 这一半与不透明 `db_dir` 关掉的那一半是**两个**洞 —— 一条论证只关得掉一个
    （Stage 4 #2：我此前把「大小写」那条论证当成两个洞都关了）。
    """
    n_before = len(tenant_repo.list_tenants())
    with pytest.raises(tp.TenantProvisioningError, match="不合法"):
        tp.create_tenant(slug=bad, name="X", allowed_http_hosts="")
    assert len(tenant_repo.list_tenants()) == n_before, f"非法 slug {bad!r} 仍建了行"


@pytest.mark.parametrize("ok", ["ac", "acme", "acme-inc", "a1", "x9-y8-z7", "a" + "b" * 30])
def test_d2pp_valid_slug_is_accepted(ok, tmp_db_path):
    """⭐ **反向守护**：合法 slug 必须**过** —— 否则「一律拒绝」也能让上面那组通过。"""
    out = tp.create_tenant(slug=ok, name="X", allowed_http_hosts="")
    assert out["tenant"]["slug"] == ok


def test_d2pp_regex_is_a_single_source_of_truth():
    """⭐ API 层的 `Field(pattern=…)` 必须**引用**写口那个正则，不得自带一份字面。

    ⚠️ 本仓形状：「一个谓词、多个执行点」是**正确的**；「多份判断」才是 N 份清单病。

    ⚠️⚠️ **本测初版的判据锚在一个名字上（`pa._SLUG_PATTERN is …`），那是错的** ——
    我随后把那个别名改成限定名 `tenant_provisioning.SLUG_PATTERN`（为挤 size gate），
    **正则依然是单一真相源，而测红了** ⇒ 它测的是「叫什么」而不是「是不是一份」。
    同一轮里第二次撞上同一形状：**判据要锚在性质上，不是锚在名字/写法上**。
    且初版第二条断言 `SLUG_PATTERN in pats` 是**相等**比较 ⇒ 抄一份一模一样的字面**照样绿**。

    ⇒ 改双判据：
    ① **AST**（与名字无关）：`pattern=` 的实参必须是**引用**（`Name`/`Attribute`），
       ⛔ 不得是字符串常量 —— 抄字面即红，无论抄得多像。
    ② **行为**：构建出的字段上挂的 pattern 与 `tp.SLUG_PATTERN` 相等（引用指错常量即红）。
    """
    import ast
    import pathlib

    from knot.api import platform_admin as pa

    # ① AST：找 `slug: str = Field(pattern=<expr>)` 的那个 <expr>
    src = pathlib.Path(pa.__file__).read_text(encoding="utf-8")
    found = []
    for node in ast.walk(ast.parse(src)):
        if not (isinstance(node, ast.AnnAssign) and getattr(node.target, "id", None) == "slug"):
            continue
        call = node.value
        if isinstance(call, ast.Call):
            for kw in call.keywords:
                if kw.arg == "pattern":
                    found.append(kw.value)
    assert found, "`platform_admin` 里没有任何 `slug: … = Field(pattern=…)`（d2'' 校验点消失了？）"
    for expr in found:
        assert not isinstance(expr, ast.Constant), (
            f"API 层把 slug 正则写成了**字面常量** {expr.value!r} —— 那就是第二份判断，"
            "必然与写口漂开。必须引用 `tenant_provisioning.SLUG_PATTERN`。"
        )
        assert isinstance(expr, ast.Name | ast.Attribute), (
            f"`pattern=` 实参形态意外（{type(expr).__name__}）—— 本测只认「引用单一真相源」这一种写法"
        )

    # ② 行为：字段上真的挂着那个正则
    field = pa.TenantCreateRequest.model_fields["slug"]
    pats = [getattr(m, "pattern", None) for m in field.metadata]
    assert tp.SLUG_PATTERN in pats, f"slug 字段没挂上写口那个 pattern：{pats}"
