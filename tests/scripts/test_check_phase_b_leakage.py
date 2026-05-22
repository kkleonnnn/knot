"""v0.6.0.22 — scripts/check_phase_b_leakage.py 守护测试。

R-PA-8 工具加固验证。覆盖：
- PHASE_B_LITERAL_TERMS 字面分割构造（R-PA-14 自指环）
- PHASE_B_DOC_GLOBS 完整性（v0.6.2 ~ v0.6.9 + v0.7.*）
- EXCLUDE_RE 豁免规则（phase-b-* 通配 + v0.6.0.x LOCKED + CLAUDE.md / README.md / 自身）
- --self-test mode subprocess 调用正常退出 0
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent


def test_phase_b_literal_terms_split_construction():
    """v0.6.0.22 — PHASE_B_LITERAL_TERMS 必须用字面分割构造（R-PA-14 自指环避免）。"""
    from scripts.check_phase_b_leakage import PHASE_B_LITERAL_TERMS

    # 验证 5 项字面齐全（拼接结果）
    expected = {"multi-tenant", "logicform", "semantic_layer_v2",
                "phase_b_started", "phase-b-started"}
    actual = set(PHASE_B_LITERAL_TERMS)
    assert actual == expected, f"应有 5 项字面：{expected}；实际 {actual}"


def test_phase_b_doc_globs_covers_v062_to_v069():
    """v0.6.0.22 — PHASE_B_DOC_GLOBS 覆盖 v0.6.2 ~ v0.6.9（防 PATCH 号跳跃绕过）。"""
    from scripts.check_phase_b_leakage import PHASE_B_DOC_GLOBS

    for minor in range(2, 10):  # 2..9
        expected_glob = f"docs/plans/v0.6.{minor}-*.md"
        assert expected_glob in PHASE_B_DOC_GLOBS, (
            f"PHASE_B_DOC_GLOBS 应含 {expected_glob}（v0.6.0.22 加固防跳号绕过）"
        )

    # v0.7.* 仍保留
    assert "docs/plans/v0.7.*-*.md" in PHASE_B_DOC_GLOBS


def test_exclude_re_phase_b_wildcard():
    """v0.6.0.22 — EXCLUDE_RE 豁免 phase-b-* 通配（不只 phase-b-proposal-draft.md）。"""
    from scripts.check_phase_b_leakage import EXCLUDE_RE

    # phase-b-proposal-draft.md 仍豁免（既有）
    assert EXCLUDE_RE.search("docs/plans/phase-b-proposal-draft.md")
    # phase-b-early-review-2026-05-21.md 也豁免（v0.6.0.22 新加）
    assert EXCLUDE_RE.search("docs/plans/phase-b-early-review-2026-05-21.md")
    # 任何 phase-b-* 命名都豁免
    assert EXCLUDE_RE.search("docs/plans/phase-b-locked.md")


def test_exclude_re_v060x_locked_manuals():
    """v0.6.0.22 — EXCLUDE_RE 豁免 v0.6.0.x-* LOCKED 手册（hotfix / micro PATCH）。"""
    from scripts.check_phase_b_leakage import EXCLUDE_RE

    # 已知 LOCKED 手册
    assert EXCLUDE_RE.search("docs/plans/v0.6.0.1-locked.md")
    assert EXCLUDE_RE.search("docs/plans/v0.6.0.2-locked.md")
    # 任意 v0.6.0.x 都豁免（防未来加号时漏豁免）
    assert EXCLUDE_RE.search("docs/plans/v0.6.0.99-hotfix.md")
    assert EXCLUDE_RE.search("docs/plans/v0.6.0.19-desensitize-3-3-locked.md")


def test_exclude_re_governance_docs():
    """v0.6.0.22 — EXCLUDE_RE 豁免治理 docs（CHANGELOG / CLAUDE.md / README.md）。"""
    from scripts.check_phase_b_leakage import EXCLUDE_RE

    assert EXCLUDE_RE.search("CHANGELOG.md")
    assert EXCLUDE_RE.search("CLAUDE.md")
    assert EXCLUDE_RE.search("README.md")


def test_exclude_re_self_and_test_self():
    """v0.6.0.22 — EXCLUDE_RE 豁免本工具自身 + 守护测试自身（R-PA-14 自指环）。"""
    from scripts.check_phase_b_leakage import EXCLUDE_RE

    assert EXCLUDE_RE.search("scripts/check_phase_b_leakage.py")
    assert EXCLUDE_RE.search("tests/scripts/test_check_phase_b_leakage.py")


def test_self_test_subprocess_exits_zero():
    """v0.6.0.22 — `python3 scripts/check_phase_b_leakage.py --self-test` 退出 0。

    这是 Codex §APPENDIX D R-PA-8 自验 gate 的可执行守护。
    """
    result = subprocess.run(
        [sys.executable, "scripts/check_phase_b_leakage.py", "--self-test"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,  # 自验失败时由本测试断言报告，不抛 CalledProcessError
    )
    assert result.returncode == 0, (
        f"--self-test 应退出 0；实际 {result.returncode}\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    # 输出应包含 PASS
    assert "PASS" in result.stdout
    assert "9/9" in result.stdout, "应有 9 个用例通过"
