#!/usr/bin/env python3
"""scripts/check_file_sizes.py — CI 行数核验（v0.5.2 R-94 起；v0.6.5.11 收官② 根治）。

v0.6.5.11 收官② R-AS-6 根治（allowlist → backend auto-discover）：
  后端 `knot/**/*.py` 全自动发现 + 默认 cap 300 + ACK 例外白名单（>300 文件须显式 ACK，
  否则红）——根治「不在 LIMITS 即无 cap」的巨型文件无声膨胀盲区（admin/http_planner/
  catalog/message_repo/doris/engine_cache 历史全漏网）。前端 + 杂项保 explicit allowlist
  （前端无包根 walk；LOCKED 只 mandate backend）。
  起 C1 前 `wc -l` 全扫复定 ACK 全集（守护者硬纠1）；time_resolver 239/llm_client 252 ≤300
  auto-pass 不入 ACK（R-137 校正：350 是 time_resolver 的旧 cap 非行数）。

历史（前端 explicit cap 沿革）：v0.5.3 R-111 Chat/Admin/子模块；R-176 Login/Motif；R-205 Shell；
  v0.6.0.2 ResultBlock 6 子组件拆分；v0.6.3.2 AdminAudit 拆 audit/ 6 子组件；v0.6.4.0 UI v2 Shared/primitives。
"""
import sys
from pathlib import Path

# ── 后端：auto-discover `knot/**/*.py` + 默认 cap 300 + ACK 例外（收官② R-AS-6 根治）──
BACKEND_DEFAULT_CAP = 300
# ACK = 全部 >300 backend 文件（起 C1 前 `wc -l` 全扫复定 = 8）。每条带理由 + split-planned 标注。
# 未列文件按 BACKEND_DEFAULT_CAP 300 核验（新文件不能逃逸 — 治盲区）。
BACKEND_ACK = {
    # admin.py 908 已于 v0.6.5.11 C2 拆 knot/api/admin/ 7 域（最大 stats 269 ≤300 auto-caught）→ ACK 移除
    # catalog.py 460 已于 v0.6.5.12 C1 拆 catalog_loaders（catalog 261 / loaders 213 ≤300 auto-caught）→ ACK 移除
    "knot/services/http_planner.py":       580,  # futures regex 下沉 catalog JIT v0.7.2 + v0.7.20 B（http_table_in_sql + failure_error_meta）+ v0.7.22 Layer A intent veto（_ANALYTICAL_INTENTS + early-return R-SL-162）565→579
    "knot/api/query.py":                   541,  # SSE 协议样板不可消除（v0.5.2 R-94）+ v0.7.x →537；v0.8.2 B6.4 +raw_question →539；v0.8.3 B6.5-Q36 +presenter 喂 params 注释 539→540→541（headroom 1）
    "knot/repositories/message_repo.py":   390,  # v0.7.4 C3 +get_messages engine enrich（F2/R-SL-46）；无 split 计划
    "knot/services/agents/sql_planner.py": 365,  # ReAct 调度（沿用既有 cap，保 headroom）
    "knot/adapters/db/doris.py":           373,  # v0.7.42 B2.2 +DORIS_READ_TIMEOUT 344→345；v0.8.0 B6.1 +_has_top_level_limit AST auto-LIMIT（§1.9 安全承重）345→364→366；v0.8.5 ②a D7 +public is_safe_sql wrapper 366→373（headroom 0，config-only）
    "knot/services/semantic/compiler.py":  350,  # v0.7.13 抽 multi_base/compile_helpers 394→275；v0.7.14~.31 outer/frame/Q5 guard →311；v0.8.0 B6.1 +_guard_fragments choke-point 片段校验（§安全承重）311→348→350（headroom 2）→ feature 增长再 ACK
    "knot/services/engine_cache.py":       337,  # 暂冻结当前行数
    "knot/services/bi_report_service.py":  340,  # v0.8.5~.8 BI 编排（脱敏/diff-by-id/tiled 刷新/reorder）；v0.8.8 ③ +reorder 2 fn 302>300 → ACK
    "knot/services/query_steps.py":        370,  # SSE 主控编排 + 纯业务步骤；v0.7.27 →306；v0.8.2 B6.4 +跨期对比 guard（_COMPARE_RE + _known_names + _period_comparison_unrepresented + _has_lag_window）306→366→370（headroom 4）→ feature 增长再 ACK
}

