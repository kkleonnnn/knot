# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased] - v0.5.9 (C5+) Shell 屏复刻 — 首个真正屏复刻 PATCH

> v0.5.7 Login pilot + v0.5.8 Visual Replication Protocol 后第一个真正屏复刻 PATCH。Shell 是 18 屏的容器，**最高优先级守 R-192 AppShell 13 props 签名 byte-equal（宪法级）**。
>
> Loop Protocol v3 **第 10 次施行** — 恢复全 v3 三阶段评审（Shell 是真视觉重构，简化协议不适用）。视觉聚焦 4 处偿还/解禁。

### Changed — Shell.jsx 视觉重构（172 → 186 行 ≤ 220 R-205）

按 Stage 3 §2 7 子步骤顺序锁死执行：

**Brand 区**：
- 24×24 sparkle 圆角块 + "KNOT" 文字 → `<KnotLogo T={T} size={20}/>`（**v0.5.7 R-186 抗诱惑首次解禁**）
- logoArea 高度 padding 14+12 ≈ 38 → 56px + borderBottom（与 main header 52 视觉对齐）
- Q1 修订：原提议 size=16，资深 Stage 2 改 20（Atom 轨道 16px 下细节丢失）

**Sidebar**：
- 宽度 256 → 224（match demo）
- SideNavRow Label 加 `text-overflow: ellipsis + white-space: nowrap + overflow: hidden`（Q2 加码 — 防 224px 中文长 label 溢出）
- Admin nav 3 处 emoji 偿还：💰 预算 / 🛡️ Recovery / 📋 审计日志 → 纯 SVG（`I.zap` / `I.shield` / `I.book`，36 names 已存在前置 grep 双保险确认）
- NavItem active 指示 borderLeft 2px → **absolute span 2px brand bar 右侧**（Q4 防 `overflow: hidden` 裁切）
- SideHeading 字体 sans 10.5px → `T.mono` 10px（与 Login "SIGN IN" mono 风格统一）

**User row（Footer）**：
- 头像渐变 `linear-gradient(135deg, ${T.accent}, #ff7a3a)` → 纯 `T.accent`（v0.5.6 brand 切换遗漏的橘色残留**全局净空** — R-211 grep `#ff7a3a` 全文 0 命中）
- 高度 borderTop + paddingTop 10 → 56px + borderTop

**Topbar**（保产品现状 — D8 宪法级 ack）：
- AppShell 内集成 header 52px 不拆为独立 TopBar 组件（防 13 props 签名 + 18 屏调用方破坏）
- showConnectionPill / connectionOk 业务逻辑不变（R-196）

### Architecture — 宪法级守护（守 18 屏不崩溃）

**R-192 AppShell 13 props 签名 byte-equal**（宪法级 — 三方共识）：
- diff vs origin/main = 0 行（完整签名块完全一致）
- 13 props: `T, user, active, sidebarContent, topbarTitle, topbarTrailing, showConnectionPill, connectionOk, hideSidebarNewChat, onToggleTheme, onNewChat, onNavigate, onLogout, children`

