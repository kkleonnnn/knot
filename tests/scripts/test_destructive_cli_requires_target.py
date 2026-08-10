"""破坏性 CLI 不得有默认目标 —— #1 事故规则的**同族第二、第三个实例**（v0.9.15 Stage 4 #5）。

═══ 为什么这一条是**本片引起的**，而不是「顺手加固」═══

本片之前，全仓在任何时刻**只可能存在一个租户** ⇒ `resolve_single_tenant()` 这个回退
**无处可错**。本片开始**把新开通的租户开成 `suspended`**（刻意的，见 §1.2）
⇒ 该回退从此**恒解析到起源租户**，而运维此刻心里想的正是那个新租户
⇒ 「动作静默作用在错误的对象上，输出照样说完成」= **与 #1 的事故逐字同形**。

⇒ 故这不是「把规则推广到更多地方」，是**把本片新造出来的危险面堵上**。

═══ 三个实例的处置差异（刻意不一刀切）═══
· `reset_admin_password.py`（#1，事故本体）→ `--tenant` **无条件必填**（该脚本无只读模式）。
· `purge_audit_log.py`（本文件）→ **真跑必填**；`--dry-run` **仍可省** ——
  它 0 副作用（跳过 bak + DELETE），而规则管的是**破坏性动作**；
  且 DEPLOY.md 的诊断范例正是 `--dry-run` 不带目标（**一刀切会破运维手册**）。
  代偿：dry-run 也**打印它解析到了谁** —— 预览若不说自己看的是哪家，同样会误导。
· `migrate_encrypt_v045.py`（本文件）→ 目标 **`required=True` 二选一**
  （`--tenant` / `--all-tenants`）；DEPLOY.md 范例本就带 `--tenant 1` ⇒ 文档零改动（已核）。

═══ oracle 选择（⚠️ 避开「恒定判据」这个第 ③ 种失效）═══
**不能**用「audit_log 行数没变」当零写入的判据 —— retention 只删 N 天前的行，
新建的 tmp 库里**本来就没有**够老的行 ⇒ 真跑也删 0 行 ⇒ 那个判据**恒真**、零判别力。
⇒ 判据取 **`_make_backup()` 的产物**：真跑**无条件**先建一个 `*.audit-purge-*.bak`
（`purge()` 里 `if not dry_run:` 之后第一件事，与删了几行无关）
⇒ 「没有 bak 文件」= 真跑没发生过。配**反向守护**证明它非空判据（带目标真跑 ⇒ bak 真出现）。
"""
from __future__ import annotations

import ast
import os
import pathlib
import subprocess
import sys

import pytest

from knot.repositories import base, tenant_repo

_REPO = pathlib.Path(__file__).resolve().parents[2]


def _run(mod: str, args: list[str]):
    """子进程跑 CLI —— 必须是子进程：`argparse` 的必填校验走 `SystemExit`，
    而**退出码本身**是被守护的性质之一。
    ⚠️ 不经管道读退出码（`cmd | tail` 的 `$?` 是 `tail` 的 —— 本会话踩过三次）。
    """
    env = dict(os.environ)
    env["SQLITE_DB_PATH"] = str(base.SQLITE_DB_PATH)
    return subprocess.run(
        [sys.executable, "-m", mod, *args],
        capture_output=True, text=True, timeout=180, env=env,
        check=False,          # ⚠️ 显式：**非 0 退出码正是本文件要断言的载荷**，不是错误
    )


def _baks() -> list[pathlib.Path]:
    """真跑留下的备份产物（零个 = 真跑没发生）。"""
    root = pathlib.Path(base.SQLITE_DB_PATH).parent
    return sorted(root.rglob("*audit-purge*"))


def _prepare() -> None:
    tenant_repo.init_platform_db()
    tenant_repo.seed_default_tenant()
    base.init_db()


# ══════════════════ purge_audit_log ══════════════════

