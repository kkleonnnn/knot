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


# ─── KnotLogo 精确文件集（R-199.5 更新值 = 5）────────────────────────────

def test_knotlogo_file_set():
    """KnotLogo 精确命中 5 文件：Shared / Shell / Login / Enroll / ForceChangePassword.

    R-199.5（v0.6.4.2 守护者裁定 3→5：Enroll + ForceChangePassword v0.6.2.0 auth 屏采用）。
    第 6 文件混入（如顺手在新屏用 KnotLogo）/ KnotLogo 蒸发 → 红。
    """
    root = Path("frontend/src")
    hits = sorted(
        p.relative_to(root).as_posix()
        for p in root.rglob("*.jsx")
        if "KnotLogo" in p.read_text(encoding="utf-8")
    )
    expected = sorted([
        "Shared.jsx",
        "Shell.jsx",
        "screens/Login.jsx",
        "screens/Enroll.jsx",
        "screens/ForceChangePassword.jsx",
    ])
    assert hits == expected, f"KnotLogo 文件集漂移（R-199.5=5）：实际 {hits} ≠ 预期 {expected}"


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
