# BI-Agent — Claude Code 项目指令

## 概述

AI 驱动的 BI 助手：自然语言 → SQL → 图表。
- v0.1.1：Python 3 / FastAPI + React（浏览器端 Babel）
- v0.2.x（当前 v0.2.4）：FastAPI + React/Vite 构建版前端
- v0.x.x（规划）：Go 后端重写

## 协作规则

1. 不确定就问，别猜
2. 没要求就不写
3. 只改被要求的部分
4. 给验收标准，别给步骤

### ⚠️ 迭代循环协议 (Loop Protocol) — v3

**严禁在未走完三阶段评审的情况下编写任何业务代码。**

> v3 相对 v2：新增「**远古守护者**」角色 + 「**MINOR 滚动前夕整体审核**」仪式。
> v0.5.0 起生效；v0.4.x 期间走的是 v2（无远古守护者机制）。

#### 一个 MINOR = 一个 Agent

Agent 的生命周期与 **MINOR 版本号**绑定，不与 PATCH 绑定：

- v0.3.0 / v0.3.1 / … / v0.3.x → **同一对话** = **v0.3 Agent**
- v0.4.0 / v0.4.1 / … / v0.4.x → **同一对话** = **v0.4 Agent**
- v0.5.0 / … / v0.5.x → **同一对话** = **v0.5 Agent**

每跨一个 MINOR，用户开**新对话**启动新 Agent；角色按 §角色滚动规则更替。

#### 角色定义（v3 — 4 级角色）

| 角色 | 实体 | 职责 | 权限 |
|---|---|---|---|
| **执行者** | 当前 MINOR 的 Agent | 出方案、整合终审意见、写代码、跑闸门、提 PR | 读 + 写 |
| **守护者** | 上一 MINOR 的 Agent（距离 = 0.1） | PATCH 内 Stage 3 终审 + 闸门复核 | **只读**（严禁改代码） |
| **远古守护者** | 上上 MINOR 起的 Agent（距离 > 0.1） | **仅 MINOR 滚动前夕**整体审核 | **只读 + 默认沉睡** |
| **辅助 AI 初审组** | 资深工程师 + Codex + 其他辅助 AI | PATCH 内 Stage 2 给 Redline / 评分 / 风险点 | 评审建议 |
| **资深架构师** | User 本人 | 战略决策 + 拍板 + 召集整体审核 | 决策 |

#### 三阶段评审（PATCH 内常规流程）

```
执行者                    辅助 AI 初审组              守护者                  执行者
   │                           │                         │                       │
   │ Stage 1: 方案/规划草案 ───┼─────────────────────┐   │                       │
   │                           │                     │   │                       │
   │                           │ Stage 2: 初审意见    │   │                       │
   │                           │   (Redline/评分)    │   │                       │
   │                           │                     │   │                       │
   │                           └─────────────────────┴──>│ Stage 3: 终审         │
   │                                                     │   (整合 1+2 后给意见)  │
   │                                                     │                       │
   │<────────────────────── 终审意见 ────────────────────┘                       │
   │                                                                             │
   │ 执行（按终审意见落 commit）                                                  │
```

1. **Stage 1 — 方案设计（执行者出）**
   执行者产出执行手册草案 `docs/plans/v0.X.Y-*.md`，包含范围 / 红线 / 验收 / commit 序列。

2. **Stage 2 — 辅助 AI 初审**
   用户把 Stage 1 草案分发给辅助 AI 评审组，收集 Redline / 评分 / 风险点。
   执行者此阶段不参与（不打扰评审独立性）。

3. **Stage 3 — 守护者终审（上一 MINOR Agent）**
   用户把 **Stage 1 草案 + Stage 2 初审意见**一起喂给守护者。
   守护者职责：
   - 校验与上一 MINOR / 历史 PATCH 的设计决策一致性
   - 查漏检文件 / 错误命名 / 既有红线遗漏
   - 评估初审意见是否被正确吸收
   - 给出**终审意见**（保留 / 修订 / 否决具体条款）
   守护者**严禁直接修改方案文件或代码**，只输出评审文本。

4. **执行（执行者落地）**
   执行者**只拿到 Stage 3 终审意见**（不直接看 Stage 2 原文，避免重复消化），
   按终审意见整合修订手册 → commit 锁定 → 按 commit 序列实施 → 全闸门绿 → 提 PR。

#### MINOR 滚动前夕整体审核（v3 新增仪式）

- **触发**：资深架构师明确 announce「整体审核」
- **参与方**：执行者 + 守护者 + 所有存活的远古守护者（独立提供意见）
- **不在 PATCH 内**，是 MINOR 间的过渡仪式
- **产物 4 份固定模板**：
  1. **代码结构评估** — 巨型文件 / 重复 / 死代码 / 可读性短板
  2. **奥卡姆剃刀清单** — 必备 / 多余 / 待简化
  3. **重命名 / 重构 / 协议增量提案**
  4. **下一 MINOR 预期范围**（骨架，不锁定）
- **冲突仲裁**：多方意见独立提供，资深架构师拍板

#### 远古守护者激活原则

- 默认沉睡（不打扰当前 PATCH 节奏）
- 仅在「整体审核」明确激活
- 不参与日常 PATCH 三阶段评审

#### 角色滚动规则

每跨一个 MINOR：
- **当前执行者** → 下一 MINOR 的**守护者**（只读 active）
- **当前守护者** → 下一 MINOR 的**远古守护者**（保留对话，dormant）
- 已存在的远古守护者 → 继续保留 dormant
- 用户开**新对话**启动下一 MINOR 的**新执行者**

PATCH 内（v0.5.0 → v0.5.1 → …）**不切换角色**，仍由同一执行者完成所有 PATCH 的三阶段循环。

#### v3 协议施行历史

- v2（v0.4.x 期间生效）：3 角色（执行者 + 守护者 + 辅助 AI 初审组）
- v3（v0.5.0 起生效）：+ 远古守护者 + 整体审核仪式
- 首次整体审核：v0.4.6 → v0.5.0 滚动前夕（执行者 v0.4 + 守护者 v0.3，因 v0.3 之前无 v3 协议未存远古守护者）
- 第二次整体审核：v0.5.44 → v0.6.0 滚动前夕（执行者 v0.5 + 守护者 v0.4 + 远古守护者 v0.3）→ 产出 9 项 LOCKED 决议 S-1~S-9 → v0.6 Agent 启动 Phase A

**v3 协议施行回顾**（v0.5.0~v0.6.0 累计 26 次完整 PATCH 内施行；首次跨 MINOR 角色滚动后施行 = v0.6.0）：