def test_purge_real_run_without_target_is_refused_with_zero_artifacts(tmp_db_path):
    """⭐ 真跑缺 `--tenant` ⇒ 非 0 退出 + **零产物**（连备份都没建）。

    ⚠️ 两条判据都要（v3.1-B #2「安全属性是什么没发生」）：
    只断非 0 不够 —— 要守的是**没动手**；只断零产物也不够 —— 静默成功正是事故形态。
    """
    _prepare()
    assert not _baks(), "前提：跑之前没有备份产物"

    proc = _run("knot.scripts.purge_audit_log", [])

    assert proc.returncode != 0, (
        f"真跑缺 --tenant 竟然成功（rc={proc.returncode}）—— 破坏性动作有了默认目标。\n"
        f"stdout={proc.stdout!r}\nstderr={proc.stderr!r}"
    )
    assert not _baks(), f"拒绝了却已经动手（留下备份产物 {_baks()}）"
    assert "--tenant" in (proc.stderr + proc.stdout), "拒绝消息没点名缺的是哪个参数"


def test_purge_real_run_with_target_actually_runs(tmp_db_path):
    """⭐ **反向守护 + 证明上一条的判据非空**：带 `--tenant` 真跑 ⇒ rc=0 且 bak **真的**出现。

    没有这条，把脚本写成「一律拒绝」也能让上一条通过 = 功能删掉还绿；
    而且「没有 bak」这个 oracle 若压根产生不了 bak，上一条就是空证明（本弧第 ② 问）。
    """
    _prepare()
    proc = _run("knot.scripts.purge_audit_log", ["--tenant", "1"])

    assert proc.returncode == 0, f"带 --tenant 真跑却失败：{proc.stderr!r}"
    assert _baks(), "真跑没有留下备份产物 —— 那么上一条的『零产物』判据是空的"
    assert "id=1" in proc.stdout, f"真跑前没有打印目标租户：{proc.stdout!r}"


def test_purge_dry_run_without_target_still_works_and_names_the_tenant(tmp_db_path):
    """⭐ `--dry-run` **刻意仍可不带目标**（0 副作用），且必须**说出它看的是谁**。

    ⚠️ 这条是**防过度收紧**：DEPLOY.md 的诊断范例正是不带目标的 `--dry-run`
    ⇒ 一刀切要求 `--tenant` 会破运维手册。
    而预览若不说自己解析到了哪家，运维会把 A 的数字当成 B 的 ⇒ 故同时断言它报了租户。
    """
    _prepare()
    proc = _run("knot.scripts.purge_audit_log", ["--dry-run"])

    assert proc.returncode == 0, f"--dry-run 不带目标被拒了（过度收紧）：{proc.stderr!r}"
    assert not _baks(), "dry-run 竟然建了备份 —— 它应当 0 副作用"
    assert "id=1" in proc.stdout, f"dry-run 没说它解析到了哪个租户：{proc.stdout!r}"


