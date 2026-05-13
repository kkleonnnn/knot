#!/usr/bin/env python3
"""scripts/audit_ohx_leakage.py — v0.6.0 Phase A 业务方言 + 旧品牌字面泄漏守护。

模式（Q-E2.A 资深拍板）：
- --mode=sanitize : 仅扫业务方言（ohx / mydb）— commit 1 完成后首次可 exit 0
- --mode=brand    : 仅扫旧品牌（bi_agent / BIAGENT_*）— commit 6 完成后首次可 exit 0
- --mode=all      : 两者都扫（默认）— commit 7 全闸门最终验证

INCLUDE_GLOBS（R-PA-6 业务代码守护范围）：
- knot/**/*.py + tests/**/*.py + scripts/**/*.py（Python 业务代码 + 测试 + 工具脚本）
- frontend/src/**/*.{jsx,js}（前端业务代码）
- .env.example + Dockerfile + pyproject.toml（部署 + 构建配置）

排除（EXCLUDE_RE 治理档案 + 自动重建产物）：
- docs/plans/v0.4.*.md / docs/plans/v0.5.*.md（治理过程历史档案豁免）
- CHANGELOG.md（v0.6.0 撤回声明 + 历史档案；含撤回命令字面）
- knot/static/assets/（Vite 构建产物自动重建）

README.md / CLAUDE.md 不在 INCLUDE_GLOBS 范围（用户文档 — 升级路径段必含
`bi_agent.db` / `BIAGENT_MASTER_KEY` 历史字面作为用户实操命令；与 R-PA-6 业务
代码守护不冲突 — 详 R-PA-6.1 业务代码 docstring 守护范围）。

执行：python3 scripts/audit_ohx_leakage.py [--mode=sanitize|brand|all]
退出码：0 = 干净 / 1 = 有命中点
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# 字面分割构造避免自指环（R-PA-1 自身脚本不命中扫描）
BUSINESS_TERMS = ["o" + "hx", "m" + "ydb"]
BRAND_TERMS = [
    "bi" + "_agent",
    "BI-A" + "gent",
    "bi" + "-agent",
    "BIAGENT" + "_MASTER_KEY",
    "BIA" + "GENT",
]

INCLUDE_GLOBS = [
    "knot/**/*.py",
    "frontend/src/**/*.jsx",
    "frontend/src/**/*.js",
    "tests/**/*.py",
    "scripts/**/*.py",
    ".env.example",
    "Dockerfile",
    "pyproject.toml",
    # README.md / CLAUDE.md 不在范围 — 用户文档允许含升级路径历史字面命令
]
EXCLUDE_RE = re.compile(
    r"^(docs/plans/v0\.4\.|docs/plans/v0\.5\.|knot/static/assets/|CHANGELOG\.md$)"
)


def _scan(terms: list[str], label: str) -> list[str]:
    violations = []
    for term in terms:
        for glob in INCLUDE_GLOBS:
            result = subprocess.run(
                ["git", "grep", "-nF", term, "--", glob],
                cwd=REPO,
                capture_output=True,
                text=True,
                check=False,
            )
            for line in result.stdout.splitlines():
                if not line:
                    continue
                path = line.split(":", 1)[0]
                if EXCLUDE_RE.match(path):
                    continue
                violations.append(f"[{label}:{term}] {line}")
    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description="v0.6.0 Phase A sanitize 守护")
    parser.add_argument(
        "--mode",
        choices=["sanitize", "brand", "all"],
        default="all",
        help="sanitize=业务方言 / brand=旧品牌 / all=两者都扫",
    )
    args = parser.parse_args()

    violations: list[str] = []
    if args.mode in ("sanitize", "all"):
        violations.extend(_scan(BUSINESS_TERMS, "sanitize"))
    if args.mode in ("brand", "all"):
        violations.extend(_scan(BRAND_TERMS, "brand"))

    if violations:
        print(f"audit_ohx_leakage --mode={args.mode} FAILED — {len(violations)} 命中")
        for v in violations[:50]:
            print(f"  {v}")
        if len(violations) > 50:
            print(f"  ... 还有 {len(violations) - 50} 条")
        return 1
    print(f"audit_ohx_leakage --mode={args.mode} OK — 0 命中")
    return 0


if __name__ == "__main__":
    sys.exit(main())