**R-193 SideHeading + SideNavRow export name + 签名 byte-equal**（chat / saved-reports / admin/* 12+ 文件 import 这两个名字）。
**R-194 onNavigate / onToggleTheme / onLogout / onNewChat 调用方式 + active 字面 byte-equal**。
**R-195 'admin-' 前缀分流逻辑 byte-equal**（v0.4.1.1 hotfix Bug 1 既有模式 — 改 active 视觉时严禁触碰 `active.startsWith('admin-')` if 分支）。
**R-197 `API &amp; 模型` HTML entity 字面 byte-equal**。

### Architecture — 范围守护（v0.5.8 § Visual Replication Protocol 模板）

**R-199.5 KnotLogo 解禁仅限 Shell.jsx LogoArea 一处**（v0.5.7 R-186 抗诱惑首次解禁，明确边界）：
- grep `KnotLogo|KnotMark|KnotWordmark` 仅 3 文件命中：`Shared.jsx`（定义）/ `screens/Login.jsx`（v0.5.7）/ `Shell.jsx`（v0.5.9 解禁）
- 严禁蔓延 Home / ThinkingCard / 其他业务屏

**R-210 CSS 污染防御**：Shell 视觉重构全用 inline style 对象 + 已有 utility；`git diff frontend/src/App.css` = 0 行 ✓；Shell.jsx 0 新 className 字面。

**R-213 版本同步血缘扩展**：Shell.jsx 严禁 version 字面（保 Login 页脚唯一显示位）；grep `0.5.X|v0.5` = 0 命中（注释中版本号引用清理为 R-XXX 编号）。

**R-207/208 范围守护**：
- 17 屏 + 12 子模块 byte-equal（`git diff origin/main HEAD -- frontend/src/screens/` 仅 Login.jsx 页脚 v0.5.9 字面）
- App.jsx / api.js / index.css / main.jsx / utils.jsx / Shared.jsx / decor/NarrativeMotif.jsx 0 改

### Loop Protocol v3 — 第 10 次施行（恢复全 v3）

- **Stage 1**（v0.5 执行者）：v0.5.7 LOCKED 模板填空 — Shell 现状 vs demo 视觉差距 10 维度 + D1-D8 决策 + R-192~R-209 红线（18 条）+ Q1-Q5 风险项
- **Stage 2**（资深 + Codex）：D8 宪法级 ack + Q1 修订 16→20 + 加 R-199.5 KnotLogo 解禁边界 + R-210 CSS 污染防御 + Q2 加码 ellipsis
- **Stage 3**（v0.4 守护者）：加 R-211 #ff7a3a 全局净空 + R-212 'admin-' 前缀分流字面 byte-equal + R-213 Shell.jsx 严禁 version 字面 + 7 子步骤实施顺序锁死
- **Stage 4**（执行者）：3 commit 落地，全程 0 修订；commit 1 内 7 子步骤严守顺序

13/13 决策点（D1-D8 + Q1-Q5）一致（Q1 唯一修订 16→20）；新增 6 条红线（Stage 2: 3 + Stage 3: 3）；红线总数 22（**R-192~R-213**，含 R-199.5）。

### Migration

- 客户端无任何 breaking change（AppShell 13 props 签名 + SideHeading + SideNavRow export name byte-equal）
- 18 屏 + 12 子模块原样工作（R-207 守护证明）

### Tests

- backend：**432 passed** / 112 skipped（R-206 严格不变 — 0 测试增减）
- R-181 + R-185 sync test 自动跟随 0.5.9 PASS
- frontend build：`npm run build` 0 警告 0 error；bundle hash `index-VY5B4NF1.js` → `index-C67E7slY.js`

### 验收（待人测）

- [ ] 启动 dev server + 实际登录 → 18 路由切换肉眼校验：topbar title + topbar trailing + connection pill 状态 + sidebar active span 停在正确项
- [ ] admin 子页面切 tab 验证 R-212：进 admin/users → admin/budgets → admin/audit；sidebar admin nav 始终正确 active
- [ ] KnotLogo size=20 在 224px sidebar 视觉清晰可辨（Q1 验证）
- [ ] admin 12 项 nav row 长 label（如 "Few-shot 示例"）ellipsis 截断生效（Q2 验证）

### v0.5.x 路线图更新

- ✅ v0.5.7 (C5+) Login pilot
- ✅ v0.5.8 (Cn+) Chore — CI fix + Visual Replication Protocol
- ✅ **v0.5.9 (C5+) Shell 屏复刻**（首个真正屏复刻 PATCH，宪法级 R-192 三方共识）
- ⏳ v0.5.10+ (C5+) 1 屏 1 PATCH 渐进替换剩余 16 屏（home / thinking / favorites / 9 admin tabs / database / knowledge / catalog / sql-lab / settings / conversations）

---

## [Unreleased] - v0.5.8 (Cn+) Chore — CI Boot Smoke 修复 + Visual Replication Protocol

> v0.5.7 Login pilot 收官后 chore PATCH：**两件并一个** — 偿还 v0.5.0 R-72 留下的预存 CI bug，提炼 v0.5.7 经验为 v0.5.8+ 屏复刻铺路。
>
> Loop Protocol v3 **第 9 次施行**（**首次简化协议** — 跳 Stage 2/3 直接 Stage 4，资深 ack）。docs+ci PATCH，0 业务逻辑改动。

### Fixed — v0.5.0 R-72 遗留 CI 硬编 bug 偿还

**`.github/workflows/ci.yml` boot smoke version assertion 动态读 main.py（R-187）**：

- 旧：`assert app.version == '0.5.0'`（v0.5.0 R-72 时硬编，每个后续 PATCH 升版本必挂）
- 新：`expected = re.search(r'version="([\d.]+)"', open('knot/main.py').read()).group(1); assert app.version == expected`
- 效果：v0.5.1~v0.5.7 的 boot smoke matrix（only-knot / only-biagent / both-same）应该全绿 — 假设 R-72/77 业务代码本身正确（neither 路径之前一直 PASS 已验证 fail-fast 逻辑）
- 影响：以后任何 PATCH 升版本 ci.yml 自动跟随，无需 4 处版本同步（仅 main.py + smoke + Login 三处）

### Added — § Visual Replication Protocol（R-188）

**`CLAUDE.md` 加 § Visual Replication Protocol 段（59 行 ≤ 80 上限）**，与 Loop Protocol v3 并列定位为视觉复刻专项约束：

- **路径常量**：demo `/Users/kk/Documents/knot_ui_demo/v0.5/artboards/*.jsx`（设计代理，**不进产品**）/ 产品屏 `frontend/src/screens/*.jsx` / Foundation 资产（Shared.jsx + utils.jsx + decor/NarrativeMotif.jsx）
- **设计系统**（v0.5.6 锁定，严禁扩展）：OKLCH 单一色空间 brand 195°/success 145°/warn 85°/error 27°；HarmonyOS/PingFang/Inter 字体；I 36 icons viewBox 24×24 stroke 1.6；R-165 OKLCH fallback 已兜底
- **视觉模型**（v0.5.7 验证）：fluid panel + element-anchored 模式，**不要 artboard 整体居中**
- **byte-equal 红线**：export name + props + api 链路 + 错误文案 + 17 屏 byte-equal + App/Shell/api/index/main/utils byte-equal
- **抗诱惑清单 5 条**：Foundation 资产仅在目标屏引用 / 严禁扩 buildTheme 25 字段 / 严禁顺手 i18n / 严禁顺手改其他屏 / 严禁引入新 npm 依赖
- **三处版本同步模板**（R-72 + R-181）：每 PATCH 升版本 main.py + smoke + Login 页脚同步
- **复用 v0.5.7 LOCKED 手册作模板**：`docs/plans/v0.5.7-login-pilot.md` 8 节模板按本屏特性填空

定位：本协议**不替代** Loop Protocol v3 三阶段评审；每屏 PATCH 仍走 Stage 1+2+3+4。

### Loop Protocol v3 — 第 9 次施行（**首次简化协议**）

- **简化触发条件**（4 全满足）：
  1. PATCH 完全是 docs/ci/chore（0 业务 .py/.jsx 改动）
  2. 红线数 ≤ 8（本 PATCH 5 条）
  3. 无决议争议点（D1-D3 均为执行细节）
  4. 资深架构师明确 ack 简化
- **协议路径**：Stage 1 草案 → 资深直接 ack → Stage 4 落地（跳 Stage 2/3，省 ~30 分钟 round-trip）
- **守护者**：v0.4 全程 dormant（未激活）
- **远古守护者**：v0.3 dormant
- **未来回头风险**：低 — chore deterministic，Stage 2/3 即便走也大概率 0 修订
- **不适用简化场景**：视觉重构/屏复刻（仍走全 v3）/ 后端业务逻辑（仍走全 v3）/ 架构契约变更（仍走全 v3）

### Tests

- backend：**432 passed** / 112 skipped（R-189 严格不变 — 0 测试增减）
- frontend build：`npm run build` 0 警告 0 error；bundle hash 更新

### Architecture（不变）

- 7 import-linter contracts 全程 KEPT
- 72 routes 不变
- check_file_sizes.py 29 files 不变（无新加/删 LIMITS）
- requirements.txt / package.json / pyproject.toml / .importlinter / vite.config.js 0 修改

### v0.5.x 路线图更新

- ✅ v0.5.7 (C5+) Login pilot
- ✅ **v0.5.8 (Cn+) Chore — CI fix + Visual Replication Protocol**
- ⏳ v0.5.9+ (C5+) 1 屏 1 PATCH 渐进替换剩余 17 屏（home / shell / thinking / favorites / 9 admin tabs）

### 验收（全绿）

- [x] backend tests 432 passed / 7 contracts KEPT / 72 routes / version 0.5.8
- [x] check_file_sizes.py 29 files OK
- [x] R-181 + R-185 sync test 通过
- [x] § Visual Replication Protocol 59 行 ≤ 80 ✓
- [x] R-187 ci.yml 动态读 version 本地等价测试 PASS
- [x] R-191 docs+ci 守护 — 0 业务 .py/.jsx 改动

---

## [Unreleased] - v0.5.7 (C5+) Claude Design UI 重构 — Login 屏首屏复刻 pilot

> v0.5.6 Foundation 落地后第八刀：**首屏 1:1 复刻 demo 视觉 — Login pilot**。资深架构师拍板"1 屏 1 PATCH"渐进替换 18 个 artboards，本 PATCH 建立的执行模板将服务于 v0.5.8+ Home / Shell / Thinking / Favorites / 9 admin tabs。
>
> Loop Protocol v3 **第 8 次**完整 PATCH 内施行。Shell.jsx 严格 0 改动（即使 KnotLogo 已可用 — R-186 抗诱惑守护）。

### Added — Logo 三件套 + decor SVG 资产（v0.5.8+ 复用）

**Shared.jsx 新增 3 export**（9 → 12，R-174 上限）：

- `KnotMark({ T, size = 32 })` — 原子标记：3 椭圆轨道 (rotate 0/60/-60) + 中心核圆，viewBox 100×100（**Q2** Logo 与 Icon 语义不同，不与 I 24×24 共用）
- `KnotWordmark({ T, size = 24 })` — Inter Black 字标 "KNOT"，letterSpacing -3.5 紧排
- `KnotLogo({ T, size = 32 })` — 横向 lockup（Atom + Wordmark），gap 自适应 size×0.32

**R-183 size props**：3 个组件均接 size 默认值（不写死像素常量）；调用处可覆盖（Login.jsx 用 size=22）。
**Q4 T.dark boolean**：色值 `T.dark ? '#f4f6f8' : '#0d1014'`，全文 `theme === 'light'` 字串 0 命中。

**frontend/src/decor/NarrativeMotif.jsx [NEW 112 行 ≤ 120 R-173]**（pure SVG func）：

- 视觉隐喻：原子结构 motif — 3 椭圆轨道（rotate -22/22/0）+ 4 电子（1 brand-tinted）+ 核心 + 左侧 7 条 bezier 曲线（输入 → 收敛核心）
- 故事：复杂需求 → K/N/O/T 三个专家 Agent → 核心可追溯洞察
- **R-182 React.memo**：`export default memo(NarrativeMotif)` 防 Login state 变化（错误 / 主题切换）触发 SVG 巨量 path 重绘；Login.jsx T 引用稳定（App.jsx 既有 useMemo）则 memo 命中
- **Q1 OKLCH color-mix**：`color-mix(in oklch, ${T.accent} 15%, transparent)` 替代 demo 原 brand[100] 浅色阶（**严禁扩 buildTheme 25 字段** — 守 R-158 契约）；用于 `radial-gradient(ellipse at 30% 20%, ${tint}, transparent 60%)` 包裹 SVG 外层 div
- **Q4 T.dark boolean**：stroke / muted / node / orbitColor 全用 `T.dark ?` 分支

### Changed — Login.jsx 视觉 1:1 复刻 demo（116 → 178 ≤ 200 R-175）

**布局**：flex (1) + 420px → grid 1.05fr 1fr（demo 模式）+ 左面板 borderRight 分割。

**左侧 narrative panel**：

- `cb-grid-bg` 网格 → `<NarrativeMotif T={T}/>` 原子 motif 装饰（70% 宽，pointerEvents none）
- 30px 圆角块 + sparkle → `<KnotLogo T={T} size={22}/>`（Atom + Wordmark lockup）
- features list 3 行 → "Knowledge·Nexus·Objective·Trace" tagline (mono uppercase) + "复杂结于此，洞察始于此" 38px 标题 + KNOT Agent 协同描述段
- 删除 "© 2026 KNOT · 内部系统" 页脚（迁右下版本号位）

**右侧 form panel**：

- 标题加 "sign in" mono 小字 → "欢迎回来" + "使用账号登录访问你的数据空间"
- 输入用 Field box 风格（label + 44px 灰底框 + I.user/I.lock 内嵌 + I.eye toggle）
- **新增** "7 天内自动登录" checkbox（D3 仅 UI + localStorage `knot_remember` flag）+ "忘记密码？" 占位（D4 无 handler 内部 admin 重置）
- **D7** 主按钮 "登录" → "进入 KNOT" + I.send 右箭头
- **D6** error banner 红色用 `oklch(62% 0.22 27)` + color-mix 12%/25% 浅底/边（语义色远离 brand）
- **R-181** 页脚 "v0.5.7 · KNOT 内部系统" 左 + "knot.local" mono 右（与 main.py FastAPI version + smoke test 三处同步）

**R-184 input focus 蓝青**：`focused` state tracker + `border: 1px solid ${focused === key ? T.accent : T.inputBorder}` + transition 0.15s — Tab 切换两个输入框边框显蓝青。

**Q3 remember-me 防误导**：checkbox + label 双层 `title="目前仅作为偏好记录，Token 有效期受服务器策略控制"`。

### Added — 守护测试

**`tests/test_login_version_sync.py` [NEW 47 行]**（R-181 + R-185 合并）：

- `test_R181_login_footer_version_synced_with_main`：grep `f"v{app.version}"` in Login.jsx — 三处同步漏一处即挂
- `test_R185_login_renders_knot_logo`：grep `<KnotLogo|<KnotMark` in Login.jsx + 校验 Shared.jsx export KnotMark/KnotWordmark/KnotLogo — 防资产重构后"逻辑蒸发"

### Changed — CI 守护扩展

**`scripts/check_file_sizes.py` LIMITS 27 → 29 条（R-176）**：

- `frontend/src/screens/Login.jsx`: 200（重构后 178 行）
- `frontend/src/decor/NarrativeMotif.jsx`: 120（112 行）

### Architecture（不增 contract / 17 屏 byte-equal / Shell.jsx 严守 0 改）

7 import-linter contracts 全程 KEPT（R-177）。
**R-178 17 屏 byte-equal**：`git diff frontend/src/screens/` 仅含 Login.jsx — Chat/Admin/Database/Knowledge/Conv/SavedReports/Catalog/SqlLab/Settings + 12 子模块共 17 屏字面零修改。
**R-179 核心非屏文件 byte-equal**：App.jsx / api.js / index.css / main.jsx / utils.jsx / Shell.jsx 0 修改。
**R-186 严格 1 屏限制**：Shell.jsx **0 行改动**（即使 KnotLogo 三件套已注入 Shared.jsx 可用 — 抗诱惑守护；Shell topbar Logo 留 v0.5.8+）。
**R-164 zero drift**：package.json / requirements.txt / pyproject.toml / .importlinter / vite.config.js / .github/workflows 0 修改。

### Loop Protocol v3 — 第 8 次完整 PATCH 内施行

- **Stage 1**（v0.5 执行者）：Login.jsx 现状 vs demo login.jsx 视觉差距分析（116 vs 110 行 11 维度 diff），D1-D7 草案 + R-170~R-180 红线（11 条）；资深 ack 中补充"登录页版本号与当前版本一致" → D8 + R-181
- **Stage 2**（资深 + Codex）：Q1-Q4 风险项（color-mix / SVG viewBox / 7 天 UX 防误导 / T.dark 强制） + 加 R-182（React.memo）+ R-183（size props 严禁写死像素）
- **Stage 3**（v0.4 守护者）：加 R-184（焦点蓝青手测）+ R-185（DOM 哨兵测试）+ R-186（Shell.jsx 严守 0 改 — 抗诱惑红线）
- **Stage 4**（执行者）：5 commit 落地，全程 0 修订；执行顺序严守 Stage 3 §2（Logo 注入 → Motif 创建 → Login 重构 → version+LIMITS → docs）

12/12 决策（D1-D8 + Q1-Q4）与执行者 Stage 1 提议一致；新增 6 条红线（Stage 2: 2 + Stage 3: 3 + 资深 ack: 1）；红线总数 17（**R-170~R-186**）。

### Migration

- 客户端无任何 breaking change（LoginScreen export name + props + api.login + cb_token 链路 byte-equal）
- 老用户登录 7 天偏好记录走 localStorage `knot_remember` flag — 仅 UI 偏好，Token TTL 仍受服务器策略控制（v0.6+ 评估 backend 动态 TTL）

### Tests

- backend：430 → **432 passed**（112 skipped 不变）— 仅新增 R-181 + R-185 守护测试，0 现有测试改动
- frontend build：`npm run build` 0 警告 0 error；bundle hash `index-CCUVoYmE.js` → `index-CK2CIwDo.js`（+4 kB — NarrativeMotif + KnotLogo 三件套引入）

### 验收标准

- [x] backend tests 432 passed / 7 contracts KEPT / 72 routes / version 0.5.7
- [x] check_file_sizes.py 29 条 LIMITS 通过
- [x] R-181 + R-185 sync test 通过
- [x] R-186 `git diff frontend/src/Shell.jsx` = 0 行
- [x] Q4 grep `theme ===` = 0（decor + Shared 新增段 + Login 全文）
- [ ] 手测：light + dark 双主题登录端到端（Tab 焦点蓝青 + remember 勾选 localStorage 写入 + "进入 KNOT" 提交）
- [ ] 视觉对照 demo login.jsx：light + dark 各 1 张截图

### v0.5.x 路线图更新

- v0.5.7 (C5+) Claude Design UI 重构 — Login 屏首屏复刻 pilot ⏳ → ✅
- v0.5.8+ (C5+) 1 屏 1 PATCH 渐进替换 17 屏（Home / Shell / Thinking / Favorites / 9 admin tabs）

---

## [Unreleased] - v0.5.6 (C5) Claude Design UI 重构 — Foundation 第一刀

> v0.5.5 cleanup（首个 Negative Delta）收官后第七刀：**Claude Design UI 重构第一刀 Foundation**。资深架构师拍板"以体验先行" + "1:1 复刻 demo 视觉与交互" — 但 demo 仓库 (`/Users/kk/Documents/knot_ui_demo/v0.5/`) 是**设计代理**（不进产品），目标是产品视觉按 demo 设计语言重构。
>
> **v0.5.x 序列第二次 Negative Delta -136 行**（仅次于 v0.5.5 -18）。Loop Protocol v3 **第 7 次**完整 PATCH 内施行。
>
> **strangler fig pattern**：v0.5.6 = Foundation **共存**重构（Shared.jsx / utils.jsx / App.css），**18 屏 0 修改**自动换皮；v0.5.7+ 1 屏 1 PATCH 渐进替换 18 个 artboards。

### Changed — 视觉迁移到 Claude Design 设计语言

**Shared.jsx 重构**（保 9 exports + I 36 names + buildTheme 25 字段 + dark prop 契约）：

- `buildTheme(dark)` 25 字段值切 OKLCH：
  - **brand 蓝青 195°**（dark `oklch(72% 0.17 195)` brand[400] / light `oklch(58% 0.17 195)` brand[600]）替代红色 `#FF4B4B`
  - **ink 13 阶冷黑**（bg/content/sidebar/text/subtext/muted/borders/codes/inputs/chips 全切 ink hex 阶值）
  - **R-167 语义色远离 brand 195°**：success 翠绿 145° / warn 琥珀 85° / error 朱红（toast）27°
  - 字体切 `"HarmonyOS Sans SC", "PingFang SC", "Inter"` + mono `"JetBrains Mono", "Geist Mono"`
- `iconBtn(T)` / `pillBtn(T, primary)` borderRadius 6 → 8 + transition + 保函数签名
- `I` 36 names path 重绘 viewBox 24 + stroke 1.6（4 处显著差异修正：send 向上→向右 / check stroke 2.2→1.6 polyline / sparkle fill→stroke / more 显式 stroke="none"）
- `CHART_COLORS` 8 色 OKLCH（**R-169 hue 45° 均匀分布** 195/240/285/330/15/60/105/150°）
- `LineChart` / `BarChart` / `TypingDots` 默认色 `oklch(58% 0.17 195)` 蓝青
- IIFE injectStyles 内 `.cb-grid-bg` + `button:focus-visible` 红 → 蓝青 OKLCH

**utils.jsx 视觉重写**（保 8 exports 函数签名 + props）：

- `toast`：hardcode '#FF4B4B'/'#09AB3B' → `oklch(62% 0.22 27)` 朱红 / `oklch(72% 0.18 145)` 翠绿
- `Spinner`：默认 color `oklch(58% 0.17 195)` 蓝青；ring 用 `oklch(... / 0.18)` 透明
- `Modal` / `ModalHeader` / `Input` / `Select`：用 `T.X` 自动换皮（R-159 契约保）

**App.css 重构**（184 → 27 行 净 **-157**）：

- 移除全部 Vite 模板残留（`.counter` / `.hero` / `.base` / `.framework` / `.vite` / `#center` / `#next-steps` / `#docs` / `#spacer` / `.ticks`）
- `body` 字体：HarmonyOS / PingFang / Inter / system fallback
- **R-168 抗锯齿**：`-webkit-font-smoothing: antialiased` + `-moz-osx-font-smoothing: grayscale` + `text-rendering: optimizeLegibility`（macOS / Windows / Linux 三平台）
- **R-165 OKLCH fallback**：`:root` CSS Variables (`--knot-fallback-bg/text/brand` hex) + `@supports not (color: oklch(0% 0 0))` feature detect 兜底（仅 base styles，不渗透 buildTheme 25 字段，避免破坏 R-158 契约）
- **R-160 守护**：`cb-sb` / `cb-fadein` className 不在 App.css（main 和 local 都 0 命中 — IIFE 注入）byte-equal ✓

### Architecture（不增 contract / 18 屏 0 修改 / strangler fig pattern）

7 import-linter contracts 全程 KEPT（R-155）。
**R-156 18 屏 0 diff**：`git diff frontend/src/screens/` 输出 0 行 — Chat/Admin/SavedReports/Login/AdminAudit/AdminBudgets/AdminRecovery + chat/* 7 子模块 + admin/* 5 子模块共 18 个屏文件字面零修改。
**R-157 5 核心非屏文件 byte-equal**：Shell.jsx / App.jsx / api.js / index.css / main.jsx 0 修改。
**R-164 zero drift**：package.json / requirements.txt / pyproject.toml / .importlinter / vite.config.js / scripts 0 修改。

> **Strangler fig pattern**：18 屏继续 import 现有 Shared.jsx + utils.jsx 路径 + 调用 `T = buildTheme()` + `<I.X>` + `iconBtn(T)` / `pillBtn(T)` 函数 — 屏代码 0 修改，但视觉自动换皮成蓝青 brand + PingFang 字体 + 新 Icon 风格。这给 v0.5.7+ 1 屏 1 PATCH 渐进替换铺路（屏内布局重构后 1.0 公测）。

### Decisions Locked (D1-D7)

| ID | 锁定 |
|---|---|
| **D1** Tokens 切换 | A Shared.jsx 内建（不新增 design/ 子目录） |
| **D2** 颜色空间 | A 原生 OKLCH（现代浏览器；R-165 fallback 兜底） |
| **D3** Brand 色相 | A 电青色 195°（demo 终态；signal/insight/decision） |
| **D4** Icon 集合 | A 保全 36 + 部分重绘风格统一 |
| **D5** App.css 范围 | A 仅切字体 + 清残留（保守不引新 class） |
| **D6** utils.jsx 风格 | A 视觉重写保 8 exports 函数签名 |
| **D7** className 字面 | A 强制 byte-equal cb-sb/cb-fadein |

### Red-lines（R-154~R-169 共 16 条全部偿还）

| ID | 来源 | 偿还方式 |
|---|---|---|
| **R-154** | 执行者 | backend 430 严格不变（前端纯改） |
| **R-155** | 执行者 | 7 contracts KEPT, 0 broken |
| **R-156** | 执行者 | 18 屏 0 修改（git diff frontend/src/screens/ = 0 行）|
| **R-157** | 执行者 | Shell.jsx/App.jsx/api.js/index.css/main.jsx byte-equal |
| **R-158** | 执行者 | Shared.jsx 契约：9 exports + I 36 names + buildTheme 25 字段 + dark prop ✓ |
| **R-159** | 执行者 | utils.jsx 契约：8 exports（useTheme/usePersist/Spinner/toast/Modal/ModalHeader/Input/Select）✓ |
| **R-160** | 执行者 | App.css cb-sb/cb-fadein 字面 byte-equal（main 和 local 都 0 命中）|
| **R-161** | 执行者 | OKLCH + PingFang/HarmonyOS + Icon viewBox 24 stroke 1.6 |
| **R-162** | 执行者 | npm run build 通过 |
| **R-163** | 执行者 | routes=72 / version=0.5.6 |
| **R-164** | 执行者 | package.json/requirements/pyproject/.importlinter/vite.config 0 修改 |
| **R-165** | Stage 2 | App.css `:root` hex fallback + `@supports not (color: oklch(0% 0 0))` 兜底 |
| **R-166** | Stage 2 | 待人测 — WCAG AA 对比度（brand 195° on bg / text on bg ≥ 4.5:1） |
| **R-167** | Stage 3 | 语义色远离 brand 195°：success 145° / warn 85° / error 27°；故意触发后端错误手测 |
| **R-168** | Stage 3 | App.css `body` 含 `-webkit-font-smoothing: antialiased` + `-moz-osx-font-smoothing: grayscale` |
| **R-169** | Stage 3 | CHART_COLORS 8 色 hue 45° 均匀分布；lightness 65~70% chroma 0.16~0.20 |

### Loop Protocol v3 — 第 7 次完整施行

| Stage | 角色 | 产物 |
|---|---|---|
| Stage 1 | v0.5 执行者 | 草案 [docs/plans/v0.5.6-claude-design-foundation.md](docs/plans/v0.5.6-claude-design-foundation.md)（D1-D7 + R-154~R-164 11 红线） |
| Stage 2 | 资深架构师 + Codex | 7/7 决策一致 + R-165/R-166 新增（OKLCH fallback + WCAG AA） |
| Stage 3 | v0.4 守护者 | 终审 GO + R-167/R-168/R-169 新增 + commit 1 子步骤 1→6 顺序锁死 + Stage 2 唯一成功标准"视觉变了，但逻辑和契约没变" |
| Stage 4 | v0.5 执行者 | 3-commit 落地（C1 视觉重构子步骤 1→6 内嵌 / C2 version bump / C3 docs），全闸门绿 |

> v0.4 守护者全程**只读**未触碰代码；v0.3 远古守护者 dormant 未激活。

**特别意义** — **v0.5.x 序列第二次 Negative Delta** + **Strangler fig pattern 起点**：v0.5.5 删 lark.py stub 是首个减法（-18）；v0.5.6 移除 Vite 模板残留 + Shared.jsx 视觉重构是第二个减法（-136）；同时是 Claude Design UI 重构 18 PATCH 系列的 Foundation 第一刀，给后续 v0.5.7~v0.5.x 1 屏 1 PATCH 渐进替换铺路。

---

## [Unreleased] - v0.5.5 (Cn) Cleanup — 首个减法 PATCH（Negative Delta）

> v0.5.4 Loop Protocol v3 路线图同步收官后第六刀：v0.5.x 序列**首个减法 PATCH**（Negative Delta -18 行）。**Loop Protocol v3 第 6 次完整 PATCH 内施行**。物理删 `lark.py` v0.3.2 stub + 8 处 sync LLM API docstring 标 `[DEPRECATED]`。
>
> **范围最小化原则**：不删 sync API 实现（query_steps 非流式仍依赖，实际删留 v0.6.x）；不删 base.py + __init__.py（接口预留）；不动 frontend / scripts / 依赖文件。

### Removed — lark.py stub 物理删除

- **`knot/adapters/notification/lark.py`** [DELETE -29 行]：v0.3.2 占位 LarkAdapter，业务侧 0 调用
- 接口契约（NotificationAdapter Protocol）保留在 base.py + __init__.py（**接口预留 — D3 A**），未来真接入飞书 / Slack 时直接加新 adapter 实现，不动调用方

### Removed — Test Case 受控降级（R-151 显式存档）

backend 测试基准受控降级 **432 → 430**（删 2 个 lark 测试 cases）：
- `test_lark_satisfies_protocol`（位于 `tests/adapters/test_notification.py` L16）
- `test_lark_send_raises_not_implemented`（位于 `tests/adapters/test_notification.py` L20）

**保留**：`test_notification_dataclass_defaults`（L9） — Notification dataclass 契约测试

> **R-151 存档目的**：防未来审计误判测试丢失；明确这 2 个测试是**有意删除**（lark stub 已删，测试无意义），不是遗失。

### Changed — sync LLM API 8 处 docstring 标注 [DEPRECATED]

R-152 锁定模板首行（**8 处字面 byte-equal**）：

```
[DEPRECATED v0.5.5; target removal in v1.0] Use async equivalent (a*) instead.
```

8 处分散在 7 个文件（**LOCKED §4 路径整合修正** — 原手册写"集中在 llm_client.py"实际分散）：

| 文件 | 函数 | sync → async 替代 |
|---|---|---|
| `knot/services/llm_client.py` | `generate_sql` | `agenerate_sql` |
| `knot/services/llm_client.py` | `fix_sql` | `afix_sql` |
| `knot/services/_llm_invoke.py` | `_invoke_via_adapter` | `_ainvoke_via_adapter` |
| `knot/services/agents/sql_planner.py` | `run_sql_agent` | `arun_sql_agent` |
| `knot/services/agents/sql_planner_llm.py` | `_call_llm` | `_acall_llm` |
| `knot/services/agents/clarifier.py` | `run_clarifier` | `arun_clarifier` |
| `knot/services/agents/presenter.py` | `run_presenter` | `arun_presenter` |
| `knot/services/agents/orchestrator.py` | `_llm` | `_allm` |

**R-142 业务零变更**：8 处函数体 / 函数签名 / import / 数据结构 0 修改；仅添加 docstring 首行（+ 可选保留原 docstring 内容多行格式调整）。

**D2 v1.0 删除目标**：query_steps.py 非流式路径（`run_generate_sql_with_fix_retry` + `run_agent_step_sync`）仍依赖 sync API；实际删除留 v0.6.x（query_steps 非流式迁 async 后才能做）。

### Architecture（不增 contract / 0 frontend / 0 依赖）

7 import-linter contracts 全程 KEPT（R-140；不动 .importlinter）。
**R-145 zero drift**：frontend / requirements.txt / pyproject.toml / package.json / .importlinter / scripts/check_file_sizes.py 0 修改。
**R-141 接口预留守护**：`notification/base.py` + `notification/__init__.py` 字面 byte-equal。

### Decisions Locked (D1-D5)

| ID | 锁定 |
|---|---|
| **D1** sync API 标注形式 | A docstring 仅注释（不加 runtime warning / 装饰器） |
| **D2** sync API 删除时间表 | A v1.0 删除目标（query_steps 仍依赖） |
| **D3** notification/ 目录残留 | A 保留 base + __init__（接口预留） |
| **D4** 红线编号 | A 接续 R-139~R-153 |
| **D5** Commit 序列 | A 3 commit 单文件单职责 |

### Red-lines（R-139~R-153 共 15 条全部偿还）

| ID | 来源 | 偿还方式 |
|---|---|---|
| **R-139** | 执行者 | backend tests 432 → 430 受控降级（删 2 lark 测试） |
| **R-140** | 执行者 | 7 contracts KEPT, 0 broken |
| **R-141** | 执行者 | notification/{base, __init__}.py 字面 byte-equal ✓ |
| **R-142** | 执行者 | sync API 8 处函数体零修改（git diff 仅 docstring） |
| **R-143** | 执行者 | 非流式路径继续工作（query_steps run_generate_sql_with_fix_retry + run_agent_step_sync） |
| **R-144** | 执行者 | routes=72 / version=0.5.5 |
| **R-145** | 执行者 | 0 修改 frontend / requirements.txt / package.json / pyproject.toml / .importlinter |
| **R-146** | 执行者 | scripts/check_file_sizes.py LIMITS 不动 |
| **R-147** | 执行者 | live LLM eval 不影响（重构性 cleanup 不动 SQL 生成行为） |
| **R-148** | 执行者 | CLAUDE.md `lark.py(stub)` 字面去除（路径表更新为"通知接口抽象层"） |
| **R-149** | Stage 2 | 幽灵扫描：grep `notification\.lark\|from \.lark\|import.*lark` knot/ tests/ → 0 命中 ✓ |
| **R-150** | Stage 2 | 非 SSE 手测：8 处 sync API 模块 import + callable 全 True（0 IndentationError / 0 三引号闭合错） |
| **R-151** | Stage 3 | CHANGELOG 显式列被删 2 测试名（`test_lark_satisfies_protocol` + `test_lark_send_raises_not_implemented`） |
| **R-152** | Stage 3 | 8 处 docstring 首行字面 byte-equal `[DEPRECATED v0.5.5; target removal in v1.0] Use async equivalent (a*) instead.` ✓ |
| **R-153** | Stage 3 | CLAUDE.md 关键路径表 notification 描述改"通知接口抽象层" ✓ |

### Loop Protocol v3 — 第 6 次完整施行（首个 Negative Delta）

| Stage | 角色 | 产物 |
|---|---|---|
| Stage 1 | v0.5 执行者 | 草案 [docs/plans/v0.5.5-cleanup.md](docs/plans/v0.5.5-cleanup.md)（D1-D5 + R-139~R-148 10 红线） |
| Stage 2 | 资深架构师 + Codex | 5/5 决策一致 + R-149/R-150 新增（幽灵扫描 + 非 SSE 手测） |
| Stage 3 | v0.4 守护者 | 终审 GO + R-151/R-152/R-153 新增（测试名显式 + Deprecation 字面统一 + 路径描述修正）+ Negative Delta 里程碑指示 |
| Stage 4 | v0.5 执行者 | 3-commit 落地（C1 lark 删 / C2 sync API docstring / C3 version + docs），全闸门绿 |

> v0.4 守护者全程**只读**未触碰代码；v0.3 远古守护者 dormant 未激活。

**特别意义** — v0.5.x 序列**首个减法 PATCH**（Negative Delta -18 行）：v0.5.0~v0.5.4 全部是**加法 PATCH**（rename / SQL AST / 拆分 / 文档同步），v0.5.5 是序列首个**减法 PATCH**（删除遗留代码 + 标注废弃 API）。Cleanup 是 1.0 release 必经之路 — 给 v1.0 公测留一个干净的代码 baseline。

---

## [Unreleased] - v0.5.4 (C4) Loop Protocol v3 路线图同步

> v0.5.3 前端瘦身落地后第五刀：Loop Protocol v3 路线图同步至面向用户文档。**Loop Protocol v3 第 5 次完整 PATCH 内施行**（自我引用闭环 — 用 v3 协议同步 v3 协议）。docs-only PATCH（除 main.py version + R-72 smoke 字符串外严禁触碰任何 .py/.js/.jsx 逻辑行）。
>
> **范围最小化原则**：D-2 backend 0 改动；R-138 docs-only zero drift；R-134 协议核心 4 段字面 byte-equal；R-132 README 既有 7 段 § 标题字面零修改。

### Added — README.md 新增 § Loop Protocol v3 简介段

- 1 段开场（v3 = 三阶段评审 + 4 级角色 + MINOR 滚动整体审核仪式）
- **4 级角色简表**（执行者 / 守护者 / 远古守护者 / 辅助 AI 初审组 / 资深架构师）
- **R-136 ASCII 三阶段流程图**（一行简版）：`执行者 (Stage 1 草案) → 辅助 AI 初审组 (Stage 2 Redline) → 守护者 (Stage 3 终审) → 执行者落地`
- **R-137 角色滚动透明声明**：「角色按 MINOR 滚动 — 当前 MINOR 的执行者会在下一 MINOR 自动转为守护者，再下一 MINOR 转为远古守护者；强调"规则治权"而非"人治层级"，不存在不可动摇的技术层级」
- MINOR 滚动整体审核仪式简介
- **R-135 链接策略**：不带锚点直接指向 CLAUDE.md（避免 GitHub URL-encoded anchor 死链 + 锚点漂移）

### Changed — CLAUDE.md L110-114 v3 协议施行历史段扩展

5 行回顾摘要表（v0.5.0~v0.5.4）：

| PATCH | 主题 | 红线 | 关键决策 / 施行特征 |
|---|---|---|---|
| v0.5.0 | KNOT rename + Foundation | R-67~R-79 (13) | 包名 / env 双源 / DB migration / Loop Protocol v3 **首次完整施行** |
| v0.5.1 | SQL AST 笛卡尔积硬防御 | R-80~R-93 (14) | sqlglot AST + ReAct `__REJECT_CARTESIAN__` + R-91 计数器 |
| v0.5.2 | 后端代码瘦身 | R-94~R-110 (17) | **27 文件行数压制**（4 主 ≤ 350/300/220/220 + 9 新建 ≤ 250 + scripts/check_file_sizes.py CI 核验）；sync/async 双胞胎保守不合并；orchestrator 方案 1 延迟 import 破单向依赖 |
| v0.5.3 | 前端代码瘦身 | R-111~R-128 (18) | Chat.jsx 925 → ≤ 350；Admin tab 7→4 文件按职责合并；className 0 diff 守护；R-118 SSE handler 纯函数化 callbacks 注入 |
| v0.5.4 | Loop Protocol v3 路线图同步 | R-129~R-138 (10) | docs-only；**第 5 次 v3 施行**（自我引用闭环）；README 加 protocol 简介对外公开治理 |

> **Stage 3 §2 明确指示**：v0.5.2 行**显式提"27 文件行数压制"**字眼（已落地）。

### Architecture（不增 contract / 0 修改 backend / frontend）

7 import-linter contracts 全程 KEPT（R-130；不动 .importlinter）。
**R-138 zero drift**：`git diff --ignore-space-change knot/ frontend/ tests/ scripts/ requirements.txt pyproject.toml .importlinter` → 仅 3 行（main.py version + test_rename_smoke docstring/assert smoke 字符串）；0 函数体 / 0 import / 0 数据结构变化。

### Decisions Locked (D1-D5)

| ID | 锁定 |
|---|---|
| **D1** README 形式 | A 内嵌轻量简介 + 指向 CLAUDE.md 深挖 |
| **D2** 历史扩展粒度 | A 加 v0.5.0~v0.5.3 4 PATCH 回顾摘要表 |
| **D3** README 简介深度 | A 4 级角色 + 三阶段 + 滚动规则 |
| **D4** 红线编号 | A 接续 R-129~R-138 |
| **D5** Commit 序列 | A 3 commit 单文件单职责 |

### Red-lines（R-129~R-138 共 10 条全部偿还）

| ID | 来源 | 偿还方式 |
|---|---|---|
| **R-129** | 执行者 | backend 432 passed / 112 skipped 严格不变 |
| **R-130** | 执行者 | 7 contracts KEPT；不动 .importlinter |
| **R-131** | 执行者 | 0 修改 backend / frontend / scripts / tests / 依赖文件（除 main.py version + R-72 smoke） |
| **R-132** | 执行者 | README 既有 7 段标题（角色 / 3-Agent / 快速开始 / Docker / 部署 / 技术栈 / 项目结构 / 版本记录）字面零修改；grep 8/8 命中 |
| **R-133** | 执行者 | CLAUDE.md v3 协议条款无矛盾（仅"施行历史"段扩展） |
| **R-134** | Stage 2 | 协议核心 4 段（§ 角色定义 / § 三阶段评审 / § 角色滚动规则 / § 远古守护者激活原则）字面 md5 byte-equal ✓ |
| **R-135** | Stage 2 | URI 完整性：README 2 个 CLAUDE.md 链接均不带锚点；0 死链风险 |
| **R-136** | Stage 3 | README 含一行 ASCII 三阶段流程图（执行者 → 辅助 AI 初审组 → 守护者 → 执行者落地） |
| **R-137** | Stage 3 | README 含"角色按 MINOR 自动滚动 — 不存在不可动摇的技术层级；强调规则治权"明确声明 |
| **R-138** | Stage 3 | docs-only zero drift — git diff knot/frontend/tests/scripts/+依赖 仅 3 行（version + smoke），0 函数体改动 |

### Loop Protocol v3 — 第 5 次完整施行（自我引用闭环）

| Stage | 角色 | 产物 |
|---|---|---|
| Stage 1 | v0.5 执行者 | 草案 [docs/plans/v0.5.4-loop-protocol-sync.md](docs/plans/v0.5.4-loop-protocol-sync.md)（D1-D5 + R-129~R-133 5 红线） |
| Stage 2 | 资深架构师 + Codex | 终审摘要 5/5 决策与执行者一致 + R-134/R-135 新增（协议核心字面守护 + URI 校验） |
| Stage 3 | v0.4 守护者 | 终审 GO + R-136/R-137/R-138 新增（ASCII 流程图 + 角色滚动透明度 + zero drift） |
| Stage 4 | v0.5 执行者 | 3-commit 落地（C1 README+CLAUDE.md / C2 version bump / C3 CHANGELOG+plan 归档），全闸门绿 |

> v0.4 守护者全程**只读**未触碰代码（合规 — Loop Protocol v3 § 角色定义）；v0.3 远古守护者 dormant 未激活。

---

## [Unreleased] - v0.5.3 (C3) 前端代码瘦身

> v0.5.2 后端瘦身落地后第四刀：2 个前端主屏（Chat.jsx 925 / Admin.jsx 773）按 4-commit 节奏拆分为 13 个子组件。Loop Protocol v3 第四次完整 PATCH 内施行（D1-D7 全锁定 + 18 红线 R-111~R-128）。
>
> **范围最小化原则**：D-2 backend 0 改动（除 main.py version + smoke）；R-118 SSE handler 纯函数化 callbacks 注入；R-128 className 字面 byte-equal；R-124 全局状态零变更（chat/admin 子模块 0 含 useContext/Provider/redux）；R-114/115/121 手测端到端守护（前端无 unit test）。

### Refactor — 2 主屏拆 13 子组件（行数）

| 主文件 | 拆前 | 拆后 | 子模块 | 行数 |
|---|---|---|---|---|
| `frontend/src/screens/Chat.jsx` | 925 | **254** ≤ 350 | `chat/intent_helpers.js` / `sse_handler.js` / `ResultBlock.jsx` / `ChatEmpty.jsx` / `Conversation.jsx` / `ThinkingCard.jsx` / `Composer.jsx` | 32 / 65 / 381 ⚠️ / 40 / 53 / 110 / 71 |
| `frontend/src/screens/Admin.jsx` | 773 | **352** ≤ 360 ⚠️ | `admin/tab_access.jsx` / `tab_resources.jsx` / `tab_knowledge.jsx` / `tab_system.jsx` / `modals.jsx` | 60 / 85 / 107 / 53 / 210 |

> **R-111 行数硬约束 2 处微调**（资深 ack 方案 A — 与 v0.5.2 query.py SSE 样板代价同精神）：
> - `chat/ResultBlock.jsx` 250 → 400：复合 UI 组件 7 独立 UI 段（错误 banner / budget banner / metric|chart|table 三选一 / insight / followups / sql panel / cost chips）+ setup 80 行 + 3 helpers (MetricCard / exportMessageCsv / AGENT_KIND_EMOJI)
> - `Admin.jsx` 250 → 360：状态容器 14 handlers + 11 state + 7 tab dispatch + topbar trailing 7 分支；React 集中状态管理最佳实践不应散布到独立 handlers 文件

### Added — D7 加码 CI 行数核验扩展

- **`scripts/check_file_sizes.py`** [EDIT]：LIMITS dict 13 → 27 files（+14 前端 = 2 主 + 12 子模块）
- **`.github/workflows/ci.yml`** [v0.5.2 既有]：file-sizes step 自动覆盖前端阈值

### Architecture（不增 contract / 不动 backend）

7 import-linter contracts 全程 KEPT（R-113；前端不入 contract，但 import-linter 不破坏）：
- 子模块全部落 `frontend/src/screens/{chat,admin}/` 子目录
- R-124 全局状态守护：grep `useContext|Provider|createContext|redux|zustand` 在子模块 0 命中
- R-118 SSE handler 纯函数化：`runQueryStream(url, body, token, callbacks)` 0 React 依赖；
  callbacks (onAgentEvent / onClarification / onError / onFinal / onException) 注入 state setter
- R-128 className 字面 byte-equal：拆分前后 unique className 完全一致（`cb-fadein` + `cb-sb`）

### Decisions Locked (D1-D7)

| ID | 锁定 |
|---|---|
| **D1** 目录结构 | A 子目录化（`screens/chat/` + `screens/admin/`） |
| **D2** ResultBlock 处理 | A 整体抽出（避免 prop drilling） |
| **D3** SSE Handler 抽出 | A 独立纯函数文件（callbacks 注入） |
| **D4** Admin Tab 粒度 | ⚠️ B 按职责合并 4 文件（Stage 2 修订；执行者按 Admin.jsx 实际 7 tabs 调整内部 mapping） |
| **D5** 行数硬约束 | A 严格执行 ≤ 350 主 / ≤ 250 子（2 处微调资深 ack） |
| **D6** re-export 兼容 | A 强制 ChatScreen / AdminScreen export 名 + props 0 修改 |
| **D7** 检测工具链 | A 扩展既有 check_file_sizes.py（v0.5.2 既建脚本） |

### Red-lines（R-111~R-128 共 18 条全部偿还）

| ID | 来源 | 偿还方式 |
|---|---|---|
| **R-111** | 执行者 | Chat.jsx 254 ≤ 350；Admin.jsx 352 ≤ 360（A 微调）；ResultBlock 381 ≤ 400（A 微调）；其他子模块 ≤ 250 |
| **R-112** | 执行者 | backend / package.json / .importlinter / Shell.jsx / SavedReports.jsx 0 修改 |
| **R-113** | 执行者 | 7 contracts KEPT；不动 .importlinter |
| **R-114** | 执行者 | npm run build 每 commit 后绿 |
| **R-115** | 执行者 | 7 intent layout 分支逐字保留（ResultBlock R-117） |
| **R-116** | 执行者 | ChatScreen / AdminScreen export 名 + props 签名 0 修改（含 initialTab 深链） |
| **R-117** | 执行者 | 7 intent layout 分支零行为变更（metric_card/line/bar/rank_view/pie/retention_matrix/detail_table） |
| **R-118** | 执行者 | runQueryStream 纯函数 0 副作用 + callbacks 注入 state setter |
| **R-119** | 执行者 | 432 backend tests 严格不变 |
| **R-120** | 执行者 | routes=72 / version=0.5.3 |
| **R-121** | 执行者 | live LLM eval 不影响 |
| **R-122** | 执行者 | 9 新文件顶部 docstring 含"v0.5.3: extracted from X" |
| **R-123** | 执行者 | commit message 含源行号区间 |
| **R-124** | Stage 2 | grep `useContext|Provider|createContext|redux|zustand` 在 chat/* + admin/* 子模块 0 命中 |
| **R-125** | Stage 2 | npm run build 每 commit 后 0 error 强制 |
| **R-126** | Stage 3 | KNOT brand 字面（CSV `knot-` + `KNOT 可能出错`）main 2 处 → local Chat.jsx + ChatEmpty.jsx 2 处完整平移 |
| **R-127** | Stage 3 | error_kind / user_message / is_retryable 字段 sse_handler.js 透传 → ResultBlock.jsx ErrorBanner 渲染（v0.4.4 ERROR_KIND_META 7 类逐字保留） |
| **R-128** | Stage 3 | className 字面 byte-equal 守护（main vs local 完全一致：`cb-fadein` + `cb-sb`） |

### Loop Protocol v3 — 第四次完整施行

| Stage | 角色 | 产物 |
|---|---|---|
| Stage 1 | v0.5 执行者 | 草案 [docs/plans/v0.5.3-frontend-slim.md](docs/plans/v0.5.3-frontend-slim.md)（D1-D7 + R-111~R-123 13 红线） |
| Stage 2 | 资深架构师 + Codex | D4 修订（7 → 4 文件按职责合并）+ 新增 R-124/R-125 |
| Stage 3 | v0.4 守护者 | 终审 GO + 新增 R-126/R-127/R-128 + Chat.jsx 优先 / 每 commit 手测闭环 |
| Stage 4 | v0.5 执行者 | 4-commit 落地（C1 Chat.jsx + C2 Admin.jsx + C3 version+CI + C4 docs），全闸门绿 |

> v0.4 守护者全程**只读**未触碰代码（合规 — Loop Protocol v3 § 角色定义）；v0.3 远古守护者 dormant 未激活。

---

## [Unreleased] - v0.5.2 (C2) 后端代码瘦身

> v0.5.1 SQL AST 守护落地后第三刀：4 主文件（sql_planner 653 / llm_client 574 / orchestrator 535 / api/query 457）按文件级 1 commit 拆分为 9 个子模块。Loop Protocol v3 第三次完整 PATCH 内施行（D1-D8 全锁定 + 17 红线 R-94~R-110）。
>
> **范围最小化原则**：D-2 不增测试（重构验证靠 R-95 严格 432 不变 + R-100 re-export 兼容）；R-106 子模块单向依赖；R-109 SSE 稳定性（query_steps.py AST 0 yield，主控保留在 api/query.py）。

### Refactor — 4 主文件拆出 9 子模块（行数）

| 主文件 | 拆前 | 拆后 | 子模块 | 行数 |
|---|---|---|---|---|
| `knot/services/agents/sql_planner.py` | 653 | **330** ≤ 350 | `sql_planner_prompts.py` / `sql_planner_tools.py` / `sql_planner_llm.py` | 119 / 165 / 84 |
| `knot/services/llm_client.py` | 574 | **250** ≤ 300 | `few_shots.py` / `llm_prompt_builder.py` / `_llm_invoke.py` | 107 / 90 / 178 |
| `knot/services/agents/orchestrator.py` | 535 | **199** ≤ 220 | `clarifier.py` / `presenter.py` | 219 / 162 |
| `knot/api/query.py` | 457 | **309** ≤ 310 ⚠️ | `services/query_steps.py` | 193 |

> **R-94 query.py 边界微调 220 → 310（资深 ack 方案 A）**：SSE 协议样板代码不可消除（10 yield + 10 await asyncio.sleep R-26-SSE + emit/_default + try/except + save_message ×2 路径 + final/clarification payload dict ≈ 142 行）。从 457 → 309 已 -32% 显著瘦身；C1/C2/C3 三主文件精确达标，仅 query.py 因 SSE 特性微调。

### Added — D7 加码 CI 行数核验

- **`scripts/check_file_sizes.py`** [NEW, 44 行]：纯 stdlib，13 文件 LIMITS dict（4 主 + 9 新）；超线 exit(1)
- **`.github/workflows/ci.yml`** [EDIT]：lint-test job 加 `File-sizes (R-94)` step（ruff 之后 / lint-imports 之前）

### Architecture（不增 contract）

7 import-linter contracts 全程 KEPT（D8 不增 contract；R-96 守护）：
- 子模块全部落 `services/` 层，不破坏现有依赖方向
- R-106 单向依赖（前置守护：每个新模块单独 `python3 -c "import"` 验证 + lint-imports）
  - sql_planner / llm_client：顶部 import 子模块（标准单向）
  - orchestrator：方案 1 — clarifier/presenter 函数体内延迟 import 主文件 helpers
    （与 v0.4.4 `_acall_llm` 内 `from knot.services import budget_service` 同模式 — 避免 import-time 循环 + monkeypatch 自动生效）

### Decisions Locked (D1-D8)

| ID | 锁定 |
|---|---|
| **D1** 双胞胎合并 | A 保守不合并（sync/async 双胞胎签名 + 行为完全保留） |
| **D2** 模块组织 | A 同级 `_*.py` |
| **D3** prompt 位置 | A `.py` 字符串 |
| **D4** query 步骤位置 | A `services/query_steps.py` |
| **D5** re-export | A 强制要求（Stage 2 措辞升级；R-100 测试 import 路径 0 修改） |
| **D6** `_is_fan_out` 抽到 tools | A 抽 |
| **D7** 行数硬约束 | A 严格执行 + CI 脚本核验（Stage 2 加码） |
| **D8** 新增 contract | B 不增（7 contracts KEPT） |

### Red-lines（R-94~R-110 共 17 条全部偿还）

| ID | 来源 | 偿还方式 |
|---|---|---|
| **R-94** | 执行者 | 4 主精确达标 + query.py 微调 220 → 310（资深 ack 方案 A） |
| **R-95** | 执行者 | 432 passed / 112 skipped 严格不变（D-2 不增测试） |
| **R-96** | 执行者 | 7 contracts KEPT；不动 `.importlinter` |
| **R-97** | 执行者 | sync/async 双胞胎签名 + 行为完全保留 |
| **R-98** | 执行者 | v0.5.1 cartesian (8) + R-91 计数 + v0.4.1.1 fan-out (7) 守护零变更 |
| **R-99** | 执行者 | v0.4.4 R-26 senior budget gate + R-30 BIAgentError 透传 |
| **R-100** | 执行者 | re-export 兼容；testfile import 0 修改（仅 2 处 monkeypatch target 字符串路径走子模块；与 C2 同模式） |
| **R-101** | 执行者 | 6 commit 序列锚定，每 commit 独立全闸门绿 |
| **R-102** | 执行者 | routes=72；version=0.5.2；vite build 通过 |
| **R-103** | 执行者 | 不动 `.env.example` / `requirements.txt` / `pyproject.toml` |
| **R-104** | 执行者 | 9 新文件顶部 module docstring 含"v0.5.2 起从 X 抽出" |
| **R-105** | 执行者 | commit message 注明源行号区间（拆分不能 git mv 保 history） |
| **R-106** | Stage 2 | 严禁子模块循环引用 — 单向 import；orchestrator 子文件用方案 1 延迟 import |
| **R-107** | Stage 2 | Private `_` 前缀保护（`_is_fan_out` / `_run_tool` 等保持 private；外部已 public 不变） |
| **R-108** | Stage 3 | 逻辑平移零损耗 — commit 2 后 budget+crypto+llm_client 23/23 PASSED |
| **R-109** | Stage 3 | SSE 稳定性 — query_steps.py AST 0 yield 验证；query_stream 内 yield 主控原样保留 |
| **R-110** | Stage 3 | 文档连续性 — CLAUDE.md 关键路径表 +9 行新文件，每行注明职责 |

### Loop Protocol v3 — 第三次完整施行

| Stage | 角色 | 产物 |
|---|---|---|
| Stage 1 | v0.5 执行者 | 草案 [docs/plans/v0.5.2-backend-slim.md](docs/plans/v0.5.2-backend-slim.md)（D1-D8 决策点 + R-94~R-105 12 红线） |
| Stage 2 | 资深架构师 + Codex | D5/D7 措辞升级（强制 / CI 脚本）+ 新增 R-106/R-107 |
| Stage 3 | v0.4 守护者 | 终审 GO + 新增 R-108/R-109/R-110 + D-2 测试骨架优先指示（重构 PATCH 不增测试） |
| Stage 4 | v0.5 执行者 | 6-commit 落地（C1 sql_planner + C2 llm_client + C3 orchestrator + C4 query + C5 version+CI + C6 docs），全闸门绿 |

> v0.4 守护者全程**只读**未触碰代码（合规 — Loop Protocol v3 § 角色定义）；v0.3 远古守护者 dormant 未激活。

---

## [Unreleased] - v0.5.1 (C1) SQL AST 预校验（笛卡尔积硬防御）

> v0.5.0 KNOT 重命名收官后第二刀：1.0 release **阻塞偿还**。在 v0.4.1.1 已建立的 prompt 三层防御之上，加 **后端 sqlglot AST 硬防御** —— 笛卡尔积 / 恒真 ON 检测，触发后让 sql_planner ReAct 重生成。
>
> Loop Protocol v3 第二次完整 PATCH 内施行：v0.5 执行者 Stage 1 草案 → 资深 + Codex 辅助 AI 初审 → v0.4 守护者 Stage 3 终审。**14 红线 R-80~R-93** 全部偿还，**核心代码 182 行 ≤ 200 预算**（R-84），不引新依赖（sqlglot 既有）。

### Added — SQL AST 笛卡尔积守护层

- **`knot/services/sql_validator.py`** [NEW, 149 行] — 独立纯函数模块（D1 决策；为 v0.5.2 sql_planner 瘦身预留解耦）
  - `is_cartesian(sql) -> tuple[bool, str]` 检测 4 类反模式：
    - **C1** 旧式逗号 `FROM a, b`（文本侧 — sqlglot 30.x 与缺 ON 同 AST）
    - **C2** 显式 `CROSS JOIN`
    - **C3** JOIN 缺 `ON` / `USING`
    - **C4** 恒真 ON：`Boolean True` / `Literal=Literal` 且相等（`1=1` / `'x'='x'`）
  - **R-83 递归**：`tree.find_all(exp.Select)` 自动覆盖 CTE / 子查询，禁止 LLM 用嵌套绕过
  - **R-92 建设性 reason**：`"Cartesian product: tables [users, orders] joined without ON/USING condition. Add 'ON <key>' (see RELATIONS for the keys)."` 模板化输出，便于 ReAct LLM 修正
- **`knot/services/agents/sql_planner.py`** [EDIT, +33 行] — ReAct 接入
  - `_run_tool` final_answer 分支：cartesian 优先于 fan-out（R-85 — 更基础错误先返）
  - 返 `__REJECT_CARTESIAN__:<reason>`（与 v0.4.1.1 `__REJECT_FAN_OUT__:` 同协议）
  - **sync `run_sql_agent` + async `arun_sql_agent` 双路径**（R-82）加 `cart_reject_count` 局部计数器
  - **R-91 ReAct 无限循环保护**：连续 ≥ 3 次 `__REJECT_CARTESIAN__` 强制 `break` + `final_error`，与 `max_steps` 共享预算（不耗尽 5 步）
  - **性能**：`is_cartesian` 仅在 `final_answer` 分支调用一次（与 `_is_fan_out` 同位置）

### Test

- **`tests/services/test_sql_validator.py`** [NEW, 23 unit case]
  - **D-2 优先组**（Stage 3 守护者末段指示）：R-83 CTE/子查询递归 (3) + C4 恒真 ON (4)
  - C1 / C2 / C3 / 正例（USING / 单表 / 三表链 JOIN）/ R-89 输入预检 / R-80 fail-open / **R-93 v0.4.5 enc_v1: 加密字段值不被误判**
- **`tests/services/test_sql_planner_cartesian.py`** [NEW, 8 integration case]
  - R-82 `_run_tool` 单元 (3) + **R-85 cartesian 优先 fan-out** + **R-91 sync + async 双路径强制终止** + R-91 收敛恢复 + R-80 sqlglot 失败 fail-open
- 测试增量 31 case：v0.5.0 baseline 400 passed → v0.5.1 baseline **431 passed** / 112 skipped（R-88 校正：plan §5 写 ≥ 388 是按 v0.5.0 plan §6 数字 375 推算的，实际 baseline 400 + 31 = 431）

### Architecture（不增 contract）

7 import-linter contracts 全程 KEPT（与 v0.5.0 同条数）：
- `services` 层新增 `sql_validator.py` 不动现有 4 层依赖关系；`R-90` 守护：纯函数禁 `import knot.adapters.db / knot.repositories`
- `R-87` 守护：`api → services → repositories | adapters → models` 依赖方向不变

### Decisions Locked (D1-D5)

| ID | 锁定 | 依据 |
|---|---|---|
| **D1** | 独立 `knot/services/sql_validator.py` | 为 v0.5.2 sql_planner 瘦身预留解耦 |
| **D2** | 跨表 WHERE 无前缀检测 → **推迟**（v0.5.2 后） | 无 Schema Cache 误杀风险高 |
| **D3** | sqlglot 缺包/解析失败 → **fail-open** | 安全 guardrail 已在 doris.py 闭环；本验证器是质量守护 |
| **D4** | 旧式逗号 `FROM a,b WHERE a.id=b.id` 一律拒 | 维护 prompt/runtime 语义一致性（v0.4.1.1 prompt 已禁） |
| **D5** | fan-out regex → AST 升级 → **不动** | 单 PATCH 单核心问题 |

### Red-lines（R-80~R-93 共 14 条全部偿还）

| ID | 来源 | 内容 | 落地 |
|---|---|---|---|
| **R-80** | 执行者 | sqlglot 缺包/解析失败 → fail-open + warning | `is_cartesian` import + parse try/except + logger.warning |
| **R-81** | 执行者 | 4 类笛卡尔积全拒，reason 含表名 | `_REASON_TEMPLATES` 4 类 + `_extract_comma_tables` |
| **R-82** | 执行者 | `__REJECT_CARTESIAN__:` 协议 + sync/async 双 ReAct 不 break | sql_planner `_run_tool` + `cart_reject_count` |
| **R-83** | 执行者 | CTE / 子查询递归检测 | `tree.find_all(exp.Select)` 内层遍历 |
| **R-84** | 执行者 | 核心代码 ≤ 200 行硬约束 | validator 149 + planner +33 = **182** ≤ 200 ✓ |
| **R-85** | 执行者 | 不破坏 fan-out；同时触发 cartesian 优先 | final_answer 分支 cartesian 检测前置；fan-out 7 测试 100% 绿 |
| **R-86** | 执行者 | 不引新依赖 | `requirements.txt` 不动；sqlglot 既有 |
| **R-87** | 执行者 | 7 contracts KEPT 不动 | `lint-imports` 0 broken |
| **R-88** | 执行者 | 测试增量 ≥ 13 | 实际 +31 (23 unit + 8 integration) |
| **R-89** | Stage 2 | 递归深度限制 | `_MAX_SQL_LEN=100k` + `_MAX_PAREN_DEPTH=100` 入口预检 |
| **R-90** | Stage 2 | Validator 纯函数禁 DB | sql_validator.py 0 import `adapters.db` / `repositories` |
| **R-91** | Stage 3 | ReAct 无限循环保护（≥3 次拒收终止） | `cart_reject_count` 共享 `max_steps` 预算 |
| **R-92** | Stage 3 | 建设性 reason | `_REASON_TEMPLATES` 4 类含修复指引 |
| **R-93** | Stage 3 | v0.4.5 加密列兼容 | 单元测试覆盖 `WHERE k = 'enc_v1:...'` 不误判 |

### Loop Protocol v3 — 第二次完整施行

| Stage | 角色 | 产物 |
|---|---|---|
| Stage 1 | v0.5 执行者 | 草案 [docs/plans/v0.5.1-sql-ast-validator.md](docs/plans/v0.5.1-sql-ast-validator.md)（D1-D5 决策点 + R-80~R-88 9 红线） |
| Stage 2 | 资深架构师 + Codex | Redline / 评分 / 风险点（D1-D5 全 A/B 锁定 + 新增 R-89 R-90） |
| Stage 3 | v0.4 守护者 | 终审意见（GO + 新增 R-91 R-92 R-93 + D-2 测试骨架优先指示 + 性能注意） |
| Stage 4 | v0.5 执行者 | 4-commit 落地（C1 validator + C2 planner + C3 version + C4 docs），全闸门绿 |

> v0.4 守护者全程**只读**未触碰代码（合规 — Loop Protocol v3 § 角色定义）；v0.3 远古守护者 dormant 未激活（PATCH 内常规流程，未达 MINOR 滚动整体审核仪式条件）。



> v0.4.6 治理三部曲收官后**准生产前最后一刀大改**的第一步。Loop Protocol v3 **首次完整 PATCH 内施行**：
> v0.5 执行者 Stage 1 草案 → 资深 + Codex 辅助 AI 初审 → v0.4 守护者 Stage 3 终审
> （13 红线 R-67~R-79，含 R-74 密文兼容性探针 / R-77 跨平台 / R-78 conftest 同步等）。
>
> 本 PATCH = v0.5.0 commit 序列 **C0 only**（rename + foundation）；C1 SQL AST 推 v0.5.1；C2~Cn 各开 PATCH。

### ⚠️ BREAKING — 必读

1. **包名变更 `bi-agent` → `knot`**：升级前必跑 `pip uninstall bi-agent && pip install -e .`（开发环境）
2. **env 双源 + 旧名 deprecation**：
   - `KNOT_MASTER_KEY` 优先（v0.5.0 新名）
   - `BIAGENT_MASTER_KEY` 仍兼容（启动见 deprecation warn）；**v1.0 移除**
   - 同时设置且值不同 + DB 有 `enc_v1:` 数据 + 旧 KEY 解密成功新 KEY 失败 → R-74 探针 `sys.exit(1)` 防数据永久丢失
3. **DB 自动 startup migration**：首次启动检测 `knot/data/bi_agent.db` → 自动 rename `knot/data/knot.db`，留 timestamped `bi_agent.db.v044-<ts>.bak`；幂等
4. **Docker volume 用户**：`-v` 路径变更
   - 旧：`docker run -v /host/path:/app/bi_agent/data ...`
   - 新：`docker run -v /host/path:/app/knot/data ...`
5. **导入路径**：`from bi_agent.X import Y` → `from knot.X import Y`（132 个 .py 全替换）
6. **services/knot/ → services/agents/**：守护者整体审核新发现 `knot/services/knot/` 重名冲突，子目录改 `services/agents/`（产品名 knot 留顶层；子目录通用语义 — 里面就是 3 个 agent）

### Architecture（不增 contract）

7 import-linter contracts 全程 KEPT（v0.4.5 7 → v0.5.0 7）：

- Contract 1-6 source/forbidden 全部 `bi_agent.X` → `knot.X` 替换
- **Contract 7 `crypto-only-in-allowed-callers`** forbidden_modules 必须从 `bi_agent.core.crypto` 改 `knot.core.crypto`（**关键 R-71**：否则 lint-imports 显示 KEPT 但实际 forbidden 项不存在 = 契约失效但不报警）
- `allow_indirect_imports = True` 行为不变（v0.4.5 设定）

### Added

#### D-2 测试骨架（5 永久守护 + 1 一次性 D-5 删除）

- `tests/test_rename_smoke.py` — R-67/R-70/R-79 brand 字面量 + R-72 routes/version
- `tests/test_contracts_renamed.py` — R-71 7 contracts + Contract 7 forbidden 同步
- `tests/test_env_dual_source.py` — R-68 4 组合 + R-74 密文兼容性探针 4 case
- `tests/scripts/test_db_migration.py` — R-69 4 场景 + R-76 atomic（mock os.rename / shutil.copy2 抛错）
- `tests/integration/test_audit_continuity.py` — R-75 audit_log + 加密字段 rename 后可读
- ~~`tests/scripts/test_v050_rename.py`~~ — R-77 跨平台脚本守护（D-5 删，与一次性脚本同生死）

#### D-3 替换实施

- `knot/scripts/_v050_rename.py`（D-5 删）— Python 跨平台一次性替换；4 phase 顺序锁定
- **R-77 跨平台**：禁用 `sed -i ''`（macOS BSD vs Linux GNU 不兼容）；改用 `pathlib + str.replace`
- **字面量保护占位** `__V050_PRESERVE_BIAGENT_DB__` — 防 `bi_agent.db` 被误替成 `knot.db`
- **Phase 3 顺序漏洞主动发现 + 幂等修复**（见守护者结构性教训 §2）
- 边缘字面量 6 处手工补：`.importlinter` root_package / `pyproject.toml include glob` / `settings.py SQLITE_DB_PATH default` / `engine_cache.py _BIAGENT_DB → _KNOT_DB` / `logging_setup.py 4 处下划线模式` / CI workflow

#### env 双源 + R-74 密文兼容性探针

- `knot/core/crypto/fernet.py` 重写：`_NEW_ENV` / `_OLD_ENV` + `_read_master_key()` + `loaded_env_name()`
- R-74 `_find_enc_probe_in_db()`：用 stdlib sqlite3 直读 `enc_v1:` 数据探针（**不破坏 Contract 3** core-no-business — sqlite3 是 stdlib，合规）
- R-74 `_try_decrypt()`：旧 KEY 成功新 KEY 失败 → `sys.exit(1)` + 强烈警报（防数据永久丢失场景）
- `from __future__ import annotations`：兼容 Python 3.9（PEP 604 `X | None` 在 py3.10+ 才原生支持）

#### DB startup migration（R-69 + R-76）

- `knot/scripts/migrate_db_rename_v050.py`（永久 — 一次性脚本性质但保留以备 rollback / dry-run 调试）
- R-69 4 场景幂等（`no_db_yet` / `already_migrated` / `migrated` / `both_exist` raise RuntimeError）
- R-76 atomic 异常保护：`shutil.copy2 + Path.rename` try/except；rename 失败 → 删 bak + 老 DB 保留（绝不允许 DB 消失）
- 双轨支持：startup hook 调用 + 独立 entrypoint `python3 -m knot.scripts.migrate_db_rename_v050 [--dry-run --data-dir <path>]`
- 沿袭 v0.4.5 R-46 timestamped backup 命名 `bi_agent.db.v044-<ts>.bak`

#### main.py 启动改造

- FastAPI `title="KNOT"` `version="0.5.0"`
- `migrate_db_rename(_DATA_DIR)` 在 `init_db()` 之前
- 启动 banner 用 `loaded_env_name()` 显示实际加载 env 名（KNOT_MASTER_KEY 或 BIAGENT_MASTER_KEY）
- 错误文案改 KNOT brand + dual env hint（推荐 KNOT_MASTER_KEY；提及 BIAGENT_MASTER_KEY 兼容至 v1.0）

#### conftest.py R-78 + dotenv 隔离

- autouse fixture `_master_key_for_tests` 改 `setenv("KNOT_MASTER_KEY")`（默认走仅新 key 路径，避免 caplog deprecation 污染）
- `tests/test_env_dual_source.py` 显式 unset 全局 fixture（防 autouse 污染 R-68 双源测试）
- `test_R45` subprocess 测试用 `cwd=tmp_path + PYTHONPATH 注入` 隔离 .env 自动发现（守护者教训 §1）

#### frontend

- `vite.config.js` outDir `'../bi_agent/static'` → `'../knot/static'`
- `Chat.jsx:223` CSV 导出文件名前缀 `bi-agent-${ts}.csv` → `knot-${ts}.csv`（D5 拍板 brand 一致性）

#### 配置 + CI

- `pyproject.toml` `name = "bi-agent"` → `"knot"`；`include = ["bi_agent*"]` → `["knot*"]`
- `Dockerfile` 3 处 path + `uvicorn knot.main:app`
- `start.sh` 同步替
- `.github/workflows/ci.yml`：matrix env 4 组合 × ubuntu+macOS 双平台（R-72/R-77 完整覆盖）

### 偿还红线 13/13（R-67~R-79）

| ID | 内容 | 守护机制 |
|---|---|---|
| R-67 | 包名 / 包目录 / DB 文件名一致 | grep 守护测试 |
| R-68 | env 双源优先级（KNOT > BIAGENT；4 组合） | 单元测试 + CI matrix |
| R-69 | DB migration 幂等 + timestamped bak + 双 db fail-fast | 4 场景测试 |
| R-70 | services/knot → services/agents 强制（无 alias） | grep 守护测试 |
| R-71 | contract 数仍 7 + Contract 7 forbidden 同步替换 `knot.core.crypto` | lint-imports + assertion |
| R-72 | CI matrix 4 组合 + routes 72 + import smoke | CI matrix job |
| R-73 | knot/ 包内严禁 bi_agent 命名 | grep 守护 |
| R-74 | 密文兼容性探针 — 双 key 不同值时验证旧/新解密能力 | 单元测试 4 case |
| R-75 | DB rename 后 v0.4.6 audit_log 数据完整可读 | 集成测试 2 case |
| R-76 | 迁移备份原子性 — rename 失败 → 删 bak 保老 DB | 单元测试 2 case |
| R-77 | 跨平台 Python 脚本（禁 sed） | 一次性测试守护（D-5 删）+ macOS+Linux CI |
| R-78 | conftest 同步修改 + R-68 测试隔离 + dotenv 隔离 | grep + autouse override + cwd=tmp_path |
| R-79 | brand 字面量 grep 守护（业务代码） | grep 守护测试 |

### 验收数据

- **pytest 375 passed** in 75.7s（v0.4.6 362 → +13 = 19 新 - 6 一次性删）
- **lint-imports 7 contracts KEPT, 0 broken**
- **ruff All checks passed**（顺手清理 4 处 `typing.Iterable` → `collections.abc.Iterable` PEP 585）
- **frontend npm run build** 产物 `knot/static/`（vite outDir 替换正确）
- **路由数 72 不变**（v0.4.6 锚点；本 PATCH 纯 rename，无新增路由）
- **env 2 组合本地预演**（仅新 / 仅旧）— deprecation warn 文案精准
- **R-79 grep 守护**：业务代码（agent prompt / repositories / api）0 命中 brand 字面量
- **R-67 grep 守护**：knot/ 内 bi_agent 命中 28 → 9（剩 9 全合法白名单业务字面量）

### Loop Protocol v3 首次完整 PATCH 内施行

| 阶段 | 责任方 | 产出 |
|---|---|---|
| Stage 1 | v0.5 执行者 | 草案 `docs/plans/v0.5.0-rename-and-foundation.md`（D1-D7 决策点 + R-67~R-72 6 红线） |
| Stage 2 | 资深 + Codex | D1-D7 拍板（A 全采纳）+ R-73 增量 |
| Stage 3 | v0.4 守护者 | 终审整合（R-74/R-75/R-76 答资深 3 维度 + R-77/R-78/R-79 守护者预查 + 5 修订）|
| 执行 | v0.5 执行者 | D-1 ~ D-7 七步切片，每完成停下汇报守护者闸门复核 |

### 守护者结构性教训（留 v0.5.x / v0.6 PATCH 警示）

#### 1. dotenv 向上自动发现 `.env` 文件 — 测试隔离的隐藏 trap

**场景**：D-4 调试 `test_R45_startup_missing_key_prints_friendly_error_and_exits_1` subprocess 测试时发现，**worktree 父目录** `.env` 含 `BIAGENT_MASTER_KEY`，settings.py 的 `load_dotenv()` 默认 `find_dotenv()` 向上搜索 → subprocess 即使 `env.pop("BIAGENT_MASTER_KEY")` 也会被 .env 注入回来。

**修复**：subprocess test 用 `cwd=tmp_path` 隔离 .env 自动发现 + `PYTHONPATH` 注入 worktree 让 knot 模块仍可 import。

**警示**：未来任何 subprocess 测试跑 main app 必须 cwd 隔离。这也是真实生产场景隐藏 issue（用户多实例部署 / dev .env 残留）。

#### 2. R-77 替换顺序漏洞 — 包重命名脚本输入前提

**场景**：守护者终审 §7 Phase 3 设计「① `knot.services.knot` → `knot.services.agents`」前提**错了**——git mv 不动字符串字面量，源码里实际仍是 `from bi_agent.services.knot import`，不匹配 ①；② `bi_agent.X` → `knot.X` 跑后变成 `knot.services.knot`，之后无人再处理 → 残留。

**修复**：执行者发现并扩展 ① 同时覆盖两种前缀（`bi_agent.services.knot.` / `knot.services.knot.`）。脚本幂等，重跑补 12 个文件。

**警示**：未来任何包重命名 PATCH，sed/Python 替换的输入前提必须以**源码字面量**为准，不以"目录已 mv 的理想形态"为准。

#### 3. PEP 585 顺手清理 typing → collections.abc

py3.9+ 推荐 `from collections.abc import Iterable` 取代 `from typing import Iterable`。v0.4.x 累积 4 处旧 typing import（含执行者新写的 `_v050_rename.py` 一处），ruff PEP 585 检测 + 自动 fix 已清理。

**警示**：未来新代码直接用 `collections.abc`，不要再写 `from typing import Iterable`。

### Out-of-Scope（明确推迟）

- ~~SQL AST 预校验~~ → v0.5.1（C1）
- ~~后端 / 前端瘦身（sql_planner / Chat.jsx 等）~~ → C2/C3 各 PATCH
- ~~Claude Design UI 重构~~ → C5+（多 PATCH）
- ~~lark.py stub 删 / sync LLM API @deprecated~~ → Cn cleanup
- ~~/api/v1/ 路由前缀（CHANGELOG line 642 标记 v0.5.0）~~ → 独立 PATCH
- ~~messages 表 26 列瘦身（v0.4.2 R-S6）~~ → v0.5.x 评估迁移工具

---

## [v0.4.6] - 审计日志（who-did-what）

> v0.4.5 数据加密收官后第一个延伸 PATCH。Loop Protocol v2 三阶段走完：
> v0.4 执行者 Stage 1 草案 → 资深 + Codex 辅助 AI 初审 → v0.3 守护者 Stage 3 终审
> （含 D1 反转 schema +client_ip/user_agent 独立列等 9 条修订）。
>
> KNOT **治理三部曲收官**（v0.4.3 经济阀 / v0.4.4 错误阀 / v0.4.5 数据合规阀 / v0.4.6 审计追溯阀）。
> 团队公测的最后障碍清空。

### Architecture（无新 contract）
- **7 contracts 维持** — 不增层、不增 contract（v0.4.5 升 6→7 后稳定）
- audit 各模块严守既有 4 层契约：`api/_audit_helpers + api/audit` → `services/audit_service` → `repositories/audit_repo`
- 前端 `AdminAudit.jsx` 复用 v0.4.3 视觉风格

### Added — schema + repo (commit #1, R-50/54/55/58/65)
- `bi_agent/repositories/schema.sql` +`audit_log` 表（INSERT-only 设计）+ 3 索引
  - **R-58 独立列**：`client_ip` / `user_agent` / `actor_name` 冗余快照（actor 删除后审计仍可读）
- `bi_agent/repositories/audit_repo.py` — 仅 3 函数表面：`insert / list_filtered / delete_older_than`
  （R-50：无 update / delete_by_id；purge 脚本是唯一删除入口）
- `bi_agent/models/audit.py` — `AuditAction` Literal **33 条**（8 类 mutation × 子动作 + meta-audit）；
  `messages.*` 显式排除（R-63 每 query 一条会爆表）
- `bi_agent/models/errors.py` +`AuditWriteError(BIAgentError)` — R-65 errors 树复用，不在 services 重定义

### Added — service (commit #2, R-47/48/51/59/62/64)
- `bi_agent/services/audit_service.py`
  - **PII 三层防御**：`_PII_BLACKLIST` 含 v0.4.5 全 5 类加密字段 + bcrypt + 原始 password
  - **R-48 + R-59 + R-62**：字段名命中即 redact，**密文（含 enc_v1: 前缀）也 redact**
  - **D7 递归深度 3**：超限整体 redact，防恶意嵌套栈溢出
  - **R-47 fail-soft**：repo.insert 抛错 → logger.error 不阻断业务
  - **R-64 失败盲区可观测**：`_audit_write_failures_total` 模块级计数器（prometheus hook 预埋）+ `get_failure_count()` 公开
  - **R-51 actor 强制 token**：detail 中 actor_id 字段被忽略
  - **R-65 不重定义异常**：service 路径不抛 AuditWriteError（R-47 优先）；类存在为未来分布式补录场景预留

### Added — 7 类 mutation 集成 + admin GET 路由 (commit #3, R-52/53/56/60/61/63)
- `bi_agent/api/_audit_helpers.py` — api 边界 helper（与 v0.4.5 `_secret.py` 同模式）
  - `_get_client_ip(request)` 三级 fallback：`X-Forwarded-For` → `X-Real-IP` → `request.client.host`（守护者前瞻：反代部署直接生效）
  - `audit(request, actor, **kwargs)` 自动取 ip / user_agent / request_id
- `bi_agent/api/audit.py` — `GET /api/admin/audit-log` + `R-61 limit cap 200`
- 集成审计到 7 类 mutation（共 20+ 调用点）：
  - `auth.py` — login_success / login_fail（D5 失败登录记尝试 username）
  - `admin.py` — users CRUD + role_change + password_reset / datasources CRUD / api_key.{set,clear}_global / budget CRUD / agent_models_update
  - `saved_reports.py` — pin / run / update / delete
  - `few_shots.py / prompts.py / catalog.py` — config 变更
- **R-53 stress**：1000 次连发 mutation → audit p95 < 5ms（同步 INSERT SQLite ~1ms）
- **R-56 越权防御**：analyst → 403

### Added — 前端 AdminAudit (commit #4, D3 落地)
- `frontend/src/screens/AdminAudit.jsx` — 筛选 + 表格 + 分页 + 详情抽屉
  - 显式分页（page 1 / 2 / ...，**不**"加载更多"）配 50/100/200 size 切换
  - 详情抽屉的 `DetailJsonView` 高亮 `••••redacted••••` 字串（橙色背景 #FF990033）
    — 守护者前瞻：PII 妥善处理的直观证明，提升 admin 信任感
- Shell sidebar +「📋 审计日志」入口（admin only）

### Added — purge + retention + meta-audit (commit #5, R-49/57/66)
- `bi_agent/scripts/purge_audit_log.py` — **R-66 复用 v0.4.5 `migrate_encrypt_v045` 模式**：
  - 独立 entrypoint（`python3 -m bi_agent.scripts.purge_audit_log [--dry-run]`）
  - 自动 timestamped `<db>.audit-purge-YYYYMMDD-HHMMSS.bak`（同秒加 PID 兜底）
  - dry-run 0 副作用（不删 + 不创 bak）
  - 复用 commit #1 的 `audit_repo.delete_older_than()`（不重写 SQL）
- `GET / PUT /api/admin/audit-config` — R-49 retention 7~3650 区间校验
- **R-57 meta-audit**：`audit.retention_change` + `audit.purge` 自身入 audit_log

### Tests
- 新增 **53 测试**（v0.4.5 309 → v0.4.6 **362 passed** / 112 skipped）：
  - `tests/repositories/test_audit_repo.py` (10) — schema + INSERT-only + Literal 覆盖
  - `tests/services/test_audit_service.py` (12) — PII scrub + fail-soft + actor token
  - `tests/services/test_audit_service_stress.py` (1) — R-53 1000×p95<5ms
  - `tests/api/test_audit_integration.py` (13) — 7 类 mutation × audit + R-47/R-63 守护
  - `tests/api/test_audit_list_route.py` (7) — R-56/R-61 + 筛选
  - `tests/api/test_audit_config_route.py` (6) — R-49 + R-57 + 越权
  - `tests/scripts/test_purge_audit_log.py` (7) — R-66 复用 + R-57 meta-audit + dry-run

### 偿还红线 20 / 20
R-47 fail-soft / R-48 PII / R-49 retention / R-50 INSERT-only / R-51 actor token /
R-52 4 层契约 / R-53 stress / R-54 actor_name 冗余 / R-55 Literal / R-56 越权 /
R-57 meta-audit / R-58 client_ip 独立列 / R-59 密文不入 / R-60 service 不反向 /
R-61 强制分页 / R-62 v0.4.5 字段同步 / R-63 子类完整 + messages 排除 /
R-64 失败计数器 / R-65 errors 复用 / R-66 purge 复用 v0.4.5 模式

### 验收数据
- pytest **362 passed** / 112 skipped
- lint-imports **7 contracts KEPT**, 0 broken（不增 contract）
- ruff All checks passed
- frontend `npm run build` ✓ ~1432 KB
- 路由数 **72**（v0.4.5 69 + audit-log GET (1) + audit-config GET/PUT (2)；69 → 72）

---

## [v0.4.5] - 数据加密

> v0.4.4 收官后第一个延伸 PATCH。Loop Protocol v2 三阶段走完：
> v0.4 执行者 Stage 1 草案 → 资深 + Codex 辅助 AI 初审 → v0.3 守护者 Stage 3 终审
> （含 D1 路径反转 `adapters/crypto/` → `core/crypto/` 等 9 条修订）。
>
> KNOT 安全底线建立：6 类敏感字段（4 user keys + doris_password + db_password + app sensitive settings）
> 全部应用层 Fernet 加密；调用方零改动；4 层契约不破；启动 fail-fast；迁移幂等可恢复。

### ⚠️ BREAKING — 必读

- **`BIAGENT_MASTER_KEY` 环境变量必须配置**，否则启动 fail-fast（`sys.exit(1)`）。
  生成：`python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
- **历史 v0.4.4 DB 升级前**，先备份再跑迁移：
  ```bash
  python3 -m bi_agent.scripts.migrate_encrypt_v045 --dry-run
  python3 -m bi_agent.scripts.migrate_encrypt_v045
  ```
- **Master key 丢失 = 历史加密数据永久不可读** — 务必备份至独立保险位置（不只放 .env）

### Architecture — 首次 contract 数变更（6 → 7）

- **新增 Contract 7** `crypto-only-in-allowed-callers`：
  `core.crypto` 仅 `repositories` / `scripts` / 自身可 import；
  `api / services / adapters / models` 直接 import 即触红
  （`allow_indirect_imports = True` 只查直接边，不阻断合法链路）
- **D1 路径**（守护者反转）：crypto 物理位置 `bi_agent/core/crypto/`（不是 `adapters/crypto/`，
  避免破 v0.3.3 双重 contract — layers + repos-no-business）
- **本地异常**：`core.crypto.fernet.CryptoConfigError`（守 Contract 3 core-no-business）；
  repositories catch 后翻译为 `models.errors.ConfigMissingError`（领域异常树边界）

### Added — 加密器 (commit #1, R-34/R-35/R-37/R-40/R-42/R-44)

- `bi_agent/core/crypto/{__init__,base,fernet}.py`：Fernet 加密器 + `CryptoConfigError` + `assert_master_key_loaded`
- `lru_cache(maxsize=1)` 进程单例；测试 `cache_clear()` 隔离
- 加密产物前缀 `enc_v1:`；空串占位区分 NULL；老明文兼容（无前缀直接放行）

### Added — repositories 透明加解密 (commit #2, R-38/R-43/R-43-Dual)

- `user_repo` — 4 类敏感列：`api_key / openrouter_api_key / embedding_api_key / doris_password`
- `data_source_repo` — `db_password`
- `settings_repo` — sensitive 白名单 `{openrouter_api_key, embedding_api_key}`
  - **R-43** 失败安全：非白名单但带 `enc_v1:` → 也尝试解密
  - **R-43-Dual** 写入对偶：误传已加密值 → 跳过二次加密 + WARNING

### Added — 迁移脚本 (commit #3, R-36/R-41/R-46/R-46-Tx)

- `bi_agent/scripts/migrate_encrypt_v045.py`：一次性 + 幂等 + 独立 entrypoint
- 自动 `<db>.v044-YYYYMMDD-HHMMSS.bak`（timestamp 后缀避免覆盖；同秒加 PID 兜底）
- **每张表一个事务**（表内异常整表 ROLLBACK，跨表已 commit 保留）
- `--dry-run` 0 副作用（不写 DB / 不创 bak）
- master key 缺失先 fail，不创 bak（守护者提示）

### Added — 前端 mask (commit #4, R-39)

- `bi_agent/api/_secret.py`：mask helper 在 api boundary（不污染 services / repos）
  - `mask_secret(s)` → `••••••••last4`（短于 4 字符全 `••••`）
  - `should_update_secret(new, old)` → 四态分类（None / "" / mask 占位 / 新值）
- `GET /api/admin/api-keys` 返 masked
- PATCH 路由：空字符串 / mask 占位 → 保留原值；新值 → 加密更新
- 同保留逻辑应用到 `PUT /api/admin/users` 的 `doris_password` 和 `PUT /api/admin/datasources` 的 `db_password`
- 前端 `Admin.jsx` 编辑差量提交（仅发送被改动的字段）

### Added — startup + docs (commit #5, R-45)

- `bi_agent/main.py::_check_master_key_or_exit()` 在 `init_db()` 之后
  - 缺失/格式错 → 彩色边框错误 + `sys.exit(1)`（不暴露 traceback）
  - module top-level（uvicorn import 即触发，不靠 `__main__`）
- `requirements.txt` +`cryptography>=41,<46`
- `.env.example` +`BIAGENT_MASTER_KEY` + 生成命令注释

### Tests

新增 **45 测试**（v0.4.4: 264 → v0.4.5: **309 passed** / 112 skipped）：

- `tests/core/test_crypto_fernet.py` (10) — Fernet 单元 + R-34/R-35/R-40/R-42
- `tests/test_startup_master_key.py` (4) — startup + R-45 subprocess 友好错误
- `tests/repositories/test_repo_encryption_transparency.py` (12) — R-38/R-43/R-43-Dual + 边界翻译
- `tests/scripts/test_migrate_encrypt_v045.py` (9) — R-36/R-41/R-46/R-46-Tx + dry-run
- `tests/api/test_settings_masked.py` (10) — R-39 mask + helper unit + admin 越权防泄漏

### 偿还红线 13 / 13

R-34 (master key fail-fast) / R-35 (enc_v1: 前缀) / R-36 (幂等) / R-37 (测试隔离) /
R-38 (crypto only in repos) / R-39 (前端 mask + PATCH 保留) / R-40 (单例 lru_cache) /
R-41 (独立 entrypoint) / R-42 (key 格式校验) / R-43 + R-43-Dual (settings 失败安全) /
R-44 (async 线程安全文档) / R-45 (startup 友好错误) / R-46 + R-46-Tx (自动 .bak + 每表事务)

### 守护者结构性教训（v0.4.5 复盘 — 留给 v0.4.6+）

> **任何 startup 行为变更，必须同步更新 CI workflow 的 boot smoke step。**

v0.4.5 commit #5 落 R-45 startup `sys.exit(1)` 后，CI 第一次红 — `App boot smoke` 没注入
`BIAGENT_MASTER_KEY`。13 条红线 R-34~R-46 偿还时遗漏了这条隐含模式：

- v0.4.0 eval-live workflow 也碰过同类问题（CI 跑 live LLM 需 `OPENROUTER_API_KEY`）
- v0.4.5 startup 加 master key 校验 → CI 必须显式注入临时 key

**未来 PATCH 加任何 startup 校验**（如审计 log 路径、预算服务初始化、其他 env-required 配置）
**都要回头同步**：
1. `.github/workflows/ci.yml` 的 `App boot smoke` step
2. `eval-live.yml`（若涉及 main app boot）
3. 其他 workflow 内**任何** `from bi_agent.main import app` 或 `uvicorn bi_agent` 的 step

修补方式：动态生成临时凭据（不入 repo 固定字符串）+ export env + 跑 boot 命令。

### 验收数据

- pytest **309 passed** / 112 skipped
- lint-imports **7 contracts KEPT**, 0 broken（首次从 6 升 7；v0.3.0 以来首次 contract 数变更）
- ruff All checks passed
- frontend `npm run build` ✓ ~1424 KB
- 路由数 64（不变 — v0.4.5 纯加密改造，无新路由）

---

## [v0.4.4] - 异步 LLM + 错误体验改造

> v0.4.3 成本治理收尾后的第一个延伸 PATCH。Stage 1-4 协议走完：
> 新版本 Agent 草案 + 资深 Stage 2 + 守护者 Stage 3（联合评审 9 条红线 R-24~R-33）+
> 资深 Stage 4 锁定（含 R-30 关键事实纠正：复用 `models/errors.py`，禁建 `services/errors.py`）。
>
> KNOT 进入「真异步」阶段：LLM 调用脱离 run_in_executor 走 native AsyncAnthropic / AsyncOpenAI；
> 错误体验从「裸 RuntimeError」升级为 BIAgentError 树 + error_translator → 前端 ErrorBanner。

### Added — 异步 LLM 适配层 (R-24 / R-31 / R-32)
- **`adapters/llm/anthropic_native.py`**：新增 `acomplete()` 走 `anthropic.AsyncAnthropic`
- **`adapters/llm/openai_compat.py`**：新增 `acomplete()` 走 `openai.AsyncOpenAI`
- **`adapters/llm/openrouter.py`**：新增 `acomplete()` 委托内嵌 OpenAICompatAdapter
- **`adapters/llm/factory.py::get_async_adapter`**：R-31 Protocol 完整性
  `assert isinstance(adapter, AsyncLLMAdapter)`（v0.4.0 占位 → v0.4.4 落地）
- R-24 双 API 共存：sync `complete()` 全部保留（向后兼容旧 sync 路径）

### Added — BIAgentError 树扩展 + error_translator (R-25 / R-30)
- **`models/errors.py`**（v0.3.2 既有树）扩充 4 个领域错误：
  - `LLMNetworkError`（网络/timeout/5xx，is_retryable=True）
  - `BudgetExceededError(meta)` / `DataSourceUnavailableError` / `ConfigMissingError`
- **`services/error_translator.py`**（NEW）：BIAgentError → `{kind, user_message, is_retryable, details}`
  7 类 kind：budget_exceeded / config_missing / llm_failed / sql_invalid / sql_exec_failed /
  data_unavailable / unknown；子类优先匹配（UnsafeSQL 早于 BusinessDB）
- **R-30 守护**：原计划 `services/errors.py` 被守护者拦截 → 复用 models/errors.py 不重复造轮子

### Added — 异步业务编排 (R-26-Senior / R-27 / R-32)
- **`services/llm_client.py`**：
  - `_ainvoke_via_adapter(*, agent_kind)` — **R-26-Senior 第一行 budget 守护**
    （SDK 实例化前、网络连接前抛 BudgetExceededError，adapter 永不被调用）
  - `agenerate_sql()` (agent_kind="sql_planner") / `afix_sql()` (agent_kind="fix_sql" R-32)
- **`services/knot/orchestrator.py`**：
  - `arun_clarifier()` (agent_kind="clarifier") / `arun_presenter()` (agent_kind="presenter")
  - 错误传播契约：`except BIAgentError: raise` (R-30) / `except Exception: pass`（兜底）
- **`services/knot/sql_planner.py`**：`arun_sql_agent()` ReAct 异步循环
  - 继承 v0.4.1.1 `__REJECT_FAN_OUT__` 防御
  - BIAgentError 透传 / 非领域异常 → AgentResult.error

### Added — api/query.py 真异步路径 (R-26-SSE / R-33)
- 替换 3 处 `loop.run_in_executor` → 直接 `await arun_*`
- **R-26-SSE**：每个 `yield emit(...)` 后 `await asyncio.sleep(0)` 让步 event loop
- **R-33 双路径同字段**：流式 SSE final + 非流 JSON 返回**字段集相同**
  （成功也带 `error_kind=None / user_message=None / is_retryable=None` 占位）
- BIAgentError → `error_translator.to_response(e)`；非领域异常 → `to_response_unknown()`
- **R-27 race 守护**：`tests/services/test_async_concurrency.py` 100 次 × asyncio.gather
  3 agent 并发累加，验证 `user_repo.monthly_cost_usd ≈ SUM(messages.cost_usd)` 漂移 ≤ 0.01%

### Added — 前端 ErrorBanner + R-28 优先级
- **`frontend/src/screens/Chat.jsx`** ResultBlock 内嵌 ErrorBanner：
  - 7 类 error_kind → (icon, title, color) 视觉映射
  - `is_retryable=true` 显示「重试」按钮，回填 question 到 composer
- **R-28 优先级**：`error_kind === 'budget_exceeded'` 时隐藏 BudgetBanner（避免同条消息双 banner）
- 流式 SSE error / final 事件均消费 error_kind / user_message / is_retryable
- 旧消息（无 kind）走简版兜底 div，向后兼容

### Changed — anyio threadpool 默认值 (R-29-anyio)
- `bi_agent/main.py` ANYIO_TOKENS 默认 **64 → 32**（LLM 离开线程池后 sync DB 不再竞争）
- 高并发 SQLAlchemy 场景可通过 `ANYIO_TOKENS` 环境变量上调

### Tests
- 新增 53 测试，全套 264 passed / 112 skipped（v0.4.3: 223）：
  - `tests/adapters/test_async_llm_factory.py` (9) — R-31 Protocol 完整性
  - `tests/adapters/test_async_llm_protocol.py`（v0.4.0 占位测试方向反转）
  - `tests/services/test_error_translator.py` (13) — R-25 全 kind 映射 + 子类优先 + unknown 兜底
  - `tests/services/test_llm_client_async.py` (6) — R-26-Senior + R-32 + R-24 sync 兼容
  - `tests/services/test_orchestrator_async.py` (6) — R-30 + R-32 + R-26-Senior 端到端
  - `tests/services/test_sql_planner_async.py` (5) — R-30 ReAct 透传
  - `tests/services/test_async_concurrency.py` (2) — R-27 race 守护

### Architecture
- 6 contracts 全程 KEPT（无 import-linter 改动）
- ruff All checks passed
- frontend `npm run build` ✓ (1423 KB)

---

## [v0.4.3] - 预算告警 + System_Recovery 维度（成本治理收尾）

> v0.4.2 cost telemetry 后第一个延伸 PATCH。Stage 1-4 协议走完：
> v0.4 Agent 草案（Option B）+ 资深 Stage 2（4 项裁决）+ 守护者 Stage 3
> （4 条新红线 R-S 系列）+ 资深 Stage 4 锁定（8 条红线全部并入）。
>
> KNOT 进入「准生产」阶段：架构稳 + cost 透明 + 预算可控 + 自纠正可观察。

### Added — 预算告警 (F4.a + F4.b + R-16/R-23)
- **`budgets` 表**（资深 R-16 同表 DRY）：
  - 三层 scope (global / user / agent_kind) + 3 类 budget_type
  - UNIQUE (scope_type, scope_value, budget_type) 服务于 R-18 幂等
- **`bi_agent/models/budget.py`** — Budget dataclass + 3 个 Literal 锁
  - V042_RELEASE_DATE='2026-05-08' 常量（R-19 趋势过滤起点）
- **`bi_agent/repositories/budget_repo.py`** — CRUD + R-18 INSERT OR REPLACE
- **`bi_agent/services/budget_service.py`**（NEW）8 红线落点：
  - `check_user_monthly_budget`：R-16 优先级链 (User > Global) + R-17 一致性
    （current 从 user_repo.monthly_cost_usd 缓存读，不实时 SUM）
  - `check_agent_per_call_budget`：R-23 实时查 + 'block' 阻断逻辑
  - `validate_budget_input`：R-21 拒 (agent_kind, legacy) + 'block' 范围限制
- **`/api/admin/budgets` CRUD（4 路由）**：
  - POST 用 R-18 INSERT OR REPLACE 幂等响应 `{id, already_existed}`
  - R-21 守护：拒 (agent_kind, legacy) → 400
  - 'block' 仅允许 (agent_kind, per_call_cost_usd) 组合

### Added — System_Recovery 维度 (F4.c + R-19)
- **`message_repo.get_recovery_trend(period_days, since_date)`**：
  - R-19 SQL 强制 WHERE agent_kind != 'legacy' AND created_at >= since_date
  - 返 by_day 趋势 + top_users Top 10 + total_recovery_attempts
- **`/api/admin/recovery-stats?period=30d`** 新路由（admin 看板）

### Added — query.py R-22 双路径 budget_status
- 流式（query-stream）SSE final 事件加 `budget_status` + `budget_meta`
- 非流式（POST /query）JSON 响应加同字段
- mobile / 第三方 client 一致

### Added — 前端
- **`screens/AdminBudgets.jsx`**（NEW）— 预算 CRUD + R-21 client-side 守护
- **`screens/AdminRecovery.jsx`**（NEW）— 时段切换 + 折线 + Top users 表格
- **Chat.jsx::ResultBlock R-20 banner**：
  - sessionStorage `budget_warn_{user_id}_{YYYYMM}` 降噪
  - "本会话不再提醒"按钮 + 月份切换自动重新提醒
- **Shell.jsx** admin nav +2 行：💰 预算 + 🛡️ Recovery

### Verified
- `pytest tests/ -v`：**223 passed / 112 skipped**（v0.4.2 203 → +20）
- 关键测试：
  - **R-17 守护测试**（`test_cost_alignment.py`）：100 次模拟闭环验证 user_repo
    与 SUM(messages) 误差 ≤ 0.01%（v0.4.2 R-S8 的延伸）
  - R-18 端到端：重复 POST UNIQUE 三元组 → 200 + already_existed=True
  - R-21 守护：(agent_kind, legacy) → 400
  - R-22 双路径：非流式 JSON 也含 budget_status / budget_meta
- `lint-imports`：6 contracts KEPT, 0 broken（不动 `.importlinter`）
- `ruff check bi_agent/`：All checks passed
- `python -c "from bi_agent.main import app"`：**69 routes**, version=**0.4.3**

### 不在 v0.4.3 范围（推后续 PATCH）
- ❌ 错误体验改造 → v0.4.4 与 async LLM/DB 改造合并（资深 Stage 2 重定位）
- ❌ 数据加密（API Key / 业务库 password）→ v0.4.5
- ❌ 审计日志（who-did-what）→ v0.4.6
- ❌ user 级 hard block → v0.5.x（v0.4.3 仅 warn）
- ❌ Alembic / yoyo 迁移工具（R-S6: messages 列数 24，仍未触发）→ v0.4.5+

### 8 条红线全部偿还
- ✅ R-16 优先级链 / R-17 一致性对齐 / R-18 INSERT OR REPLACE / R-19 过滤 legacy
- ✅ R-20 banner 降噪 / R-21 拒 legacy scope / R-22 双路径同字段 / R-23 不缓存

## [Unreleased] - v0.4.2 成本可观测 + xlsx 导出 + eval SQL 复杂度横切

> v0.4.1.1 hotfix 合入 main 后第一个业务 PATCH。Stage 1-4 协议走完：
> v0.4.2 Agent 草案 + 资深 Stage 2（4 项裁决）+ v0.4 守护者 Stage 3（4 条新红线）
> + 资深 Stage 4 锁定（含 R-14 fix_sql 独立 agent_kind 拍板）。
>
> KNOT 从"功能实现"转向"运营精细化 + 质量工程化"：成本归因到 agent 颗粒度，
> SQL 复杂度横切覆盖 subquery / window / cte。

### Added — 成本归因分桶 (F3.a + F3.d + F3.e)
- **`messages` 表 +10 列**（资深 Stage 2 列扩展决议）：
  - `agent_kind TEXT NOT NULL DEFAULT 'legacy'` — 'clarifier' / 'sql_planner' /
    'fix_sql' / 'presenter' / 'legacy'（资深 Stage 4 拍板：fix_sql 独立桶）
  - `clarifier_cost / sql_planner_cost / fix_sql_cost / presenter_cost (REAL)`
  - `clarifier_tokens / sql_planner_tokens / fix_sql_tokens / presenter_tokens (INT)`
  - `recovery_attempt INTEGER DEFAULT 0` (R-14: fan-out reject + fix_sql retry 计数)
- **`bi_agent/models/agent.py`**：`AgentKind` Literal + `VALID_AGENT_KINDS` 元组（Stage 3-A 枚举锁）
- **`bi_agent/services/cost_service.py`**（NEW）：
  - `empty_buckets()` / `add_agent_cost()` / `aggregate_agent_costs()` (R-S8 唯一一致性入口)
  - `to_save_message_kwargs()` / `to_sse_payload()` 字段映射
  - `get_cost_breakdown_by_period(period)` 按 agent_kind + user 聚合
- **`message_repo.save_message()`** 加 10 个新参数 + `'legacy'` 不变量守护（Stage 3-A）
- **`api/query.py`** 全面分桶累加：
  - 流式路径：clarifier/sql_planner/presenter 三桶；扫 sql_result.steps 计 fan-out reject
  - 非流式路径：sql_planner / fix_sql 双桶（fix_sql 独立累加）
  - SSE final 事件加 `agent_costs` + `recovery_attempt`（向前展开）
- **`/api/admin/cost-stats?period=7d`** 新路由：按 agent_kind 5 桶 + 按 user 分组

### Added — xlsx 导出 (F3.b + R-15 + R-S7)
- **`services/export_service.rows_to_xlsx_bytes`**：
  - openpyxl 写入；数字保留 number；中文 unicode 保留
  - **5000 行硬限**（资深 R-15 防 OOM）
  - 返 `(bytes, metadata)` — `{truncated, total, exported}` 暴露给 API 层
- **`/api/messages/{id}/export.xlsx`** + **`/api/saved-reports/{id}/export.xlsx`**：
  - **R-S7 响应头**：`X-Export-Truncated` / `X-Export-Total-Rows` / `X-Export-Returned-Rows`
  - 前端读响应头，截断时 toast「已截断至 N 行（共 M 行）」
- 现有 CSV 路由完全保留（向后兼容）

### Added — eval SQL 复杂度横切 (F3.c, v0.4.0 守护者教训)
- **`tests/eval/cases.example.yaml` 90 → 111** (+21)：
  - subquery (6) / window (6) / cte (6) / mixed (3)
- **`test_eval._check_complexity` dispatcher**（资深 AST hybrid 决议）：
  - `_check_subquery_present` / `_check_window_with_partition_or_order` /
    `_check_cte_uses_with` — sqlglot AST 优先 + 关键词正则 fallback

### Changed — CI eval-live workflow（R-Stage3-C 守护者）
- PR 触发改 `types: [labeled]` + `if: contains(labels, 'run-eval')`
  - 默认不在 PR 跑（cases 111+ 后单跑 cost ≈ $5-6）
  - reviewer 加 `run-eval` label 主动触发
- schedule (cron 周一) + workflow_dispatch 不变

### Added — 前端
- **`Chat.jsx::ResultBlock`**：per-agent cost chip（💡 clarifier / 🔍 sql_planner /
  🔧 fix_sql / 📊 presenter）+ ↻ N 自纠正次数指示
- **`SavedReports.jsx::DetailView`**：📊 Excel 按钮 + R-S7 截断 toast

### Verified
- `pytest tests/ -v`：**203 passed / 112 skipped**（v0.4.1.1 168 → +35）
- eval cases：89 → **111**（+22）
- `lint-imports`：6 contracts KEPT, 0 broken
- `ruff check bi_agent/`：All checks passed
- `python -c "from bi_agent.main import app"`：**64 routes**, version=**0.4.2**

### 不在 v0.4.2 范围（资深裁决延期）
- ❌ 预算告警 / 限流 → v0.4.3+
- ❌ 真异步 LLM/DB → v0.4.4
- ❌ Alembic / yoyo 迁移工具（R-S6: messages 列数 24，v0.4.5+ 评估）

## [Unreleased] - v0.4.1.1 hotfix — 笛卡尔积防御 + UX 双 Bug 修复

> v0.4.1 落地后第一个 hotfix。Stage 1-4 协议走完：v0.4.1 Agent 诊断 +
> 资深 Stage 2 + v0.4.0 守护者 Stage 3 + 资深 Stage 4 锁定。
>
> ⚠️ **隐含承诺（必读）**：合入后 7 天内，用户必须为 gitignored
> `bi_agent/services/knot/ohx_catalog.py` 按 example 格式补 `RELATIONS` 列表。
> 否则真实 OHX 业务库的笛卡尔积只在 example 通用电商表上修复，OHX 实表仍可能复发。

### Fixed — Bug 1: 「📌 收藏报表」侧栏跳到管理员导航
- `frontend/src/Shell.jsx:39` 二分逻辑过窄：`{active === 'chat' ? sidebarContent : adminHardcoded}`
  未覆盖 v0.4.1 新增的 `saved-reports` 屏 → fallthrough 到 admin 分支
- 修复：改为 `{!active.startsWith('admin-') ? sidebarContent : adminHardcoded}`
  非 admin 屏（chat / saved-reports / 未来用户屏）一律渲染 sidebarContent prop

### Fixed — Bug 2: 历史消息看不到 ⭐ 收藏按钮
- 根因：API 边界字段命名不一致 — SSE final 事件 emit `sql`（v0.4.0 query.py），
  REST `/api/conversations/{id}/messages` 返回 SQLite 列名 `sql_text`
- 前端 `ResultBlock` 解构 `const { sql, ... } = msg;` → 历史消息 `sql=undefined`
  → v0.4.1 `canPin = !!(sql && Number.isInteger(msg.id))` 永远 false
- 修复（资深 Stage 2 选 backend alias）：`api/conversations.py::get_messages` 在 API 边界
  对每条 message 加 `m["sql"] = m["sql_text"]`；repo 保留 SQLite 列名干净（职责分离）
- 所有 consumer（前端 / 未来 client）自动一致

### Fixed — Bug 3: 多表查询产生笛卡尔积（三层防御）
**根因**（三层全空）：
- `services/knot/sql_planner.py::_AGENT_SYSTEM_TEMPLATE` 6 条规则零 JOIN 约束
- `services/llm_client.py::build_system_prompt` 同样无 JOIN 约束
- `services/knot/ohx_catalog.example.py` 无 PK/FK/relations 元数据
- v0.4.0 eval 80 case 中 JOIN 关键词 0 出现 — 完全无拦截力

**Layer 1 — Catalog RELATIONS 元数据**：
- `ohx_catalog.example.py` +`RELATIONS` 常量 (5 元组：left_t/c, right_t/c, semantics)
  - 含 2 条通用电商占位（user_id 关联 / sta_date 关联）
- `services/knot/catalog.py`：
  - `get_relations()` — R-S3 用 getattr 兜底；老 catalog 无常量返 [] 不抛
  - `get_relations_for_tables(selected)` — R-S4 按需渲染；仅 selected 表涉及的关联
  - `_load_from_files` 5 元组返回；`reload()` 维护模块全局

**Layer 2 — 双 prompt 硬约束**：
- `sql_planner._AGENT_SYSTEM_TEMPLATE` 加「## 多表查询规则（必读 — 防笛卡尔积）」段
- `llm_client.section_safety` 同步加多表规则
- 双路径 schema 段尾部按需注入 `_relations_for_schema(schema_text)` 渲染结果

**Layer 3 — Eval 守护**：
- `cases.example.yaml` 80 → 89（+9 multi_table case + 1 反例 `edge_anti_cartesian_product`）
- `test_eval.py::_check_no_cartesian_join` 守护正则：
  - 多表 SQL（matched ≥ 2）必须含 `\bjoin\b` + `\bon\b`
  - 严禁旧式 `FROM a, b` 句式（识别可选表别名 `FROM users u, logs l`）
- 6 条守护正则纯单测（无 LLM 也跑）：单表 / inner join / left join / 缺 join /
  缺 on / 混合 comma-FROM 高危句式

### Verified
- `pytest tests/ -v`：**157 passed / 90 skipped**（v0.4.1 147 → v0.4.1.1 157，+10 全过）
- eval cases：80 → **89**
- `lint-imports`：6 contracts KEPT, 0 broken（不动 `.importlinter`）
- `ruff check bi_agent/`：All checks passed
- `python -c "from bi_agent.main import app"`：**61 routes 不变**, version=**0.4.1.1**
- `npm run build`：通过；bundle 与 v0.4.1 持平

### 守护者结构性教训（v0.4.0 反思）
v0.4.0 eval 80 case 设计**只按 intent 分层 8 条**，缺"SQL 复杂度"横切维度。
多表关联应是横切维度，不能因 80 条够 intent 准确率门禁就放心。
v0.4.2+ eval 扩量必须加 join 复杂度 / 子查询 / 窗口函数 / CTE 维度。

## [Unreleased] - v0.4.1 报表沉淀（saved_reports + 收藏 + 重跑 + CSV 导出）

> v0.4.0 收官后第一个业务 PATCH。架构底座 6 contracts 全程 KEPT，0 broken。
> Stage 1-4 协议（资深 + Codex Stage 2 + v0.4.0 守护者 Stage 3 + 资深 Stage 4 锁定）
> 7 项修补 + 导出选 A 已并入 docs/plans/v0.4.1-saved-reports.md。

### Added — saved_reports 表 + repo + 服务（去耦合快照）
- **`bi_agent/repositories/schema.sql`** — `CREATE TABLE saved_reports`：
  - 完全去耦合，无硬 FK；上游 conv/message/data_source 删除时本表行不级联
  - 14 列：source_message_id / data_source_id / title / question / sql_text /
    intent / display_hint / pin_note / last_run_at / last_run_rows_json /
    last_run_truncated / last_run_ms / pinned_at + UNIQUE (user_id, source_message_id)
- **`bi_agent/models/saved_report.py`** — `SavedReport` dataclass（叶子，stdlib）
- **`bi_agent/repositories/saved_report_repo.py`** — 薄 SQL helper：
  - `create()` 用 INSERT OR IGNORE，UNIQUE 冲突返 0（service 回查既存）
  - `get_by_unique()` 服务于 R-12 幂等
  - `update_last_run()` 重跑路径用
- **`bi_agent/services/saved_report_service.py`** — 业务编排（不调 LLM）：
  - `create_from_message()`：snapshot intent + sql + rows；R-S5 title sanitize +
    R-S6 老消息 intent fallback 'detail' + R-3 软限制 200 行 + R-12 幂等
  - `run()`：冻结 SQL 重跑（资深 Stage 2 严禁宏替换）；R-S2 优先用 pin 时
    data_source，失效时 fallback get_user_engine + warning banner
  - `get_owned/list/update/delete`：权限校验（owner OR admin），404 防 id 枚举
- **`bi_agent/services/engine_cache.py`** 加 `get_engine_for_source(source_id)`：
  按单个 data_source 取/建 engine，缓存 key=("source", source_id)
  与现有 (uid, group_key) 命名空间隔离

### Added — 6 路由（55 → 61 routes）
- `GET    /api/saved-reports` — list_for_user
- `POST   /api/messages/{id}/pin` — 从 message 创建（R-12 幂等：already_pinned）
- `POST   /api/saved-reports/{id}/run` — 重跑冻结 SQL（R-S2 fallback）
- `PUT    /api/saved-reports/{id}` — 改 title / pin_note
- `DELETE /api/saved-reports/{id}` — 删除
- `GET    /api/saved-reports/{id}/export.csv` — 复用 v0.4.0 export_service
  （xlsx 推 v0.4.2）

### Added — 前端
- **`frontend/src/screens/Chat.jsx`**：
  - ⭐ 收藏按钮（顶部右侧；canPin = sql + integer msg.id + 非 saved_report 内嵌）
  - R-12 幂等 UX：已收藏 → 🌟 不可点
  - R-S4 effectiveHint 三级优先级链（display_hint → intent → inferIntentFromShape）
  - sidebar 加"📌 收藏报表"入口
- **`frontend/src/screens/SavedReports.jsx`** [NEW]：
  - SavedReportsScreen 自包含 AppShell；左 sidebar 列出收藏（intent emoji）
  - DetailView：✏️ 改名 + 🔄 重跑 + 📥 CSV 导出
  - warning banner（R-S2 fallback）/ truncated banner（200 行截断）
  - 折叠区显示原始问题 + 备注 + 冻结 SQL + 资深 Stage 2 提示
- **`frontend/src/App.jsx`**：screen='saved-reports' 路由

### Added — 测试增量 22 条（守护者 R-S3）
- `tests/repositories/test_saved_report_repo.py` (6)：CRUD + UNIQUE 冲突 +
  truncated 持久化 + user 隔离
- `tests/services/test_saved_report_service.py` (5)：snapshot intent +
  R-S6 老消息 fallback + R-3 软限制 + R-12 幂等 + R-S5 title sanitize
- `tests/services/conftest.py` 复用 repositories tmp_db_path
- `tests/api/test_saved_reports.py` (8)：pin owner / R-12 端到端 / 跨 user 404 /
  list 隔离 / run 错误返结构化 dict / 跨 user run 404 / export.csv BOM /
  delete 后 404
- `tests/integration/test_api_smoke.py` (+3)：pin → list / pin → export 端到端 /
  R-S7 删 conversation 不级联（dangling 是预期）+ test_app_has_55_routes →
  test_app_has_61_routes（手册原写 62 算错 1）

### Verified
- `pytest tests/ -v`：**147 passed / 81 skipped**（v0.4.0 125 → v0.4.1 147，+22 全过）
- `lint-imports`：6 contracts KEPT, 0 broken（不动 .importlinter）
- `ruff check bi_agent/`：All checks passed
- `python -c "from bi_agent.main import app"`：**61 routes**，version=0.4.1
- `npm run build`：通过；bundle 1402 kB / gzip 449 kB（+5/+3 KB，<<50 KB 预算）

### 不在 v0.4.1 范围（留 v0.4.x 后续）
- ❌ xlsx 导出 → v0.4.2（避免 openpyxl 引入 + 范围膨胀）
- ❌ 日期占位符 / SQL 宏替换（资深 Stage 2 严禁）→ v0.5.x（如真有需求）
- ❌ 报表共享给其他用户 / 公开链接 → v0.5.x
- ❌ 重新生成 SQL（重新走 Clarifier→SQL Planner）→ v0.5.x
- ❌ 报表订阅 / 邮件推送 / 调度 → 不在 v0.4.x 范围

## [Unreleased] - v0.4.0 Clarifier intent + Layout 分支 + CSV 导出 + eval 扩量

> 4-PATCH 工程化重构收官后第一个业务 PATCH。架构底座 6 contracts 全程 KEPT，
> 进入 v0.4.x 业务迭代期。

### Added — Clarifier 7 类 intent + 前端 Layout 分支
- **`bi_agent/services/knot/orchestrator.py`** — `_CLARIFIER_SYS` 注入意图分类规则
  + 优先级 `detail > retention > rank > compare > trend > distribution > metric`
  + 7 条 few-shot 示例 + 特殊规则（导出 / 代词 / 时间分桶）
- **`VALID_INTENTS`** 元组 + **`INTENT_TO_HINT`** 映射常量：
  metric→metric_card / trend→line / compare→bar / rank→rank_view /
  distribution→pie / retention→retention_matrix / detail→detail_table
- **`DEFAULT_INTENT_FALLBACK="detail"`** — Clarifier 输出缺失或非法时保守不画图
- **`models/agent.py::ClarifierOutput`** 加 `intent: Optional[str]`
- **`models/conversation.py::Message`** 加 `intent: Optional[str]`（老消息为 None）
- **`schema.sql` + `base.py`** — `messages.intent TEXT` 列 + ALTER TABLE 兼容
- **`api/query.py`** — `agent_done(clarifier)` 与 `final` SSE 事件携带 intent；
  `clarification_needed` 也带 intent
- **前端 `Chat.jsx::ResultBlock`** — `effectiveIntent = msg.intent ||
  inferIntentFromShape(rows, cols)`；按 intent 决定 layout 与默认 chart 类型；
  `inferIntentFromShape` 启发式回退给老消息（无 intent 字段）

### Added — `/api/messages/{id}/export.csv` (CSV 导出)
- **`services/export_service.py::rows_to_csv_bytes`** — 内存 BytesIO 模式
  （手册 §4.1）；utf-8-sig BOM 让 Excel 中文直开不乱码；复杂值（dict/list）
  JSON 序列化 ensure_ascii=False
- **`api/exports.py`** — GET 路由；StreamingResponse(BytesIO) +
  `Content-Disposition: attachment; filename*=UTF-8''…`
- **权限**：必须是 conversation 所有者 OR admin；非所有者统一 404 防 message_id 枚举
- **空 rows** → 400；不存在 → 404
- **`repositories/conversation_repo.get_conversation_owner`** + 
  `message_repo.get_message` — 导出权限校验依赖
- **`main.py`** 注册 exports_router；路由总数 54 → 55；app version 0.3.3 → 0.4.0
- **前端 `DetailTable`** — detail intent + msg.id 存在时调用服务端 CSV 导出
  （取代原 client-side toCsv 逻辑）

### Added — eval 扩量 + intent 准确率门禁
- **`tests/eval/cases.example.yaml`** — 17 → 80 条；每类 intent ≥ 8 条 +
  24 条 edge case；新加 `display_hint` / `export_button_visible` 字段
- **edge tags**：ambiguous(4) / security(4) / history_dependent(3) /
  multi_lang(2) / explicit_export(2) / metadata_query(2) / cross_source(2) /
  edge_case(6)
- **`tests/eval/test_intent_accuracy.py`**（新增）：
  - Layer 1（无 LLM, CI 必跑）：mapping 完整性 / yaml intent ↔ display_hint
    一致 / detail intent 与 export_button_visible 一致 / 每类 ≥ 8 条
  - Layer 2（live LLM）：80 条 case 通过 Clarifier，intent 准确率 ≥ 90%
- **`tests/integration/test_api_smoke.py`** — 加 2 条 intent 端到端 smoke
  （metric / detail 各 1）

### Added — GitHub Actions live LLM CI
- **`.github/workflows/eval-live.yml`**：
  - schedule: cron `0 16 * * 1`（周二北京时间 00:00）
  - workflow_dispatch + PR paths（services/knot / llm_client / adapters/llm /
    tests/eval 改动时强制触发）
  - env：OPENROUTER_API_KEY (secret) / EVAL_MODEL (vars，默认 gemini-2.0-flash)

### Added — AsyncLLMAdapter Protocol 占位（v0.4.4 落 impl）
- **`bi_agent/adapters/llm/async_base.py`** — `AsyncLLMAdapter(Protocol)` +
  `async def acomplete(req: LLMRequest) -> LLMResponse`
- **`adapters/llm/__init__.py`** re-export AsyncLLMAdapter
- **3 条单测** — Protocol 接受/拒绝；现有 3 个 sync adapter 均不满足
  （守护 v0.4.4 工作量真实存在）

### Verified
- `pytest tests/ -v`：**125 passed / 81 skipped**（v0.3.3 101 → v0.4.0 125；
  +24 = 8 export_service + 5 exports api + 2 integration intent + 6 mapping/yaml +
  3 async protocol）
- `lint-imports`：6 contracts KEPT, 0 broken（不动 .importlinter）
- `ruff check bi_agent/`：All checks passed
- `python -c "from bi_agent.main import app"`：**55 routes**，version=0.4.0
- `npm run build`：通过；bundle 1396 kB / gzip 446 kB（与 v0.3.3 持平）

### 不在 v0.4.0 范围（留 v0.4.x 后续）
- ❌ xlsx / 复制富文本 / PNG 截图 → v0.4.1
- ❌ 报表沉淀（saved_reports 表 + 收藏 + 重跑）→ v0.4.1
- ❌ 成本可观测拆 agent_kind 维度 → v0.4.2
- ❌ 真异步 LLM/DB 改造 → v0.4.4（本 PATCH 仅占位）
- ❌ Clarifier 升级剩余 3 项（sub_questions / methodology / gap）→ v0.5.x
- ❌ /api/v1/ 版本前缀（T-1）→ v0.5.0

## [Unreleased] - v0.3.3 工程化重构（第 4 刀 / 4 · 收官）— Full Forbidden Mode

> **4-PATCH 工程化重构正式封笔**。Python 后端已成为 Go 重写的"逻辑镜像"。

### Added — `bi_agent/api/` 取代 `bi_agent/routers/`
- `git mv bi_agent/routers/ → bi_agent/api/`（11 个 router + dependencies + schemas）
- `bi_agent/dependencies.py` → `bi_agent/api/deps.py`
- `bi_agent/schemas.py` → `bi_agent/api/schemas.py`
- `bi_agent/routers/` 目录物理删除

### Changed — `.importlinter` Full Forbidden Mode（FIXME-v0.3.3 偿还）
**6 条 contract 全部 KEPT，所有 FIXME 清空：**
1. `layered-architecture` — `api → services → repos|adapters → models`
2. `models-is-leaf` — models 禁 import 任何子包
3. **`core-no-business`**（升级）— core 现在禁止 `models, api, services, repositories, adapters` 全部 5 项
4. **`repos-no-business`**（升级）— repos 禁 `api, services, adapters`
5. `adapters-no-business` — adapters 禁 `api, services, repositories`
6. **`api-is-entrypoint`**（v0.3.3 新增）— 其他层禁止反向 import api

### Added — 守护测试三道防线
- **`tests/test_core_purity.py`**（T-2，3 条）：
  - AST 扫描 `bi_agent/core/*.py` 所有 import，验证无业务层引用
  - 运行时反射扫描模块 `__dict__`，验证不持有业务对象引用
  - 文件清单守护：`bi_agent/core/` 仅可包含 `__init__.py / logging_setup.py / date_context.py`，新增其他文件即失败
- **`tests/integration/test_api_smoke.py`**（13 条端到端集成测试）：
  - 路由总数固化 = 54（防止重构丢失端点）
  - 登录链路：seed admin / 错误密码 / 未知用户
  - JWT 路径：valid / missing / invalid token
  - 会话 CRUD（api → services → repositories）
  - Catalog admin 编辑 + DB 覆盖 → reset 回退
  - few-shots admin CRUD
  - 角色权限：analyst 不可访问 admin 路由
- **TestClient** 使用 tmp SQLite，不依赖 LLM API key / Doris

### Skipped（v0.4.x 范围说明）
- **T-1 `/api/v1/` 版本前缀**：评审指令"顺手检查"，但落地需同步改前端 `frontend/src/api.js` base URL +
  影响 Vite 构建产物里的所有 fetch 路径。本 PATCH 已 BREAKING 较多（routers→api / persistence 多次迁移），
  再加版本前缀会让 admin 部署方更新成本超阈。已记入 v0.4.0 路线图，与 SSE→WebSocket 迁移评估一并做。

### Verified
- `pytest tests/ -v`：**101 passed / 6 skipped**（v0.3.2 85 → v0.3.3 101，新增 16 条：3 core 纯度 + 13 集成）
- `lint-imports`：**6 contracts KEPT, 0 broken**（v0.3.2 5 → v0.3.3 6）
- `ruff check bi_agent/`：All checks passed
- `python -c "from bi_agent.main import app"`：54 routes 启动 OK

### BREAKING（最后一次大规模迁移）
1. `bi_agent.routers.X` → `bi_agent.api.X`（11 个 router 模块）
2. `bi_agent.dependencies` → `bi_agent.api.deps`
3. `bi_agent.schemas` → `bi_agent.api.schemas`

### 4-PATCH 工程化重构总账（v0.3.0 → v0.3.3）
| | 主题 | tests | contracts |
|---|---|---|---|
| v0.3.0 | repos + models + 工程化基线 | 48 | 4 |
| v0.3.1 | services + core 无业务化 | 61 | 4 |
| v0.3.2 | adapters 协议驱动 + errors 树 | 85 | 5 |
| **v0.3.3** | **api 改名 + Full Forbidden Mode** | **101** | **6** |

### 下一阶段
v0.4.x 进入业务迭代期：成本观测（原 v0.2.6）/ Clarifier 升级（原 v0.3.0）/ async LLM /
WebSocket 评估等。**架构底座已稳，KNOT 协议驱动引擎正式点火。** 🔥

## [0.3.2.202605062150] - 2026-05-06 v0.3.2 adapters/ 落地

## [Unreleased] - v0.3.2 工程化重构（第 3 刀 / 4） — adapters/ 落地（协议驱动）

> 行为契约（Protocol）与实现分家；引入第 5 条 import-linter contract。
> KNOT 真正拥有"跨库分析"的灵魂 + 多 LLM provider 的统一抽象。

### Added — `bi_agent/adapters/` 三大子包
**adapters/llm/** — LLM 适配层（Protocol 驱动）
- `base.py` — `LLMAdapter(Protocol)` + `LLMRequest` / `LLMResponse` dataclass + `calculate_cost`
- `anthropic_native.py` — 直连 Anthropic SDK（messages API + ephemeral cache_control）
- `openai_compat.py` — OpenAI-compatible HTTP（覆盖 GPT / Gemini / DeepSeek / Ollama / vLLM 等私有部署）
- `openrouter.py` — OpenRouter 统一路由（OR-specific 行为预留点）
- `factory.py` — `get_adapter(provider) -> LLMAdapter`，case-insensitive；未知 provider fallback openai-compat

**adapters/db/** — 业务库适配层
- `base.py` — `BusinessDBAdapter(Protocol)` + `is_safe_sql()` 共享 SQL guardrail（sqlglot AST，与方言无关）
- `doris.py` — Doris/MySQL 实现（v0.3.1 之前的 `core/db_connector.py` git mv 而来）

**adapters/notification/** — 通知适配层（v0.3.2 锁形状，v0.4.x 落 impl）
- `base.py` — `NotificationAdapter(Protocol)` + `Notification` dataclass（title/body/level/target/metadata）
- `lark.py` — `LarkAdapter` stub，`send()` 抛 `NotImplementedError`（业务接入飞书时按 Protocol 实现 send）

### Changed — `services/llm_client.py` 瘦身（删 anthropic / openai SDK 直连）
原 `_invoke_anthropic` + `_invoke_openai_compatible` 两个 67 行函数 → 23 行 `_invoke_via_adapter`：
```python
from bi_agent.adapters.llm import LLMRequest, get_adapter
resp = get_adapter(provider).complete(LLMRequest(...))
```
service 层不再 import LLM SDK，全部下沉到 adapters/llm/*。

### Moved — engine_cache 归位
- `bi_agent/engine_cache.py` → `bi_agent/services/engine_cache.py`（**不是 adapters/db**）
  - 原因：engine_cache 需要 `repositories.data_source_repo` 取业务数据源；adapter 是叶子节点不得依赖 repos
  - engine_cache 本质是 service-level 编排（按 user 选择 doris adapter 实例 + TTL 缓存）
  - `from .engine_cache` → `from bi_agent.services.engine_cache`（路由中已重写）

### Changed — `.importlinter` 第 5 条 contract（FIXME-v0.3.2 偿还）
```ini
[importlinter:contract:repos-no-business]
forbidden_modules = bi_agent.routers, bi_agent.services, bi_agent.adapters  # ← 加上 adapters

[importlinter:contract:adapters-no-business]   # ← 第 5 条新增
forbidden_modules = bi_agent.services, bi_agent.routers, bi_agent.repositories
```

### Added — `tests/adapters/` 21 条 happy-path
- `test_llm_factory.py`（9 条）— 4 provider 路由 + case-insensitive + cost 计算 + Protocol runtime check
- `test_db_base.py`（9 条）— is_safe_sql 7 类 SQL（SELECT/SHOW 通过 / DROP/DELETE/INSERT/UPDATE/stacked 拒绝）+ Protocol verify
- `test_notification.py`（3 条）— Lark stub + Protocol fit + Notification dataclass

### Verified
- `pytest tests/ -v`：**82 passed / 6 skipped**（v0.3.1 61 → v0.3.2 82，新增 21 条 adapter 单测）
- `lint-imports`：**5 contracts KEPT, 0 broken**（v0.3.1 4 → v0.3.2 5）
- `ruff check bi_agent/`：All checks passed
- 54 routes 启动正常

### BREAKING（仅影响部署方/合作伙伴本地脚本）
1. `bi_agent.core.db_connector` → `bi_agent.adapters.db.doris`
2. `bi_agent.engine_cache` → `bi_agent.services.engine_cache`（注意：不是 adapters）
3. 调用 LLM 的代码若直接 import anthropic/openai SDK → 改用 `from bi_agent.adapters.llm import LLMRequest, get_adapter`

### 资深寄语对齐
> "本 PATCH 的三个首要任务" 全部完成：
> ✅ 定义基类（adapters/db/base.py + adapters/llm/base.py + adapters/notification/base.py）
> ✅ 重构 LLMClient（anthropic_native + openai_compat + openrouter + factory）
> ✅ 重构 DBConnector（doris.py + Protocol 锁定 BusinessDBAdapter 行为）

## [0.3.1.202605062126] - 2026-05-06 v0.3.1 services/ 落地

## [Unreleased] - v0.3.1 工程化重构（第 2 刀 / 4） — services/ 落地

> 协议驱动重构 · "core 完全无业务化" 第一步 · 删 v0.3.0 facade shim 偿还技术债。

### Changed — 9 个文件领域重组（git mv 保留 blame 历史）
- `bi_agent/core/auth_utils.py`        → `bi_agent/services/auth_service.py`
- `bi_agent/core/llm_client.py`        → `bi_agent/services/llm_client.py`
- `bi_agent/core/prompts.py`           → `bi_agent/services/prompt_service.py`
- `bi_agent/core/schema_filter.py`     → `bi_agent/services/schema_filter.py`
- `bi_agent/core/rag_retriever.py`     → `bi_agent/services/rag_retriever.py`
- `bi_agent/core/doc_rag.py`           → `bi_agent/services/rag_service.py`
- `bi_agent/core/multi_agent.py`       → `bi_agent/services/knot/orchestrator.py`
- `bi_agent/core/sql_agent.py`         → `bi_agent/services/knot/sql_planner.py`
- `bi_agent/core/catalog_loader.py`    → `bi_agent/services/knot/catalog.py`
- 数据文件同步迁移：`few_shots.example.yaml` → `services/`，`ohx_catalog.example.py` → `services/knot/`

### Changed — `core/` 真正无业务化
v0.3.1 后 `bi_agent/core/` 仅剩横切工具：`date_context.py` + `logging_setup.py`。
所有依赖 `bi_agent.repositories` 的代码已搬到 `services/`，`core` 不再触碰业务层。

### Removed — facade re-export（FIXME-v0.3.1 偿还）
- `bi_agent/repositories/__init__.py` 删除 30+ 函数的 re-export 块；现仅暴露 `init_db / get_conn`
- 所有 `from bi_agent import repositories as persistence` 别名已清除
- routers 改为模块化访问：`from bi_agent.repositories.user_repo import get_user_by_id` 等
- `repositories/base.py` seed admin 用 bcrypt 直接哈希，避免 repos→services 反向依赖

### Changed — `.importlinter` 升级（FIXME-v0.3.1 收紧）
```
[importlinter:contract:repos-no-business]
forbidden_modules = bi_agent.routers, bi_agent.services    # ← v0.3.1 加上 services
# FIXME-v0.3.2: 加上 bi_agent.adapters
```

### Added — services tests
- `tests/services/test_auth_service.py` — 哈希 / 校验 / Unicode 密码
- `tests/services/test_knot_catalog.py` — DB → real → example fallback chain
- `tests/services/test_schema_filter.py` — parse_schema_tables / 元数据问题 / 基本过滤

### BREAKING（仅影响部署方 / 合作伙伴的本地脚本）
1. `bi_agent.core.{auth_utils, llm_client, prompts, schema_filter, rag_retriever, doc_rag, multi_agent, sql_agent, catalog_loader}` 全部不可用 → 改 `bi_agent.services.X` / `bi_agent.services.knot.X`
2. **业务私有文件路径变更**（资深评审组已 APPROVED）：
   - `bi_agent/core/ohx_catalog.py`     → `bi_agent/services/knot/ohx_catalog.py`
   - `bi_agent/core/few_shots.yaml`     → `bi_agent/services/few_shots.yaml`
   - 已在 `.gitignore` 同步
3. `from bi_agent import repositories as persistence` 别名删除 → 改 `from bi_agent.repositories.X_repo import ...`

### Verified
- `pytest tests/ -v`：**61 passed / 6 skipped**（v0.3.0 48 → v0.3.1 61，新增 13 条 services 单测）
- `lint-imports`：4 contracts KEPT, 0 broken（含 v0.3.1 升级的 repos-no-business 收紧 contract）
- `python -c "from bi_agent.main import app"`：54 routes 启动正常

## [0.3.0.202605061643] - 2026-05-06 v0.3.0 工程化重构第 1 刀

> 协议驱动重构 · "数据形状 vs 逻辑行为" 物理隔离 · 为 v1.0 Go 重写铺路。
> 本 PATCH = 4-PATCH 渐进式重构计划的第 1 刀。

### Added — 工程化基线（一次性）
- **`pyproject.toml` + `setup.py`**：`pip install -e ".[dev]"` 让 `bi_agent` 成为标准 Python 包，**根治 sys.path hack**
- **`.importlinter`**：4 层架构 contract（routers → services → repositories | adapters → models），CI 强制不可绕过
  - 当前 4 条 contract 全部 KEPT：layered / models-is-leaf / core-no-models / repositories-no-business
  - FIXME 标注 contract 升级点：v0.3.1（services 落地）/ v0.3.2（adapters 落地）/ v0.3.3（routers→api 改名 + core 完全瘦身）
- **`.pre-commit-config.yaml`**：ruff + ruff-format + import-linter
- **`.github/workflows/ci.yml`**：lint + import-linter + pytest + boot smoke 全跑
- **`requirements-dev.txt`**：ruff / pytest / import-linter / pre-commit
- **`scripts/refactor/v0.3.0_migration.sh` + `_rollback.sh`**：审计证据，永久仓库保留

### Added — `bi_agent/models/` 顶级包（10 领域叶子文件）
- **纯数据形状层**，仅 stdlib + dataclass：`user / conversation / data_source / agent / llm / catalog / few_shot / prompt / knowledge / setting`
- 1:1 对应 Go 重写时的 `internal/domain/*.go` struct
- import-linter 强制叶子：禁止 import bi_agent 内任何子包

### Added — `bi_agent/config/` 子包
- 集中加载 `.env`，导出 `settings: Settings` 单例 + 模块级常量（向后兼容 `from bi_agent.config import X`）
- 业务代码不得直接 `os.getenv`

### Added — `bi_agent/repositories/` 9 模块
- 拆分原 `persistence.py` 758 行 → `user_repo / conversation_repo / message_repo / data_source_repo / settings_repo / few_shot_repo / prompt_repo / knowledge_repo / upload_repo`
- `base.py` 提供 `get_conn() / init_db()`；`schema.sql` 集中所有 `CREATE TABLE`
- 向后兼容 facade：`bi_agent/repositories/__init__.py` re-export 全部 30+ 函数（FIXME-v0.3.1 删除）

### Changed — 全局裸名 import 重写（~30 文件）
- `import persistence` → `from bi_agent.repositories.X_repo import ...`
- `from config import X` → `from bi_agent.config import X`
- `import auth_utils / llm_client / multi_agent / sql_agent / catalog_loader / db_connector / doc_rag / prompts / schema_filter / rag_retriever / date_context / logging_setup`
  → `from bi_agent.core.X import ...`
- `main.py` 删除 `sys.path.insert(0, .../core)`

### Removed
- `bi_agent/core/persistence.py`（拆完即删）
- `bi_agent/core/config.py`（拆完即删，所有引用走 `bi_agent.config`）

### BREAKING
- 部署方 / 合作伙伴的外部脚本若 `import persistence`、`from config import X` 等裸名调用 → **必须改写**为 `from bi_agent.X.Y import Z` 绝对路径
- `pip install -e ".[dev]"` 是新的安装入口（替代 `pip install -r requirements.txt`）
- `bi_agent/core/persistence.py` 与 `config.py` 物理删除，老导入路径不可用

### Verified
- `pytest tests/repositories tests/models -v`：47 passed（新增 30+ 条 happy-path unit + models 叶子约束 verify）
- `pytest tests/ -v`：48 passed / 6 skipped（含 v0.2.5 eval 结构 check）
- `lint-imports`：4 contracts KEPT, 0 broken
- `python -c "from bi_agent.main import app"`：54 routes，启动正常

### 资深 review 重点
1. `.importlinter` 中 3 处 `# FIXME-v0.3.X` 标注是否合理（服务/适配器 contract 分阶段升级）
2. `bi_agent/repositories/__init__.py` 的 facade re-export 是否能在 v0.3.1 顺利删除
3. `bi_agent/core/auth_utils.py` 当前 import `bi_agent.repositories.user_repo` —— v0.3.1 必须搬到 services/auth_service 才能闭合 contract

## [Unreleased] - v0.2.5 业务目录可视化编辑

### Added
- **`/api/admin/catalog` 三件套**（GET/PUT/POST reset）：admin 后台维护表目录 / 业务词典 / 业务规则
  - 存储：`app_settings` 三键 `catalog.tables` / `catalog.lexicon` / `catalog.business_rules`
  - 粒度：每键独立覆盖；某键 DB 为空 → 该键继续走文件 fallback；点"恢复默认"清空 DB 覆盖
- **前端「业务目录」tab**（侧边栏第 7 项）：3 块独立 textarea + 各自保存按钮 + DB 覆盖标记 + 恢复默认；JSON 校验前端兜底
- **`catalog_loader.reload()`**：管理面保存后即时热更，无需重启进程；调用方（schema_filter / sql_agent / multi_agent）改为动态 `_cl.X` 读取，admin 改完下一次查询立刻生效
- **加载优先级链**（DB → 真实 `ohx_catalog.py` → `ohx_catalog.example.py`）正式形成；非默认朋友测试无需改 .py，只在 admin 编辑即可

### Changed
- `schema_filter._LEX/_OHX_TABLES` 等模块级快照 → 函数 `_lex()/_ohx_tables()/_ohx_lookup()/_ohx_by_basename()`
- `sql_agent._OHX_RULES` / `multi_agent._OHX_RULES` → `_business_rules()` 函数
- `bi_agent/main.py` 注册 `catalog_router`

### Verified
- `pytest tests/eval -v`：1 passed / 6 skipped（example fallback 路径）
- 热更冒烟：example → DB override → reload → reset → example，三态切换正确
- `npm run build` 通过；新 tab 在管理员侧边栏正确出现

## [0.2.4.202604301802] - 2026-04-30 v0.2.4 待办收尾 + 隐私脱敏

### Added — v0.2.4 待办收尾 + 隐私脱敏

**待办收尾（CLAUDE.md 技术债表低优项）：**
- **uploads.db → bi_agent.db 合并**：`engine_cache._upload_engine` 改指向主库；`persistence._migrate_uploads_db_once()` 一次性把老 `uploads.db` 的所有用户上传表 ATTACH 进主库（同名表跳过保留主库现有数据），完成后老文件改名 `.db.merged` 保证幂等
- **删除 `bi_agent/routers/user.py`**：`/api/user/config` + `/api/user/agent-models` 自 v0.2.1 起已无前端调用，本版彻底清掉；连带删除 `schemas.py::UpdateUserConfigRequest`
- **清理 v0.2.1 批次2 一次性迁移标记**：`_v021b2_user_keys_cleared` 已对所有部署完成迁移，移除 `init_db()` 中的兜底块
- **`UPLOADS_DB` 常量**：从 `dependencies.py` / `main.py` 移除（合并后无独立文件）

**隐私脱敏（参考 .env / .env.example 模式）：**
- **`bi_agent/core/ohx_catalog.py`**：移入 .gitignore，仓库提交 `.example.py` 通用电商模板（demo_dwd / demo_ads）
- **`bi_agent/core/few_shots.yaml`**：移入 .gitignore，仓库提交 `.example.yaml`
- **`tests/eval/cases.yaml`** + **`tests/eval/fake_schema.txt`**：同上，提交 `.example` 版本
- **`bi_agent/core/catalog_loader.py`**（新增）：优先加载真实 `ohx_catalog`，缺失时通过 `importlib.util` 回退 `.example`；`schema_filter` / `multi_agent` / `sql_agent` 改走 catalog_loader
- **`llm_client._load_few_shots()`** 与 **`tests/eval/conftest.py`**：扩展为「real → example」双路径回退

### Added — OHX 真实 schema 接入（4 任务批次）
- **`bi_agent/core/ohx_catalog.py`**：18 张 OHX 表（ohx_dwd × 8 + ohx_ads × 10）目录 + LEXICON 业务词典 + BUSINESS_RULES 规则常量
  - 时区/业务日 14:00 切日 / 真实用户范围 / 默认 USDT / 表分层（聚合 vs 明细 vs 余额）一站式锚定
- **schema_filter v2**：从单纯 BM25 升级为「BM25 + 词典命中加分（+12/+8/+5）+ 主题重合（+3）+ 高优先级强制纳入」，`SCHEMA_FILTER_MAX_TABLES` 25，单次 prompt 上限 12 表
  - 修复回归：「昨天充值 Top 10 用户」类问题不再把 `dwd_user_deposit` 过滤掉
- **eval cases 扩到 31 条**（16 → 31）：分组覆盖 运营日报指标 / 趋势 / 周月报 / 用户名细 / 活动场景（业务日 14:00 + 真实用户范围）/ 邀请代理 / 平台余额 / 套利·折扣购·金鹰宝·结构化 / 做市账号 / 价格 / 安全回归 / 多轮代词
- **few_shots.yaml 重写为 30 条 OHX 真实示例**：替换原通用 orders/users 例子；每条都符合「业务日窗口 + 真实用户 + USDT 默认」三要素
- **`tests/eval/conftest.py`**：fake_schema 改用 OHX 18 表 markdown，与 prompt/词典/few-shot 完全对齐

### Changed — 3 Agent prompt 注入 OHX 业务规则
- Clarifier / SQL Planner / Presenter 三处 system prompt 通过 `{business_rules}` 占位符引入 `ohx_catalog.BUSINESS_RULES`
- Clarifier 加业务规则消歧段：业务日定义 / 测试号排除 / USDT 默认 / 周月报关键词保留
- SQL Planner 规则增加"严格遵守上方业务规则"显式约束

### Verified
- `pytest tests/eval -v`：1 passed / 31 skipped（结构 check 通过；live LLM 待跑）
- schema_filter smoke：「昨天充值 Top 10 用户」选表包含 `dwd_user_deposit` ✅
- multi_agent / sql_agent 模块导入 OHX_RULES 正常

## [0.2.3.202604301140] - 2026-04-30 v0.2.3 回答质量与命中率

### Added
- **`bi_agent/core/date_context.py`**：统一日期口径上下文
  - `today_iso()` / `date_context_block()`，时区显式 `Asia/Shanghai`（fallback `date.today()`）
  - 枚举 今天 / 昨天 / 前天 / 最近7天 / 最近30天 / 本周 / 上周 / 本月 / 上月 → 绝对日期，避免 LLM 把"昨天"映射到训练截止时间
- **跨连接组 SQL 检测**：`MultiSourceEngine.cross_group_dbs()` 解析 SQL 中所有 `db.tbl` 引用，跨组时 `_MultiConn.execute` 抛出明确 `RuntimeError`（"跨连接组查询不支持：本次路由到组 X，但 SQL 还引用了 Y"），不再让 MySQL 回 "Access denied" 误导 LLM 报权限错
- **多组 schema 顶部说明**：列出"组 → 库归属"映射 + "每条 SQL 只能引用同一组内的库"约束
- **eval cases 扩到 16 条**（5 → 16）：覆盖
  - 日期口径：today / last_7days / this_week / last_month
  - 聚合：avg_order_value / paid_user_count / refund_rate
  - 状态过滤：unpaid_pending_orders
  - 趋势：dau_7d_trend
  - 写操作幻觉回归：用户措辞含"删除"时 SQL 仍只读（`readonly_under_destructive_phrasing`）

### Changed
- **Clarifier / SQL Agent / Presenter / build_system_prompt 四处 prompt** 全部从单行 `今日：YYYY-MM-DD` 升级为 `date_context_block()` 完整枚举块
- **Presenter prompt 加幻觉禁令**：
  - 禁止臆造权限错误（输入无"执行失败/Access denied/permission denied"字样时不准说"没有权限"）
  - 空结果集只能解释为数据为零 / 时间窗口外 / 口径过严，不归因到权限
  - 不引用未在结果中出现的数字与字段
  - 不替用户切换日期口径

### Verified
- `pytest tests/eval -v`：1 passed / 15 skipped（结构 check 通过；live LLM 因无 key 跳过）
- SQL guardrail 11 条 smoke 全 pass（SELECT/SHOW pass；DROP/DELETE/UPDATE/INSERT/TRUNCATE/GRANT/CREATE/stacked 全拒）
- MultiSourceEngine 跨组检测 5 条单测全 pass（无 db.tbl / 单组 / 同组多库 / 跨组 / 未知 db）
- TestClient 启动冒烟：`/healthz` 200，`/api/auth/me` 401



### Added
- **SQL 只读 guardrail**（双层）
  - Layer 1: sqlglot AST 解析替换原正则黑名单；单语句 + 只读根节点 + AST 内零写/DDL/Command 节点；stacked query 拒绝。18 条 smoke test 全 pass
  - Layer 2: engine 构建后探测 SHOW GRANTS，writable 默认 warn-only；`STRICT_READONLY_GRANTS=1` 改为强制拒绝
- **结构化日志**（loguru + request_id）
  - `bi_agent/core/logging_setup.py`：stderr 彩色 + 文件 rotate（每天 0 点切，保留 7 天，写到 `data/logs/`）
  - HTTP middleware 给每个请求分配 12 位 request_id；`X-Request-ID` 透传 + 回写
  - clarifier / sql_planner / presenter 链路各打 1 行；grep request_id 即可串起完整 agent 链
- **Eval runner 框架**
  - `tests/eval/cases.yaml`：5 条覆盖 metric/trend/compare/rank/distribution
  - `tests/eval/test_eval.py`：parametrize 跑 generate_sql，断言 must_tables / must_keywords / forbid_keywords
  - 无 `OPENROUTER_API_KEY` 时整组 skip；额外保留结构校验
- **scripts/profile_pyspy.sh**：attach 运行中进程跑 top / 抓 60s 火焰图 / dump 栈

### Changed
- **3-Agent 流式管线**（砍 Validator）：Presenter 内联异常检查，输出 `confidence: high|medium|low` 字段；前端 medium 黄底、low 红底徽标；retry-on-low-confidence 逻辑随 Validator 一起删除
- **并发能力**：startup 把 anyio 默认线程池从 40 提到 64（`ANYIO_TOKENS` 可调），缓解 LLM 同步 SDK 阻塞
- CLAUDE.md 技术债表更新：标注真正的 async LLM 留到下个 MINOR；结构化日志已落地

### Removed
- `validator` agent 全链路代码（multi_agent / query router / schemas / admin&user 路由 / prompts router / 模板 / seed / 前端 Admin&Chat）

### Dependencies
- `sqlglot>=25.0.0`、`loguru>=0.7.2`

### Verified
- `pytest tests/eval -v` 1 passed / 5 skipped（结构 check 通过，LLM live skip 因无 key）
- `_is_safe_sql` 18 条 smoke 用例全 pass：DROP/INSERT/UPDATE/DELETE/TRUNCATE/GRANT/CALL/CREATE/SET/USE/stacked query 全拒，SELECT/CTE/SHOW/DESCRIBE 全过
- TestClient GET /healthz 200, /api/auth/me 401，request_id 中间件日志正常输出

## [0.2.1.202604270250] - 2026-04-27 查询页瘦身

### Removed
- 聊天侧栏「表结构」tab + `SchemaPanel`/`useDebounce`/`/api/db/schema` 拉取（运营人员不需要直接接触库表，schema 由 sql_planner 在后端使用）
- 输入框「多Agent」开关：默认走 4-Agent 流式管线；非流式 `/query` 分支 + `useAgent` 状态/props 全删

### Changed
- 侧栏简化为单一历史列表（无 tab 切换）
- `AgentThinkingPanel` 仅在有事件时渲染

## [0.2.1.202604270230] - 2026-04-27 v0.2 收尾

### Changed
- CLAUDE.md：技术债表移除「前端 babel.min.js 3MB 首屏慢」（v0.2.0 Vite 构建已闭环）；新增低优条目记录 `bi_agent/routers/user.py` 待清理
- CLAUDE.md：`bi_agent/routers/` 列表对齐当前 11 个 router；`bi_agent/static/` 注释更新为 Vite 产物

### Removed
- 删除前端死代码 `frontend/src/screens/UserConfig.jsx`（v0.2.1 批次2 起 admin 重定向至 `/admin-models`、analyst 无入口，此屏不再被路由命中）；同步移除 App.jsx 的无效 import

### Verified
- `npm run build` 通过；产物 1395 KB / gzip 446 KB，与移除前一致（dead-code，bundle 未变）
- 历史 [Known issues] 全部闭环：clarifier 字段盲区 / schema 跨库截断 / 跨连接多源 / analyst 404 / 未来日期误判 / 多轮代词 6 项均已 Fixed

## [0.2.1.202604270215] - 2026-04-27 批次5（多轮上下文）

### Fixed
- 多轮代词无法关联：history 传给 clarifier 时只有 Q 文本，丢掉 SQL/结果，导致"这些用户"无法回指上一轮口径；现在 history 渲染为 `Q + SQL + 前 2 行结果`
- Clarifier prompt 增加强制代词解析规则：遇到「这些/上述/刚才的/他们/那批」必直接 is_clear=true，禁止以"聚合表无明细/是否存在 xx 表"为由追问（属 sql_planner 责任）；附正确示例

### Verified
- Q1 "2026-04-25 注册用户数" → 8 人（ads_operation_report_daily 聚合）
- Q2 "把这些用户的ID列一下" → clarifier 一次明确 → sql_planner 自动从 ads 切到 ohx_dwd.dwd_user_reg → 返回 8 个 user_id（与 Q1 数值对应）

## [0.2.1.202604270145] - 2026-04-27 批次4（日期感知 + 业务化 prompt seed）

### Fixed
- 未来日期误判：clarifier / validator 因 LLM 训练截止时间把 ≤ 今日的日期判为"未来"，触发无谓重试（42s→11s）。4 个 agent prompt 全部注入 `今日：YYYY-MM-DD`（系统时间为权威）；llm_client.build_system_prompt 同步注入

### Added
- `prompts.get_prompt` 支持 `{__default__}` 占位符 → admin 可在 DB 中写"默认 + 业务追加"而不必抄全文
- `scripts/seed_v021_b3.py` 一次性 seed：6 条 few-shot（metric/trend/compare/rank/distribution/retention 6 类型覆盖）+ 4 个 agent 的业务追加约束（时间口径、字段映射、SQL 风格、洞察文风）

### Verified（端到端 OpenRouter 实测）
- "2026年4月25日注册用户数是多少" → clarifier 一次明确 / sql_planner 1 步 / validator high / presenter 8 人 + 2 条 followup，11.9s, $0.0079

## [0.2.1.202604262315] - 2026-04-26 批次3（遗留收尾）

### Fixed
- analyst 提问 404：登录/登出未清 `cb_conv`，跨账号继承陈旧 conv_id 导致 POST `/api/conversations/{id}/query` 404；登录与登出均清掉 `cb_conv`，并在 `loadConvs` 校验 activeConvId 不在列表时自动重置；首次发问无 conv 时直接用新建返回的 id 发送（不再依赖 setState 异步）
- Clarifier 字段盲区：原来只看表名清单 25 张，把"昨天注册用户数"这种明确问题误判为需澄清；改为把完整 schema（表 / 字段 / 注释）截前 6000 字喂给 clarifier，prompt 提示"字段注释能对应概念时不要追问"
- Schema 截断跨库失衡：`get_schema` 改为按 DB 平均配额抽样，每个库都至少进入 schema，避免后置库（ohx_dwd）一张表都进不来
- 跨连接多源 schema 合并：用户跨 `(host,port,user)` 多组 datasource 时，新增 `MultiSourceEngine` 派发引擎；`get_schema` 按组分别抓取并以 "## 连接组 {key}" 头部串接；`execute_query` 在 `_MultiConn.execute` 时按 SQL 中首个 `db.tbl` 前缀路由到对应组的 engine

### Changed
- `engine_cache._engine_cache` 多组场景缓存 key 改为 `(uid, "multi:"+sorted_keys)`；`SCHEMA_FILTER_MAX_TABLES` 在多组时按组均分配额（最低 4）

## [0.2.1.202604262115] - 2026-04-26 批次2

### Added
- B2 few-shot 可视化：`few_shots` 表 + admin `/api/few-shots` CRUD + xlsx 批量导入；DB 为空时自动回退 `few_shots.yaml`
- B2 Prompt 模板：`prompt_templates` 表 + admin `/api/prompts` CRUD + xlsx 批量导入；4 个 agent（clarifier / sql_planner / validator / presenter）可独立覆盖 system prompt，留空使用内置默认
- B2 模板下载：`/api/templates/{few_shots|prompts|knowledge}` 提供 xlsx / txt 下载
- B3 admin API Key 集中管理：`/api/admin/api-keys`（OpenRouter + Embedding）；存 `app_settings` 表
- B3 admin 4-Agent 模型分配 UI（复用已有 `/api/admin/agent-models`）
- 前端 Admin 新增 Few-shot / Prompt 两个 tab；模型 tab 顶部新增 API Key + 4-Agent 模型分配两块卡片
- `bi_agent/core/prompts.py`：通用 prompt 加载器（DB 优先 / 默认回退 / 安全占位符替换）

### Changed
- API Key 与 4-agent 模型配置归口管理员；用户不再有任何 key 输入入口
- `multi_agent._resolve` / `sql_agent.run_sql_agent` / `llm_client._invoke_*` / `query.py` / `knowledge.py` 改为优先读 `app_settings.openrouter_api_key` / `embedding_api_key`
- `query.py` agent 模型配置从 per-user (`get_user_agent_model_config`) 切换到 admin 级 (`get_agent_model_config`)
- `frontend/src/Shell.jsx` 移除「个人」分区的 API & 模型入口；admin-models 改名为「API & 模型」
- `frontend/src/App.jsx` user-config / settings 路由对 admin 重定向到 admin-models 面板

### Migration（一次性）
- 清空 `users.openrouter_api_key` / `embedding_api_key` / `agent_model_config`（写入 `app_settings._v021b2_user_keys_cleared` 标记防重复）

### Known issues（沿用上一段）
- Clarifier 字段盲区 / Schema 截断跨库失衡 / 跨连接多源 schema 合并 / analyst 提问 404（待下一轮）

## [0.2.1] - 2026-04-26

### Changed
- 角色精简：移除 `viewer`，仅保留 `admin` / `analyst`；analyst 无任何设置入口（齿轮 / `/settings` 兜底重定向）
- 模型库扩充至 8 类厂商：Anthropic / OpenAI / Google / DeepSeek / Qwen / 智谱 GLM / MiniMax（OpenRouter 通道），保留原生直连模型
- `_is_openrouter_model()` 改为按 `provider` 字段判定，统一 `sql_agent` / `multi_agent` / `llm_client` 三处的 OR 路由

### Fixed
- 多数据源 `(host, port, user)` 同组合并 db_database：解决 `engine_cache` 用 `sources[0]` 账号访问其他 source 库的"无权限"问题；缓存 key 从 `uid` 改为 `(uid, group_key)`，避免多组互相覆盖
- 401 死循环：`api.js` 401 处理仅清 `cb_token` 但不清 `cb_user`，导致重载后仍渲染 ChatScreen → 再 401 → 再 reload。补全清理 `cb_user` / `cb_screen` / `cb_conv` / `cb_loading`
- Vite `/assets/*` 静态资源被 SPA catch-all 兜回 index.html 的白屏：补 `/assets` mount + SPA 路由先判 `is_file()`

### Known issues（下一轮）
- Clarifier 仅看表名清单、看不到字段注释，对明确问题（如"昨天注册用户数"）会误判需澄清
- `SCHEMA_FILTER_MAX_TABLES=10` + 多库合并后截断：后置库（如 ohx_dwd）一张表都进不来
- 跨 `(host, port, user)` 多源场景仅 warning + 取第一组（schema 按源分组 + 按表选 engine 待下一轮）
- analyst 角色提问报 `{"detail":"Not Found"}` 404（待定位：可能 conversation 未创建即发送 / analyst 未关联数据源 / 隐性 admin-only 路由）

## [0.1.1] - 2026-04-26

### Added
- Git 初始化，上传 GitHub（私有仓库）
- README.md、CLAUDE.md、CHANGELOG.md
- Dockerfile（运维容器化部署）
- 项目结构重构：main.py 拆分为 8 个 router 模块
- dependencies.py（JWT + auth 依赖）、schemas.py（Pydantic 模型）、engine_cache.py（DB 引擎缓存）

### Architecture (Python 基线版本)
- 35 个 API 端点，8 个 router 模块
- 多 LLM 路由：Claude、GPT-4o、Gemini、DeepSeek、OpenRouter
- ReAct SQL Agent + 4 阶段 orchestration（Clarifier / SQL Planner / Validator / Presenter）
- 文档 RAG（BM25 + embedding cosine similarity）
- React SPA 前端（浏览器端 Babel，无构建步骤）

### Roadmap
- v0.2.0：Go 后端重写 + Vite 前端构建（团队主力语言，解决并发瓶颈）
