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
    "knot/services/agents/sql_planner.py": 365,  # v0.6.2.1 commit 3 +R-PB-C3-1 __REJECT_NON_SQL__ sync+async 双分支
    "knot/services/llm_client.py":         300,
    "knot/services/agents/orchestrator.py": 220,
    "knot/api/query.py":                   440,  # v0.6.1.4 +120 (HTTP 路由分流 + R-PB2-4 跨源 hard raise + agent_start/done/final SSE event 链路)
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
    "knot/services/query_helper.py":               120,  # v0.6.2.6 段 4 (A1 并发半) D3 Extract Method (ContextVar 入口捕获)
    "knot/services/desensitize.py":                150,  # v0.6.0.19 新增 (脱敏链 3/3 后端模块)
    "knot/repositories/catalog_repo.py":           250,  # v0.6.2.5 段 4 (A1) catalogs CRUD + per-user active
    # ── 前端 (v0.5.3 R-111) ──────────────────────────────────
    # 2 主文件
    "frontend/src/screens/Chat.jsx":  350,
    "frontend/src/screens/Admin.jsx": 420,  # v0.5.44 360→380; v0.6.2.0 380→400; v0.6.2.5 段4 400→420（+多 catalog 切换 state/handlers — 状态容器 ack 微调先例）
    # 12 个新建模块（v0.5.3）
    "frontend/src/screens/chat/intent_helpers.js":  80,
    "frontend/src/screens/chat/sse_handler.js":    150,
    "frontend/src/screens/chat/ResultBlock.jsx":   460,  # v0.5.39 440→460 (Trace 4th step 推导 + suggestions chevron 改造)
    "frontend/src/screens/SavedReports.jsx":       380,  # v0.5.15 R-363 新增 (Favorites 屏复刻)
    "frontend/src/screens/AdminAudit.jsx":         210,  # v0.6.3.2 C5 490→210 (6 视觉段抽 audit/ 子组件;编排层瘦身)
    "frontend/src/screens/audit/AuditStatGrid.jsx":     50,   # v0.6.3.2 C5 AdminAudit 拆分
    "frontend/src/screens/audit/AuditRetentionBar.jsx": 60,   # v0.6.3.2 C5 AdminAudit 拆分
    "frontend/src/screens/audit/AuditFilterStrip.jsx":  70,   # v0.6.3.2 C5 AdminAudit 拆分
    "frontend/src/screens/audit/AuditTable.jsx":        120,  # v0.6.3.2 C5 AdminAudit 拆分
    "frontend/src/screens/audit/AuditPagination.jsx":   40,   # v0.6.3.2 C5 AdminAudit 拆分
    "frontend/src/screens/audit/AuditDetailDrawer.jsx": 110,  # v0.6.3.2 C5 AdminAudit 拆分
    "frontend/src/screens/AdminBudgets.jsx":       380,  # v0.5.18 R-460 新增 (AdminBudgets 屏复刻)
    "frontend/src/screens/AdminRecovery.jsx":      380,  # v0.5.19 R-490 新增 (AdminRecovery 屏复刻;admin 三部曲收官)
    "frontend/src/screens/AdminMetrics.jsx":       200,  # v0.6.0.16 新增 (内测指标屏 — 4 KPI cards + period tabs + rules)
    "frontend/src/screens/AdminQueryHistory.jsx":  250,  # v0.6.0.18 新增 (查询历史屏 — filter strip + CSS grid table + drawer detail)
    "frontend/src/screens/chat/ChatEmpty.jsx":     100,  # v0.5.30 80→100 (suggestion icons spark/flow 扩张)
    "frontend/src/screens/chat/Conversation.jsx":  250,
    "frontend/src/screens/chat/ThinkingCard.jsx":  240,  # v0.6.1.4 220→240 (HTTP path Trace 分支 + _shouldHideClarifierApproach)
    "frontend/src/screens/chat/Composer.jsx":      100,  # v0.5.11 R-260 收紧 250→100
    "frontend/src/screens/admin/tab_access.jsx":   250,
    "frontend/src/screens/admin/tab_resources.jsx": 250,
    "frontend/src/screens/admin/tab_knowledge.jsx": 440,  # v0.5.35/36 250→440 (Knowledge + Few-shot 完整 UI demo 重写)
    "frontend/src/screens/admin/tab_system.jsx":   250,
    "frontend/src/screens/admin/modals.jsx":       320,  # v0.6.1.4 +70 (SourceFormModal HTTP type 5 字段 + isHttp 分支 + parsedHttpCfg 反序列化)
    # ── v0.5.7 R-176 ──────────────────────────────────────────
    "frontend/src/screens/Login.jsx":              295,  # v0.6.4.1 UI v2 复刻 270→295 (card + Btn 采纳 + error 迁)
    "frontend/src/screens/Enroll.jsx":             240,  # v0.6.2.0 commit 5 NEW — 4-step TOTP enroll 流程
    "frontend/src/decor/NarrativeMotif.jsx":       120,
    # ── v0.5.9 R-205 ──────────────────────────────────────────
    "frontend/src/Shell.jsx":                      220,
    # ── v0.6.0.1 LOCKED §1 ─────────────────────────────────────
    "scripts/check_phase_b_leakage.py":            350,  # R-PA-8 守护工具 (v0.6.0.22 加 --self-test mode)
    "knot/api/_rate_limit.py":                     200,  # v0.6.0.23 in-memory rate limiter; v0.6.2.0 commit 3 +totp_verify/enroll
    "tests/scripts/test_dockerfile_copy.py":       100,  # G-6 R-PA-7 字面单元测试
    # ── v0.6.0.2 LOCKED §1 — ResultBlock 6 子组件拆分（R-341 偿还）──────────
    "frontend/src/screens/chat/ResultBlock/MetricCard.jsx":      80,  # v0.6.2.2 A5 复合 metric 多值网格双分支（η1 选项 A 50→80）
    "frontend/src/screens/chat/ResultBlock/TableContainer.jsx":  100,  # chart + table 复合最大
    "frontend/src/screens/chat/ResultBlock/InsightCard.jsx":     50,
    "frontend/src/screens/chat/ResultBlock/BudgetBanner.jsx":    60,
    "frontend/src/screens/chat/ResultBlock/ErrorBanner.jsx":     80,   # 含 ERROR_KIND_META 7 类
    "frontend/src/screens/chat/ResultBlock/TokenMeter.jsx":      60,
    # ── v0.6.0.3 F-A — FeedbackBar 子组件（M-A4 复用 utils Modal）──────────
    "frontend/src/screens/chat/ResultBlock/FeedbackBar.jsx":     100,
    # ── v0.6.0.4 F-B — 前端 JS 错误上报基础设施 ──────────────────────────
    "frontend/src/error_reporter.js":              120,   # M-B1 throttle/dedupe
    "frontend/src/screens/AdminErrors.jsx":        150,   # 姊妹屏（视觉沿用 AdminAudit/Recovery）
    # ── v0.6.1 LOCKED §1 F2 — 时间语义引擎（R-PA-PB-2 守护）──────────────
    "knot/core/time_resolver.py":                  350,  # ~235 行 + 后续预留扩展
    # ── v0.6.2.3 R-PB-SH-9 — Foundation 解冻后纳入 CI 行数闸门 ──────────────
    # R-365 退役（首次受准修改 Shared.jsx）后两文件可增长 → 须 cap 防无界膨胀。
    # 注意路径在 frontend/src/（非 frontend/src/screens/）。v0.6.4.0 UI v2: Shared 692/760 + primitives 67/150。
    "frontend/src/Shared.jsx":                     760,  # v0.6.4.0 UI v2 720→760 (+TOKENS_V2 + 16 图标 additive)
    "frontend/src/primitives.jsx":                 150,  # v0.6.4.0 UI v2 新增 (Btn/Tag 拆独立文件;资深拍 B)
    "frontend/src/utils.jsx":                      200,  # v0.6.2.3 新增 (Foundation 纳管;PATCH-1 不动)
}
# v0.6.0.2 R-PA-PB-V0.5：ResultBlock.jsx 主文件 LIMIT 460 → 280 收紧（拆分后）
# v0.6.0.3 F-A: 280 → 290 (FeedbackBar import + 调用 ~5 行；子组件已抽出主体逻辑)
# v0.6.0.17: 290 → 295 (user prop + isAdmin 守护非 admin 隐 SQL accordion)
LIMITS["frontend/src/screens/chat/ResultBlock.jsx"] = 295

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
