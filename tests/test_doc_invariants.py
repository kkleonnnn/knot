"""tests/test_doc_invariants.py — v0.6.4.11 task #44 doc-不变量 CI 守护一揽子.

元教训：doc 宣称的不变量（版本字面 / 文件集 / CHANGELOG）无 CI 强制 → 跨 PATCH 静默 drift
（8 stale-doc 数据点，PRIMARY = Shell sidebar version stale v0.6.4.2 drift 8 PATCH）。

本文件补 3 个 grounded 缺口（守护者 grounded 清单）；现有守护勿重造（奥卡姆）：
- R-72 main.py version → tests/test_rename_smoke.py
- R-181 Login footer + R-185 KnotLogo DOM + KNOW-1 README → tests/test_login_version_sync.py
- Foundation additive → tests/test_foundation_additive.py
"""
import re
from pathlib import Path


def _main_version():
    from knot.main import app
    return app.version


# ─── PRIMARY: 前端版本单一真相源 bridge（Shell drift 8 PATCH 根治）──────────

def test_app_version_synced_with_main():
    """frontend/src/version.js APP_VERSION === knot.main.app.version.

    Shell sidebar + Login footer 读 {APP_VERSION}（不再硬编）→ 本 bridge 保前端版本不 drift。
    改 main.py 不改 version.js（或反之）即红 —— 根治 v0.6.4.2 stale 8 PATCH 的条件式同步缺陷。
    """
    src = Path("frontend/src/version.js").read_text(encoding="utf-8")
    m = re.search(r"APP_VERSION\s*=\s*['\"]([^'\"]+)['\"]", src)
    assert m, "version.js 须 export const APP_VERSION = '...'"
    assert m.group(1) == _main_version(), (
        f"前端 version.js APP_VERSION={m.group(1)!r} ≠ main.py version={_main_version()!r}（版本 drift）"
    )


def test_shell_sidebar_renders_app_version():
    """Shell.jsx sidebar 渲染 `v{APP_VERSION}`（非硬编 version 字面）+ import version.js.

    断言渲染引用（非仅 import）→ 与 bridge 组合 ⟹ sidebar = main version。
    防 v0.6.4.2 式硬编 stale 复发。
    """
    src = Path("frontend/src/Shell.jsx").read_text(encoding="utf-8")
    assert "v{APP_VERSION}" in src, "Shell.jsx sidebar 须渲染 v{APP_VERSION}（version.js 单一真相源）"
    assert "version.js" in src, "Shell.jsx 须 import APP_VERSION from version.js"
    assert not re.search(r">v\d+\.\d+\.\d+", src), "Shell.jsx 不得含硬编 version 字面（>vN.N.N）"


# ─── KnotLogo 渲染集（精确 4 渲染；Shared 定义归 R-185）──────────────────

def test_knotlogo_file_set():
    """`<KnotLogo` JSX 渲染精确命中 4 文件：Shell / Login / Enroll / ForceChangePassword.

    v0.6.4.12 收紧：子串 `"KnotLogo"` → `"<KnotLogo"`（仅渲染引用计入）。
    Shared.jsx 仅 `export function KnotLogo` 定义（0 渲染），由 R-185
    （test_login_version_sync）守护 → 收紧不丢守护，消注释/字符串 false-red。
    R-199.5：KnotLogo 共 5 文件 = 4 渲染（本 guard）+ 1 Shared 定义（R-185）。
    第 5 渲染文件混入（如顺手在新屏用）/ 任一渲染蒸发 → 红。
    """
    root = Path("frontend/src")
    hits = sorted(
        p.relative_to(root).as_posix()
        for p in root.rglob("*.jsx")
        if "<KnotLogo" in p.read_text(encoding="utf-8")
    )
    expected = sorted([
        "Shell.jsx",
        "screens/Login.jsx",
        "screens/Enroll.jsx",
        "screens/ForceChangePassword.jsx",
    ])
    assert hits == expected, f"KnotLogo 渲染集漂移（R-199.5 渲染=4）：实际 {hits} ≠ 预期 {expected}"


# ─── CHANGELOG 顶部 version 同步（漏条目 / stale → 红）────────────────────

def test_changelog_top_version_synced_with_main():
    """CHANGELOG 首个 `## [` 条目 header 含 `v{main.py version}`.

    防 v0.6.4.1.1 式漏 CHANGELOG 条目 / 顶部 stale（8 数据点之一）。
    """
    lines = Path("CHANGELOG.md").read_text(encoding="utf-8").splitlines()
    top = next((ln for ln in lines if ln.startswith("## [")), None)
    assert top, "CHANGELOG 无 `## [` 条目"
    expected = f"v{_main_version()}"
    assert expected in top, f"CHANGELOG 顶部条目不含 {expected!r}（版本 stale / 漏条目）；实际：{top!r}"


# ─── CHANGELOG 单一 [Unreleased]（历史漏 demote → stale 堆积 → 红）──────────

def test_changelog_single_unreleased():
    """CHANGELOG 恰有 1 个 `## [Unreleased]`（仅当前在飞 PATCH）。

    元教训 #5：约定 = 在飞 `[Unreleased] - vX`、已发 demote `[Released] - vX`；
    历史漏 demote → stale [Unreleased] 堆积（v0.6.4.12 实查 41 条全史 relabel）。
    count==1 防再 drift：每 PATCH 须 demote 上一 top + 新 top 唯一。
    """
    text = Path("CHANGELOG.md").read_text(encoding="utf-8")
    n = len(re.findall(r"^## \[Unreleased\]", text, flags=re.MULTILINE))
    assert n == 1, f"CHANGELOG `## [Unreleased]` 应恰 1 个（当前在飞）；实际 {n}（历史漏 demote → stale 堆积）"