def test_destructive_clis_can_target_a_freshly_provisioned_suspended_tenant(tmp_db_path):
    """⭐ 两个脚本都必须能作用于**刚开通的 `suspended` 租户** —— 那正是本片的主要使用场景。

    **为什么这条不是「顺手加的」**：本片让新租户**恒 `suspended`**（§1.2）
    ⇒ 运维对一个新租户最先要做的事（补迁移旧凭据 / 按合规清审计）**都在它 active 之前**。
    若这两个脚本的解析走 `resolve_*`（只返可服务的），这条路径**结构上到不了**新租户 ——
    而这恰是守护者对 #1 指出的同一个缺陷（「这个恢复路径到不了 suspended 租户」）。

    ⇒ 本测把「用 `get_*` 而非 `resolve_*`」这条**成文命名约定**（`tenant_repo` 里写着）
    变成可执行判据：约定是散文，改错了不会红；这条会。
    取材：把任一脚本的 `get_tenant` 换成 `resolve_tenant`（active-only）⇒ 本测红。
    """
    _prepare()
    from knot.repositories import tenant_provisioning as tp

    out = tp.create_tenant(slug="newco", name="NewCo", allowed_http_hosts="", allowed_webhook_hosts="")
    assert out["tenant"]["status"] == "suspended", "前提：本片开通的新租户恒 suspended"
    tid = str(out["tenant"]["id"])

    p1 = _run("knot.scripts.purge_audit_log", ["--tenant", tid, "--dry-run"])
    assert p1.returncode == 0, (
        f"purge 到不了刚开通的 suspended 租户（rc={p1.returncode}）——\n"
        f"  解析大概走了 `resolve_*`（只返可服务的）而非 `get_*`。stderr={p1.stderr!r}"
    )
    assert f"id={tid}" in p1.stdout, f"没打印目标租户：{p1.stdout!r}"

    p2 = _run("knot.scripts.migrate_encrypt_v045", ["--tenant", tid, "--dry-run"])
    assert p2.returncode == 0, (
        f"迁移脚本到不了刚开通的 suspended 租户（rc={p2.returncode}）——\n"
        f"  而「导入旧库凭据后补跑加密迁移」正是开通后的第一件事。stderr={p2.stderr!r}"
    )

# ══════════════════ migrate_encrypt_v045 ══════════════════

def test_migrate_without_target_is_refused_with_zero_artifacts(tmp_db_path):
    """⭐ 迁移脚本缺目标 ⇒ 非 0 退出（argparse 互斥组 `required=True`）+ 零产物。

    本脚本处理的是**凭据列**（v0.9.11 已加 WAL-safe 备份 + 写前 decrypt preflight）
    ⇒ 作用在错误的库上代价更高。
    """
    _prepare()
    root = pathlib.Path(base.SQLITE_DB_PATH).parent
    before = {p.name for p in root.rglob("*.bak*")}

    proc = _run("knot.scripts.migrate_encrypt_v045", [])

    assert proc.returncode != 0, (
        f"缺目标竟然成功（rc={proc.returncode}）—— 破坏性动作有了默认目标。\n"
        f"stdout={proc.stdout!r}\nstderr={proc.stderr!r}"
    )
    after = {p.name for p in root.rglob("*.bak*")}
    assert after == before, f"拒绝了却已经动手（新增备份 {after - before}）"


def test_migrate_with_explicit_target_still_works(tmp_db_path):
    """**反向守护**：带 `--tenant 1 --dry-run` 仍正常（防「一律拒绝」式假通过）。"""
    _prepare()
    proc = _run("knot.scripts.migrate_encrypt_v045", ["--tenant", "1", "--dry-run"])
    assert proc.returncode == 0, f"带显式目标却失败：{proc.stderr!r}"


def test_migrate_target_group_is_required():
    """⛔ 静态钉住互斥组的 `required=True`（防有人「顺手」改回可选 + 回退默认目标）。

    判据是 **AST**：要问的是「那个 `add_mutually_exclusive_group` 调用的 `required` 是不是 True」，
    文本匹配答不了（`required=True` 会出现在别的参数上，而本文件正**讨论**着这个词）。
    """
    src = (_REPO / "knot/scripts/migrate_encrypt_v045.py").read_text(encoding="utf-8")
    groups = [
        n for n in ast.walk(ast.parse(src))
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        and n.func.attr == "add_mutually_exclusive_group"
    ]
    assert groups, "找不到互斥组 —— 目标参数被重构了？"
    for g in groups:
        req = next((kw.value for kw in g.keywords if kw.arg == "required"), None)
        assert isinstance(req, ast.Constant) and req.value is True, (
            "迁移脚本的目标互斥组不再是 `required=True` ——\n"
            "  ⛔ 无目标会回退『唯一 active 租户』= **起源租户**，而新开通的租户是 suspended\n"
            "     ⇒ 运维想迁新租户、实际重写了部署方自己的凭据列，输出照样报『完成』。\n"
            "  **破坏性工具不得有默认目标。**"
        )


