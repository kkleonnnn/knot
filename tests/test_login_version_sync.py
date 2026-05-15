"""tests/test_login_version_sync.py — v0.5.7 R-181 + R-185 守护。

R-181：Login.jsx 页脚版本字符串与 knot.main.app.version 一致（每 PATCH 三处同步）
R-185：Login.jsx 引用 KnotLogo / KnotMark（DOM 哨兵 — 防资产重构后"逻辑蒸发"）

⚠️ 本文件含字面量断言；v0.6.0 单源化后路径含 knot/ 而非旧包名。
"""
from pathlib import Path

# ─── R-181 三处同步守护 ──────────────────────────────────────────────

def test_R181_login_footer_version_synced_with_main():
    """Login.jsx 页脚 `v{version}` 字面必须与 knot.main.app.version 一致。

    每 PATCH 三处同步：knot/main.py + tests/test_rename_smoke.py + Login.jsx 页脚。
    漏一处即此测试挂。
    """
    from knot.main import app

    login_src = Path("frontend/src/screens/Login.jsx").read_text(encoding="utf-8")
    expected = f"v{app.version}"  # 例：v0.5.7

    assert expected in login_src, (
        f"R-181 违规：Login.jsx 页脚必须含字面 {expected!r}（与 FastAPI version 同步）"
    )


# ─── R-185 DOM 资产存在性哨兵 ──────────────────────────────────────

def test_R185_login_renders_knot_logo():
    """Login.jsx 必须含 <KnotLogo 或 <KnotMark JSX 调用（防 v0.5.7 重构后资产"逻辑蒸发"）。

    Shared.jsx 同时必须 export 三件套（KnotMark / KnotWordmark / KnotLogo）。
    """
    login_src = Path("frontend/src/screens/Login.jsx").read_text(encoding="utf-8")
    shared_src = Path("frontend/src/Shared.jsx").read_text(encoding="utf-8")

    assert ("<KnotLogo" in login_src) or ("<KnotMark" in login_src), (
        "R-185 违规：Login.jsx 必须含 <KnotLogo 或 <KnotMark JSX 调用"
    )

    for name in ("KnotMark", "KnotWordmark", "KnotLogo"):
        assert f"export function {name}(" in shared_src, (
            f"R-185 违规：Shared.jsx 必须 export {name}"
        )


# ─── v0.6.0.8 KNOW-1: README 顶部版本同步守护 ────────────────────────

def test_readme_top_version_synced_with_main():
    """README 顶部 `当前版本 vX.Y.Z` 必须与 knot.main.app.version 一致。

    v0.5.0~v0.6.0.6 期间漏了 8 个 PATCH 未同步（README 仍标 v0.5.44），
    导致内测人员看 README 觉得"还在 v0.5"不知道新功能。本守护防再漂。
    """
    from knot.main import app

    readme = Path("README.md").read_text(encoding="utf-8")
    expected = f"v{app.version}"  # 例：v0.6.0.8

    assert expected in readme[:1000], (
        f"v0.6.0.8 KNOW-1 违规：README 顶部 1000 字符内必须含字面 {expected!r}（与 FastAPI version 同步）；"
        f"实际首 200 字符:\n{readme[:200]}"
    )