| PATCH | 主题 | 红线 | 关键决策 / 施行特征 |
|---|---|---|---|
| v0.5.0 | KNOT rename + Foundation | R-67~R-79 (13) | 包名 / env 双源 / DB migration / Loop Protocol v3 **首次完整施行** |
| v0.5.1 | SQL AST 笛卡尔积硬防御 | R-80~R-93 (14) | sqlglot AST + ReAct `__REJECT_CARTESIAN__` + R-91 计数器 |
| v0.5.2 | 后端代码瘦身 | R-94~R-110 (17) | **27 文件行数压制**（4 主 ≤ 350/300/220/220 + 9 新建 ≤ 250 + scripts/check_file_sizes.py CI 核验）；sync/async 双胞胎保守不合并；orchestrator 方案 1 延迟 import 破单向依赖 |
| v0.5.3 | 前端代码瘦身 | R-111~R-128 (18) | Chat.jsx 925 → ≤ 350；Admin tab 7→4 文件按职责合并；className 0 diff 守护；R-118 SSE handler 纯函数化 callbacks 注入 |
| v0.5.4 | Loop Protocol v3 路线图同步 | R-129~R-138 (10) | docs-only；**第 5 次 v3 施行**（自我引用闭环 — 用 v3 协议同步 v3 协议）；README 加 protocol 简介对外公开治理 |
| v0.5.5 | Cn cleanup（遗留清理） | R-139~R-153 (15) | **首次净行数减少（Negative Delta -18）**；物理删 `lark.py` stub；8 处 sync API 标 `[DEPRECATED v0.5.5; target removal in v1.0]`；测试受控降级 432→430；**第 6 次 v3 施行** |
| v0.5.6 | C5 Claude Design UI 重构 — Foundation | R-154~R-169 (16) | **第二次 Negative Delta -136**；Shared.jsx + utils.jsx + App.css 视觉重构 — OKLCH 蓝青 195° brand + PingFang/HarmonyOS 字体 + Icon viewBox 24 stroke 1.6；R-167 语义色翠绿 145°/琥珀 85° 远离 brand；R-169 CHART_COLORS hue 45° 均匀分布；R-156 18 屏 0 修改自动换皮；R-158/159 Shared/utils 契约 9+8 exports byte-equal；**第 7 次 v3 施行** |
| v0.5.7 | C5+ Login 屏首屏复刻 pilot | R-170~R-186 (17) | **1 屏 1 PATCH 模式确立**；Shared.jsx +3 exports (KnotMark/Wordmark/Logo) 9→12；decor/NarrativeMotif.jsx [NEW 112 行] React.memo + OKLCH color-mix tint；Login.jsx 116→178 demo grid 1.05fr 1fr + KNOT tagline + "进入 KNOT" + "7 天内自动登录" + 页脚 v0.5.7；R-184 input focus 蓝青；R-186 抗诱惑 — Shell.jsx 严守 0 改；R-181 三处版本同步（main.py + smoke + Login 页脚）；432 tests / 112 skipped；**第 8 次 v3 施行** |
| v0.5.8 | Cn+ Chore — CI fix + Visual Replication Protocol | R-187~R-191 (5) | docs+ci chore；偿还 v0.5.0 R-72 留下的 ci.yml boot smoke 硬编 0.5.0 bug（R-187 动态读 main.py）；CLAUDE.md 加 § Visual Replication Protocol 段（R-188）提炼 v0.5.7 经验为 v0.5.8+ 屏复刻铺路；432 tests / 112 skipped 不变；7 contracts KEPT；**第 9 次 v3 施行**（简化 — 跳 Stage 2/3 直接 Stage 4，资深 ack） |
| v0.5.9 | C5+ Shell 屏复刻（首个真正屏复刻） | R-192~R-213 (22) | **宪法级 R-192 AppShell 13 props 签名 byte-equal** 三方共识；Shell.jsx 172→186 视觉重构 7 子步骤：sidebar 256→224 + ellipsis（R-198 + Q2 加码）/ KnotLogo size=20 替代 sparkle+KNOT 文字（R-199 + Q1 修订 16→20，**R-186 抗诱惑首次解禁**）/ logoArea 56px borderBottom（R-200）/ user row #ff7a3a 渐变 → 纯 T.accent（R-201 + R-211 全局净空）/ admin nav 3 emoji 偿还（R-202 — 💰/🛡️/📋 → I.zap/I.shield/I.book）/ NavItem active span 右侧（R-203 + Q4 防 overflow:hidden 裁切）/ SideHeading T.mono（R-204）；R-199.5 KnotLogo 仅限 Shared+Login+Shell 三文件；R-210 CSS 0 污染（App.css 0 行 diff）；R-213 Shell.jsx 严禁 version 字面；R-207 17 屏 + 12 子模块 byte-equal；432 tests / 112 skipped；7 contracts KEPT；72 routes；**第 10 次 v3 施行**（恢复全 v3 — 视觉重构不适用简化协议） |
| v0.5.10 | C5+ Home 屏复刻（首个 chat 子模块屏复刻） | R-214~R-239 (27 含 R-227.5) | ChatEmpty.jsx 40→80 行 = R-218 上限；6 子步骤：容器 0 80 + 10vh 黄金分割（R-239）/ "knot · ready" label + color-mix oklch ring（R-229 + Q2 严禁 hex alpha）/ 标题 36px + "解" brand span + word-break keep-all + maxWidth 640（R-230 + R-224 + R-236 + Q1）/ 副标题新文案 + KNOT 大写（R-231）/ suggestions 扩 {icon,text} 硬编码映射 + chip 44 + radius 10 + flex-wrap（R-232/233/235/238）/ Footer T.mono（R-234）；契约 R-214 9 props 签名 byte-equal + R-215 firstName + R-216 text + **R-217 Composer.jsx 0 改**（三方共识，留 v0.5.11+）；**R-227.5 KNOT 字面分流首次确立**（"knot · ready" 装饰小写 vs "KNOT 可能出错" 声明大写共存）；R-222 KnotLogo sustained 仅 3 文件；R-225 CSS 0 污染；R-237 firstName 兜底三态；R-238 4 icon 语义映射；432 tests / 112 skipped；7 contracts KEPT；72 routes；**第 11 次 v3 施行**（全 v3） |
| v0.5.11 | C5+ Composer 重构 — **R-217 清偿里程碑** | R-240~R-265 (26) | Composer.jsx 71→100 = R-260 上限；7 子步骤：boxShadow 双模式 T.dark 切换（R-254/Q2 rgba 豁免）/ 容器 T.inputBg → T.content（R-252/D1 不扩 25 字段）/ padding 16 + **width 100% Q3 解耦严禁 720**（R-253/D5 修订）/ textarea minHeight 24→48（R-257/263）/ Submit 30→32 + disabled opacity 0.5（R-256/262）/ Footer hint "Enter 发送 · Shift+Enter 换行" mono + brand dot（R-255/Q4 去 Unicode）/ focus-within React state useState + onFocus/onBlur + transition 200ms + border T.accentSoft + shadow 微放大 color-mix oklch（R-261）；契约 R-240 Composer 9 props 签名 byte-equal + R-241~R-246 placeholder/activeUpload/handlers/disabled/autoresize/上传 6 业务逻辑；**R-251 视觉自动跟随设计模式首次确立** — ChatEmpty + Conversation git hash 0 漂移（R-264 diff --stat = 0 files）— 改一处惠及两屏无代价；R-259 R-217 解禁范围限定（仅 Composer 一处）；R-250 KnotLogo sustained 仅 3 文件；R-258 CSS 0 污染；432 tests / 112 skipped；7 contracts KEPT；72 routes；**第 12 次 v3 施行**；**R-217 自 v0.5.10 hold 至今正式清偿** |
| v0.5.12 | C5+ Thinking 屏复刻（AgentThinkingPanel 右 rail） | R-266~R-291 (27 含 R-227.5.1) | ThinkingCard.jsx 110→160 = R-270 上限；9 子步骤：letter chip K/N/O 22×22 Inter 800 flex 居中（R-277/289）/ emoji→chip + name 字面 Knowledge/Nexus/Objective mono（R-277/278/**R-227.5.1 单字母装饰豁免首次确立**）/ Panel 272→320（R-276/288 — Conversation 无 margin-right 字面方案 A 适用）/ 卡片 bg T.card→T.content + radius 8→10 + padding 12（R-279/283）/ Header step count "N/3 STEPS" + `transition cubic-bezier(0.4, 0, 0.2, 1) 0.3s`（R-280/287）/ done svg checkmark 11×11 stroke 2.5 + T.success（R-281）保 TypingDots + ○ / sqlSteps tag chip + slice 80→120 + ellipsis 兜底（R-282）/ **R-286 hex 全面禁止首次确立**（#09AB3B/T.accent+'60'/#FF9900 → T.success / color-mix oklch / T.warn）/ R-290 SSE 鲁棒性 Array.isArray + 全 optional chaining 防三场景崩溃；契约 R-266 2 exports 签名 + R-267 AGENTS 3 keys + R-268 业务逻辑 byte-equal；R-291 Conversation.jsx 调用点字节码对齐 git diff = 0 行；范围 R-272/274/275/284 全 0 改；432 tests / 112 skipped；7 contracts KEPT；72 routes；**第 13 次 v3 施行**（全 v3） |
| v0.5.13 | C5+ ResultBlock 偿还（hex+emoji+token 受控） | R-292~R-316 (26 含 R-302.5) | ResultBlock.jsx 381→420 = R-307 上限（v0.5.3 R-111 400→420 资深 ack 微调；svg path 占行不可压）；9 子步骤受控：getErrorKindMeta(T, kind) helper（Q1 修订 useMemo→helper function 更解耦）/ RB_SVG 7 path 字典 + SvgPath helper（不动 Shared）/ AGENT_KIND_EMOJI 4 emoji → svg path（字典名+keys byte-equal）/ 收藏 ⭐🌟 → SvgPath star fill={pinned?T.accent:none} 双态（R-303/314）/ BudgetBanner 🛑⚠️ → SvgPath shield/triangle（R-304）/ ErrorBanner 7 emoji 保留（**R-302.5 语义级 Emoji 业务豁免首次确立** — 字面分流体系第三条 v0.5.10 R-227.5+v0.5.12 R-227.5.1+v0.5.13 R-302.5）/ Token meter → TokenPill chip mono 纯度（R-306/315）/ **R-286 hex 全清扩展至 ResultBlock**（v0.5.x hex 残留最重组件收尾） — 14 处 hex 字面（#cc6600/#FF990022/#FF9900/#fff/#0001/T.accent+'30'）全清 → T tokens + color-mix in oklch（R-312 精度）/ rgba 边界 R-313 仅 boxShadow；契约 R-292 7 props 签名 + R-293 msg 25 字段解构 byte-equal + R-294 ERROR_KIND 7 keys/icons/titles byte-equal + R-295 7 layout 分支 + R-296 resolveEffectiveHint/exportMessageCsv/MetricCard 业务 + R-297 5 handlers；范围 R-309 8 核心非屏 + 17 屏 + App.css 0 改 + R-310 chat/ 其他 6 子模块 0 改 + R-274/250 KnotLogo sustained 仅 3 文件；432 tests / 112 skipped；7 contracts KEPT；72 routes；**第 14 次 v3 施行**（全 v3） |
| v0.5.14 | C5+ ResultBlock 视觉大重构 — **v0.5.x 收官 + 三大设计先例** | R-317~R-344 (28) | ResultBlock.jsx 420→440 = R-332 上限 v0.5 **final ack**；7 子步骤：Observation card brandSoft inset + color-mix(in oklch, T.accent 8%, transparent) + svg info icon + "OBSERVATION" mono（Codex 8% 精确；**R-227.5.1 装饰豁免延伸**仅 Insight 容器其他屏"洞察"保中文）/ Suggestion chips height 28 + chevron + lineHeight 1 + outer `&& onFollowup` (R-342 conditional)/ **Token meter 反向修正 TokenPill→inline stat svg ↑↓**（**v0.5.13 R-306/315 受控撤回 — 红线撤回首例**；架构判定红线服从视觉真理；严格复刻 > 局部推测性红线）/ agent_costs chip pill 999 + bgInset border / Table thead 删 uppercase + Codex letter-spacing normal / SQL accordion `<>` T.mono 几何对称 + 时长 Codex flex:1 text-align right；**三大设计先例首次落地**：① 红线撤回首例 ② **R-341 v0.5 ResultBlock 行数收官**（440 final；v0.6 必须开启子组件拆分 MetricCard/TableContainer/InsightCard/BudgetBanner/ErrorBanner/TokenMeter）③ R-227.5.1 装饰豁免延伸；契约 R-317 7 props + R-318 msg 25 字段 + R-319 ERROR_KIND 7 keys + R-320 7 layout 分支 + R-321 业务逻辑 + R-322 5 handlers byte-equal；范围 R-334/335 全 0 改（SavedReports 0 改 — R-342 内嵌守护验证不直接 import 转化为 R-317 props 签名 + outer condition）；432 tests / 112 skipped；7 contracts KEPT；72 routes；**第 15 次 v3 施行**（全 v3）+ v0.5.x ResultBlock 维度收官之战 |
| v0.5.15 | C5+ Favorites 屏复刻 — **首个新顶层屏 + brandSoft 8% 全站闭环** | R-345~R-373 (29) | SavedReports.jsx 318→380 = R-363 上限正好（新增 LIMIT 380；首次纳入 30→31 条）；9 子步骤受控：起手 grep Q3 LIMIT dict 标定 / 5 处 hex 全清（pillBtn '#fff' → T.sendFg Q4 严禁 'white' / Warning #FF990022/#FF9900/#cc6600 → T.warn + color-mix / Error ${T.accent}30 → color-mix in oklch）/ SAVED_SVG 6 path 字典 + INTENT_EMOJI 字典名+7 keys byte-equal value 偿还 svg path / Sidebar header 删 📌 + T.mono / SavedItem bookmark svg 14×14 + gap 10（Codex R-369 精度）+ brandSoft bg + 删 borderLeft + time mono 9px "YYYY.MM.DD"（R-373 formatTime）/ Title block 22px fontWeight 600 + meta mono `│` U+2502 separator（R-370 字符精度）+ StatusDot frozen 装饰硬编（Q5 不依赖业务字段）/ Quote inset color-mix in oklch 8% **与 v0.5.14 R-323 ResultBlock Insight 字面 byte-equal**（**R-372 全站 brandSoft inset 设计语言闭环 — 未来全站 inset 沿用此字面**）+ "原始问题" mono uppercase / Table thead 删 uppercase + letter-spacing normal（v0.5.14 R-327 sustained）/ 4 按钮 emoji（✏️/🔄/📥/📊）→ SvgPath（pencil/refresh/download/table）+ pillBtn helper 保 disabled/loading 状态机；**D6 Shell 13 props 契约严守** — topbarTitle 仍传简单 string（不破 R-192 R-349 sustained）；视觉补偿全部在 Title block (R-355) — 22px + meta · + StatusDot frozen；契约 R-345 SavedReportsScreen 5 props 签名 byte-equal + R-346 4 helpers + R-347 5 handlers + R-348 INTENT_EMOJI 字典名+7 keys byte-equal（仅 value 偿还） + R-349 AppShell + R-350 api 5 endpoint URL；范围 R-365 App/api/main/utils/Shared/Shell/decor/16 屏/chat 7 子模块 0 改 + R-367 KnotLogo sustained 仅 3 文件 + R-368 CSS 0 污染；R-302.5 banner emoji 业务豁免 sustained（⚠️/🔍/❌）；432 tests / 112 skipped；7 contracts KEPT；72 routes；**第 16 次 v3 施行**（全 v3）+ v0.5.x 首个新顶层屏复刻 |
| v0.5.22 | C5+ admin tab_system 屏复刻（Catalog）— **⭐ Inset 8% 第九处扩张（7→8 文件）+ borderLeft 25% 第四处闭环 + 蓝色 hex 双残留偿还 + 自审简化协议首次** | R-551~R-580 (30) | tab_system.jsx 53→102 行；LIMITS dict 不动；5 sub-step（R-580 前置 + R-556 优先 + R-571 收尾）；**⭐ Inset 8% 闭环字面文件总数 7→8 第九处扩张**（admin/tab_system 加入）；**borderLeft 25% 第四处闭环**（SavedReports + AdminBudgets + AdminRecovery + tab_system Helper banner 4 文件 byte-equal）；**v0.5.x 第三个 admin tab 子模块复刻**（tab_access + tab_resources + tab_system）；**蓝色 hex 双残留偿还**（rgba(43,127,255,0.12) + #2B7FFF + #fff — v0.5.16~21 蓝色 hex 唯一残留正式清零）；R-580 R-548 核爆守护扩展（TabSystem 6 props + Admin.jsx 挂载点 byte-equal）；D2 双兼模式延伸（保 textarea 业务 + 借 demo Helper banner brand inset + Section number chip）；NumChip + OverrideChip helpers inline 第七次复用 sustained；契约 R-551 6 props + R-552 catalog 5 字段 + R-553 3 sections keys + R-554 overrides 业务逻辑 byte-equal；**⭐ 自审简化协议首次** — 资深 ack 授权 v0.5.x 收官冲刺（Stage 1 草案预纳入 Stage 2/3 候选；Stage 4 直接落地）；432 tests / 112 skipped；7 contracts KEPT；72 routes；**已偿还** 30 红线 R-551~R-580；**四大里程碑同时落地**（Inset 8% 第九处 + borderLeft 25% 第四处 + 蓝色 hex 偿还 + 自审简化协议首次）。 |
| v0.5.21 | C5+ admin tab_resources 屏复刻 — **⭐ Inset 8% 铁律进攻性扩张第八处（文件总数 6→7）+ 项目单色化一致性 80% 深度宣告 + R-546~R-550 五大守护立约** | R-521~R-550 (30) | tab_resources.jsx 85→110 行 ≤ 250 LIMIT（dict 不动）；5 子步骤顺序锁死（R-548 前置 + R-531 优先 + R-539 收尾）：① baseline + **R-548 起手前置签名核爆守护**（grep `export function TabResources` + grep `<TabResources` Admin.jsx 挂载点 byte-equal）+ **R-531 thead bg R-480 闭环字面率先落地**（铁律进攻性扩张第八处）+ R-537 hex 余效 grep 立即执行 ② API Keys Card padding `'16px 20px'→'20px 22px'` + radius 10→12 + Card header `fontSize 12.5→14 + letterSpacing -0.01em` + desc lineHeight 1.55 + **R-529 trailingChip helper**（fontSize 10 + T.mono + letterSpacing 0.06em + uppercase — "已填写/未填写" 工业感）+ **R-547 API Key 安全感**（trailing 在 password 遮罩下可见）③ Agent allocation Card padding/radius 升级 + 3-col grid `'120px 1fr 80px'→'120px 1fr 90px'` + **D4 plain span hint byte-equal**（管理端可读性优先，不引入 TagChip）④ Models Table thead **R-532 mono + 0.06em + uppercase + fontWeight 500 + T.subtext** + Row minWidth: 0 + ellipsis 兜底（5 字段列）+ **R-546 Model ID `fontFamily: T.mono`**（技术元数据识别度）+ **R-549 价格业务标签 $ 单位保留**（`${m.input_price}/{m.output_price}` byte-equal）+ **R-550 borderBottom `1px solid ${T.border}` byte-equal**（与 tab_access / tab_knowledge 字面一致 — 设计语言铁律第三维度候选）⑤ **R-536 Hex 偿还** Spinner `color="#fff"` 2 处 → `color={T.sendFg}`（R-484 sustained）+ 三处版本同步 0.5.20→0.5.21 + R-540 字面严防 + **⭐ R-539 7 文件验证**（`git grep -F` 命中 ResultBlock/SavedReports/admin/tab_access/AdminAudit/AdminBudgets/AdminRecovery/**admin/tab_resources** 7 文件）；**⭐ Inset 8% 铁律从"防御性稳固"转向"进攻性扩张"**（v0.5.20 R-511 6 文件恒定 → v0.5.21 R-539 文件总数 6→7 正式扩张）；**项目单色化一致性进入 80% 深度**（Stage 3 §3 里程碑宣告）；**v0.5.x 第二个 admin tab 子模块复刻**（v0.5.16 tab_access + v0.5.21 tab_resources）；**R-484 'white' 字面残留偿还**（Spinner color #fff 2 处）；**R-546/547/548/549/550 五大守护立约**（Model ID Mono / API Key 安全感 / 核爆级 props / 价格业务标签 / borderBottom byte-equal）；**Card/TagChip/trailingChip helpers inline 第六次复用 sustained** — v0.6 Shared 移植承诺加强（累计 8+ inline helpers）；契约 R-521 12 props 签名 byte-equal + R-522 apiKeys 2 keys + R-523 agentCfg 3 keys + R-524 model 8 字段 + R-525 Input 调用 + R-526 pillBtn 调用 byte-equal（R-365 sustained）；范围 R-541 App/api/index.css/main/utils/Shared/Shell/decor/18 屏 + Admin/SavedReports/AdminAudit/AdminBudgets/AdminRecovery 0 改 + R-542 admin/ 其他 3 子模块 + modals + chat/ 7 子模块 0 改 + R-543 App.css 0 行 diff + R-544 KnotLogo sustained 仅 3 文件 + **R-548 sustained Admin.jsx 内 `<TabResources` 挂载点 0 改**；字面分流体系 sustained — R-302.5 全清 + R-227.5.1 thead 中文 + trailingChip mono uppercase 装饰豁免；R-286 hex 0 命中扩展 v0.5.13~v0.5.21 九 PATCH sustained；R-313 rgba 豁免边界 sustained；432 tests / 112 skipped；7 contracts KEPT；72 routes；**已偿还** 30 红线 R-521~R-550（25+2+3）；**六大里程碑同时落地**（⭐ Inset 8% 铁律进攻性扩张 + 80% 深度宣告 + v0.5.x 第二个 admin tab 子模块复刻 + R-484 'white' 残留偿还 + R-546~R-550 五大守护立约 + Card/TagChip v0.6 Shared 移植加强）。 |
| v0.5.20 | Cn+ admin/users 视觉偿还 — **⭐ R-376 hex 债务正式清偿 + TabAccess 全 OKLCH/T-System 时代 + Inset 8% 闭环第七处扩展（6 文件恒定深耕）** | R-496~R-520 (25) | tab_access.jsx 88→90 行；LIMITS dict 不动（250 远未触达）；4 子步骤顺序锁死（R-501/R-504 优先 Step 1）：① baseline + R-501 Avatar brandSoft 8% 字面落地 + R-504 thead bg 升级 + **R-518 R-376 余效 grep 立即执行**（hex 0 严格 ✓）② Avatar **26→22** + T.accent 字母 + inline-flex 居中 + **R-516 lineHeight:1 + fontSize:10.5 + flexShrink:0**（与 AdminAudit R-410 + AdminRecovery R-479 字面 byte-equal）③ thead **mono + 0.06em + uppercase + fontWeight 500 + T.subtext** + Row minWidth:0 + ellipsis 兜底 + **R-517 场景 B 确认**（Sources 无 hover → Users 不引入避免不对称）④ 三处版本同步 0.5.19→0.5.20 + **R-511 6 文件恒定** git grep -F + **R-512+R-519 Sources 绝对零度** md5(Sources 段) byte-equal `3593b6b0edfca69eb28b39c628f62d74` + **R-520 roleChip 不动**；**⭐ R-376 hex 债务正式清偿** — `linear-gradient(135deg, ${T.accent}, #ff7a3a)` → `color-mix(in oklch, ${T.accent} 8%, transparent)` + `color: '#fff'` → `color: T.accent`（v0.5.16 hold 4 PATCH 偿还 — **v0.5.x 最长 hold 历史性纪录**）；**⭐ TabAccess 模块正式进入全 OKLCH/T-System 时代**（Stage 3 §3 里程碑宣告）；**Inset 8% 闭环第七处扩展** — 6 文件恒定深耕（v0.5.14/15/16/17/18/19/20 — `git grep -F` 命中文件总数恒定 6；tab_access 内部命中数 1→3）；**R-518 R-376 余效验证立约**（v0.5.x 视觉治理硬指标制度化）；**R-519 Sources 绝对零度**（IDE format-on-save 关闭纪律确立 + md5 字节相同验证）；**R-520 roleChip 装饰豁免界限**（父屏 props 函数调用允许重构 + 定义严禁触碰 + v0.5.16 业务字段不动红线延续）；**R-516 Avatar 跨浏览器精度**（inline-flex + lineHeight:1 + fontSize:10.5 三件套）；**Avatar inline 第四次复用确认** — 累计 7+ inline helpers（StatusDot/ActionChip/BudgetActionChip/EnabledChip/WarnNote/KpiCard/PeriodTab/TagChip/trophy/medal/**Avatar**）v0.6.0 Shared 移植承诺**加强**；契约 R-496 TabAccess 9 props 签名 + R-497 u 5 字段（id/display_name/username/role/is_active）+ R-498 roleChip(u.role) + R-499 onEditUser(u)/onDeleteUser(u.id) byte-equal；范围 R-513 App/api/index.css/main/utils/Shared/Shell/decor/17 屏 + Admin/SavedReports/AdminAudit/AdminBudgets/AdminRecovery 0 改 + R-514 admin/ 其他 4 子模块 + chat/ 7 子模块 0 改 + R-520 Admin.jsx 内 roleChip 定义 0 改；字面分流体系 sustained — R-302.5 全清（本 PATCH 无 emoji）+ R-227.5.1 thead 中文 + roleChip 装饰豁免；R-286 hex 0 命中扩展 v0.5.13~v0.5.20 八 PATCH sustained；R-313 rgba 豁免边界 sustained（无新增豁免）；432 tests / 112 skipped；7 contracts KEPT；72 routes；**已偿还** 25 红线 R-496~R-520（20+2+3）；**四大里程碑同时落地**（⭐ R-376 hex 债务正式清偿 v0.5.x 最长 hold 历史性纪录 + ⭐ TabAccess 全 OKLCH/T-System 时代 + Inset 8% 第七处扩展 6 文件恒定深耕 + R-518/519/520 守护立约 + Avatar v0.6 Shared 移植承诺加强）。 |
| v0.5.19 | C5+ AdminRecovery 屏复刻 — **⭐ admin 顶层屏三部曲收官 + Inset 8% 闭环第六处铁律加冕 + borderLeft 25% 第三处闭环铁律加冕 + R-495 字面严防立约** | R-466~R-495 (30) | AdminRecovery.jsx 152→242 行 ≤ R-490 LIMIT 380（新增 LIMITS dict 33→34 条）；9 子步骤顺序锁死（**R-480 优先 Step 1 — 视觉铁律第六处加冕**）：① R-480 brandSoft 8% 闭环字面率先落地（thead + Avatar + Rules note）② Topbar 删 🛡️ ③ **PeriodTab inline helper** + **R-492 active box-shadow color-mix 20% 选中浮起感** + mono + brandSoft active + minHeight 30 + borderRadius 6（D1 R-192 13 props 宪法级 sustained — 时段 tabs 不移 topbar）④ **KPI 3 cards grid** + **KpiCard inline helper** + **R-491 transition color 0.2s**（加载→数据态平滑变色）+ **R-474 第 3 卡 accent**（自纠正率 T.accent + fontWeight 700 + 34px）+ R-394 auto-fit ⑤ **Chart card** — svg chart icon header + **Q1 动态 Tag chip `PERIOD_LABELS[period]` → last 7/30/90 days** + **D2 R-365 LineChart from Shared 字面 byte-equal** + **R-494 height={280}**（90d 大数据折线清晰）+ empty state R-19 提示 ⑥ Top user table HTML 全删 → **CSS Grid 5-col `64px 1.4fr 1fr 1fr 1fr`**（#/User/自纠正次数/消息数/自纠正率）+ thead 视觉应用 R-480（第二处命中）+ **Q2 VRP 局部例外 inline trophy svg path**（circle 8 + medal ribbon — Shared 无 I.medal；v0.6 偿还）+ TagChip top N + **R-479 row**（rank `#` mono T.accent fontWeight 600 + Avatar 22 brandSoft + username + id mono）+ **R-493 NaN 守护**（`u.msg_count ? ((u.count / u.msg_count) * 100).toFixed(1) + '%' : '0.0%'` 防 NaN%）⑦ Rules note 2 条 brandSoft inset + **R-481 borderLeft 3px 25% 第三处闭环铁律加冕**（与 SavedReports R-356 + AdminBudgets R-465 字面 byte-equal — 设计语言铁律第二维度）+ TagChip helper + 📌 删 ⑧ emoji 🛡️/📈/🏆/📌 全清 + hex 0 命中（除 boxShadow + rgba）+ R-484 sustained 严禁 'white' ⑨ **R-495 字面 byte-equal 严防死守立约** — `git grep -F` 双闭环 6+3 文件 byte-equal（任何空格/逗号差异 reset 重写）+ 三处版本同步 0.5.18→0.5.19；**⭐ admin 顶层屏三部曲收官**（v0.5.17 Audit + v0.5.18 Budgets + v0.5.19 Recovery — 视觉一致性 100% 覆盖）；**Inset 8% 闭环字面 6 屏 byte-equal**（v0.5.14 R-323 ResultBlock + v0.5.15 R-372 SavedReports + v0.5.16 R-386 tab_access + v0.5.17 R-409 AdminAudit + v0.5.18 R-444 AdminBudgets + **v0.5.19 R-480 AdminRecovery**）— 视觉铁律加冕里程碑；**borderLeft 25% 闭环字面 3 屏 byte-equal**（v0.5.15 R-356 + v0.5.18 R-465 + **v0.5.19 R-481**）— 设计语言铁律第二维度加冕；**R-495 字面严防立约** — `git grep -F` 全站自动化校验制度化（视觉铁律执行从文档约束升级为工具链强制校验）；**Q2 VRP 局部例外原则**（Shared 无对应资产时 inline svg 允许；v0.6 Shared 解锁后 trophy/medal 纳入；累计第四次复用确认 → 偿还触发）；**技术债登记加强**（Q5）— KpiCard + PeriodTab + TagChip + trophy svg 累计第三次复用（自 v0.5.17 起 6+ inline helpers：StatusDot/ActionChip/BudgetActionChip/EnabledChip/WarnNote/KpiCard/PeriodTab/TagChip/medal/trophy）；v0.6.0 首个 PATCH 移入 Shared.jsx 偿还承诺**加强**；**D1 R-192 13 props 宪法级 sustained**（Shell.jsx git diff = 0 行）；**D2 R-365 Shared 0 改动绝对红线 sustained**（Shared.jsx git diff = 0 行）；契约 R-466 5 props + R-467 3 useState slots（period '30d' / stats null / loading true）+ R-468 api URL `/api/admin/recovery-stats?period=` + R-469 period 3 values ['7d', '30d', '90d'] + useEffect [period] + R-470 stats 10 业务字段（total_recovery_attempts/total_messages/period_days/by_day[].date+count/top_users[].user_id+username+count+msg_count）byte-equal；范围 R-485 App/api/index.css/main/utils/Shared/Shell/decor/13 屏 + Admin/SavedReports/tab_access/AdminAudit/AdminBudgets 0 改 + R-486 admin/ 4 子模块 0 改 + R-487 chat/ 7 子模块 0 改 + R-488 App.css 0 行 diff + R-489 KnotLogo sustained 仅 3 文件；字面分流体系 sustained — R-302.5 全清 + R-227.5.1 thead mono uppercase + TagChip mono uppercase + KPI label 中文 装饰豁免；R-286 hex 0 命中扩展 v0.5.13~v0.5.19 七 PATCH sustained；R-313 rgba 豁免边界 sustained；432 tests / 112 skipped；7 contracts KEPT；72 routes；**已偿还** 30 红线 R-466~R-495（25 Stage 1 + 2 Stage 2 + 3 Stage 3）；**五大里程碑同时落地**（⭐ admin 顶层屏三部曲收官 + Inset 8% 闭环第六处铁律加冕 + borderLeft 25% 第三处闭环铁律加冕 + R-495 字面严防立约 + Q2 VRP 局部例外原则 + 技术债登记加强）。 |
| v0.5.18 | C5+ AdminBudgets 屏复刻 — **v0.5.x 第三顶层屏 + Inset 8% 闭环铁律化 100% 覆盖后端管理资产屏 + borderLeft 25% 第二处闭环 + 技术债登记** | R-431~R-465 (35) | AdminBudgets.jsx 232→357 行 ≤ R-460 LIMIT 380（新增 LIMITS dict 32→33 条）；9 子步骤顺序锁死（**R-444 优先 Step 1 — 视觉铁律化覆盖里程碑**）：① baseline + LIMIT + **R-444 brandSoft 8% 闭环字面率先落地**（thead bg + Rules note bg + Tag chip）② Topbar 删 💰 emoji → "预算配置"（R-439）③ Hero usage card 4-stat grid `repeat(auto-fit, minmax(180px, 1fr))` + **Q1 修订部分聚合**（第 1 卡 `{budgets.length}` 真实聚合 + 3 卡 `—` mono placeholder + tooltip — 已配置预算项/本月已用 token/预计花费/本月使用率）+ **R-461 progress transition** `transition: 'width 0.3s ease-in-out'`（即使 0% 也含动效预留）+ 0/50%/100% mono ticks ④ Form labels **D2 双兼**（Label `作用范围 (Scope Type)` / `范围值 (Value)` / `预算类型 (Budget Type)` / `阈值 (Threshold)` / `超阈值动作 (Action)`）+ **R-462 Form Grid** `gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))'` + `gap: 16` + 重置 ghost + 创建/更新 primary T.accent+T.sendFg（R-450 严禁 'white'）+ emoji ✏️/➕ 删 ⑤ Table HTML `<table>/<thead>/<tbody>/<th>/<td>/<tr>` 全删 → CSS Grid 7-col `0.8fr 1fr 1.4fr 0.6fr 0.8fr 0.9fr 50px`（Scope/Value/类型/阈值/Action/Enabled/操作）+ thead 视觉应用 R-444 brandSoft 8% bg + T.subtext + mono + 0.06em + uppercase + fontWeight 500 ⑥ **BudgetActionChip inline helper**（v0.5.17 R-411/R-426 模式延伸）— `action === 'block' ? T.warn : T.accent` 2 色 + chip 三件套 `color-mix(in oklch, ${color} 12%, transparent)` bg + `padding: '2px 8px'` + `borderRadius: 4` + `fontWeight: 500` + fontSize 11 + T.mono ⑦ **EnabledChip inline helper**（v0.5.17 R-412 StatusDot pattern 延伸）— 6×6 圆 + `currentColor` + flexShrink: 0 + "已启用"/"已停用" 文字 + 内置 onClick={handleToggle} 取代原 ✓ on / ○ off emoji ⑧ Rules note 4 条（R-16/R-23/R-21/block）brandSoft inset + **R-465 borderLeft 3px 25% 第二处闭环** `borderLeft: \`3px solid color-mix(in oklch, ${T.accent} 25%, transparent)\`` **与 SavedReports v0.5.15 R-356 字面 byte-equal**（设计语言铁律第二维度）+ Tag chip mono uppercase + 📌 emoji 删 → 纯 Tag chip + **D9 修订 R-448 WarnNote**（warning emoji 偿还 → inline 14×14 svg 感叹号 + T.warn 文字 + brandSoft Warn 内嵌；用于 isLegacyScope + isBlockMisuse 双警告）+ grep `#[0-9a-fA-F]{3,6}` AdminBudgets \| grep -v boxShadow \| grep -v rgba = **0 命中** ✓（R-452）+ grep `💰\|✏️\|➕\|⚠️\|📌\|○` = **0 命中** ✓（R-453）⑨ 三处版本同步 0.5.17→0.5.18 + **R-463 R-21 守护手测**（legacy/block disabled）+ **R-464 CRUD 幂等手测**（创建/已更新/已删除 toast 三态）+ grep `rgba(` AdminBudgets = **0 命中** ✓（本 PATCH 无 modal/drawer）；**KNOT 视觉铁律宣告：Inset 8% 设计语言正式覆盖 100% 后端管理资产屏** — `color-mix(in oklch, ${T.accent} 8%, transparent)` 字面 5 屏 byte-equal（v0.5.14 R-323 ResultBlock + v0.5.15 R-372 SavedReports + v0.5.16 R-386 tab_access + v0.5.17 R-409 AdminAudit + **v0.5.18 R-444 AdminBudgets**）；`git grep` 命中 5 文件；**R-465 borderLeft 3px 25% 第二处闭环**（v0.5.15 R-356 SavedReports + v0.5.18 R-465 AdminBudgets 字面 byte-equal）— 设计语言铁律第二维度；**技术债正式登记**（D8/Q5）— BudgetActionChip + EnabledChip + StatusDot 累计第二次复用确认；v0.6.0 首个 PATCH 移入 Shared.jsx 偿还承诺（R-365 Shared 0 改动绝对红线 sustained）；**Q1 部分聚合先例**（Hero placeholder 模式进化：v0.5.16/17 全 `—` → v0.5.18 1 真+3 占位 — 视觉信息密度提升 + 不误导后端契约）；**D9 WarnNote 模式**（warning emoji 偿还新通用方案 — 14×14 inline svg 感叹号 + T.warn 文字 + brandSoft Warn 内嵌；未来全站 warning 沿用）；契约 R-431 5 props + R-432 4 useState + R-433 api 4 endpoint + R-434 3 常量（SCOPE_TYPES/BUDGET_TYPES/ACTIONS）+ R-435 SCOPE_HINT 3 keys + R-436 budget 7 字段+draft 5 字段 byte-equal + R-437 isLegacyScope/isBlockMisuse/canSubmit R-21 业务守护 byte-equal + R-438 4 handlers + 4 处 reload（R-23 实时性）byte-equal；范围 R-454 App/api/index.css/main/utils/Shared/Shell/decor/14 屏 + Admin/SavedReports/tab_access/AdminAudit/AdminRecovery 0 改 + R-455 admin/ 4 子模块 0 改 + R-456 chat/ 7 子模块 0 改 + R-457 App.css 0 行 diff + R-458 KnotLogo sustained 仅 3 文件；字面分流体系 sustained — R-302.5 全清 + R-227.5.1 thead+Tag chip mono uppercase 装饰豁免；R-286 hex 0 命中扩展 v0.5.13~v0.5.18 六 PATCH sustained；R-313 rgba 豁免边界 sustained（本 PATCH 无新增豁免）；432 tests / 112 skipped（CI 干净 env；本地 BIAGENT_MASTER_KEY R-74 预存在问题）；7 contracts KEPT；72 routes；**已偿还** 35 条红线 R-431~R-465（30 Stage 1 + 2 Stage 2 + 3 Stage 3）；**五大设计先例同时落地**（v0.5.x 第三顶层屏 + Inset 8% 闭环铁律化 100% 覆盖后端管理资产屏 + borderLeft 25% 第二处闭环 + 技术债登记 + Q1 部分聚合 + D9 WarnNote）；**待人测**：① 进 admin → 切 admin-budgets → loading → budgets 加载 ② Hero 第 1 卡 budgets.length 真实 + 3 卡 — + tooltip + 进度条 transition 预留 ③ Form D2 双兼 ④ **R-463 R-21 legacy/block 双场景 WarnNote + disabled** ⑤ **R-464 CRUD 幂等三态 toast**（已创建/已更新/已删除）⑥ EnabledChip 切换 ⑦ **三档窗宽**（1024/1280/1920）⑧ **light+dark 双模式** ⑨ **Inset 8% 5 屏视觉一致**（ResultBlock/SavedReports/DataSources/AdminAudit/AdminBudgets）⑩ **R-461 进度条 dev tools width 测试**。 |
| v0.5.17 | C5+ AdminAudit 屏复刻 — **v0.5.x 第二顶层屏 + Inset 8% 闭环铁律化 + rgba 豁免架构原则确立** | R-399~R-430 (32) | AdminAudit.jsx 264→372 行 ≤ R-425 LIMIT 380（新增 LIMITS dict 31→32 条）；9 子步骤顺序锁死（R-409 优先 Step 1 — 铁律化里程碑）：① baseline + LIMIT + **R-409 brandSoft 8% 闭环字面率先落地** ② Topbar 删 📋 emoji ③ Stat 4-card grid + R-394 auto-fit + Q1 tooltip placeholder (4 inline cards grep ≥4) ④ Filter strip + **D2 双兼模式** Label `操作人 (Actor ID)` + Placeholder `输入用户 ID...`（业务字段 + Demo 风格平衡）+ 重置/查询双按钮 ⑤ Table HTML `<table>/<thead>/<tbody>/<th>/<td>/<tr>` 全删 → CSS Grid 7-col `1.4fr 1fr 1.3fr 2fr 0.7fr 0.6fr 60px` + thead 视觉应用 R-409 ⑥ Avatar 22 brandSoft + role chip mono + **ActionChip helper**（R-411 actionColor + R-426 color-mix 12% bg + padding 2px 8px + radius 4 + fontWeight 500）⑦ **StatusDot inline helper**（v0.6 候选移入 Shared）+ **R-428 actor null check** `actor_name \|\| actor_id \|\| 'System'` ⑧ Pagination + **R-430 边界 disabled**（page===1 / items.length<size）+ Redacted hex 全清 → `color-mix(in oklch, ${T.warn} 20%, transparent)` + **R-427 cursor:help** "敏感字段已脱敏" + **R-429 DetailJsonView try-catch 畸形 JSON 兜底**（防主界面卡死）⑨ **R-415 R-313 sustained 扩展豁免 #2** — drawer overlay `rgba(0,0,0,0.4)` evidence 注释（Chrome<111 / WebKit backdrop-filter OKLCH→sRGB GPU 渲染抖动；rgba 全平台稳健）；**R-409 brandSoft 8% 闭环字面 4 屏 byte-equal**（v0.5.14 R-323 ResultBlock + v0.5.15 R-372 SavedReports + v0.5.16 R-386 tab_access + **v0.5.17 R-409 AdminAudit**）— **视觉规范铁律化里程碑**；**R-313 rgba 豁免架构原则**：两处豁免（v0.5.11 R-254 boxShadow + v0.5.17 R-415 modal overlay）；**StatusDot 首次 inline 抽取**（v0.6 候选）；**D2 双兼模式**（防 admin 混淆 actor_id 与 username）；契约 R-399 5 props + R-400 6 useState + R-401 api URL + 4 filter params + R-402 _PAGE_SIZES/_REDACTED_RE + R-403 row 13 字段访问 byte-equal；范围 R-419 App/api/main/utils/Shared/Shell/decor/15 屏/Admin/SavedReports/tab_access 0 改 + R-420 admin/ 4 子模块 0 改 + R-421 chat/ 7 子模块 0 改 + R-422 App.css 0 行 diff + R-423 KnotLogo sustained 仅 3 文件；R-418 hex 0 命中（除 boxShadow + rgba 豁免）+ R-415 rgba 仅 1 命中（drawer overlay）；432 tests / 112 skipped（CI 干净 env；本地 BIAGENT_MASTER_KEY 残留 R-74 预存在问题）；7 contracts KEPT；72 routes；**已偿还** 32 条红线 R-399~R-430（27 Stage 1 + 2 Stage 2 + 3 Stage 3）；**第 18 次 v3 施行**（全 v3）+ **五大设计先例同时落地**（v0.5.x 第二顶层屏 + Inset 8% 闭环铁律化 + rgba 豁免架构原则 + StatusDot 首次抽取 + R-428~R-430 复杂业务屏守护 + D2 双兼模式）。 |
| v0.5.16 | C5+ DataSources 屏复刻（tab_access Sources 部分）— **首个 admin tab 子模块复刻 + Inset 8% 三处闭环 + I.db 复用先例** | R-374~R-398 (25) | tab_access.jsx 60→88 行 ≤ R-387 110 行预算（LIMIT 250 远未触达；不动 dict）；9 子步骤受控：① baseline diff 标定 Users (L9-33) / Sources (L35-57) 边界 → R-376 准备 ② Summary grid 4 卡片 `repeat(auto-fit, minmax(180px, 1fr))` 替代 media query（R-394 Stage 2 Codex）+ 已连接实数 + 3 placeholder '—' mono + `title="后端数据对接中 (v0.6+)"` tooltip（Q1 加码）③ Table 容器 radius 10→12 ④ thead bg → `color-mix(in oklch, ${T.accent} 8%, transparent)` + T.mono + letterSpacing 0.06em + fontWeight 600→500 + 保 uppercase（R-381；v0.5.14 R-327 删 uppercase 仅对 ResultBlock）⑤ Grid 5→6 列 `1.2fr 0.8fr 1.4fr 0.6fr 0.8fr 80px` + 表数 '—' placeholder + tooltip ⑥ Name 28×28 brandSoft + `<I.db width="14" height="14"/>` **复用 Shared.jsx 既有图标**（R-383 + Q3 修订 — v0.5.x 资产复用首例）+ flex 绝对居中 R-397 ⑦ Type inline chip — brandSoft 8% bg + T.accent color + padding 2 8 + radius 999 + 11px + letterSpacing 0.02em + T.mono（R-384/395 Stage 2 Codex 工业感）⑧ 每列 minWidth: 0 (5 处) + textOverflow ellipsis (4 处) 兜底（R-396 Stage 3 列宽稳定性）⑨ StatusDot 颜色 `s.status === 'online' ? T.success : T.warn` byte-equal sustained + flexShrink: 0（R-398 Stage 3 语义粘性）；**R-376 Users 部分 L9-33 字面零修改 — Stage 2/3 双重强制 out-of-scope**（含 `#ff7a3a` 渐变残留保留；hex 残留偿还推未来独立 admin/users PATCH；`git diff` L9-33 段 0 行）；**R-386 brandSoft 8% 全站第三处闭环** — `color-mix(in oklch, ${T.accent} 8%, transparent)` 字面与 v0.5.14 R-323 (ResultBlock Observation) + v0.5.15 R-372 (SavedReports Quote) byte-equal；**I.db 复用先例** — v0.5.13/14/15 inline svg dict 模式 → 本 PATCH 优先复用 Shared.jsx `I.*`；R-385 Sources hex 0 命中（grep `#[0-9a-fA-F]{3,6}` 排除 boxShadow 0 hits）；契约 R-374 TabAccess 8 props 签名 byte-equal + R-375 users/sources 数据流 + 5 handlers + roleChip + R-377 Sources 业务字段（s.name/db_type/db_host/db_port/db_database/status）byte-equal；范围 R-389 App/api/index.css/main/utils/Shared/Shell/decor/16 屏/Admin/SavedReports 0 改 + R-390 admin/ 其他 4 子模块 0 改 + R-391 chat/ 7 子模块 0 改 + R-393 KnotLogo R-199.5/222 sustained 仅 3 文件 + App.css 0 行 diff；字面分流体系 sustained — R-302.5/R-227.5.1；R-286 hex 0 命中扩展 v0.5.12~v0.5.16 五 PATCH；432 tests / 112 skipped；7 contracts KEPT；72 routes；**已偿还** 25 条红线 R-374~R-398（20 Stage 1 + 2 Stage 2 + 3 Stage 3）；**第 17 次 v3 施行**（全 v3）+ **首个 admin tab 子模块复刻 + Inset 8% 三处闭环 + I.db 复用先例**三大设计先例同时落地。 |


## § Visual Replication Protocol（v0.5.7+ 屏复刻通用约束）

> **触发**：v0.5.7 起每个屏复刻 PATCH（home / shell / thinking / favorites / 9 admin tabs）
> **依据**：v0.5.7 Login pilot 实证经验提炼；适用于 v0.5.8+ 17 屏渐进复刻
> **与 Loop Protocol v3 关系**：本协议是视觉复刻专项约束，**不替代** v3 三阶段评审；每屏 PATCH 仍走 Stage 1+2+3+4

### 路径常量

- **Demo 设计稿**：`/Users/kk/Documents/knot_ui_demo/v0.5/artboards/*.jsx`（设计代理，**不进产品**）
- **产品屏**：`frontend/src/screens/*.jsx`
- **共享 Foundation**（v0.5.6 + v0.5.7 落地）：
  - `Shared.jsx` — buildTheme(dark) 25 字段 + I 36 icons + iconBtn/pillBtn + CHART_COLORS 8 色 + LineChart/BarChart/PieChart/TypingDots + KnotMark/KnotWordmark/KnotLogo 三件套
  - `utils.jsx` — Modal/ModalHeader/Input/Select/Spinner/toast/useTheme/usePersist
  - `decor/NarrativeMotif.jsx` — 原子 motif SVG（React.memo + OKLCH color-mix tint）

### 设计系统（v0.5.6 锁定，严禁扩展）

- **色彩**：OKLCH 单一色空间 — brand 195° / success 145° / warn 85° / error 27° / chart 8 色 hue 45° 均匀分布
- **字体**：HarmonyOS Sans SC / PingFang SC / Inter（sans）+ JetBrains Mono / Geist Mono（mono）
- **图标**：I 36 names viewBox 24×24 stroke 1.6（Logo 用 KnotMark viewBox 100×100，语义不同）
- **OKLCH fallback**：R-165 :root CSS Variables + `@supports not` 已兜底，新代码无需重复

### 视觉模型（v0.5.7 验证）

- **底色面板** → fluid 100%（铺满 viewport 边缘；不要 artboard 整体居中）
- **元素** → 尺寸不变，位置 anchor 到 panel 边角（与主题切换 fixed 右上同思路）
- demo 是 1200×760 artboard 设计代理，产品按"viewport-fluid + element-anchored"模式呈现，**不要照搬 artboard 尺寸**

### byte-equal 红线（每屏 PATCH 通用，沿用 v0.5.7 R-170~172/178/179/186 模板）

- export name + props 签名 byte-equal（App.jsx / Shell.jsx / 父组件调用 0 改动）
- 业务链路（api.* / state hooks / SSE handler / localStorage key）byte-equal
- 错误文案 / 提示文案字面 byte-equal（i18n 留 v0.6+）
- 其他 17 屏 + 子模块 byte-equal（`git diff origin/main HEAD -- frontend/src/screens/` 仅含目标屏）
- App.jsx / api.js / index.css / main.jsx / utils.jsx / Shell.jsx byte-equal（除非 PATCH 明确改 Shell 屏）

### 抗诱惑清单（5 条 — v0.5.7 R-186 经验）

- 即使 Foundation 资产可用，**仅在当前 PATCH 目标屏引用**
- 严禁顺手扩 buildTheme 加新字段（破 R-158 25 字段契约）
- 严禁顺手 i18n / 国际化（zh-CN 写死至 v0.5.x 末）
- 严禁顺手改其他屏 / Shell topbar / favicon 等不在 PATCH scope 内的资产
- 严禁引入新 npm 依赖（若需要 → 单独 chore PATCH 评估）

### 三处版本同步（v0.5.0 R-72 + v0.5.7 R-181 模板）

每 PATCH 升版本须**三处同步**：
1. `knot/main.py` FastAPI version
2. `tests/test_rename_smoke.py` R-72 smoke 字面 + docstring
3. **若改 Login.jsx**：`frontend/src/screens/Login.jsx` 页脚 `v{version}` 字面（R-181 守护测试 grep）

未来若复刻 home/shell 等新屏含版本字面，加对应同步红线。

### 复用 v0.5.7 LOCKED 手册作模板

每屏 PATCH 沿用 `docs/plans/v0.5.7-login-pilot.md` 8 节模板（决议 / 红线 / 文件改动 / 验收 / commit 序列 / 协议合规 / 自检），按本屏特性填空即可。


## 启动

```bash
# 本地开发
pip install -e ".[dev]"
python3 -m uvicorn knot.main:app --reload --port 8000

# Docker 部署（v0.6.0 5 分钟全新部署快速开始 — 详 README §5 分钟）
docker build -t knot . && docker run -d -p 8000:8000 -v $(pwd)/data:/app/knot/data --env-file .env knot

# v0.4.x dev 用户升级（v0.5.0 R-67/68/74 双源兼容已撤回 — 详 CHANGELOG v0.6.0 撤回声明）
# 1. .env 改名 + 同值: BIAGENT_MASTER_KEY → KNOT_MASTER_KEY / JWT_SECRET 改通用 secret
# 2. DB 文件手动 rename: bi_agent.db → knot.db（详 README v0.4.x → v0.6.0 升级路径）
```

## 关键路径（v0.5.0 起包名 knot）

| 文件 | 职责 |
|------|------|
| `DEPLOY.md` | **运维部署手册**（v0.6.0.10 加）— 一键部署 + 升级 + 故障排查 + 监控；运维 / AI 助手优先参考 |
| `knot/main.py` | App 工厂，FastAPI title=KNOT version=0.5.6；启动 banner 显示实际加载 env 名 |
| `knot/api/deps.py` | JWT 常量、create_token、get_current_user、require_admin |
| `knot/api/schemas.py` | 所有 Pydantic 请求模型（9 个） |
| `knot/api/query.py` | v0.5.2 拆分：路由 + SSE generator 主控（yield 保留），业务计算 delegate query_steps |
| `knot/services/engine_cache.py` | 用户 DB 引擎缓存（TTL 1h）、_upload_engine |
| `knot/api/` | 业务域路由文件（72 路由：auth / admin / conversations / database / few_shots / knowledge / prompts / query / templates / uploads / saved_reports / audit / catalog / exports） |
| `knot/services/agents/` | 3 agent 实现（v0.5.0 从 services/knot/ rename）；v0.5.2 sql_planner 拆 prompts/tools/llm + orchestrator 拆 clarifier/presenter |
| `knot/services/agents/sql_planner.py` | v0.5.2 主文件：ReAct 调度员；拆出 prompts (`_AGENT_SYSTEM_TEMPLATE` + `_business_rules` + `_relations_for_schema`) / tools (`_strip_sql` + `_parse_agent_output` + `_is_fan_out` + `_run_tool` 含 v0.5.1 cartesian + v0.4.1.1 fan-out 守护) / llm (`_call_llm` + `_acall_llm` 含 v0.4.4 R-26 budget gate + R-30 透传) |
| `knot/services/agents/clarifier.py` | v0.5.2：VALID_INTENTS / INTENT_TO_HINT / DEFAULT_INTENT_FALLBACK + `_CLARIFIER_SYS` + `run_clarifier` / `arun_clarifier`（R-26 budget gate + R-30 透传）；v0.6.0 F2.6 `_CLARIFIER_SYS` 从 `knot/prompts/clarifier.md` lazy load |
| `knot/services/agents/presenter.py` | v0.5.2：`_PRESENTER_SYS`（含幻觉禁令 + 异常判断）+ `run_presenter` / `arun_presenter`；v0.6.0 F2.7 `_PRESENTER_SYS` 从 `knot/prompts/presenter.md` lazy load |
| `knot/services/agents/orchestrator.py` | v0.5.2 调度员：保留共享 helpers `_resolve` / `_llm` / `_allm` / `_parse_json` / `_today` / `_date_block` / `_business_rules` / `_app_or_key`（子文件函数体内延迟 import — R-106 方案 1）+ re-export 子文件 public 符号 |
| `knot/services/` | 业务编排层（auth_service / budget_service / cost_service / audit_service / error_translator / llm_client 等） |
| `knot/services/llm_client.py` | v0.5.2 主文件：generate_sql / agenerate_sql / fix_sql / afix_sql；拆出 few_shots / llm_prompt_builder / _llm_invoke + R-100 re-export |
| `knot/services/few_shots.py` | v0.5.2：DB 优先 / yaml 回退的 few-shot 装配 (`_load_few_shots` / `classify_question_type` / `get_few_shot_examples`) |
| `knot/services/llm_prompt_builder.py` | v0.5.2：`build_system_prompt`（含 v0.4.1.1 RELATIONS 注入 + Fan-Out 防御 prompt） |
| `knot/services/_llm_invoke.py` | v0.5.2：`calculate_cost` / `_invoke_via_adapter` / `_ainvoke_via_adapter`（含 v0.4.4 R-26 senior budget gate + R-30 透传 + R-32 agent_kind 分桶）/ `_parse_llm_response` 等 |
| `knot/services/query_steps.py` | v0.5.2 R-109：纯业务步骤函数（**0 yield**），SSE 主控保留在 api/query.py — `enrich_semantic` / `select_agent_key` / 3 流式 step (clarifier/sql_planner/presenter) + 2 非流式分支 (use_agent / generate+fix retry) |
| `frontend/src/screens/Chat.jsx` | v0.5.3 拆分：ChatScreen 主屏调度员（保留 export 名 + props）；sendQuery 走 sse_handler 纯函数 + callbacks 注入 state setter |
| `frontend/src/screens/chat/` | v0.5.3：7 个子模块 — `intent_helpers.js` (INTENT_TO_HINT 7 类) / `sse_handler.js` (R-118 纯函数 runQueryStream) / `ResultBlock.jsx` (R-117 7 intent layout 分支 + R-127 ErrorBanner ERROR_KIND_META + MetricCard + AGENT_KIND_EMOJI + exportMessageCsv) / `ChatEmpty.jsx` / `Conversation.jsx` / `ThinkingCard.jsx` (含 AgentThinkingPanel) / `Composer.jsx` |
| `frontend/src/screens/Admin.jsx` | v0.5.3 拆分：AdminScreen 状态容器（14 handlers + 11 state + 7 tab dispatch + AppShell + topbarTrailing 7 分支）；保留 export 名 + props 含 initialTab 深链 |
| `frontend/src/screens/admin/` | v0.5.3：5 个子模块（D4 4 tab dumb component + 1 modals）— `tab_access.jsx` (Users + Sources) / `tab_resources.jsx` (Models + API Keys + Agent Models) / `tab_knowledge.jsx` (Knowledge + FewShots + Prompts) / `tab_system.jsx` (Catalog) / `modals.jsx` (UserFormModal + SourceFormModal + FewShotModal) |
| `knot/repositories/` | 9 个 *_repo.py + audit_repo.py |
| `knot/adapters/` | llm/{anthropic_native,openai_compat,openrouter,async+sync 双 API} + db/doris.py + notification/{base.py,__init__.py}（通知接口抽象层 — v0.5.5 删 lark.py stub；接口预留供未来加 adapter） |
| `knot/core/` | 横切工具（logging_setup / date_context / crypto/fernet）|
| `knot/scripts/` | migrate_encrypt_v045.py / purge_audit_log.py（v0.6.0 删 migrate_db_rename_v050.py — R-67/68 撤回；详 CHANGELOG）|
| `knot/prompts/` | 默认 3-Agent system prompts（v0.6.0 F2 — sql_planner.md / clarifier.md / presenter.md；启动期幂等 seed 到 DB；admin UI 可覆盖）|
| `knot/static/` | Vite 构建产物（`frontend/` 源码 → `npm run build` 输出至此） |
| `knot/data/` | SQLite 数据库（gitignore，runtime 自动创建；v0.5.0 起文件名 knot.db） |
| `scripts/audit_ohx_leakage.py` | v0.6.0 F6 — 业务方言 + 旧品牌字面泄漏守护（--mode=sanitize/brand/all；R-PA-1/R-PA-6 闸门 6 工具）|

## 导入约定

v0.3.0 起 `pip install -e .` editable 安装；解释器原生识别 `knot` 包，无 sys.path hack。
所有业务模块用 `from knot.X import Y` 绝对导入（`from knot.api.deps import get_current_user` 等）。

## 数据库

- `knot/data/knot.db` — 用户 / 会话 / 消息 / 知识库 / 用户上传 CSV/Excel / 审计日志
  （v0.2.4 合并 uploads.db；v0.4.6 加 audit_log）
- v0.4.x dev 用户升级路径（README §v0.4.x → v0.6.0）：手动 `mv bi_agent.db knot.db`（v0.5.0 startup auto-rename migration 已撤回 — 详 CHANGELOG v0.6.0）
- Apache Doris / MySQL — 业务查询目标（通过 .env 配置）

## 加密 master key（v0.6.0 单一 KNOT_MASTER_KEY）

- **v0.6.0+ 唯一**：`KNOT_MASTER_KEY`
- v0.5.x 的双源（KNOT_MASTER_KEY + 兼容旧名）已于 v0.6.0 Phase A 物理删除（详 [CHANGELOG v0.6.0 撤回声明](CHANGELOG.md#unreleased---v060-phase-a-knot-sanitize--bi_agent-兼容层清算--deploy-ready-内测可启动门)）
- v0.4.x dev 用户升级路径（README 同步）：DB 文件 rename + env 改名（同值）

## 版本管理

格式：`vMAJOR.MINOR.PATCH.YYYYMMDDHHmm`

- **MAJOR**：`0` = 内测；`1` = 团队公测（由用户决定何时跨过）
- **MINOR**：阶段性大节点（重大重构 / 用户认为"这一阶段已迭代完"）
- **PATCH**：每完成一轮需求迭代 +1
- **时间戳**：每次实际打 tag 的精确时间；同一 PATCH 周期内的小修补只更新时间戳，不动 PATCH

示例：

- 起点：`v0.2.0.xxx`
- 完成本轮 5 点（4/26 16:00）→ `v0.2.1.202604261600`
- 当晚 18:00 修补本轮遗留 → `v0.2.1.202604261800`（PATCH 不动）
- 下一轮新需求完成 → `v0.2.2.xxx`
- 后端 Go 重写或阶段性收尾 → `v0.3.0.xxx`

记录文件：`CHANGELOG.md`（Keep a Changelog 格式）

分支策略：`main`（默认分支 + 集成 + tag；PR squash merge 直入）/ `feat|fix|chore|hotfix/*`（开发分支）

> **历史**：早期协议设计 `main` 仅打 tag / `develop` 集成。实际自 v0.3.0 起所有 PR 都直合 `main`，`develop` 事实废弃停留 v0.2.4（落后 9+ PATCH）。v0.5.1 后正式将 GitHub default branch 切到 `main`、CLAUDE.md 同步现状；`develop` 分支保留作 v0.2.4 历史快照不再使用。

## 已知技术债

| 优先级 | 问题 | 目标分支 |
|--------|------|---------|
| ~~高~~ ✅ v0.4.4 已偿还 | LLM 全面 async（AsyncAnthropic / AsyncOpenAI），threadpool 64→32 | — |
| 中 | 路由中 sync SQLAlchemy；DB 端短查询为主，暂未切 async（v0.4.4 LLM 离开池后压力已大幅缓解，可观察是否还需要） | feat/async-db |
| ~~中~~ ✅ v0.2.2 已用 loguru | 结构化日志 | — |
| ~~低~~ ✅ v0.2.4 已合并 | uploads.db → bi_agent.db | — |
| ~~低~~ ✅ v0.2.4 已删 | `bi_agent/routers/user.py` 的 `/api/user/config` `/api/user/agent-models` | — |

## v0.3.x 工程化重构 — Contract 升级路线图

v0.3.0（已合入）建立 4 层架构 `routers → services → repositories | adapters → models`，
当前 import-linter contract **4 条 KEPT** 但部分采用渐进式 FIXME 锁定（资深架构师 + Codex 评审组 APPROVED）。
后续 PATCH 必须按下表升级 `.importlinter`，**不得跳过**：

| FIXME 标签 | 当前状态 | 升级动作 | 落地版本 |
|-----------|---------|---------|---------|
| ~~`FIXME-v0.3.1`~~ ✅ v0.3.1 已偿还 | `repositories` 仅禁 `routers` | 加上 `bi_agent.services` 到 `forbidden_modules` | v0.3.1 services 落地后 |
| ~~`FIXME-v0.3.2`~~ ✅ v0.3.2 已偿还 | `repositories` 仅禁 `routers + services` | 加上 `bi_agent.adapters` + 新增 contract `adapters-no-business` | v0.3.2 adapters 落地后 |
| ~~`FIXME-v0.3.2`~~ ✅ v0.3.2 已偿还 | `repositories` 仅禁 `routers / services` | 再加 `bi_agent.adapters` | v0.3.2 adapters 落地后 |
| ~~`FIXME-v0.3.3`~~ ✅ v0.3.3 已偿还 | `core-no-models` 仅禁 `models / routers` | 完整 `forbidden_modules`：`models, api, services, repositories, adapters` | v0.3.3 core 完全瘦身后 |

**v0.3.3 终态（Full Forbidden Mode）**：6 条 contract 全部 KEPT，所有 FIXME 清空。
4-PATCH 工程化重构正式收官，进入 v0.4.x 业务迭代期。

### 4 层依赖图（v0.3.3 终态）

```mermaid
graph TD
    api["🌐 api/ (FastAPI 路由)"]
    services["🧩 services/ (业务编排)<br/>knot/ + auth + catalog + rag + ..."]
    repos["🗄️ repositories/ (SQLite CRUD)<br/>9 个 *_repo.py"]
    adapters["🔌 adapters/ (Protocol 实现)<br/>llm + db + notification"]
    models["📦 models/ (数据形状·叶子)<br/>10 个领域 dataclass"]
    core["🛠️ core/ (横切工具)<br/>logging + date_context"]
    config["⚙️ config/ (settings 单例)"]

    api --> services
    services --> repos
    services --> adapters
    repos --> models
    adapters --> models
    services --> models
    api --> models

    api -.-> core
    services -.-> core
    repos -.-> core
    adapters -.-> core
    api --> config
    services --> config
    repos --> config
    adapters --> config

    classDef leaf fill:#e8f5e9,stroke:#2e7d32
    classDef horizontal fill:#fff3e0,stroke:#e65100,stroke-dasharray:5
    class models,core leaf
    class core horizontal
```

> **规则**：实线 = 业务依赖（自上而下）；虚线 = 横切工具（任意层可用，不构成业务依赖）。
> import-linter 6 条 contract 把所有反向箭头都禁了。

### 4-PATCH 演进时间轴

```mermaid
gantt
    title 4-PATCH 工程化重构总账（v0.3.0 → v0.3.3）
    dateFormat X
    axisFormat %s

    section v0.3.0
    repos + models + 工程化基线 (4 contracts, 48 tests)  :done, 0, 1

    section v0.3.1
    services + core 无业务化 (4 contracts, 61 tests)     :done, 1, 2

    section v0.3.2
    adapters 协议驱动 + errors 树 (5 contracts, 85 tests) :done, 2, 3

    section v0.3.3
    api 改名 + Full Forbidden (6 contracts, 101 tests)   :done, 3, 4
```

资深寄语：v0.3.3 结束前 `core` 的 `forbidden_modules` 必须锁死至最高级别。

辅助 v0.3.x 计划：

| PATCH | 主题 | 关键交付 |
|-------|------|---------|
| ✅ v0.3.0 | repos 拆分 + models 顶级包 + 工程化基线 | `pyproject.toml` / `.importlinter` / `pip install -e .` |
| ✅ v0.3.1 | services/ 落地（含 knot/）+ 删 repos facade re-export + core 无业务化 | 9 个文件 git mv → services/[knot/]，repos 仅暴露 `init_db / get_conn` |
| ✅ v0.3.2 | adapters/ 落地（llm/db/notification 协议驱动）+ services/llm_client 瘦身 | adapters/{llm,db,notification}/{base,...}.py，5 contracts KEPT |
| ✅ v0.3.3 | routers→api 改名 + core 完全瘦身 + Full Forbidden Mode + 端到端集成测试 | api/ + 6 contracts KEPT + 13 集成测试 + 3 core 纯度守护测试 |

## v0.4.x 业务迭代路线图（v0.3.3 之后）

架构底座已稳，进入业务能力迭代期。v0.3.3 → v0.4.4 期间 **6 条 contract** 全程 KEPT；v0.4.5 首次升至 **7 条**（新增 `crypto-only-in-allowed-callers` — core.crypto 仅 repositories / scripts 可用）；v0.4.6 维持 7 条不变。

| PATCH | 主题 | 关键交付 |
|-------|------|---------|
| ✅ v0.4.0 | Clarifier intent + Layout 分支 + CSV 导出 + eval 扩量 | Clarifier 7 类 intent；前端按 intent 渲染 layout（MetricCard/Chart/RankView/RetentionMatrix/DetailTable）；`/api/messages/{id}/export.csv`（utf-8-sig BOM）；eval 80 条（每 intent ≥8 + 24 edge）；GH Actions live LLM CI；intent 准确率 ≥90% 门禁；AsyncLLMAdapter Protocol 占位 |
| ✅ v0.4.1 | 报表沉淀（saved_reports + 收藏 + 重跑 + CSV 导出）| `saved_reports` 表（去耦合快照）+ 6 路由（list/pin/run/update/delete/export.csv）+ 前端 ⭐ 收藏按钮 + SavedReportsScreen + R-S4 effectiveHint 三级链 + R-12 幂等 + R-S2 data_source 重跑 fallback；6 contracts KEPT；147 tests / 81 skipped；xlsx 推 v0.4.2 |
| ✅ v0.4.1.1 | hotfix — 笛卡尔积防御 + UX 双 Bug | Bug 1 (Shell.jsx active.startsWith('admin-')) + Bug 2 (后端 sql alias) + Bug 3 三层防御（Catalog RELATIONS + 双 prompt JOIN 硬约束 + eval 9 multi_table case + comma-FROM 守护正则）；157 tests / 90 skipped；89 eval cases；61 routes 不变；6 contracts KEPT。**隐含承诺**：合入后 7 天内须为 gitignored ohx_catalog.py 补 RELATIONS。 |
| ✅ v0.4.2 | 成本可观测 + xlsx 导出 + eval SQL 复杂度横切 | messages +10 列（4 agent_kind 分桶 + recovery_attempt）+ `cost_service` (R-S8 一致性入口) + `/api/admin/cost-stats` + xlsx 导出 (5000 行硬限 + R-S7 截断 metadata header) + eval 89→111 (subquery/window/cte +21) + AST hybrid dispatcher + CI label opt-in；64 routes / 203 tests / 112 skipped；6 contracts KEPT。**预算告警延期 v0.4.3**。**R-S6**：messages 列数 24，v0.4.5+ 评估迁移工具。 |
| ✅ v0.4.3 | 预算告警 + System_Recovery 维度（成本治理收尾）| `budgets` 表（global/user/agent_kind 三层 DRY）+ `budget_service` (R-16 优先级 + R-17 一致性对齐 + R-23 不缓存) + 5 路由（budgets CRUD + recovery-stats）+ R-22 流式/非流式同字段 + 前端 AdminBudgets/AdminRecovery + R-20 banner 降噪；69 routes / 223 tests / 112 skipped；6 contracts KEPT。**8 条红线 R-16~R-23 全部偿还**。错误体验/加密/审计推 v0.4.4-6。 |
| ✅ v0.4.4 | 异步 LLM + 错误体验改造 | AsyncLLMAdapter 落地（AsyncAnthropic / AsyncOpenAI / OpenRouter）+ R-31 Protocol 完整性；models/errors.py 扩 4 类（R-30 复用不重造）+ services/error_translator.py 7 类 kind 映射；async 业务链 (arun_clarifier/arun_sql_agent/arun_presenter) + R-26-Senior 首行 budget 守护 + R-32 fix_sql 独立桶；api/query.py 真异步 + R-26-SSE sleep(0) + R-33 双路径同字段；R-27 race 守护（100×gather 误差 ≤ 0.01%）；前端 ErrorBanner + R-28 优先级（覆盖 BudgetBanner）；R-29-anyio threadpool 默认 64→32；264 tests / 112 skipped；6 contracts KEPT。**已偿还** 9 条红线 R-24~R-33。 |
| ✅ v0.4.5 | 数据加密（API Key / DB 密码）| Loop Protocol v2 三阶段：v0.4 执行者 Stage 1 + 资深/Codex Stage 2 + v0.3 守护者 Stage 3（D1 路径反转 `adapters/crypto/` → `core/crypto/`）；6 类敏感字段 Fernet 应用层加密 + `enc_v1:` 前缀；`BIAGENT_MASTER_KEY` env fail-fast + 友好彩色错误（R-45 sys.exit(1)）；`bi_agent/scripts/migrate_encrypt_v045.py` 一次性幂等迁移 + 自动 timestamped `.v044-<ts>.bak`（R-46/R-46-Tx 每表事务）；前端 API Key `••••••••last4` masked + PATCH 空值/mask 占位保留（R-39）；**首次 contract 数变更 6 → 7 条**（新增 `crypto-only-in-allowed-callers` + `allow_indirect_imports = True` 只查直接边）；309 tests / 112 skipped；**已偿还** 13 条红线 R-34~R-46。 |
| ✅ v0.4.6 | 审计日志（who-did-what）| Loop Protocol v2 三阶段：v0.4 执行者 Stage 1 + 资深/Codex Stage 2 + v0.3 守护者 Stage 3（D1 反转 schema +client_ip/user_agent 独立列）；`audit_log` 表 INSERT-only + 3 索引；`AuditAction` Literal 33 条覆盖 8 类 mutation × 子动作（messages 显式排除 R-63 防爆表）；`audit_service.log()` fail-soft + R-64 失败计数器 hook + R-48/59/62 PII 三层防御（含 v0.4.5 加密字段 + 密文也 redact）+ D7 递归深度 3 防嵌套炸弹；`AuditWriteError(BIAgentError)` 复用 errors 树（R-65 不重复造轮子）；7 类 mutation 集成（auth/users/datasources/api-keys/budgets/agent-models/saved_reports/few_shots/prompts/catalog）+ admin GET 路由 + R-61 强制分页 cap 200 + R-56 越权 403 + R-53 stress 1000×p95<5ms；前端 AdminAudit 列表 + 筛选 + 详情抽屉（D3 落地，redacted 高亮提升 admin 信任感）；`purge_audit_log` 脚本复用 v0.4.5 模式（独立 entrypoint + timestamped .bak + dry-run）+ retention 90 天默认 7~3650 admin 可调 + R-57 meta-audit；362 tests / 112 skipped；7 contracts KEPT；72 routes（+3）；**已偿还** 20 条红线 R-47~R-66。 |

## v0.5.x 业务迭代路线图（v0.4.6 之后 — KNOT 准生产）

**bi-agent 品牌正式归档历史**（v0.5.0 起包名 knot）。Loop Protocol v3 首次完整 PATCH 内施行（执行者 + 守护者 + 远古守护者 + 辅助 AI 初审组 4 级角色 + MINOR 滚动整体审核仪式）。7 条 contract 全程 KEPT。

| PATCH | 主题 | 关键交付 |
|-------|------|---------|
| ✅ v0.5.0 | (C0) bi-agent → KNOT 重命名 + Foundation | Loop Protocol v3 三阶段：v0.5 执行者 Stage 1 + 资深/Codex Stage 2 + v0.4 守护者 Stage 3（含资深 3 维度提问回应：R-74 密文兼容性探针 / R-75 审计连续性 / R-76 迁移备份原子性）；`bi_agent/` → `knot/` 包重命名（git mv 132 个 .py 保 history）+ `services/knot/` → `services/agents/`（守护者整体审核新发现重名冲突）；env 双源 `KNOT_MASTER_KEY` 优先 + `BIAGENT_MASTER_KEY` deprecated 回退（v1.0 移除）；R-74 密文兼容性探针（双 key 不同值时 sqlite3 直读 enc_v1: 探针验证旧/新解密能力，旧成功新失败 → sys.exit(1) 防数据永久丢失）；DB startup migration `bi_agent.db` → `knot.db`（R-69 4 场景幂等 + R-76 atomic try/except + 独立 entrypoint --dry-run 双轨 + timestamped .v044-<ts>.bak）；`_v050_rename.py` 一次性 Python 跨平台替换脚本（R-77 禁 sed -i ''；4 phase 顺序锁定；字面量保护占位防 `bi_agent.db` 误替）；7 contracts KEPT（Contract 7 forbidden_modules 同步替换 `knot.core.crypto` 关键 R-71）；frontend vite outDir + Chat.jsx CSV 文件名前缀 `knot-`；CI matrix 4 组合 × ubuntu+macOS 双平台（R-72/R-77 完整覆盖）；375 tests / 112 skipped（v0.4.6 362 → +13）；**已偿还** 13 条红线 R-67~R-79；**守护者结构性教训** 3 条（dotenv 自动发现 / R-77 替换顺序漏洞 / PEP 585 顺手清理）。 |
| ✅ v0.5.1 | (C1) SQL AST 预校验（笛卡尔积硬防御）| Loop Protocol v3 第二次完整 PATCH 内施行（v0.5 执行者 Stage 1 + 资深/Codex Stage 2 新增 R-89/90 + v0.4 守护者 Stage 3 新增 R-91/92/93）；`knot/services/sql_validator.py` (149 行) 检测 4 类反模式（C1 旧式逗号 / C2 CROSS JOIN / C3 缺 ON / C4 恒真 ON）；C1 文本侧（sqlglot 30.x 与缺 ON 同 AST 无法区分）+ C2/C3/C4 AST；R-83 `tree.find_all(exp.Select)` 递归覆盖 CTE/子查询；R-92 建设性 reason 模板（含表名 + 修复指引指向 RELATIONS）；sql_planner `_run_tool` final_answer 分支 cartesian 优先 fan-out（R-85，更基础错误先返）+ sync/async 双 ReAct 加 `cart_reject_count` 计数器（R-91 ≥3 次强制终止 + 共享 max_steps 预算）；R-89 `_MAX_SQL_LEN=100k` + `_MAX_PAREN_DEPTH=100` 预检 fail-open；R-90 纯函数禁 `import adapters.db/repositories`；R-93 v0.4.5 `enc_v1:` 加密字段值不被误判；**核心代码 182 行** ≤ R-84 200 预算（validator 149 + planner +33）；431 tests / 112 skipped（v0.5.0 400 → +31 = 23 unit + 8 integration）；7 contracts KEPT 不动；72 routes 不变；不引新依赖（sqlglot 既有）；**已偿还** 14 条红线 R-80~R-93。**1.0 阻塞偿还**（runtime 硬防御 + v0.4.1.1 prompt 三层防御共同形成 4 层笛卡尔积防御）；**跨表 WHERE 无前缀检测延期**（D2 — 无 Schema Cache 误杀风险高）+ **fan-out regex → AST 升级延期**（D5 — 单 PATCH 单核心问题）。 |
| ✅ v0.5.2 | (C2) 后端代码瘦身 | Loop Protocol v3 第三次完整 PATCH 内施行（D1-D8 全锁定 + 17 红线 R-94~R-110）；4 主文件按文件级 1 commit 拆出 9 个新模块（sql_planner 653→330 拆 prompts/tools/llm 三模块；llm_client 574→250 拆 few_shots/llm_prompt_builder/_llm_invoke；orchestrator 535→199 拆 clarifier/presenter；api/query 457→309 抽 services/query_steps）；R-100 re-export 兼容（测试 + 业务 import 路径 0 修改 — 仅 2 处 monkeypatch target 字符串路径微调走子模块）；R-106 单向依赖 — sql_planner / llm_client 顶部 import 子模块；orchestrator 用方案 1 函数体内延迟 import 主文件 helpers（避免 import-time 循环 + monkeypatch 自动生效，与 v0.4.4 `_acall_llm` 内 `from knot.services import budget_service` 延迟 import 同模式）；R-109 SSE 稳定性 — query_steps.py AST 0 yield expression 验证；query_stream 内 `for ... yield emit(...)` 主控原样保留（10 yield + 10 await asyncio.sleep R-26-SSE 让步全部保留）；R-94 query.py 边界微调 220 → 310（资深 ack 方案 A — SSE 协议样板代码不可消除：10 yield/sleep + emit/_default + try/except + save_message ×2 + final/clarification payload dict ≈ 142 行不可消除）；scripts/check_file_sizes.py [NEW, 44 行] D7 加码 CI 行数核验（13 文件 LIMITS dict + ruff 之后 lint-imports 之前）；R-108 强化验证 — commit 2 后 budget(7) + crypto(10) + llm_client_async(6) 共 23/23 PASSED；432 tests / 112 skipped（R-95 严格不变 — D-2 不增测试）；7 contracts KEPT（D8 不增 contract）；72 routes 不变；不动 requirements.txt / pyproject.toml；**已偿还** 17 条红线 R-94~R-110。 |
| ✅ v0.5.3 | (C3) 前端代码瘦身 | Loop Protocol v3 第四次完整 PATCH 内施行（D1-D7 全锁定 + 18 红线 R-111~R-128）；2 主屏按 4-commit 节奏拆出 13 子组件（Chat.jsx 925→254 拆 chat/* 7 子模块；Admin.jsx 773→352 拆 admin/* 5 子模块按 D4 职责合并 4 tab + modals）；R-118 SSE handler 纯函数化 — `runQueryStream(url, body, token, callbacks)` 0 React 依赖，callbacks (onAgentEvent/onClarification/onError/onFinal/onException) 注入 state setter；R-127 错误边界平移 — error_kind / user_message / is_retryable 透传 + v0.4.4 ERROR_KIND_META 7 类 ErrorBanner 渲染逻辑逐字保留；R-128 className 字面 byte-equal — main vs local unique className 完全一致 (`cb-fadein` + `cb-sb`)；R-126 KNOT brand 字面（CSV `knot-` 前缀 + `KNOT 可能出错` 提示）2 处完整平移；R-124 全局状态零变更 — chat/* + admin/* 子模块 0 含 useContext/Provider/createContext/redux/zustand；R-117 7 intent layout 分支零行为变更（metric_card/line/bar/rank_view/pie/retention_matrix/detail_table）；R-111 行数 2 处微调（资深 ack 方案 A — 与 v0.5.2 query.py SSE 样板代价同精神）— ResultBlock.jsx 250→400（复合 UI 7 段 + 3 helpers）+ Admin.jsx 250→360（状态容器 14 handlers + 11 state + 7 tab dispatch）；scripts/check_file_sizes.py [EDIT] LIMITS dict 13→27 files（+14 前端 = 2 主 + 12 子模块）；432 tests / 112 skipped（R-119 严格不变）；7 contracts KEPT 不动（R-113）；72 routes 不变；不动 package.json / .importlinter / Shell.jsx / SavedReports.jsx；**已偿还** 18 条红线 R-111~R-128。 |
| ✅ v0.5.4 | (C4) Loop Protocol v3 路线图同步 | Loop Protocol v3 **第 5 次**完整 PATCH 内施行（**自我引用闭环** — 用 v3 协议同步 v3 协议；D1-D5 全锁定 + 10 红线 R-129~R-138）；README.md +26 行 § Loop Protocol v3 段（4 级角色简表 + R-136 ASCII 三阶段流程图 + R-137 角色滚动透明声明"规则治权而非人治层级" + R-135 不带锚点链接指向 CLAUDE.md 深挖避免死链）；CLAUDE.md L110-114 v3 协议施行历史段扩展 5 行回顾摘要表（含 v0.5.2 27 文件行数压制特别提及）；R-134 协议核心字面守护（§ 角色定义 / § 三阶段评审 / § 角色滚动规则 / § 远古守护者激活原则 字面 byte-equal）；R-138 docs-only zero drift（除 main.py version + R-72 smoke 字符串外严禁触碰任何 .py/.js/.jsx 逻辑行）；3 commit（README+CLAUDE.md / version bump / CHANGELOG+plan 归档）；432 tests / 112 skipped（R-129 严格不变 — backend 0 修改）；7 contracts KEPT 不动（R-130）；72 routes 不变；不动 frontend / scripts / requirements / package / pyproject / .importlinter；**已偿还** 10 条红线 R-129~R-138。 |
| ✅ v0.5.6 | (C5) Claude Design UI 重构 — Foundation 第一刀 | Loop Protocol v3 **第 7 次**完整 PATCH 内施行（D1-D7 全锁定 + 16 红线 R-154~R-169）；**v0.5.x 序列第二次 Negative Delta -136 行**；Shared.jsx + utils.jsx + App.css 视觉重构（**18 屏 0 修改自动换皮** — strangler fig pattern）—— buildTheme(dark) 25 字段切 OKLCH（brand 蓝青 195° dark/light 双值；ink 13 阶冷黑 hex；R-167 success 翠绿 145°/warn 琥珀 85° 远离 brand 195°）；R-169 CHART_COLORS 8 色 hue 45° 均匀分布（195/240/285/330/15/60/105/150°，lightness 65~70% chroma 0.16~0.20）；I 36 names path 重绘（send/check/sparkle/more 与 demo viewBox 24 stroke 1.6 风格统一）；iconBtn / pillBtn 样式重写 borderRadius 6→8（保签名）；CHART_COLORS + 4 charts 默认色 + IIFE cb-grid-bg + button focus 切蓝青 OKLCH；utils.jsx Modal/ModalHeader/Input/Select/Spinner/toast 视觉重写（保 8 exports 函数签名）；toast/Spinner hardcode 红 → R-167 朱红 27°/翠绿 145°；App.css 184→27 行净 -157（移除 Vite 模板 counter/hero/next-steps/docs/spacer/ticks 全部）+ HarmonyOS/PingFang/Inter 字体 + R-168 -webkit-font-smoothing antialiased + -moz-osx-font-smoothing grayscale + R-165 :root fallback CSS Variables + @supports not 兜底；R-156 18 屏 git diff 0 行 ✓；R-157 Shell.jsx/App.jsx/api.js/index.css/main.jsx byte-equal ✓；R-158 Shared.jsx 9 exports + I 36 names + buildTheme 25 字段 + dark prop ✓；R-159 utils.jsx 8 exports byte-equal ✓；R-160 App.css cb-sb/cb-fadein 字面 byte-equal（main 和 local 都 0 命中 — IIFE 注入）；R-164 不动 package.json/requirements/pyproject/.importlinter/vite.config；430 tests / 112 skipped；7 contracts KEPT；72 routes；**已偿还** 16 条红线 R-154~R-169；**待人测**：R-166 WCAG AA 对比度 + R-167 错误 banner 视觉醒目 + R-169 PieChart 邻接扇区不混淆 + 18 屏 dark/light 双模式肉眼。 |
| ✅ v0.5.7 | (C5+) Claude Design UI 重构 — Login 屏首屏复刻 pilot | Loop Protocol v3 **第 8 次**完整 PATCH 内施行（D1-D8 + Q1-Q4 全锁定 + 17 红线 R-170~R-186）；**1 屏 1 PATCH 模式正式确立**（为 v0.5.8+ 提供执行模板）；Shared.jsx +3 exports `KnotMark/KnotWordmark/KnotLogo` 9→12 上限（R-174）— 接 `{ T, size }` 严禁写死像素（R-183）+ viewBox 100×100 与 I 24×24 解耦（Q2）+ T.dark boolean 替代 theme 字串（Q4）；frontend/src/decor/NarrativeMotif.jsx [NEW 112 行 ≤ 120 R-173] pure SVG func — 原子结构 motif (3 椭圆轨道 + 4 电子 + 核心 + 7 bezier 输入流)；React.memo 包裹防 SVG 巨量 path 重绘（R-182）+ `color-mix(in oklch, T.accent 15%, transparent)` 替代 demo brand[100]（Q1 不破 R-158 25 字段契约）；Login.jsx 116→178 行 ≤ 200（R-175）— 视觉 1:1 复刻 demo（grid 1.05fr 1fr + KnotLogo + NarrativeMotif + Knowledge·Nexus·Objective·Trace tagline + "复杂结于此，洞察始于此" headline + Field 44px 灰底框 + 7 天 remember checkbox 含 title 防误导 Q3 + 进入 KNOT 主按钮 + oklch 红 error banner D6 + 页脚 v0.5.7 三处同步 R-181）；R-184 input focus 蓝青 (focused state tracker + transition 0.15s)；R-170/171/172 LoginScreen export name + props + api.login + cb_token + 错误文案 byte-equal；R-186 **抗诱惑严守** — Shell.jsx 0 行改动（即使 KnotLogo 可用，topbar Logo 留 v0.5.8+）；tests/test_login_version_sync.py [NEW 47 行] 含 R-181 三处版本同步守护 + R-185 DOM 哨兵；scripts/check_file_sizes.py LIMITS 27→29 (R-176)；432 tests (430 baseline + R-181 + R-185) / 112 skipped；7 contracts KEPT；72 routes；**已偿还** 17 条红线 R-170~R-186；**待人测**：light/dark 双主题登录端到端 + Tab 焦点蓝青 + remember localStorage 写入 + 视觉对照 demo 双截图。 |
| ✅ v0.5.8 | (Cn+) Chore — CI fix + Visual Replication Protocol | Loop Protocol v3 **第 9 次施行** — **首次简化协议**（跳 Stage 2/3 直接 Stage 4，资深 ack）；docs+ci chore 0 业务逻辑改动（R-191）；偿还 v0.5.0 R-72 留下的 ci.yml boot smoke 硬编 0.5.0 bug（R-187 — 改为 regex 动态读 main.py），未来 PATCH 升版本 ci 自动跟随（boot smoke matrix only-knot/only-biagent/both-same 应全绿）；CLAUDE.md 加 § Visual Replication Protocol 段（R-188 — 59 行 ≤ 80）：路径常量 + 设计系统（v0.5.6 锁定）+ 视觉模型（v0.5.7 验证 fluid panel + element-anchored）+ byte-equal 红线 + 抗诱惑清单 5 条 + 三处版本同步 + 复用 v0.5.7 LOCKED 手册模板；R-190 三处版本同步 0.5.7→0.5.8（main.py + smoke + Login 页脚）；432 tests / 112 skipped 严格不变（R-189）；7 contracts KEPT；72 routes；**已偿还** 5 条红线 R-187~R-191；**简化协议适用规则**确立：仅 docs/ci/chore 且红线 ≤ 8 + 无决议争议 + 资深 ack → 跳 Stage 2/3。 |
| ✅ v0.5.9 | (C5+) Shell 屏复刻 — 首个真正屏复刻 PATCH | Loop Protocol v3 **第 10 次施行**（恢复全 v3 三阶段）；**宪法级 R-192 AppShell 13 props 签名 byte-equal** 三方共识守 18 屏不崩溃；Shell.jsx 172→186 行 ≤ 220（R-205）— 7 子步骤顺序锁死视觉重构：① sidebar 256→224 + ellipsis（R-198 + Q2）② I.book/I.shield 36 names 双保险 ③ Brand 区 KnotLogo size=20 替代 sparkle+文字（**R-199 + Q1 修订 16→20** — v0.5.7 R-186 抗诱惑首次解禁）+ logoArea 56px borderBottom（R-200）④ user row 渐变橘 #ff7a3a → 纯 T.accent + 56px borderTop（R-201 + R-211 全局净空）⑤ admin nav 3 emoji 偿还（R-202 — 💰/🛡️/📋 → I.zap/I.shield/I.book）⑥ NavItem active 改 absolute span 2px brand bar **右侧**（R-203 + Q4 防 overflow:hidden 裁切）⑦ SideHeading 字体 T.mono（R-204）；契约守护 R-193/194/195/196/197 SideHeading + SideNavRow + onNavigate/handlers + 'admin-' 前缀分流 + Connection pill + HTML entity 字面 byte-equal（守 12+ 文件 import）；范围守护 R-199.5（KnotLogo 仅 Shared+Login+Shell 三文件命中）+ R-210（App.css 0 行 diff + Shell.jsx 0 新 className）+ R-211（Shell 全文 #ff7a3a 0 命中）+ R-212（'admin-' 前缀分流字面 byte-equal — 改 active 视觉时严禁触碰 startsWith if 分支）+ R-213（Shell.jsx 严禁 version 字面，注释中版本号清理为 R-XXX 编号）；R-207 17 屏 + 12 子模块 byte-equal；R-208 App/api/index.css/main/utils/Shared/NarrativeMotif 0 改；R-209 三处版本同步 0.5.8→0.5.9；432 tests / 112 skipped；7 contracts KEPT；72 routes；**已偿还** 22 条红线 R-192~R-213；**待人测**：18 路由切换 + admin tab 切换 + KnotLogo size=20 视觉 + ellipsis 截断。 |
| ✅ v0.5.10 | (C5+) Home 屏复刻 — 首个 chat 子模块屏复刻 | Loop Protocol v3 **第 11 次施行**（全 v3 三阶段）；ChatEmpty.jsx 40→80 行 = R-218 上限（v0.5.3 R-111 LIMIT 250→80 收紧）；6 子步骤顺序锁死视觉重构：① 容器 padding 0 80 + paddingBottom 10vh + center（R-239 黄金分割）② "knot · ready" brand label + box-shadow color-mix(in oklch, T.accent 13%, transparent)（R-229 + R-227.5 装饰小写 + Q2 严禁 hex alpha）③ 标题 36px + "解" brand span + letterSpacing -0.035em + word-break keep-all + maxWidth 640（R-230 + R-224 + R-236 + Q1 — **KNOT 品牌"解结"双关首次在产品出现**）④ 副标题新文案 + KNOT 大写（R-231 + R-127 sustained）⑤ suggestions 扩 {icon, text} 硬编码语义映射（sparkle/chart/users/db）+ chip 44 + radius 10 + flex-wrap wrap（R-232/233/235/238）⑥ Footer T.mono + marginTop 28 + "KNOT 可能出错" 大写（R-234 + R-227 sustained）；契约守护 R-214 ChatEmpty 9 props 签名 byte-equal（diff 0 行）+ R-215 firstName + R-216 4 text 字面 + **R-217 Composer.jsx 0 改**（三方共识 + Stage 3 §3 强制 — 留 v0.5.11+ 独立 PATCH 避免层级断层）；**R-227.5 KNOT 大小写字面分流首次确立**（"knot · ready" 装饰元素小写 vs "KNOT 可能出错" 品牌命名+声明文本大写共存）；范围 R-222 KnotLogo sustained 仅 Shared+Login+Shell 三文件 + R-223 chat/ 其他 6 子模块 0 改 + R-225 CSS 0 污染（App.css 0 diff + inline style only）+ R-226 17 屏 + 11 子模块 byte-equal；Stage 3 加 R-237 firstName 三态兜底 + R-238 4 icon 语义硬编码映射 + R-239 垂直黄金分割；432 tests / 112 skipped；7 contracts KEPT；72 routes；**已偿还** 27 条红线 R-214~R-239；**待人测**：① Chat 屏空对话视觉对照 demo ② 实际提问 Composer 不破坏 ③ firstName 三态兜底 ④ icon 语义对齐肉眼校验。 |
| ✅ v0.5.11 | (C5+) Composer 重构 — **R-217 清偿里程碑** + 视觉自动跟随模式确立 | Loop Protocol v3 **第 12 次施行**（全 v3 三阶段）；**R-217 三方共识自 v0.5.10 hold 至 v0.5.11 正式清偿**；Composer.jsx 71→100 = R-260 上限收紧（v0.5.3 R-111 250 → 100）；7 子步骤顺序锁死：① boxShadow 双模式 T.dark 切换（R-254 + Q2 rgba 豁免 — boxShadow rgba 不属 brand 色彩系统）② 容器 T.inputBg → T.content（R-252 + D1 bgElev 等价物不扩 25 字段保 R-158）③ padding 16 + **width 100%**（R-253 + D5/Q3 **修订** — Stage 2 严禁硬编 720px，max-width 由父容器决定 = 组件化最佳实践）④ textarea minHeight 24→48（R-257 + R-263 垂直生长）⑤ Submit 30→32 + disabled opacity 0.5 反馈（R-256 + R-262）⑥ Footer hint **"Enter 发送 · Shift+Enter 换行"**（R-255 + Q4 修订 — 去 Unicode ↵ 字符全平台兼容）+ mono + brand dot ⑦ focus-within React state useState + onFocus/onBlur + transition 200ms + border T.accentSoft + boxShadow 微放大 color-mix(in oklch, T.accent 15%, transparent)（R-261 — inline style 无 :focus-within 必须 React state）；契约守护 R-240 9 props 签名 byte-equal（diff vs origin/main = 0 行）+ R-241~R-246 6 业务逻辑 byte-equal（placeholder / activeUpload chip / onSubmit/onKeyDown/onChange handlers / disabled `loading \|\| !value.trim()` / autoresize maxHeight 120 / File 上传 .csv/.xlsx）；**R-251 视觉自动跟随设计模式首次确立** — Composer 改动惠及 ChatEmpty + Conversation 两屏自动跟随，R-264 git hash 字节对齐校验 `git diff --stat origin/main HEAD -- ChatEmpty.jsx Conversation.jsx` = **0 files changed**（无代价证明）；R-259 R-217 解禁范围限定（仅 Composer.jsx 一处 — chat/ 其他 5 子模块 sustained 0 改）；R-265 brand-ready → Composer 黄金间距 32-48px；范围 R-250 KnotLogo R-199.5/222 sustained 仅 Shared+Login+Shell 三文件 + R-258 CSS 0 污染（App.css 0 行 diff + inline style only）+ R-248 App/api/index.css/main/utils/Shared/Shell/decor 0 改；432 tests / 112 skipped；7 contracts KEPT；72 routes；**已偿还** 26 条红线 R-240~R-265；**待人测**：① ChatEmpty 空对话 + Conversation 非空双场景视觉一致 ② focus-within 反馈 ③ disabled 视觉 ④ 1/3/10 行三档行高 ⑤ 黄金间距。 |
| ✅ v0.5.12 | (C5+) Thinking 屏复刻（AgentThinkingPanel 右 rail） | Loop Protocol v3 **第 13 次施行**（全 v3）；ThinkingCard.jsx 110→160 = R-270 上限；9 子步骤顺序锁死：① letter chip helper K/N/O 22×22 Inter 800 flex 居中（R-277 + R-289 跨浏览器）② AGENTS 扩 `{key, label, letter, name}` 4 字段 — clarifier→K Knowledge / sql_planner→N Nexus / presenter→O Objective（R-227.5.1 单字母装饰豁免首次确立）+ Agent name mono uppercase（R-278）③ Panel 272→320（R-276 + R-288 — Conversation 无 margin-right 字面方案 A 适用）④ 卡片 bg T.card → T.content + radius 8→10 + padding 12（R-279 + R-283）⑤ Header step count "N/3 STEPS" + `transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)'` 平滑无闪（R-280 + R-287）⑥ done svg checkmark 11×11 stroke 2.5 + T.success polyline（R-281）；保 TypingDots（thinking）+ ○ 字符（pending）⑦ sqlSteps S1/S2/S3 tag chip + T.accentSoft bg + slice 80→120 + textOverflow ellipsis（R-282）⑧ **R-286 hex 全面禁止首次确立** — `#09AB3B` / `T.accent + '60'` / `#FF9900` / `#FF990022` 全部清理 → `T.success` / `color-mix(in oklch, T.accent 38%, transparent)` / `T.warn`（grep `#[0-9a-fA-F]{3,6}` = 0 命中）⑨ R-290 SSE 鲁棒性 — `Array.isArray(events)` 兜底 + 全 optional chaining `?.type ?.agent ?.thought ?.step` 防三场景（空 events / 中断 / 字段缺失）崩溃；契约守护 R-266 2 exports 签名 byte-equal（diff 0 行）+ R-267 AGENTS 3 keys (clarifier/sql_planner/presenter) + R-268 getStatus/getDoneOutput/sqlSteps 业务逻辑 byte-equal + R-269 output 字段访问 byte-equal；R-291 Conversation.jsx 调用点字节码对齐 git diff = 0 行；范围 R-272 App/api/main/utils/Shared/Shell/decor 0 改 + R-274 KnotLogo sustained 仅 3 文件 + R-275 chat/ 其他 6 子模块 0 改 + R-284 App.css 0 行 diff；432 tests / 112 skipped；7 contracts KEPT；72 routes；**已偿还** 27 条红线 R-266~R-291；**字面分流体系扩展**（v0.5.10 R-227.5 + v0.5.12 R-227.5.1）；**待人测**：① 真实 SSE 3 agent K/N/O 状态切换 ② step count transition 平滑 ③ sqlSteps tag chip + ellipsis ④ 三档窗宽 ⑤ 跨浏览器 ⑥ SSE 异常兜底。 |
| ✅ v0.5.13 | (C5+) ResultBlock 偿还 — hex 清理 + emoji 偿还 + 局部视觉微调（受控） | Loop Protocol v3 **第 14 次施行**（全 v3）；ResultBlock 是 chat 子模块最复杂 UI（381 行 7 段 + 3 helpers），完整视觉重构超单 PATCH scope — 本 PATCH **受控**聚焦 3 类偿还（hex/emoji/token）；ResultBlock.jsx 381→420 = R-307 上限（v0.5.3 R-111 400→420 资深 ack 微调 — svg path 占行不可压）；9 子步骤：① getErrorKindMeta(T, kind) helper（Q1 修订 — Stage 1 useMemo → Stage 2 helper function 更解耦）+ ERROR_KIND_ICONS/TITLES 字典模块顶层（R-294 7 keys byte-equal）② const RB_SVG = {sparkle, search, wrench, chart, star, shield, triangle} 7 path 字典 + SvgPath helper（不动 Shared — R-309 sustained）③ AGENT_KIND_EMOJI 4 emoji → svg path 引用（字典名+4 keys byte-equal）（R-302）④ 收藏 ⭐🌟 → `<SvgPath d={RB_SVG.star} fill={pinned ? T.accent : 'none'}/>` 实心/描边双态（R-303 + R-314 onPin API 绑定）⑤ BudgetBanner 🛑⚠️ → SvgPath shield/triangle size=16（R-304）+ border T.warn + color-mix in oklch ⑥ ErrorBanner 7 emoji 保留（**R-302.5 语义级 Emoji 业务豁免首次确立** — 字面分流体系第三条 v0.5.10 R-227.5/v0.5.12 R-227.5.1/v0.5.13 R-302.5；7 emoji 是业务状态唯一辨识符号且无对应 SVG 视觉标准） ⑦ Token meter 行内 stat → TokenPill chip helper + mono 纯度（R-306 + R-315）— input_tokens/output_tokens/cost_usd/confidence/recovery_attempt 全 pill 风格 ⑧ **R-286 hex 全清扩展至 ResultBlock**（v0.5.x hex 残留最重组件收尾） — 14 处 hex 字面全清：3 处 `${T.accent}30` hex+alpha → `color-mix(in oklch, T.accent 19%, transparent)`（R-299）；ERROR_KIND_META 4 处 #cc6600/#FF990022 → getErrorKindMeta 内 T tokens（R-300）；BudgetBanner 3 处 #FF990022/#FF9900/#cc6600 → T.warn + color-mix；chart selector '#fff' → T.sendFg；recovery '#FF9900' fallback → T.warn；agent_costs '#0001' → T.bg（R-301）；grep `#[0-9a-fA-F]{3,6}` ResultBlock |grep -v boxShadow = 0 命中 ✓；5 处 color-mix 命中全部含 `in oklch`（R-312 精度）⑨ rgba 边界 R-313（仅 boxShadow；本 PATCH 0 boxShadow 使用 0 命中）+ msg 25 字段解构字面 byte-equal R-316；契约守护 R-292 7 props 签名 byte-equal + R-293 msg 25 字段解构 byte-equal + R-294 ERROR_KIND 7 keys/7 icons/7 titles byte-equal + R-295 7 layout 分支字面（R-117 sustained 14 处命中）+ R-296 resolveEffectiveHint/exportMessageCsv/MetricCard 业务 + R-297 5 handlers 调用方式不变；范围 R-309 8 核心非屏 + 17 屏 + App.css 0 改 + R-310 chat/ 其他 6 子模块 0 改 + R-274/250 KnotLogo sustained 仅 3 文件；432 tests / 112 skipped；7 contracts KEPT；72 routes；**已偿还** 26 条红线 R-292~R-316（含 R-302.5）；**字面分流体系第三条确立**；**hex 残留最重组件收尾**；**待人测**：① 7 intent 端到端 ② 收藏 svg star 双态 + onPin API ③ ErrorBanner 7 类 kind emoji 保留 ④ Token meter pill 对齐 ⑤ SQL/CSV/followup 业务回归。 |
| ✅ v0.5.14 | (C5+) ResultBlock 视觉大重构 — v0.5.x ResultBlock 维度收官 + 三大设计先例 | Loop Protocol v3 **第 15 次施行**（全 v3）；ResultBlock.jsx 420→440 = R-332 上限 v0.5 **final ack**（R-341 锁定 — v0.5.x 序列对 ResultBlock 行数最后一次扩张；v0.6 必须开启子组件拆分 6 候选：MetricCard.jsx / TableContainer.jsx / InsightCard.jsx / BudgetBanner.jsx / ErrorBanner.jsx / TokenMeter.jsx）；7 子步骤顺序锁死：① Observation card brandSoft inset — `color-mix(in oklch, T.accent 8%, transparent)` bg + `color-mix(in oklch, T.accent 25%, transparent)` border + svg info icon + "OBSERVATION" mono uppercase brand color（R-323 + Codex 8% 精确；**R-227.5.1 装饰豁免延伸第二处** — 仅 ResultBlock Insight 容器；其他屏"洞察"中文保留）② Suggestion chips height 28 + radius 14 + chevron svg + T.content + lineHeight 1 + center + outer `&& onFollowup` conditional rendering（R-324/343 + R-342 SavedReports 内嵌守护落地）③ **Token meter 反向修正 TokenPill→inline stat + svg ↑↓ icon**（R-325 = v0.5.13 R-306/315 **受控撤回 — v0.5.x 红线撤回首例**；架构判定：**红线服从视觉真理；严格复刻 > 局部推测性红线**；TokenPill helper 完全删除 grep = 0；与 demo thinking.jsx L177-195 1:1 像素对齐）④ agent_costs chip pill 999 — height 24 + padding 0 10 + borderRadius 999 + bgInset border + svg icon T.accent 包裹（R-326）⑤ Table thead 删 uppercase — fontWeight 600→500 + textTransform 删 + letterSpacing `0.03em` → `'normal'`（R-327 + Codex 防 inherited 残留）⑥ SQL accordion `<>` text icon T.mono color T.text + 时长 mono flex:1 + textAlign right（R-328/344 + Codex；R-344 几何对称 `<` 与 `>` mono 等宽）⑦ grep 守护 — R-330 hex 0 + R-331 emoji 业务豁免 + R-338 KnotLogo 3 文件 + R-339 color-mix 6 处全 in oklch + R-340 rgba 0 命中；**三大设计先例首次落地**：① **红线撤回首例**（v0.5.13 R-306/315 TokenPill 受控撤回 — 红线非硬规则是软约束；视觉真理高于推测）② **R-341 v0.5 ResultBlock 行数收官**（LIMIT 历程 250→400→420→440 final；v0.6 必须子组件拆分）③ **R-227.5.1 装饰豁免延伸**（OBSERVATION 短英文 mono → 装饰豁免；仅 Insight 容器）；契约 R-317 ResultBlock 7 props 签名 byte-equal（diff vs origin/main 0 行）+ R-318 msg 25 字段解构 byte-equal + R-319 ERROR_KIND 7 keys/icons/titles + R-320 7 layout 分支 + R-321 业务逻辑（resolveEffectiveHint/exportMessageCsv/MetricCard）+ R-322 5 handlers 调用方式 byte-equal；R-342 SavedReports 守护（前置探查发现 SavedReports.jsx 不直接 import ResultBlock — 仅 Conversation.jsx 真实 import；R-342 转化为 R-317 签名 byte-equal + outer condition `&& onFollowup` 落地）；范围 R-334 App/api/main/utils/Shared/Shell/decor/SavedReports/16 屏 0 改 + R-335 chat/ 其他 6 子模块 0 改 + R-337 CSS 0 污染 + R-338 KnotLogo sustained 仅 3 文件；432 tests / 112 skipped；7 contracts KEPT；72 routes；**已偿还** 28 条红线 R-317~R-344；**v0.5.x ResultBlock 维度收官之战**（v0.5.3 拆分提取 → v0.5.13 hex+emoji 偿还 → v0.5.14 视觉大重构）。 |
| ✅ v0.5.15 | (C5+) Favorites 屏复刻（SavedReports）— v0.5.x 首个新顶层屏 + brandSoft 8% 全站闭环 | Loop Protocol v3 **第 16 次施行**（全 v3）；**v0.5.x 首个新顶层屏复刻**（v0.5.14 ResultBlock 收官后）；SavedReports.jsx 318→380 = R-363 上限正好（首次纳入 LIMIT 380；30→31 条）；9 子步骤顺序锁死：① 起手 grep Q3 LIMIT dict 标定（前置 SavedReports 未在 dict → 新增 380）② 5 处 hex 全清（pillBtn `'#fff'` → `T.sendFg` Q4 严禁 'white' / Warning #FF990022/#FF9900/#cc6600 → `T.warn` + `color-mix(in oklch, ${T.warn} 13%, transparent)` / Error `${T.accent}30` → `color-mix(in oklch, ${T.accent} 19%, transparent)`）③ SAVED_SVG 6 path 字典（bookmark/chevronL/pencil/refresh/download/table）+ INTENT_EMOJI 字典名 + 7 keys (metric/trend/compare/rank/distribution/retention/detail) byte-equal + value 偿还 svg path ④ Sidebar header 删 📌 + T.mono "收藏报表 N" ⑤ Sidebar SavedItem 重构 — bookmark svg 14×14 + gap 10（R-369 Codex 精度）+ brandSoft bg + `color-mix(in oklch, T.accent 25%, transparent)` border + 删 borderLeft 2px + time mono 9px T.muted "YYYY.MM.DD"（R-373 formatTime helper）⑥ Title block 22px fontWeight 600 + letterSpacing -0.01em + meta 行 mono + `│` U+2502 separator（R-370 字符精度）+ StatusDot frozen 视觉装饰硬编（Q5 不依赖业务字段）⑦ Original question quote inset — borderLeft 3px `color-mix(in oklch, T.accent 25%, transparent)` + background `color-mix(in oklch, ${T.accent} 8%, transparent)` **字面与 v0.5.14 R-323 ResultBlock Insight byte-equal**（**R-372 全站 brandSoft inset 设计语言闭环 — 未来全站 inset 沿用此字面**）+ "原始问题" mono uppercase + pin_note 合并入 quote ⑧ Table thead 删 uppercase + letter-spacing normal + fontWeight 600→500（R-357 v0.5.14 R-327 sustained）⑨ 4 按钮 emoji（✏️/🔄/📥/📊）→ SvgPath dict（pencil/refresh/download/table）+ pillBtn helper 保 disabled/loading 状态机；**D6 Shell 13 props 契约严守** — topbarTitle 仍传简单 string（不破 R-192/R-349 sustained）；视觉补偿全部在 Title block (R-355) — 22px + meta · + StatusDot frozen 加倍补回；契约 R-345 SavedReportsScreen 5 props 签名 byte-equal（diff vs origin/main 0 行）+ R-346 EmptyView/DetailView/safeParseRows/pillBtn 4 helpers + R-347 loadReports/handleDelete/handleRun/handleSaveEdit/handleExport 5 handlers + R-348 INTENT_EMOJI 字典名+7 keys byte-equal（仅 value 偿还）+ R-349 AppShell 调用 props（R-192 sustained）+ R-350 api 5 endpoint URL byte-equal；范围 R-365 App/api/index.css/main/utils/Shared/Shell/decor/16 屏/chat 7 子模块 0 改 + R-367 KnotLogo sustained 仅 Shared+Login+Shell 三文件 + R-368 CSS 0 污染（App.css 0 行 diff）；字面分流体系 sustained — R-302.5 banner ⚠️/🔍/❌ 业务豁免（v0.5.13） + R-227.5.1 "原始问题"+INTENT_EMOJI 装饰豁免延伸；R-286 hex 0 命中 v0.5.13/14/15 三 PATCH 三处守护扩展；432 tests / 112 skipped；7 contracts KEPT；72 routes；**已偿还** 29 条红线 R-345~R-373；**首个新顶层屏复刻** + **brandSoft 8% 全站设计语言闭环**；**待人测**：① SavedReports 加载 ② SavedItem 切换 ③ 编辑/重跑/导出/删除 ④ light+dark 双模式 Title block 极简感 ⑤ Quote inset 与 ResultBlock Insight 闭环视觉。 |
| ✅ v0.5.16 | (C5+) DataSources 屏复刻（tab_access Sources 部分）— 首个 admin tab 子模块复刻 + Inset 8% 三处闭环 + I.db 复用先例 | Loop Protocol v3 **第 17 次施行**（全 v3）；**首个 admin tab 子模块复刻**（v0.5.15 SavedReports 顶层屏复刻后）；tab_access.jsx 60→88 行 ≤ R-387 110 行预算（LIMIT dict 不动 — 250 远未触达）；9 子步骤顺序锁死：① baseline diff 标定 Users (L9-33) / Sources (L35-57) 边界（R-376 准备）② Summary grid 4 卡片 `repeat(auto-fit, minmax(180px, 1fr))` 替代 media query（R-378/394 Stage 2 Codex auto-fit）+ "已连接" brandSoft 8% bg + brand color label + sources.length 实数 + 3 placeholder（总 schema / 总表数 / 上次心跳）`—` mono + `title="后端数据对接中 (v0.6+)"` tooltip（Q1 加码）③ Table 容器 radius 10→12（R-380）④ thead bg → `color-mix(in oklch, ${T.accent} 8%, transparent)` + T.subtext color + T.mono + letterSpacing 0.06em + fontWeight 600→500 + 保 uppercase（R-381 — v0.5.14 R-327 删 uppercase 仅对 ResultBlock；本 PATCH thead 重出 uppercase + mono 工业感）⑤ Grid 5→6 列 `1.2fr 0.8fr 1.4fr 0.6fr 0.8fr 80px` + 表数列 `—` placeholder + tooltip（R-382 + Q2）⑥ Name 28×28 brandSoft + `<I.db width="14" height="14"/>` **复用 Shared.jsx 既有图标**（R-383 + Q3 修订 — **v0.5.x 资产复用首例**；inline svg dict 模式让位）+ flex 绝对居中（R-397）+ name span `T.mono` + ellipsis ⑦ Type inline chip — brandSoft 8% bg + T.accent color + padding 2 8 + radius 999 + 11px + letterSpacing 0.02em + T.mono（R-384/395 Stage 2 Codex 工业感）⑧ 每列 `minWidth: 0` (5 处) + `textOverflow: 'ellipsis'` (4 处) 兜底（R-396 Stage 3 列宽稳定性 — 防超长主机名挤出按钮）⑨ StatusDot 颜色 `s.status === 'online' ? T.success : T.warn` byte-equal sustained（origin/main 同字面）+ flexShrink: 0 防压缩（R-398 Stage 3 语义粘性）；**R-376 Users 部分 L9-33 字面零修改 — Stage 2/3 双重强制 out-of-scope**（含 `linear-gradient(135deg, ${T.accent}, #ff7a3a)` 渐变残留**保留**；hex 残留偿还推未来独立 admin/users PATCH；`git diff` L9-33 段 0 行 ✓）；**R-386 brandSoft 8% 全站第三处闭环** — `color-mix(in oklch, ${T.accent} 8%, transparent)` 字面在 ResultBlock (v0.5.14 R-323 Observation) + SavedReports (v0.5.15 R-372 Quote) + DataSources (v0.5.16 R-386 Summary+thead+Name icon+Type chip 4 处) **三屏 byte-equal**；**I.db 复用先例**（Q3 修订）— v0.5.13/14/15 inline svg dict（RB_SVG/SAVED_SVG）→ 本 PATCH 优先复用 Shared.jsx `I.*`；**架构判定**：未来如 Shared 已有图标**优先复用**（仅 Shared 缺失才 inline svg dict）；R-385 Sources hex 0 命中（grep `#[0-9a-fA-F]{3,6}` 排除 boxShadow = 0 hits；Users `#ff7a3a` 残留 R-376 豁免）；契约 R-374 TabAccess 8 props 签名 byte-equal + R-375 users/sources 数据流 + 5 handlers + roleChip + R-377 Sources 业务字段（s.name/db_type/db_host/db_port/db_database/status）byte-equal；范围 R-389 App/api/index.css/main/utils/Shared/Shell/decor/16 屏/Admin/SavedReports 0 改 + R-390 admin/ 其他 4 子模块（tab_resources/knowledge/system/modals）0 改 + R-391 chat/ 7 子模块 0 改 + R-393 KnotLogo R-199.5/222 sustained 仅 3 文件 + App.css 0 行 diff；字面分流体系 sustained — R-302.5 banner emoji 业务豁免（v0.5.13） + R-227.5.1 "OBSERVATION" 仅 ResultBlock Insight 容器（v0.5.14） — 本 PATCH thead 中文 + Summary 中文 label 保留；R-286 hex 0 命中扩展 v0.5.12~v0.5.16 五 PATCH；432 tests / 112 skipped（worktree env BIAGENT_MASTER_KEY 残留触发 R-74 预存在问题 — CI 干净 env 全绿）；7 contracts KEPT；72 routes；**已偿还** 25 条红线 R-374~R-398（20 Stage 1 + 2 Stage 2 + 3 Stage 3）；**首个 admin tab 子模块复刻 + Inset 8% 三处闭环 + I.db 复用先例**三大设计先例同时落地；**待人测**：① Admin 切 admin-sources tab Summary grid + 6 列 + db icon + type chip 视觉 ② 切 admin-users tab **视觉完全原始**（含橘色渐变残留 R-376）③ 编辑/删除按钮 onEditSource/onDeleteSource ④ **三档窗宽实测**（1024/1280/1920）⑤ **超长主机名 ellipsis 兜底** ⑥ 4 处 tooltip 悬停 ⑦ **Inset 8% 三屏视觉一致**。 |
| ✅ v0.5.17 | (C5+) AdminAudit 屏复刻 — v0.5.x 第二顶层屏 + Inset 8% 闭环铁律化 + rgba 豁免架构原则确立 | Loop Protocol v3 **第 18 次施行**（全 v3）；**v0.5.x 第二个顶层屏复刻**（v0.5.15 SavedReports → v0.5.17 AdminAudit）；AdminAudit.jsx 264→372 行 ≤ R-425 LIMIT 380（新增 LIMITS dict 31→32 条）；9 子步骤顺序锁死（**R-409 优先 Step 1 — 铁律化里程碑**）：① baseline + LIMIT 新增 + **R-409 brandSoft 8% 闭环字面率先落地**（thead bg + Avatar bg）② Topbar 删 📋 emoji → "审计日志"（R-404）③ Stat 4-card grid `repeat(auto-fit, minmax(180px, 1fr))` + 4 inline cards（总记录数/今日/失败数/涉及用户）+ Q1 tooltip placeholder `title="后端聚合 API 对接中 (v0.6+)"` 4 处命中 + statCardStyle/statLabelStyle/statValueStyle helpers ④ Filter strip Field helper mono uppercase 0.06em + bgInset + **D2 双兼模式** 4 字段 Label `操作人 (Actor ID)` / `操作类型 (Action)` / `资源类型 (Resource Type)` / `起始时间 (Since)` + Placeholder `输入用户 ID...` / `如 auth.login...` / `如 user / budget...` / `YYYY-MM-DD...`（业务字段 byte-equal + Demo 工业感平衡 — 防 admin 混淆 actor_id 与 username）+ 重置 ghost + 查询 primary T.accent+T.sendFg（R-416 严禁 'white'）⑤ Table HTML `<table>/<thead>/<tbody>/<th>/<td>/<tr>` 全删 → CSS Grid 7-col `1.4fr 1fr 1.3fr 2fr 0.7fr 0.6fr 60px`（时间/Actor/Action/资源/IP/状态/详情按钮）+ thead 视觉应用 R-409 brandSoft 8% bg + T.subtext + mono + 0.06em + uppercase + fontWeight 500 ⑥ Avatar 22×22 brandSoft 8% bg + T.accent color + flex 居中 + flexShrink: 0 + role chip mono uppercase 10px + **ActionChip helper**（R-411 `actionColor(T, action)`: auth.* → T.warn / budget.*+prompt.*+fewshot.* → T.accent / export.* → T.warn / default → T.muted；R-426 chip 三件套 `color-mix(in oklch, ${color} 12%, transparent)` bg + `padding: '2px 8px'` + `borderRadius: 4` + `fontWeight: 500` + fontSize 11 + T.mono）⑦ **StatusDot inline helper**（v0.6 候选移入 Shared 与 ResultBlock/AdminBudgets 共用）— 6×6 圆 + `currentColor` + flexShrink: 0 + "成功"/"失败" 文字 + **R-428 actor null check** `displayName = row.actor_name \|\| row.actor_id \|\| 'System'` + `displayInitial = (displayName \|\| 'S').charAt(0).toUpperCase()` — Table cell 渲染 actor 字段全走兜底链；mock 系统级日志（actor_name=null）不崩溃 ⑧ Pagination + **R-430 边界 disabled**（`page === 1` / `items.length < size`）+ Redacted hex 全清（`#FF990033` → `color-mix(in oklch, ${T.warn} 20%, transparent)` + `#cc6600` → `T.warn`；R-414）+ **R-427 cursor:help**（redacted 高亮 span 加 `cursor: 'help'` + `title="敏感字段已脱敏"`）+ **R-429 DetailJsonView try-catch**（`try { JSON.parse } catch { return <pre>{raw}</pre>; }` — 畸形 JSON 兜底显原始字符串，防主界面卡死）+ success `'#2e7d32'` fallback hex 全删 → `T.success`（R-417）+ grep `#[0-9a-fA-F]{3,6}` AdminAudit \| grep -v boxShadow \| grep -v rgba = **0 命中** ✓（R-418）⑨ **R-415 R-313 sustained 扩展豁免 #2** — drawer overlay `rgba(0,0,0,0.4)` 上方 evidence 注释（Chrome < 111 / WebKit backdrop-filter OKLCH→sRGB fallback GPU 渲染抖动；rgba 全平台稳健；架构原则确立 — 红线服从浏览器真理）+ grep `rgba(` AdminAudit = **1 命中** ✓ + 三处版本同步 0.5.16→0.5.17；**R-409 brandSoft 8% 闭环字面 4 屏 byte-equal**（v0.5.14 R-323 ResultBlock + v0.5.15 R-372 SavedReports + v0.5.16 R-386 tab_access + **v0.5.17 R-409 AdminAudit**）— **视觉规范铁律化里程碑**；`git grep` 命中 4 文件；**R-313 rgba 豁免架构原则**：两处豁免（v0.5.11 R-254 boxShadow + v0.5.17 R-415 modal overlay）；**StatusDot 首次 inline 抽取**（Q5 准许 — v0.5.x 冲刺 R-419 优于组件提取）；**D2 双兼模式**（Stage 2 强化 — 业务字段名 + Demo 风格 Label/Placeholder 平衡）；**R-428~R-430 三大复杂业务屏守护**新模式确立；契约 R-399 5 props 签名 byte-equal + R-400 6 useState slots byte-equal + R-401 `api.get('/api/admin/audit-log?...')` URL + 4 filter query params byte-equal + R-402 `_PAGE_SIZES = [50, 100, 200]` + `_REDACTED_RE = /••••redacted••••/g` 字面 byte-equal + R-403 row 13 字段访问 byte-equal（id/created_at/actor_name/actor_role/actor_id/action/resource_type/resource_id/client_ip/user_agent/request_id/success/detail_json）；范围 R-419 App/api/index.css/main/utils/Shared/Shell/decor/15 屏（不含 AdminAudit）/Admin/SavedReports/tab_access 0 改 + R-420 admin/ 4 子模块 0 改 + R-421 chat/ 7 子模块 0 改 + R-422 App.css 0 行 diff + R-423 KnotLogo R-199.5/222 sustained 仅 Shared+Login+Shell 三文件；字面分流体系 sustained — R-302.5 drawer ✓/✗ Unicode 业务豁免 + R-227.5.1 thead 中文 + Filter Label 中英双兼装饰豁免；R-286 hex 0 命中扩展 v0.5.13~v0.5.17 五 PATCH sustained；432 tests / 112 skipped（CI 干净 env；本地 worktree BIAGENT_MASTER_KEY 残留 R-74 预存在问题）；7 contracts KEPT；72 routes；**已偿还** 32 条红线 R-399~R-430（27 Stage 1 + 2 Stage 2 + 3 Stage 3）；**五大设计先例同时落地**（v0.5.x 第二顶层屏复刻 + Inset 8% 闭环铁律化 + rgba 豁免架构原则 + StatusDot 首次抽取 + R-428~R-430 复杂业务屏守护 + D2 双兼模式）；**待人测**：① 进 admin → 切 admin-audit → loading → items 加载 ② Filter 4 字段 D2 双兼显示 + 重置 + 查询 ③ **R-430 翻页边界**（page=1 上一页 disabled + items < size 下一页 disabled）+ 50/100/200 size 切换 ④ eye 按钮 → drawer 打开 → 5 KV + DetailJsonView ⑤ **R-427 cursor:help 实测**（悬停 redacted 显帮助光标 + tooltip "敏感字段已脱敏"）⑥ **R-429 畸形 JSON 兜底实测**（mock not-a-json）⑦ **R-428 actor null check 实测**（mock actor_name=null 显 actor_id 或 'System'）⑧ Drawer click outside 关闭（R-415 rgba backdrop 仍生效）⑨ **三档窗宽实测**（1024/1280/1920）⑩ **light+dark 双模式 Stat/Filter/Table/Drawer 视觉一致** ⑪ **Inset 8% 四屏视觉一致**（ResultBlock/SavedReports/DataSources/AdminAudit）。 |
| ✅ v0.5.18 | (C5+) AdminBudgets 屏复刻 — v0.5.x 第三顶层屏 + Inset 8% 闭环铁律化 100% 覆盖后端管理资产屏 + borderLeft 25% 第二处闭环 + 技术债登记 | Loop Protocol v3 **第 19 次施行**（全 v3）；**v0.5.x 第三个顶层屏复刻**（v0.5.15 SavedReports → v0.5.17 AdminAudit → v0.5.18 AdminBudgets）；AdminBudgets.jsx 232→357 行 ≤ R-460 LIMIT 380（新增 LIMITS dict 32→33 条）；**业务模型不兼容裁定**：保 multi-scope CRUD（R-16/R-23/R-21 后端硬契约）+ 借 demo 视觉语言（D2 双兼模式延伸）；9 子步骤顺序锁死（R-444 优先 Step 1）：① R-444 brandSoft 8% 闭环率先落地 ② 删 💰 ③ Hero 4-stat grid + **Q1 部分聚合**（第 1 卡 budgets.length） + R-461 transition 0.3s ④ Form D2 双兼 + R-462 gap 16 + minmax + 双按钮 ⑤ Table → CSS Grid 7-col ⑥ BudgetActionChip helper ⑦ EnabledChip helper（StatusDot pattern）⑧ Rules note brandSoft + R-465 borderLeft 3px 25% + Tag chip + **D9 WarnNote** ⑨ 三处版本同步 + R-463/R-464 双手测；**KNOT 视觉铁律宣告：Inset 8% 设计语言正式覆盖 100% 后端管理资产屏** — `color-mix(in oklch, ${T.accent} 8%, transparent)` 字面 5 屏 byte-equal（v0.5.14/15/16/17/**18**）；**R-465 borderLeft 3px 25% 第二处闭环**（v0.5.15 R-356 + v0.5.18 R-465 字面 byte-equal）；**技术债登记**（D8/Q5）— BudgetActionChip + EnabledChip + StatusDot 累计第二次复用；v0.6.0 首个 PATCH 移入 Shared.jsx 偿还承诺（R-365 sustained）；**Q1 部分聚合先例**；**D9 WarnNote 模式**（warning emoji 偿还通用方案）；契约 R-431 5 props + R-432 4 useState + R-433 api 4 endpoint + R-434 3 常量 + R-435 SCOPE_HINT + R-436 7+5 字段 byte-equal + R-437 R-21 守护 byte-equal + R-438 4 handlers 调用方式 byte-equal；范围 R-454/455/456/457/458 全 sustained；R-452 hex 0 + R-453 emoji 全清 + R-444 5 文件 + R-465 2 文件命中；432 tests / 112 skipped；7 contracts KEPT；72 routes；**已偿还** 35 红线 R-431~R-465（30+2+3）；**五大设计先例同时落地**（v0.5.x 第三顶层屏 + Inset 8% 100% 覆盖 + borderLeft 25% 第二处闭环 + 技术债登记 + Q1 部分聚合 + D9 WarnNote）。 |
| ✅ v0.5.19 | (C5+) AdminRecovery 屏复刻 — ⭐ admin 顶层屏三部曲收官 + Inset 8% 闭环第六处铁律加冕 + borderLeft 25% 第三处闭环铁律加冕 + R-495 字面严防立约 | Loop Protocol v3 **第 20 次施行**（全 v3）；**⭐ admin 顶层屏三部曲收官**（v0.5.17 Audit + v0.5.18 Budgets + v0.5.19 Recovery — 视觉一致性 100% 覆盖）；AdminRecovery.jsx 152→242 行 ≤ R-490 LIMIT 380（LIMITS dict 33→34 条）；9 子步骤顺序锁死（R-480 优先 Step 1）：① R-480 brandSoft 8% 闭环字面率先落地 ② 删 🛡️ ③ PeriodTab + R-492 active box-shadow ④ KPI 3 cards + KpiCard helper + R-491 transition + 第 3 卡 accent ⑤ Chart svg icon + Q1 动态 Tag + LineChart byte-equal + R-494 height=280 ⑥ Top user CSS Grid 5-col + Q2 VRP trophy svg + R-493 NaN 守护 ⑦ Rules note brandSoft inset + R-481 borderLeft 3px 25% 第三处 ⑧ emoji 全清 + hex 0 ⑨ R-495 字面 byte-equal git grep -F 双闭环 6+3 文件；**Inset 8% 闭环第六处铁律加冕**（6 屏字面 byte-equal v0.5.14/15/16/17/18/**19**）；**borderLeft 25% 第三处闭环铁律加冕**（3 屏 v0.5.15/18/**19**）— 设计语言铁律第二维度加冕；**R-495 字面 byte-equal 严防死守立约** — git grep -F 全站自动化校验制度化（视觉铁律执行机制升级）；**Q2 VRP 局部例外原则**（Shared 无对应资产 inline svg 允许；v0.6 偿还）；**D1 R-192 sustained**（Shell 0 改）；**D2 R-365 sustained**（Shared 0 改）；技术债登记加强（KpiCard/PeriodTab/TagChip/trophy svg 累计第三次复用；v0.6.0 移入 Shared.jsx 承诺加强）；契约 R-466 5 props + R-467 3 useState + R-468 api URL + R-469 period 3 + R-470 stats 10 字段 byte-equal；范围 R-485~489 全 sustained；432 tests / 112 skipped；7 contracts KEPT；72 routes；**已偿还** 30 红线 R-466~R-495（25+2+3）；**五大里程碑同时落地**（⭐ admin 三部曲收官 + Inset 8% 第六处铁律加冕 + borderLeft 25% 第三处闭环加冕 + R-495 字面严防立约 + Q2 VRP 局部例外原则 + 技术债登记加强）。 |
| ✅ v0.5.20 | (Cn+) admin/users 视觉偿还 — ⭐ R-376 hex 债务正式清偿（v0.5.x 最长 hold 4 PATCH 历史性纪录）+ TabAccess 全 OKLCH/T-System 时代 + Inset 8% 第七处扩展 | Loop Protocol v3 **第 21 次施行**（全 v3）；tab_access.jsx 88→90 行；LIMITS dict 不动；4 子步骤（R-501/R-504 优先 Step 1）；**R-376 hex 债务正式清偿** — `linear-gradient(...#ff7a3a)` + `color:'#fff'` → brandSoft 8% + T.accent；**TabAccess 全 OKLCH/T-System 时代**（Stage 3 §3 里程碑宣告）；**Inset 8% 闭环第七处扩展** — 6 文件恒定深耕（tab_access 内部命中 1→3）；**R-518/519/520 守护立约**（R-376 余效验证 + Sources 绝对零度 md5 byte-equal + roleChip 装饰豁免界限）；**Avatar inline 第四次复用** — 7+ inline helpers v0.6 Shared 承诺加强；契约 R-496 9 props + R-497 5 字段 + R-498 roleChip + R-499 2 handlers byte-equal；范围 R-513/R-514/R-520 全 sustained；432 tests / 112 skipped；7 contracts KEPT；72 routes；**已偿还** 25 红线 R-496~R-520（20+2+3）；**四大里程碑同时落地**。 |
| ✅ v0.5.21 | (C5+) admin tab_resources 屏复刻 — ⭐ Inset 8% 铁律进攻性扩张第八处（文件总数 6→7）+ 80% 深度宣告 | Loop Protocol v3 **第 22 次施行**（全 v3）；tab_resources.jsx 85→110 行；LIMITS dict 不动；5 sub-step（R-548 前置 + R-531 优先 + R-539 收尾）；**⭐ Inset 8% 铁律从"防御性稳固"转向"进攻性扩张"**（6→7 文件）；**项目单色化一致性进入 80% 深度**（Stage 3 §3 里程碑宣告）；R-546 Model ID Mono + R-547 API Key 安全感 + R-548 核爆级 props 守护 + R-549 价格 $ 单位 + R-550 borderBottom byte-equal 五大守护立约；R-484 'white' 字面残留偿还（Spinner #fff → T.sendFg）；契约 R-521 12 props + R-522~R-524 业务字段 byte-equal；范围 R-541/R-542/R-548 全 sustained；432 tests / 112 skipped；7 contracts KEPT；72 routes；**已偿还** 30 红线 R-521~R-550（25+2+3）；**六大里程碑同时落地**。 |
| ⏳ v0.5.23+ | (C5+) 剩余 2 PATCH 收官 | v0.5.23 tab_knowledge 3 sub-tabs 合一（knowledge + fewshot + prompts）+ v0.5.24 modals.jsx + v0.5.x 正式收官；**⭐ 自审简化协议（v0.5.22 起授权持续）** — 资深 ack 授权 v0.5.x 收官冲刺：Stage 1 草案预纳入 Stage 2/3 候选 + Stage 4 直接落地；通用约束 sustained: | 5 admin tabs（catalog/fewshot/knowledge/prompts/system）；业务屏（database/sql-lab/conversations/settings）当前不存在为独立屏（Chat.jsx 内部路由或概念占位）；执行模板由 v0.5.7~v0.5.21 十五 pilot 确立；视觉复刻通用约束由 v0.5.8 § Visual Replication Protocol + 字面分流体系三条（R-227.5 / R-227.5.1 / R-302.5）+ R-286 hex 全面禁止 + **R-480 brandSoft 8% 全站铁律加冕第六处（v0.5.19）+ 七处扩展（v0.5.20）+ 进攻性扩张第八处（v0.5.21 6→7 文件）** + **R-481 borderLeft 3px 25% 第三处闭环铁律加冕（设计语言铁律第二维度）** + **R-495 字面 byte-equal 严防死守立约**（git grep -F 全站自动化校验制度化）+ **R-518 hex 余效验证立约 + R-519 Sources 绝对零度立约 + R-520 装饰豁免界限立约**（v0.5.20 守护制度化）+ **R-546~R-550 五大守护立约**（Model ID Mono / API Key 安全感 / 核爆级 props / 价格业务标签 / borderBottom byte-equal — v0.5.21 守护制度化）+ **I.db 资产复用先例（Shared 优先）** + **R-313 rgba 豁免架构原则**（boxShadow + modal overlay）+ **D9 WarnNote 模式**（warning emoji 偿还通用方案）+ **Q1 部分聚合先例**（Hero placeholder 进化）+ **Q2 VRP 局部例外原则**（Shared 无资产时 inline svg 允许）+ v0.5.14 红线撤回首例设计先例锁定；v0.6 路线图加强 **ResultBlock 子组件拆分**承诺（R-341 锁定 — 6 候选）+ **8+ inline helpers 移入 Shared.jsx 技术债偿还承诺**（StatusDot/ActionChip/BudgetActionChip/EnabledChip/WarnNote/KpiCard/PeriodTab/TagChip/Avatar/medal/trophy svg/**trailingChip** — 累计第六次复用确认）|
| ✅ v0.5.5 | (Cn) cleanup（遗留清理） | Loop Protocol v3 **第 6 次**完整 PATCH 内施行（D1-D5 全锁定 + 15 红线 R-139~R-153）；**v0.5.x 序列首个减法 PATCH（Negative Delta -18 行）** — 物理删 `knot/adapters/notification/lark.py` (29 行) v0.3.2 占位 stub（业务侧 0 调用，接口契约 base.py + __init__.py 保留供未来加 adapter）；删 2 个 lark 测试 cases (`test_lark_satisfies_protocol` + `test_lark_send_raises_not_implemented`) 受控降级 backend 432→430；sync LLM API 8 处 docstring 加 R-152 锁定模板首行 `[DEPRECATED v0.5.5; target removal in v1.0] Use async equivalent (a*) instead.`（分散在 7 个文件：llm_client.py 2 处 + _llm_invoke.py / sql_planner.py / sql_planner_llm.py / clarifier.py / presenter.py / orchestrator.py 各 1）；R-142 函数体零修改（仅 docstring）；R-149 幽灵 import 0 残留；R-150 非 SSE 手测 8 处 callable ✓；R-153 关键路径表 notification 描述改"通知接口抽象层"；D2 sync API v1.0 删除目标（query_steps 非流式仍依赖，实际删留 v0.6.x）；3 commit；430 tests / 112 skipped；7 contracts KEPT 不动；72 routes 不变；不动 frontend / scripts / requirements / package / pyproject / .importlinter；**已偿还** 15 条红线 R-139~R-153。 |

> v0.5.x 主线推进 1.0 release 准备。1.0 团队公测起点。

## v0.6.x 路线图（v0.5.44 之后 — Phase A Deploy-Ready 内测可启动门 → 4 周缓冲 → Phase B 评估）

v0.5→v0.6 滚动整体审核 9 项决议（S-1~S-9）LOCKED 后开启。Phase A 范围窄而硬：sanitize + bi_agent 兼容层清算 + 默认 prompts 明文化 + Deploy-Ready 内测可启动门 4 大主题；业务功能 0 变更。

| PATCH | 主题 | 关键交付 |
|---|---|---|
| ✅ v0.6.0 | (Phase A) Sanitize + bi_agent 兼容层清算 + **Deploy-Ready 内测可启动门** | Loop Protocol v3 **第 26 次完整施行**（首次跨 MINOR 角色滚动 + 首次公开承诺撤回 + 首次 sanitize/Deploy-Ready 二合一 PATCH）；18 In-Scope (F1~F8+F11~F18) + 15 OOS（Phase B / v0.7+ 推迟）+ 8 红线 R-PA-1~8（含 R-PA-6.1 业务代码 docstring 字面豁免立约）+ 13 闸门 + 7 commit + commit 0 LOCKED 终稿归档；撤回 v0.5.0 R-67/68/74 公开承诺（"承诺接收方为空"治理学习）；默认 prompts 抽 knot/prompts/*.md + DB seed；fernet.py 单源化 237→102；merge 后 30 分钟可云服务器 docker run 内测部署 + 默认 admin/admin123；413 tests / 112 skipped（净 -19：F14.1/14.2/14.3 整文件删 19 tests）；7 contracts KEPT；77 routes；详 [docs/plans/v0.6.0-phase-a-sanitize.md](docs/plans/v0.6.0-phase-a-sanitize.md) + [CHANGELOG v0.6.0 撤回声明](CHANGELOG.md#unreleased---v060-phase-a-knot-sanitize--bi_agent-兼容层清算--deploy-ready-内测可启动门) |
| ✅ v0.6.1（Phase B 决议 B 修订版首个正式 PATCH）| 窄场景宣告 + 时间语义引擎 — Loop Protocol v3 第 29 次施行；R-PA-5 Day 1（2026-05-14）启动（提前于 LOCKED "Day 7+"）；v0.5/v0.4 双守护者 Phase B 预评估 §6 V4 ⭐⭐⭐ 必做；F1 窄场景宣告（README §能做不能做 + Login + ChatEmpty hint）+ F2 时间语义引擎 knot/core/time_resolver.py [NEW 234 行 + 32 守护测试]；5 类核心时间表达 + 同比基准（latest 锚定跨年正确）+ 2026 节假日 hardcoded + D-1 数据延迟默认；R-PA-PB-V1 + R-PA-PB-1~7 共 8 红线立约；R-PA-8 工具豁免 v0.6.1-* 文件；453 tests / 112 skipped（+32）；7 contracts KEPT；详 [docs/plans/v0.6.1-narrow-scope-time-resolver.md](docs/plans/v0.6.1-narrow-scope-time-resolver.md) |
| ✅ v0.6.0.2（micro PATCH）| ResultBlock 6 子组件拆分（v0.5.14 R-341 承诺偿还）— Loop Protocol v3 第 28 次施行；Phase B 预评估 §6 v0.5 守护者强制建议 5 前置；ResultBlock.jsx 449→279（-170）+ 6 子组件（MetricCard / TableContainer / InsightCard / BudgetBanner / ErrorBanner / TokenMeter）；R-PA-PB-V0.1~V0.6 守护红线；421 tests sustained；7 contracts KEPT；详 [docs/plans/v0.6.0.2-locked.md](docs/plans/v0.6.0.2-locked.md) |
| ✅ v0.6.0.1（micro PATCH）| 5 in 1 hotfix + 守护者立约归档 — Loop Protocol v3 第 27 次施行（v0.5.22 自审简化协议 sustained）；R-PA-5 Day 0 触发后立即启动；5 in 1：① SavedReports ⭐ → inline svg star（F1 — v0.5.13 R-303 遗漏视觉债）② R-PA-8 守护工具 scripts/check_phase_b_leakage.py（F2 — 检测 Phase B 字面 + Schema 列 + 文件 glob；R-PA-14 自指环避免）③ R-PA-9/10/11 立约归档 LOCKED §3 附录 + CHANGELOG（F3 — 守护者 G-4 提议）④ G-5 .github/workflows/ci.yml docker build CI 闸门（F4 — continue-on-error 非阻塞 R-PA-15）⑤ G-6 tests/scripts/test_dockerfile_copy.py R-PA-7 字面单元测试（F5 — 3 测试 / regex grep）；6 红线 R-PA-12~R-PA-17 立约；421 tests / 112 skipped（+3 G-6 测试）；7 contracts KEPT；详 [docs/plans/v0.6.0.1-locked.md](docs/plans/v0.6.0.1-locked.md) |
| ⏳ 内测期（4 周缓冲） | 团队 5-10 人真实使用反馈 | 资深架构师开 GitHub issue `🚀 v0.6.0 Phase A — 内测启动` + label `/start-internal-test` 创建日 = R-PA-5 Day 0 计时起点；**严禁 Phase B 草案**（R-PA-5 + R-PA-8）|
| ⏳ Phase B 评估 | 三方拍板（执行者 + 守护者 + 远古守护者 + 资深） | 视真实需求：① 需求充分 → Phase B v0.6.1 草案启动；② 需求不足 → Phase B 缩减（仅做 OOS-5/6 代码组织债务）；③ 需求归零 → Phase B 跳过 → 直接 1.0 团队公测准备 |

**v0.6.0 Loop Protocol v3 施行回顾**：

| 阶段 | 内容 | 关键决议 |
|---|---|---|
| Stage 1 v1 草案 | v0.6 执行者起草 — 18 In-Scope + 15 OOS + 6 红线 + 12 闸门 + 7 commit | 2026-05-13 |
| Stage 1 v2 草案 | Deploy-Ready 内测可启动门修正 — 加 R-PA-7 + 闸门 13 + F18 扩 5 子项 + 附录 J | 同日 |
| Stage 2 辅助 AI 初审 | Codex + 其他 AI — 3 条预检全接受（KNOT_MASTER_KEY 单行命令 + Dockerfile COPY 熔断 + 缓冲期标记机制）| 同日 |
| Stage 3 v0.5 守护者终审 | 8 处修订（P-1~P-6）+ 2 项补丁（N-1 R-PA-8 + N-2 catalog 方案 C）+ 0 否决 | 同日 |
| Q-E1.A / Q-E2.A 执行者澄清 | commit 3/4 边界 + audit 工具 --mode 分模式 | 同日 |
| 资深架构师拍板 | §5 6 项 + Q-E1.A + Q-E2.A 共 8 项 LOCKED | 同日 |
| commit 4 守护者复核 | 0 否决 + 2 修订（M-1/M-2 grep audit）+ G-1 R-PA-6.1 立约（资深拍板）+ G-3 LOCKED retro 推 v0.6.0 收官 | 同日 |
| **总计** | **第 26 次完整 v3 三阶段施行** — 首次跨 MINOR 角色滚动 + 首次公开承诺撤回 + 首次 sanitize/Deploy-Ready 二合一 + LOCKED 终稿盲区识别 4 处补救（commit 1 五处 / F14.3 修订 / F18 提前联动 / R-PA-6 闸门修订） | — |

## v0.2.0 Go 重写技术栈（分支 feat/go-rewrite）

- HTTP：`gin-gonic/gin` 或 `gofiber/fiber`
- ORM：`gorm.io/gorm`
- LLM：`anthropic/anthropic-sdk-go` + `sashabaranov/go-openai`
- JWT：`golang-jwt/jwt`
- 前端：React + Vite（保留 ECharts 逻辑，加构建步骤）