# ══════════════════ 分类哨兵（新脚本必须表态）══════════════════

#: `knot/scripts/` 里**允许**调用 `resolve_single_tenant()` 的脚本 → 理由。
#: ⚠️ 这不是「豁免清单」而是**表态清单**：新脚本若带隐式回退，本测会红，
#: 迫使作者写下「为什么这个回退在破坏性动作上是安全的」。
_IMPLICIT_FALLBACK_OK: dict[str, str] = {
    "purge_audit_log.py":
        "仅 `--dry-run` 路径可达（0 副作用）；真跑由 `--tenant is None and not dry_run` 门拒绝，"
        "且 dry-run 会打印解析到的租户。守护：本文件三条 purge 测。",
    "scan_secrets_at_rest.py":
        "v0.9.12 刻意做成**只读** CLI（无任何写路径）⇒ 回退最坏只是扫错一家、不造成损害。",
}


def test_every_script_with_implicit_tenant_fallback_is_accounted_for():
    """⭐ **新脚本必须表态**：`knot/scripts/` 里凡调用 `resolve_single_tenant()` 的都要在表里有理由。

    ⚠️ 判据是 **AST 按被调名**（R-SENTINEL-AST）—— 文本匹配在这里原理上答不了：
    多个文件（含本文件、含 `reset_admin_password.py` 的事故记录）都在**讨论**这个名字，
    prose 里的反引号会被 tokenizer 剥掉 ⇒ 自匹配。

    ⇒ 失效模式：有人加一个新的破坏性脚本、带上「默认目标」的回退 ——
    本测会红并要求他表态，而不是等下一次事故。
    """
    offenders = {}
    for py in sorted((_REPO / "knot/scripts").glob("*.py")):
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except SyntaxError as e:                      # noqa: PERF203 —— 报清楚是哪个文件读不了
            pytest.fail(f"{py.name} 解析失败（哨兵扫描面不能静默跳过文件）：{e}")
        calls = {
            n.func.id if isinstance(n.func, ast.Name) else getattr(n.func, "attr", None)
            for n in ast.walk(tree) if isinstance(n, ast.Call)
        }
        if "resolve_single_tenant" in calls and py.name not in _IMPLICIT_FALLBACK_OK:
            offenders[py.name] = "调用了 resolve_single_tenant() 但未在表态清单里"

    assert not offenders, (
        "以下脚本有**隐式租户回退**却未表态：\n  "
        + "\n  ".join(f"{k} —— {v}" for k, v in offenders.items())
        + "\n\n⇒ 回退恒解析到『唯一 active 租户』= **起源租户**；本片起新租户开成 suspended"
          "\n   ⇒ 运维想操作新租户、实际作用在部署方自己身上（v0.9.15 Stage 4 #1 的事故形状）。"
          "\n   **破坏性工具不得有默认目标** —— 若确为只读/无害，把理由写进 `_IMPLICIT_FALLBACK_OK`。"
    )


#: 扫描面**派生**（`git ls-files '*.md'`）而非枚举 —— 枚举清单会漂，派生的不会：
#: 新增的活文档自动进扫描面，不必有人记得来加一行。
#: **唯一排除** `docs/plans/**` —— 那是「当时是这样」的留痕，
#: 改它等于篡改历史（同本仓「不动历史」的版本纪律）。
_EXCLUDED_PREFIX = "docs/plans/"


def _tracked_live_docs() -> list[pathlib.Path]:
    out = subprocess.run(
        ["git", "ls-files", "*.md"], cwd=_REPO, capture_output=True, text=True, timeout=60,
        check=False,          # 退出码下一行自己断（要给出「扫描面不能静默变空」这条消息）
    )
    assert out.returncode == 0, f"git ls-files 失败（扫描面不能静默变空）：{out.stderr!r}"
    names = [n for n in out.stdout.splitlines() if n and not n.startswith(_EXCLUDED_PREFIX)]
    assert names, "扫描面为空 —— 派生失败时必须响亮地红，而不是静默通过 0 个文件"
    return [_REPO / n for n in names]

