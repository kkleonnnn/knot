#!/usr/bin/env python3
"""scripts/check_file_sizes.py — D7 加码 CI 行数核验（v0.5.2 R-94 / v0.5.3 R-111 / v0.5.7 R-176 落地）。

v0.5.2 R-94：后端 4 主文件硬上限 + 8 个新建模块 ≤ 250；query.py 220 → 310（SSE 样板）。
v0.5.3 R-111：前端 Chat.jsx ≤ 350 / Admin.jsx ≤ 360 / 子模块 ≤ 250；
  ResultBlock.jsx 250 → 400（复合 UI 组件）+ Admin.jsx 250 → 360（状态容器）资深 ack 微调。
v0.5.7 R-176：Login.jsx ≤ 200 + decor/NarrativeMotif.jsx ≤ 120（27 → 29 条 LIMITS）。
v0.5.9 R-205：Shell.jsx ≤ 220（29 → 30 条 LIMITS）。
v0.5.10 R-218：chat/ChatEmpty.jsx 由 250 → 80 收紧（30 条 LIMITS 不变，仅 cap 收紧）。
v0.5.11 R-260：chat/Composer.jsx 由 250 → 100 收紧（30 条不变，R-217 清偿 PATCH）。
v0.5.12 R-285：chat/ThinkingCard.jsx 由 250 → 160 收紧（30 条不变，Thinking 屏复刻 PATCH）。
v0.5.13 R-307：chat/ResultBlock.jsx 由 400 → 420 微调 ack（svg path 占行不可压；与 v0.5.3 R-111 同模式）。
v0.5.14 R-341：chat/ResultBlock.jsx 由 420 → 440 v0.5 final ack（视觉大重构 svg + observation card；v0.6 必须开启子组件拆分）。
v0.5.15 R-363：SavedReports.jsx 新增 LIMIT 380（30 → 31 条；首次纳入；Favorites 屏复刻）。
v0.5.17 R-425：AdminAudit.jsx 新增 LIMIT 380（31 → 32 条；首次纳入；AdminAudit 屏复刻）。
v0.5.18 R-460：AdminBudgets.jsx 新增 LIMIT 380（32 → 33 条；首次纳入；AdminBudgets 屏复刻）。
v0.5.19 R-490：AdminRecovery.jsx 新增 LIMIT 380（33 → 34 条；首次纳入；AdminRecovery 屏复刻；admin 顶层屏三部曲收官）。
"""
import sys
from pathlib import Path

LIMITS = {
    # ── 后端 (v0.5.2 R-94) ───────────────────────────────────
    # 4 主文件
    "knot/services/agents/sql_planner.py": 350,
    "knot/services/llm_client.py":         300,
    "knot/services/agents/orchestrator.py": 220,
    "knot/api/query.py":                   310,  # SSE 协议样板，资深 ack
    # 9 个新建模块（v0.5.2）
    "knot/services/agents/sql_planner_prompts.py": 250,
    "knot/services/agents/sql_planner_tools.py":   250,
    "knot/services/agents/sql_planner_llm.py":     250,
    "knot/services/agents/clarifier.py":           250,
    "knot/services/agents/presenter.py":           250,
    "knot/services/few_shots.py":                  250,
    "knot/services/llm_prompt_builder.py":         250,
    "knot/services/_llm_invoke.py":                250,
    "knot/services/query_steps.py":                250,
    # ── 前端 (v0.5.3 R-111) ──────────────────────────────────
    # 2 主文件
    "frontend/src/screens/Chat.jsx":  350,
    "frontend/src/screens/Admin.jsx": 380,  # v0.5.44 360→380 (catalog state 加 relations 字段)
    # 12 个新建模块（v0.5.3）
    "frontend/src/screens/chat/intent_helpers.js":  80,
    "frontend/src/screens/chat/sse_handler.js":    150,
    "frontend/src/screens/chat/ResultBlock.jsx":   460,  # v0.5.39 440→460 (Trace 4th step 推导 + suggestions chevron 改造)
    "frontend/src/screens/SavedReports.jsx":       380,  # v0.5.15 R-363 新增 (Favorites 屏复刻)
    "frontend/src/screens/AdminAudit.jsx":         430,  # v0.5.38 380→430 (字体 sweep + 时段下拉 + 导出 CSV)
    "frontend/src/screens/AdminBudgets.jsx":       380,  # v0.5.18 R-460 新增 (AdminBudgets 屏复刻)
    "frontend/src/screens/AdminRecovery.jsx":      380,  # v0.5.19 R-490 新增 (AdminRecovery 屏复刻;admin 三部曲收官)
    "frontend/src/screens/chat/ChatEmpty.jsx":     100,  # v0.5.30 80→100 (suggestion icons spark/flow 扩张)
    "frontend/src/screens/chat/Conversation.jsx":  250,
    "frontend/src/screens/chat/ThinkingCard.jsx":  220,  # v0.5.39 160→220 (Trace 4th step + 信任度推导)
    "frontend/src/screens/chat/Composer.jsx":      100,  # v0.5.11 R-260 收紧 250→100
    "frontend/src/screens/admin/tab_access.jsx":   250,
    "frontend/src/screens/admin/tab_resources.jsx": 250,
    "frontend/src/screens/admin/tab_knowledge.jsx": 440,  # v0.5.35/36 250→440 (Knowledge + Few-shot 完整 UI demo 重写)
    "frontend/src/screens/admin/tab_system.jsx":   250,
    "frontend/src/screens/admin/modals.jsx":       250,
    # ── v0.5.7 R-176 ──────────────────────────────────────────
    "frontend/src/screens/Login.jsx":              200,
    "frontend/src/decor/NarrativeMotif.jsx":       120,
    # ── v0.5.9 R-205 ──────────────────────────────────────────
    "frontend/src/Shell.jsx":                      220,
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