# ── 前端 + 杂项：explicit allowlist（无包根 auto-discover；LOCKED 只 mandate backend）──
EXPLICIT_LIMITS = {
    # 2 主屏
    "frontend/src/screens/Chat.jsx":  350,
    "frontend/src/screens/Admin.jsx": 420,  # v0.6.2.5 段4 400→420（多 catalog 切换 state/handlers 状态容器 ack）
    # chat/ 子模块
    "frontend/src/screens/chat/intent_helpers.js":  80,
    "frontend/src/screens/chat/sse_handler.js":    150,
    "frontend/src/screens/chat/ResultBlock.jsx":   312,  # v0.6.0.17 拆分后编排层（460 旧值已废）；v0.7.23 图表硬化 295→305；v0.7.30 D3 LLM ID-like 列启发式 305→312
    "frontend/src/screens/chat/ChatEmpty.jsx":     100,
    "frontend/src/screens/chat/Conversation.jsx":  250,
    "frontend/src/screens/chat/ThinkingCard.jsx":  240,  # v0.6.1.4 220→240 (HTTP path Trace 分支)
    "frontend/src/screens/chat/Composer.jsx":      100,
    # ResultBlock 6 子组件（v0.6.0.2）+ FeedbackBar（v0.6.0.3）
    "frontend/src/screens/chat/ResultBlock/MetricCard.jsx":      80,  # v0.6.2.2 复合 metric 多值网格
    "frontend/src/screens/chat/ResultBlock/TableContainer.jsx":  100,
    "frontend/src/screens/chat/ResultBlock/InsightCard.jsx":     50,
    "frontend/src/screens/chat/ResultBlock/BudgetBanner.jsx":    60,
    "frontend/src/screens/chat/ResultBlock/ErrorBanner.jsx":     80,
    "frontend/src/screens/chat/ResultBlock/TokenMeter.jsx":      60,
    "frontend/src/screens/chat/ResultBlock/FeedbackBar.jsx":     100,
    # 顶层屏
    "frontend/src/screens/SavedReports.jsx":       380,
    "frontend/src/screens/AdminAudit.jsx":         210,  # v0.6.3.2 C5 490→210 (拆 audit/ 6 子组件)
    "frontend/src/screens/AdminBudgets.jsx":       380,
    "frontend/src/screens/AdminRecovery.jsx":      380,
    "frontend/src/screens/AdminMetrics.jsx":       200,  # 内测健康 KPI 屏（≠ v0.7 metric registry）
    "frontend/src/screens/AdminMetricRegistry.jsx": 215,  # v0.7.0 C5 语义层指标注册表（≠ AdminMetrics KPI 屏）；v0.7.25 +unit 值格式 FormRow 200→215
    "frontend/src/screens/AdminLogicForm.jsx":     200,  # v0.7.3 C2 LogicForm 审计屏（read-only）
    "frontend/src/screens/logicform/LogicFormHistory.jsx": 130,  # v0.7.5 C2 版本历史 + diff 子组件
    "frontend/src/screens/AdminMonitors.jsx":      200,  # v0.7.7 C5 事件/规则/动作监控屏（CRUD + 立即检查）
    "frontend/src/screens/AdminQueryHistory.jsx":  250,
    "frontend/src/screens/AdminErrors.jsx":        150,
    "frontend/src/screens/Login.jsx":              295,  # v0.6.4.1 UI v2 复刻
    "frontend/src/screens/Enroll.jsx":             256,  # v0.6.5.2 F5 sessionStorage 缓存 helpers
    # BI 模式（v0.8.5 ②a + v0.8.6 ②b）—— 补前端 size-gate 盲区（critic D：bi/ 原零登记 = 不受守护）
    "frontend/src/screens/BI.jsx":                        210,  # BIScreen 调度（AppShell slots + ActBtn + 模态）
    "frontend/src/RightPanel.jsx":                        60,   # 共享右栏 chrome（BI da-asst ∥ ASK 思考过程）
    "frontend/src/screens/bi/ReportDirectory.jsx":        200,  # 报表目录树 + 搜索
    "frontend/src/screens/bi/ReportBuilderModal.jsx":     200,  # 双类型 builder（宽表覆盖层 / 仪表盘 TileBuilder）
    "frontend/src/screens/bi/WideTableReport.jsx":        160,  # 宽表（sheet/冻结列/条件色/覆盖层公式）
    "frontend/src/screens/bi/WideTable.jsx":              140,  # v0.8.7 宽表表体核心（单宽表 + tabbed 页签共用）
    "frontend/src/screens/bi/TabbedTableReport.jsx":      100,  # v0.8.7 多页表（每页一条 SQL，运营日报式）
    "frontend/src/screens/bi/TileBuilder.jsx":            180,  # ②b 结构化拼板（type/SQL/viz/span/DnD）
    "frontend/src/screens/bi/ColumnConfigEditor.jsx":     70,   # v0.8.8 ② 逐列配置（label/desc/unit/conditional）
    "frontend/src/screens/bi/OverlayEditor.jsx":          70,   # v0.8.9 per-页公式行编辑器（formula.js 覆盖层）
    "frontend/src/screens/bi/SkillPanel.jsx":             130,  # da-asst UI 壳（真接 ③）
    "frontend/src/screens/bi/DashboardReport.jsx":        120,  # ②b tiles[] 分发渲染
    "frontend/src/screens/bi/ModeToggle.jsx":             60,   # ASK/BI 分段 pill
    "frontend/src/screens/bi/InsightCard.jsx":            50,
    "frontend/src/screens/bi/formula.js":                 400,  # ⭐ 安全承重（零 eval 求值器 R-BI-11）；guards 增长 ACK
    "frontend/src/screens/bi/formula.test.js":            220,  # 公式对抗/正确性单测
    "frontend/src/screens/bi/tiles/_shared.jsx":          100,  # Card/Donut/TileState 共享件
    "frontend/src/screens/bi/tiles/tile_data.js":         90,   # orderedCols/parseTile/numericCol 纯 helper
    "frontend/src/screens/bi/tiles/tile_data.test.js":    50,   # v0.8.8 orderedCols 列序守护（rows-first）
    "frontend/src/screens/bi/tiles/KpiTile.jsx":          90,
    "frontend/src/screens/bi/tiles/LineTile.jsx":         60,
    "frontend/src/screens/bi/tiles/DonutTile.jsx":        90,
    "frontend/src/screens/bi/tiles/BarTile.jsx":          90,
    "frontend/src/screens/bi/tiles/TableTile.jsx":        90,
    # audit/ 子组件（v0.6.3.2 C5）
    "frontend/src/screens/audit/AuditStatGrid.jsx":     50,
    "frontend/src/screens/audit/AuditRetentionBar.jsx": 60,
    "frontend/src/screens/audit/AuditFilterStrip.jsx":  70,
    "frontend/src/screens/audit/AuditTable.jsx":        120,
    "frontend/src/screens/audit/AuditPagination.jsx":   40,
    "frontend/src/screens/audit/AuditDetailDrawer.jsx": 110,
    # admin/ tab 子模块
    "frontend/src/screens/admin/tab_access.jsx":   250,
    "frontend/src/screens/admin/tab_resources.jsx": 250,
    "frontend/src/screens/admin/tab_knowledge.jsx": 440,  # v0.5.35/36 Knowledge + Few-shot 完整 UI
    "frontend/src/screens/admin/tab_system.jsx":   250,
    "frontend/src/screens/admin/modals.jsx":       320,  # v0.6.1.4 SourceFormModal HTTP type 5 字段
    # Foundation + 基础设施
    "frontend/src/Shared.jsx":                     760,  # v0.6.4.0 UI v2 (TOKENS_V2 + 16 图标 additive)
    "frontend/src/primitives.jsx":                 150,  # v0.6.4.0 UI v2 (Btn/Tag 独立文件)
    "frontend/src/utils.jsx":                      200,  # v0.6.2.3 Foundation 纳管
    "frontend/src/decor/NarrativeMotif.jsx":       120,
    "frontend/src/Shell.jsx":                      235,  # v0.7.7 C5 +指标监控 nav；v0.8.5 ②a +inline ModeToggle 集群 222→225；+子屏返回来时模式 backMode 逻辑 →233（headroom 2）
    "frontend/src/error_reporter.js":              120,  # v0.6.0.4 throttle/dedupe
    "frontend/src/ErrorBoundary.jsx":              120,  # v0.7.33 B1.1 App+ResultBlock error boundary
    # 杂项（非 knot 后端，不被 auto-discover 覆盖）
    "tests/scripts/test_dockerfile_copy.py":       100,  # G-6 R-PA-7 字面单元测试
}