#: 脚本 → 该脚本的调用行**必须**出现其中之一（否则那条命令照抄即被拒）。
_DOC_REQUIRED_FLAGS = {
    "reset_admin_password": ("--tenant",),
    "migrate_encrypt_v045": ("--tenant", "--all-tenants"),
    "purge_audit_log": ("--tenant", "--dry-run"),      # dry-run 允许无目标（0 副作用）
    # ⭐ v0.9.20 P-c：改租户服务状态 —— **两个**参数都必填、都无默认
    # （`--status` 尤其不给默认：「默认激活」是最危险的那个默认）。
    "set_tenant_status": ("--tenant", "--status"),
}


def test_live_docs_do_not_show_commands_that_would_be_refused():
    """⭐ **活文档里的调用范例必须是真能跑的** —— 照抄即被拒的命令是运维陷阱。

    ⚠️ **这条哨兵是「只扫一侧」的直接产物**（v3.1-B #8）：
    修 #1 时我改了脚本、写了测、写了 CHANGELOG —— 却漏了**描述它的地方**：
    `DEPLOY.md` 两处 + `README.md` 一处的 `reset_admin_password` 范例都不带 `--tenant`
    ⇒ 那三条命令在修完的那一刻起就**照抄必被拒**，而四闸门全绿。
    ⇒ **兑现或推翻一个承诺时，要扫两侧：描述它的地方，和断言它的地方。**

    ⚠️ 判据刻意用文本而非 AST（R-SENTINEL-AST 要求写明理由）：
    扫的是 **Markdown 散文里的命令行**，那里没有 AST 可言；
    且「同一行里有没有那个 flag」正是照抄者会遇到的判据本身。
    自匹配风险天然不存在：扫描面只有 `.md`，而本文件是 `.py`。

    ⚠️ 扫描面**派生**自 `git ls-files`，不是枚举清单 —— 后者会漂（新活文档没人记得加）。
    实测切换前后命中集**完全相同**（今天 0 违规）⇒ 零代价、纯赚。
    """
    offenders = []
    for p in _tracked_live_docs():
        name = p.relative_to(_REPO).as_posix()
        for lineno, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            for mod, flags in _DOC_REQUIRED_FLAGS.items():
                if f"knot.scripts.{mod}" in line and not any(f in line for f in flags):
                    offenders.append(
                        f"{name}:{lineno} 的 `{mod}` 范例缺 {'/'.join(flags)} ⇒ 照抄即被拒"
                    )
    assert not offenders, (
        "活文档里有**照抄即被拒**的命令范例：\n  " + "\n  ".join(offenders)
        + "\n\n⇒ 破坏性 CLI 加了必填目标之后，**描述它的地方也要一起改**"
          "（v0.9.15 修 #1 时我恰好漏了这三处 —— 那正是本哨兵存在的原因）。"
    )


def test_the_accounted_for_list_has_no_stale_entries():
    """⚠️ 反向：表态清单里不得有**已经不再需要**的条目（否则清单会祝福不存在的风险）。

    实证价值：本片把 `migrate_encrypt_v045.py` 的回退**物理删掉**了
    ⇒ 它不该出现在清单里；若有人日后把回退加回来又忘了改这里，上一条会红。
    """
    for name in _IMPLICIT_FALLBACK_OK:
        p = _REPO / "knot/scripts" / name
        assert p.exists(), f"表态清单里的 {name} 已不存在 —— 清单过期"
        calls = {
            n.func.id if isinstance(n.func, ast.Name) else getattr(n.func, "attr", None)
            for n in ast.walk(ast.parse(p.read_text(encoding="utf-8"))) if isinstance(n, ast.Call)
        }
        assert "resolve_single_tenant" in calls, (
            f"{name} 已不再有隐式回退，却仍在表态清单里 —— 请删掉该条目"
            "（留着会让清单看起来在管一个不存在的风险）"
        )
