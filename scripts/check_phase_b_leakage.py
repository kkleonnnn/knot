#!/usr/bin/env python3
"""scripts/check_phase_b_leakage.py — v0.6.0.1 R-PA-8 内测期 Phase B 准备性 commit 守护。

LOCKED §3 R-PA-5 + R-PA-8 联合守护：R-PA-5 内测期（Day 0~28）严禁 Phase B 准备性
commit。本工具扫 main 分支（默认）或当前工作目录字面，命中即 exit 1。

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
PHASE_B_DOC_GLOBS = [
    "docs/plans/v0.6.1-*.md",
    "docs/plans/v0.6.2-*.md",
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
EXCLUDE_RE = re.compile(
    r"docs/plans/v0\.4\.|"
    r"docs/plans/v0\.5\.|"
    r"docs/plans/v0\.6\.0-|"
    r"docs/plans/v0\.6\.0\.1-|"
    r"docs/plans/phase-b-proposal-draft\.md|"
    r"CHANGELOG\.md|"
    r"CLAUDE\.md|"
    r"README\.md|"
    r"scripts/check_phase_b_leakage\.py|"
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


def main() -> int:
    parser = argparse.ArgumentParser(description="R-PA-8 内测期 Phase B 准备性内容守护")
    parser.add_argument("--strict", action="store_true",
                        help="严格模式：任何命中都 exit 1（默认行为相同）")
    args = parser.parse_args()

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