repo = Path(__file__).resolve().parent.parent
violations = []


def _lines(p: Path) -> int:
    return sum(1 for _ in p.open())


# ── 后端 auto-discover：knot/**/*.py 全扫，未在 ACK 即按 DEFAULT_CAP 300 ──
for p in sorted((repo / "knot").rglob("*.py")):
    rel = p.relative_to(repo).as_posix()
    cap = BACKEND_ACK.get(rel, BACKEND_DEFAULT_CAP)
    n = _lines(p)
    if n > cap:
        violations.append(f"{rel}: {n} > {cap}")

# ── 前端 + 杂项 explicit allowlist ──
for rel, limit in EXPLICIT_LIMITS.items():
    p = repo / rel
    if not p.exists():
        violations.append(f"{rel}: missing")
        continue
    if _lines(p) > limit:
        violations.append(f"{rel}: {_lines(p)} > {limit}")

if violations:
    print("R-94 行数核验 FAILED:", file=sys.stderr)
    for v in violations:
        print(f"  - {v}", file=sys.stderr)
    sys.exit(1)

_backend_n = sum(1 for _ in (repo / "knot").rglob("*.py"))
print(f"R-94 行数核验 OK (backend auto-discover {_backend_n} files, "
      f"ACK {len(BACKEND_ACK)}, default cap {BACKEND_DEFAULT_CAP}; "
      f"frontend/misc explicit {len(EXPLICIT_LIMITS)})")
