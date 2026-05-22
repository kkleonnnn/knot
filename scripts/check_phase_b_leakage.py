#!/usr/bin/env python3
"""scripts/check_phase_b_leakage.py — v0.6.0.1 R-PA-8 内测期 Phase B 准备性 commit 守护。

LOCKED §3 R-PA-5 + R-PA-8 联合守护：R-PA-5 内测期（Day 0~28）严禁 Phase B 准备性
commit。本工具扫 main 分支（默认）或当前工作目录字面，命中即 exit 1。

v0.6.0.22 加固（Codex §APPENDIX D R-PA-8 自验 gate — v0.6.2.0 启动闸门之一）：
- 加 --self-test mode：构造合成 positive/negative 用例验证检测函数行为
- EXCLUDE_RE 扩 docs/plans/phase-b-*.md（豁免合法 phase-b-* 命名 docs）
- PHASE_B_DOC_GLOBS 扩 v0.6.4-* ~ v0.6.9-*（防 PATCH 号跳跃绕过）
- 加单元测试：tests/scripts/test_check_phase_b_leakage.py

检测对象（字面分割构造避免自指环 — R-PA-14）：
1. 文件存在：docs/plans/v0.6.1-*.md / docs/plans/v0.7.x-*.md（Phase B 规划文档落地）
2. 字面命中：
   - "multi" + "-tenant"（OOS-1 多租户）
   - "logic" + "form"（Phase B 提案核心组件）
   - "semantic" + "_layer_v2"（5 层语义建模）
   - "phase_b_started" / "phase-b-started"（启动 marker）
3. Schema 列字面（DB migration 准备性内容）：
   - `users.project_id`
   - `users.tenant_id`
   - `users.organization_id`

豁免（不构成 Phase B 准备性）：
- docs/plans/phase-b-proposal-draft.md（提案草案 — Day 28+ 三方会议评估材料，**非启动**）
- docs/plans/v0.6.0.1-locked.md（当前 micro PATCH LOCKED 手册）
- 历史治理档案（docs/plans/v0.4.*.md / docs/plans/v0.5.*.md / docs/plans/v0.6.0-*.md）
- CHANGELOG.md（含撤回声明 + 历史；可能引用 Phase B 词汇但非准备性）
- 本工具自身（R-PA-14 自指环豁免）

执行：python3 scripts/check_phase_b_leakage.py [--strict]
退出码：0 = 干净 / 1 = 命中 Phase B 准备性内容

资深架构师拍板回滚：若 main 分支命中 → alert + 触发 hard reset 或 revert commit
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# 字面分割构造（R-PA-14 自指环避免 — 本脚本自己不被这些字面命中）
PHASE_B_LITERAL_TERMS = [
    "multi" + "-tenant",
    "logic" + "form",
    "semantic" + "_layer_v2",
    "phase" + "_b_started",
    "phase" + "-b-started",
]

# Phase B 准备性 Schema 列字面（DB migration 准备性内容）
PHASE_B_SCHEMA_COLUMNS = [
    "users." + "project_id",
    "users." + "tenant_id",
    "users." + "organization_id",
]

# Phase B 准备性文档文件 glob（落地即触发 alert）
# v0.6.1 R-PA-PB-7：v0.6.1-* 从 PHASE_B_DOC_GLOBS 移除（已合法启动），
#   保留 v0.6.2+ / v0.7+ 继续防御后续准备性内容
# v0.6.0.22 加固：扩 v0.6.4 ~ v0.6.9（防 PATCH 号跳跃绕过 — 攻击者可故意跳号）
PHASE_B_DOC_GLOBS = [
    "docs/plans/v0.6.2-*.md",
    "docs/plans/v0.6.3-*.md",
    "docs/plans/v0.6.4-*.md",
    "docs/plans/v0.6.5-*.md",
    "docs/plans/v0.6.6-*.md",
    "docs/plans/v0.6.7-*.md",
    "docs/plans/v0.6.8-*.md",
    "docs/plans/v0.6.9-*.md",
    "docs/plans/v0.7.*-*.md",
]

# 扫描范围（与 audit_ohx_leakage R-PA-6 一致）
INCLUDE_GLOBS = [
    "knot/**/*.py",
    "tests/**/*.py",
    "scripts/**/*.py",
    "frontend/src/**/*.{jsx,js,ts,tsx}",
    "docs/plans/**/*.md",
    ".env.example",
    "Dockerfile",
    "pyproject.toml",
]
# 注：CLAUDE.md / README.md 不在 INCLUDE_GLOBS（用户文档；可含 OOS-1~15 路线图引用）— R-PA-6.2 模式

# 豁免：治理档案 + 提案草案 + 本工具 + 自动重建 + 用户文档（CLAUDE.md 含路线图引用 OOS）
# v0.6.1 R-PA-PB-7：v0.6.1 已正式启动（Phase B 决议 B 修订版首个 PATCH），LOCKED 手册不属准备性内容
# v0.6.0.22 加固：扩 phase-b-* 通配豁免（早评估 / locked / 提案等合法 phase-b-* 命名 docs）
#   + 扩 v0.6.0.{3..22}-* LOCKED 手册显式（防未来加号时漏豁免）
EXCLUDE_RE = re.compile(
    r"docs/plans/v0\.4\.|"
    r"docs/plans/v0\.5\.|"
    r"docs/plans/v0\.6\.0-|"
    r"docs/plans/v0\.6\.0\.\d+-|"      # v0.6.0.x LOCKED 手册全豁免（hotfix / micro PATCH）
    r"docs/plans/v0\.6\.1-|"           # R-PA-PB-7（v0.6.1 已正式启动）
    r"docs/plans/phase-b-|"            # phase-b-proposal-draft / phase-b-early-review-* 等
    r"CHANGELOG\.md|"
    r"CLAUDE\.md|"
    r"README\.md|"
    r"scripts/check_phase_b_leakage\.py|"
    r"tests/scripts/test_check_phase_b_leakage\.py|"   # 守护测试自身豁免
    r"knot/static/assets/"
)


def find_phase_b_doc_files() -> list[Path]:
    """检测 Phase B 准备性文档文件 glob 命中（最高级别 alert — 文件存在即触发）。"""
    hits = []
    for glob in PHASE_B_DOC_GLOBS:
        for p in REPO.glob(glob):
            hits.append(p.relative_to(REPO))
    return hits


def grep_phase_b_literals(strict: bool) -> list[tuple[str, str]]:
    """grep Phase B 字面 + schema 列字面。返 [(file, matched_term), ...]。"""
    hits = []
    patterns = PHASE_B_LITERAL_TERMS + PHASE_B_SCHEMA_COLUMNS

    # 用 git grep（含工作目录改动）— 不依赖网络
    for term in patterns:
        try:
            result = subprocess.run(
                ["git", "grep", "-l", "-F", term],
                cwd=REPO,
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0 and result.stdout.strip():
                for line in result.stdout.strip().split("\n"):
                    file_path = line.strip()
                    if EXCLUDE_RE.search(file_path):
                        continue
                    hits.append((file_path, term))
        except subprocess.CalledProcessError:
            continue
    return hits


def run_self_test() -> int:
    """v0.6.0.22 自验 mode — 构造合成 positive/negative 用例验证检测逻辑。

    Codex §APPENDIX D R-PA-8 自验 gate：v0.6.2.0 MINOR 滚动前必须证明本工具
    实际工作（不只是文档约束）。返 0 = 自验 PASS / 1 = FAIL。
    """
    import tempfile

    print("R-PA-8 自验 mode：构造合成用例验证检测逻辑...")

    # 临时仓库结构（不污染真实仓库）
    cases_passed = 0
    cases_failed = []

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)

        # ─── Positive 用例（必须命中） ────────────────────────────────
        # P1: Phase B 文档 glob 命中 (v0.6.2-foo.md)
        (tmpdir / "docs" / "plans").mkdir(parents=True)
        synth_v062 = tmpdir / "docs" / "plans" / "v0.6.2-synthetic-leak.md"
        synth_v062.write_text("# synthetic Phase B PATCH leak")
        # 切到 tmp 模拟扫描
        global REPO
        original_repo = REPO
        REPO = tmpdir
        try:
            doc_hits = find_phase_b_doc_files()
            if any(str(h) == "docs/plans/v0.6.2-synthetic-leak.md" for h in doc_hits):
                cases_passed += 1
                print("  ✅ P1: v0.6.2-*.md 文档 glob 命中")
            else:
                cases_failed.append("P1: v0.6.2-*.md 文档 glob 应命中但未命中")

            # P2: v0.6.5-*.md (扩展 glob 内)
            synth_v065 = tmpdir / "docs" / "plans" / "v0.6.5-future.md"
            synth_v065.write_text("# synthetic")
            doc_hits2 = find_phase_b_doc_files()
            if any(str(h) == "docs/plans/v0.6.5-future.md" for h in doc_hits2):
                cases_passed += 1
                print("  ✅ P2: v0.6.5-*.md 扩展 glob 命中（v0.6.0.22 加固）")
            else:
                cases_failed.append("P2: v0.6.5-*.md 应命中但未命中（v0.6.0.22 扩展 glob 失效）")

            # P3: v0.7.0-*.md 命中
            synth_v07 = tmpdir / "docs" / "plans" / "v0.7.0-major.md"
            synth_v07.write_text("# synthetic")
            doc_hits3 = find_phase_b_doc_files()
            if any(str(h) == "docs/plans/v0.7.0-major.md" for h in doc_hits3):
                cases_passed += 1
                print("  ✅ P3: v0.7.*-*.md 命中")
            else:
                cases_failed.append("P3: v0.7.0-*.md 应命中但未命中")

            # ─── Negative 用例（不能命中 — 豁免）─────────────────────
            # N1: phase-b-proposal-draft.md 豁免
            exempt1 = tmpdir / "docs" / "plans" / "phase-b-proposal-draft.md"
            exempt1.write_text("# Phase B proposal — exempt by name")
            # phase-b-* 不属 v0.6.x-*.md 或 v0.7.x-*.md glob，本来就不会命中
            # 这里验证 EXCLUDE_RE 对 phase-b-* 字面豁免
            if not EXCLUDE_RE.search("docs/plans/phase-b-proposal-draft.md"):
                cases_failed.append("N1: phase-b-proposal-draft.md 应被 EXCLUDE_RE 豁免")
            else:
                cases_passed += 1
                print("  ✅ N1: phase-b-proposal-draft.md 豁免（EXCLUDE_RE）")

            # N2: phase-b-early-review-*.md 豁免（v0.6.0.22 新加）
            if not EXCLUDE_RE.search("docs/plans/phase-b-early-review-2026-05-21.md"):
                cases_failed.append("N2: phase-b-early-review-*.md 应被 EXCLUDE_RE 豁免（v0.6.0.22 新加）")
            else:
                cases_passed += 1
                print("  ✅ N2: phase-b-early-review-*.md 豁免（v0.6.0.22 通配豁免）")

            # N3: v0.6.0.19-locked.md 豁免（hotfix LOCKED 手册）
            if not EXCLUDE_RE.search("docs/plans/v0.6.0.19-desensitize-3-3-locked.md"):
                cases_failed.append("N3: v0.6.0.19-*.md 应被 EXCLUDE_RE 豁免")
            else:
                cases_passed += 1
                print("  ✅ N3: v0.6.0.x-*.md hotfix LOCKED 手册豁免")

            # N4: CLAUDE.md 豁免（路线图引用）
            if not EXCLUDE_RE.search("CLAUDE.md"):
                cases_failed.append("N4: CLAUDE.md 应被 EXCLUDE_RE 豁免")
            else:
                cases_passed += 1
                print("  ✅ N4: CLAUDE.md 豁免")

            # N5: 本工具自身豁免
            if not EXCLUDE_RE.search("scripts/check_phase_b_leakage.py"):
                cases_failed.append("N5: 本工具自身应被 EXCLUDE_RE 豁免（R-PA-14 自指环）")
            else:
                cases_passed += 1
                print("  ✅ N5: 本工具自身豁免（R-PA-14 自指环）")

        finally:
            REPO = original_repo

    # ─── 字面 PATCH 边界用例（非 tmpdir，验证 PHASE_B_LITERAL_TERMS） ────
    # 必须能拆出原字面：multi-tenant / logicform / semantic_layer_v2 等
    expected_literals = {"multi-tenant", "logicform", "semantic_layer_v2",
                         "phase_b_started", "phase-b-started"}
    actual_literals = set(PHASE_B_LITERAL_TERMS)
    if actual_literals != expected_literals:
        cases_failed.append(
            f"P4: PHASE_B_LITERAL_TERMS 应为 {expected_literals}，实际 {actual_literals}"
        )
    else:
        cases_passed += 1
        print("  ✅ P4: PHASE_B_LITERAL_TERMS 5 项字面齐全")

    print()
    if cases_failed:
        print(f"R-PA-8 自验 FAIL — {len(cases_failed)} 用例失败：")
        for f in cases_failed:
            print(f"   - {f}")
        return 1

    print(f"R-PA-8 自验 PASS — {cases_passed}/{cases_passed} 用例通过 (Codex §APPENDIX D gate)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="R-PA-8 内测期 Phase B 准备性内容守护")
    parser.add_argument("--strict", action="store_true",
                        help="严格模式：任何命中都 exit 1（默认行为相同）")
    parser.add_argument("--self-test", action="store_true",
                        help="自验模式：构造合成用例验证检测逻辑（v0.6.0.22 + Codex §APPENDIX D gate）")
    args = parser.parse_args()

    if args.self_test:
        return run_self_test()

    print("R-PA-8 内测期 Phase B 准备性守护扫描...")
    print(f"  REPO: {REPO}")
    print(f"  扫描范围: {len(INCLUDE_GLOBS)} globs")
    print("  豁免: docs/plans/phase-b-proposal-draft.md (草案) + 治理档案 + 自身 + CLAUDE.md")
    print()

    # 1. 文件 glob 检测
    doc_hits = find_phase_b_doc_files()
    if doc_hits:
        print("❌ Phase B 准备性文档文件命中：")
        for p in doc_hits:
            print(f"   - {p}")
        print()
        print("   → R-PA-5 内测期严禁此类 commit。若属 Phase B 提案草案，")
        print("     请重命名为 docs/plans/phase-b-proposal-*.md（豁免范围）")

    # 2. 字面 grep 检测
    literal_hits = grep_phase_b_literals(args.strict)
    if literal_hits:
        print(f"❌ Phase B 字面命中 ({len(literal_hits)} 处)：")
        for file_path, term in literal_hits[:20]:
            print(f"   - {file_path}  →  '{term}'")
        if len(literal_hits) > 20:
            print(f"   ... 还有 {len(literal_hits) - 20} 处")

    if doc_hits or literal_hits:
        print()
        print("R-PA-8 内测期 Phase B 准备性守护：FAIL")
        print("→ 资深架构师 alert：审视是否属误命中（更新 EXCLUDE_RE）或真违规（revert commit）")
        return 1

    print("R-PA-8 内测期 Phase B 准备性守护：OK — 0 命中")
    return 0


if __name__ == "__main__":
    sys.exit(main())
