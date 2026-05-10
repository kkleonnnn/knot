#!/usr/bin/env python3
"""scripts/check_file_sizes.py — v0.5.2 D7 加码 CI 行数核验（R-94 落地）。

LOCKED 红线 R-94：4 主文件硬上限 + 8 个新建模块 ≤ 250。
仅 query.py 经资深 ack 微调 220 → 310（SSE 协议样板代码不可消除）。
"""
import sys
from pathlib import Path

LIMITS = {
    # 4 主文件（v0.5.2 拆分目标）
    "knot/services/agents/sql_planner.py": 350,
    "knot/services/llm_client.py":         300,
    "knot/services/agents/orchestrator.py": 220,
    "knot/api/query.py":                   310,  # R-94 微调（SSE 协议样板，资深 ack）
    # 8 个新建模块
    "knot/services/agents/sql_planner_prompts.py": 250,
    "knot/services/agents/sql_planner_tools.py":   250,
    "knot/services/agents/sql_planner_llm.py":     250,
    "knot/services/agents/clarifier.py":           250,
    "knot/services/agents/presenter.py":           250,
    "knot/services/few_shots.py":                  250,
    "knot/services/llm_prompt_builder.py":         250,
    "knot/services/_llm_invoke.py":                250,
    "knot/services/query_steps.py":                250,
}

repo = Path(__file__).resolve().parent.parent
violations = []
for rel, limit in LIMITS.items():
    p = repo / rel
    if not p.exists():
        violations.append(f"{rel}: missing")
        continue
    n = sum(1 for _ in p.open())
    if n > limit:
        violations.append(f"{rel}: {n} > {limit}")

if violations:
    print("R-94 行数核验 FAILED:", file=sys.stderr)
    for v in violations:
        print(f"  - {v}", file=sys.stderr)
    sys.exit(1)
print(f"R-94 行数核验 OK ({len(LIMITS)} files)")
