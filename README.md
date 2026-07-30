# KNOT

[![CI](https://github.com/kkleonnnn/knot/actions/workflows/ci.yml/badge.svg)](https://github.com/kkleonnnn/knot/actions/workflows/ci.yml)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

公司内部用的 AI 取数助手：自然语言 → SQL → 图表 + 洞察。

> ⚠️ **内测阶段**（MAJOR=0 · 团队内部工具，日活 5-20 人）。无 uptime SLA 承诺（best-effort，详 [docs/SLA.md](docs/SLA.md)）；公开对外部署前请落实 HTTPS / 监控 / 防暴力破解（见 [DEPLOY.md](DEPLOY.md) + [SECURITY.md](SECURITY.md)）。

## Demo

https://github.com/user-attachments/assets/008c1ba2-aea8-4f71-9f2a-e3c5c17e3ea3

> 40 秒产品演示 · v0.6 · 1920×1080 · 3.3 MB · 由 [HyperFrames](https://hyperframes.heygen.com) 渲染

> **当前版本** v0.9.6 · **file catalog owner-gate（隔离栈第六刀 · 数据面）**：部署方写的业务目录（真实库表名 / 词典 / 业务口径）此前是**进程级、与租户无关**的 —— **每一家公司**的目录里都会被注入它。本刀让它**只归起源租户**（多租户之前就存在的那一家 = 部署方本人），其余租户拿到的是**完整的空**（而不是「清了表但留着口径」那种半空 —— 业务口径只在库为空时才回落到文件层，半清等于继续泄漏）。⚠️ 门装在**能力被行使的那一行**（`executor.execute` 内 —— 唯一发请求且唯一读进程凭据的函数），不是决策点：`run_http_step` 是公开函数、自带 spec、不重新求路由，门只放决策点时任何新接入方都能绕过。配一道软降级让查询**优雅落 SQL 而不是流中途报错**，并**必须记日志**（否则就是「HTTP 悄悄走了 SQL」那种旧病）。⚠️ **本片只闭合了三项里的第一项**：per-tenant 凭据与出网白名单**仍是放开第二家公司前的硬门槛**，现在这道门是**临时代偿、不是修复** —— 配了一条**行为级** CI，谁去放开硬门槛就会撞上一条点名这道门的红测。单租户部署行为不变。<br>**上版** v0.9.5 · **鉴权拆分 platform / tenant admin（隔离栈第五刀 · 权限层）**：`admin` 从此明确是「**哪一家公司的** admin」—— 90 处依赖层守护改名 `require_tenant_admin`（22 文件）。平台面（跨租户视角）**不是**租户里的一个角色：它走 out-of-band 共享密钥的**平行认证路径**，因为 `get_current_user` 结构性要求 `tid`（签不出无 tid 的 token）—— 硬塞进去等于「每个平台请求先假装在某家公司里」。平台密钥与租户 JWT **语法域不相交**（`kpa_` 前缀 + **禁含 `.`**，而 JWT 恒含 2 个点）⇒ 「误把一枚有效用户 JWT 配成平台密钥」在语法上不可能。策略分类新增互斥的 `PLATFORM_SECRET` 类，**同时挂两域守护的路由会让快照生成器直接失败**（拒绝分类，而不是给它一个标签被祝福）。并删掉 `/api/admin/catalog` 一个**死字段** —— 它把**部署方真实业务库表 + 业务口径**（部署级 `_local_catalog`，绕过 per-tenant 槽）吐给**任何租户** admin，而前端零处渲染。⚠️ 这是**部分**减暴露：`current` 仍含 file 层，且「让它不含」会让 HTTP 查询静默落 SQL（v0.7.29b），故 per-tenant file catalog 仍在 R-T-GATE 清单。⚠️ 平台侧**无身份、无吊销、无审计落点**（刻意零平台写操作）。单租户 byte-equal，R-T-GATE 仍挡第二租户。<br>**更早** v0.9.4 · **JWT 带公司编号 + 请求级租户解析（隔离栈第四刀）**：每请求「读哪家公司的库」从**假设全站只有一家 active 租户**（`resolve_single_tenant`）改成**读 JWT 的 `tid` claim**。两条签发路径（正常登录 + TOTP 中途的 interim）均带 tid —— `create_interim_token` **由内部取 ctx 而非调用方传**（`token_version` 那种传参风格正是让「漏传」变静默的原因）+ **别名感知** AST 哨兵防将来第三条签发路径漏带（初版只认字面 `jwt.encode`，`import jwt as _j` 直接绕过）。middleware **永不 401**：若由它出 401 就必须维护一份「哪些端点本来没 token」的漂移清单（SPA / 静态 Mount / docs / OPTIONS 预检 / 登录）—— 改为只在「凭证可用且租户可服务」时设 ctx，否则**不设**（下游 fail-closed 响亮崩掉，不静默跨租户供数）；401 责任回 `get_current_user`：**tid 门**（判别式是 tid 有无、不是 ver ⇒ 存量 token 全员重登一次）+ 首次接上生产调用点的**租户漂移 tripwire** `assert_tenant_context`（挡 `get_conn` 免疫的「ctx 非 None 但是**错的**租户」）。interim 校验**两段化 + 单一组合入口** `interim_session`（两段均模块私有 ⇒ 「忘记验吊销」不是一个能犯的错）+ 顺序 `清 ctx → 验签取 tid（ctx-free）→ 建 ctx → 限流 → 吊销`（限流先于吊销：否则持已吊销 interim 者每次尝试都触发一次 DB 读）。登录改**每家公司专属链接** `?c=<slug>`（复用已有 `tenants.slug` ⇒ **不需要** user_directory 表、各租户照样可各有 `admin`）+ **五个失败分支同一句「账号或密码错误」且各恰一次 bcrypt**（原短路 `and` 只有口令错那支跑 bcrypt ⇒ 耗时差可枚举公司/账号）。前端：登录流程请求**不带 Authorization 且不触发 401 重载**（原先密码错会整页重载把提示冲掉）· 会话清理三份分叉清单收成一份（登出此前漏清 enroll 缓存 ⇒ v0.6.5.2 那个 400 bug 可从登出路径复发）· SSE 的 401 打标签交上层统一处置（原先只显示裸 `{"detail":...}`，用户不会被登出）。⚠️ **顺带修一个测试盲区**：`conftest` 的环境 tenant ctx 会渗进 TestClient ⇒ 把中间件整体改成「永不解析租户」仍 **1437 测全绿**；装 `NoAmbientTenantTestClient`（HTTP 调用期间清环境 ctx）后同一 sabotage → **262 红**。单租户 byte-equal，R-T-GATE 仍挡第二租户。<br>**更早** v0.9.3 · **catalog 载体 per-tenant 化（隔离栈第三刀）**：catalog 是**唯一一处「读隔离、写不隔离」**的状态 —— `reload()` 读当前租户库、写**进程全局**（已实证跨租户串供：租户#1 reload 后切租户#2，6 个 module global 全部双向串）。6 个全局→ per-tenant 载体 `catalog_state`（tid 单键单默认槽 + 整槽原子发布 + lazy miss loader），`catalog.py` 6 名物理删除改 **PEP 562 `__getattr__` 代理**（13 个 importer 写法 byte-equal 即租户感知）；删 import 期 reload 与启动 warm-up；`current_catalog()` 回退目标从进程全局改**当前租户默认槽**；6 处 catalog 读的 fail-soft 吞点经单一 helper 接 fail-closed（含**脱敏链** —— 原降级会让 alias_map 空、非 admin 裸看内部库表名）。槽 producer 必须是**完整 reload 流水线**（严禁 DB-only，否则丢 file HTTP 表 → HTTP 查询静默落 SQL）。单租户 byte-equal，R-T-GATE 仍挡第二租户。<br>**更早** v0.9.2 · **uploads.db per-tenant 化（隔离栈第二刀）**：上传问数库从数据根全局单库改 **per-tenant** `tenants/<id>/uploads.db`（`_upload_engine` import 期值绑 → `get_upload_engine()` fail-closed resolver）+ **C4 式物理迁移**（data-root uploads.db → 租户目录，crash-safe copy+校验+last-good；空 uploads 合法）—— 闭合**跨租户上传表混池**（原全局库下上传问数 SQL 的 `sqlite_master` 可列举/SELECT 别租户 t_* 表）。relocation 提为独立无条件状态机（真实升级 knot.db 已迁走走 skip:migrated 也须迁 uploads）；单租户 byte-equal，R-T-GATE 仍挡第二租户。<br>**更早** v0.9.1 · **进程内租户状态 per-tenant 化（隔离栈第一刀）**：把 5 个「按 per-tenant id 键」的模块级缓存/桶（引擎缓存 / JWT 吊销版本缓存 / 限流桶 / 数据源健康 + 统计缓存）加租户维 —— 闭合跨租户**凭据泄漏**（引擎缓存按冲突 AUTOINCREMENT id 复用 → B 重跑打 A 库/凭据）+ **JWT 吊销绕过**（安全 critical）+ **DoS**；`invalidate_all` 非对称（engine 收当前租户 / token 保全局 rollout 清）；**单租户 tenant#1 全行为 byte-equal**，R-T-GATE 仍挡第二租户开通。<br>**更早** v0.9.0 · **OOS-1 红线修订仪式 + 多租户地基第一刀**（C 方案 per-tenant 文件隔离）：正式翻转 OOS-1 单租户死线为 **OOS-1v2**（多租户 = per-tenant SQLite 文件边界隔离，fail-closed；租户库内仍严禁 tenant_id 列——行级租户列对 LogicForm 编译器 fail-open）；落 tenant ContextVar fail-closed + `get_conn` 双层库解析 + 平台库（tenants 表）+ knot.db→platform.db/tenants/1/knot.db 存量迁移，**tenant#1 下全行为 byte-equal**。R-T-GATE 挡第二租户开通直到隔离栈就绪。<br>**更早** v0.8.24 · **data_source 删除级联清理 + 悬空引用治愈**（数据完整性 bug fix）：删数据源时 `delete_datasource` 只删主行、不清 `users.default_source_id` / `user_sources` / `bi_reports.data_source_id`（无 FK 兜底）→ 留悬空引用。补代码级 ON DELETE 级联（单事务原子）+ 幂等迁移治存量（含空集护栏）+ admin 写侧存在性校验（default_source_id + source_ids 双入口）+ 删源撤引擎缓存两命名空间；saved_reports 按 R-S7 保留 dangling。<br>**更早** v0.8.23 · **数据源徽标冷启假 0 修复**（cosmetic · checking-gated 计数）：修 v0.8.21 探测解耦引入的回归 —— admin 顶栏「数据源 · N 已连接」冷启探测缓存空时列表全 status='checking' 被误算 0（与绿点自相矛盾），改 checking-gated 计数（冷启未探测=未知→回落 dbOk 地板；暖缓存真 0=全 error/空列表→保留 0 不谎报 1）。<br>**更早** v0.8.22 **base.py → migrations.py 拆分**（纯重构 chore · 0 行为改）：init_db 的历史兼容迁移块（pre/post-schema + startup cleanup + 2 上传库迁移函数）拆入 `knot/repositories/migrations.py`，base.py 373→84 行，为 v0.9 多租户 `get_conn` 双层库解析释放 size-gate headroom（兑现 R-LP-v3-EX-3 承诺登记）。<br>**更早** v0.8.21 **admin 取数体验修**：数据源列表**探测与列表解耦** —— 原每次加载对每个源实时建连探测（不可达源 TCP 卡 >1min，数据源/用户页各卡分钟级），改即时返元数据 + 健康状态异步 `/datasources/status` 探测（源挂了页面也秒开，状态标"检测中"→更新）。<br>**更早** v0.8.20 **整体审核收口 19b**（use_agent 源头修 + 2 SSRF + SSE 记账 + default-admin 竞态 + echarts XSS）· v0.8.19 **上传问数隔离 + 存量 P1 修**（引擎脱主库 uploads.db + 修 SQLAlchemy 2.x bug 恢复上传功能）· v0.8.18 **③ da-asst 洞察嵌入** · v0.8.17 **②c BI 定时刷新调度器**。<br>**更早** v0.8.16 修 sparkline 宽屏折线消失（clipping bug）· v0.8.15 **BI 报表分享**（快照 PNG → Lark / Telegram，三重出境控制 + ⭐手写 foreignObject 截图引擎）· v0.8.14 **UI 视觉升级**（玻璃 chrome + 外观预设 雾面/极光 × 青/紫/翡翠/琥珀 + 自托管字体 Inter/Noto Sans SC/JetBrains Mono + 玻璃确认框）。<br>**更早** v0.8.13 admin 批量运维 · v0.8.12 **BI 设置 + 目录权限 RBAC**：BI 模式独立设置面板（数据源 / 用户 / API&模型 / 报表目录 / 目录权限）；新 `bi_permissions` = **按用户 × 目录/报表 × 4 权限**（定时 / 编辑 / 导出 / 分享，admin 恒全权，default-deny）—— 单租户内 user×resource（⚠️ OOS-1 死线 sustained，0 tenant_id）；da-asst 升为**第一类数据分析引擎**（独立模型槽 + BI 右栏只读报表解读 + 成本控制平面）。<br>**更早** v0.8.10~.11 **BI 仪表盘 12 列组件网格 builder**（6 类型 tile：KPI / 折线 / 圆盘 / 横条 / 表 / donut + 拖拽占列 + 冻结快照）+ 逐图视觉打磨。<br>**更早** v0.8.5~.9 **BI / ASK 双模**（共用 `<AppShell>` + 分段 ModeToggle + 共享 RightPanel；报表模式 = 仪表盘 tile / 多页 tabbed 报表 / 宽表 + 零 eval `formula.js` 覆盖层公式）· v0.7.x **5 层语义层 + LogicForm**（指标注册表 → NL→LogicForm→SQL 编译 → 混合路由；`KNOT_SEMANTIC_LAYER` flag 默认 off，待填真实 corpus + eval-live 达标后开）。

## 文档导航

按角色上手 —— 入口 [docs/ONBOARDING.md](docs/ONBOARDING.md)（三视角导航）：

- 业务方 / 分析师 → [业务方使用指南](docs/ANALYST_GUIDE.md)
- 管理员 → [管理员指南](docs/ADMIN_GUIDE.md)（day-1 走查）
- 运维 / SRE → [DEPLOY.md](DEPLOY.md) · [SLA.md](docs/SLA.md) · [PRIVACY.md](docs/PRIVACY.md)
- 贡献者 → [CONTRIBUTING.md](CONTRIBUTING.md) · [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)

## 角色

- **admin**：配置数据源、API key、Agent 模型（3-agent + da-asst）；维护 few-shot / prompt / 知识库 / 业务目录（表 / 词典 / 规则 / **表关系 RELATIONS**）/ 指标注册表 / 预算配置；BI 侧管理**报表目录 + 目录权限（按用户 RBAC）**（v0.8.12）
- **analyst**（运营 / 执行）：**ASK 问数**（自动生成 SQL、图表、洞察 + 思考过程 4-step Knowledge → Nexus → Objective → Trace 透明可追溯）+ **BI 报表**（在授权目录内查看/编辑/导出仪表盘与报表，da-asst 只读解读）

## knot 当前能做什么 / 不能做什么（v0.8.x 阶段宣告）

> v0.6.1 R-PA-PB-1 立约延续 — 窄场景宣告 + 责任边界；随 v0.7 语义层 + v0.8 BI 双模扩围更新。

### ✅ 当前能做（v0.8.x 范围）

**ASK 问数模式**（自然语言 → SQL → 图表 + 洞察）

- **NL → SELECT SQL**：单表 / 多表 JOIN / GROUP BY / 时间过滤 / 排序 / TopN / 子查询 / CTE
- **简单业务问题**：销售统计 / 用户行为 / 趋势分析 / 维度对比 / 同比环比
- **数据可视化**：line / bar / pie / table / metric card / rank_view / retention_matrix
- **笛卡尔积 6 层硬防御** + **复杂 CTE 多表查询** + **时间语义统一**（5 类核心表达 + 同比基准 + 节假日上下文 + D-1 数据更新延迟）
- **成本治理**：agent_kind 4 桶分桶 + 预算 gate + 告警 + audit_log INSERT-only

**BI 报表模式**（v0.8 ② · 与 ASK 共用 `<AppShell>`，分段 ModeToggle 切换）

- **仪表盘 builder**：12 列组件网格，6 类型 tile（KPI / 折线 / 圆盘 / 横条 / 表 / donut）+ 拖拽占列 + 每 tile 独立只读 SQL + 冻结快照 + 整表原子刷新
- **多页 tabbed 报表**（运营日报式：日 / 周 / 月每页一条 SQL）+ **宽表** + 零 eval `formula.js` 覆盖层公式（SUM/SUMIF/AVG/COUNT/MIN/MAX + A1 引用）
- **目录权限 RBAC**：按用户 × 目录/报表 × 4 权限（定时 / 编辑 / 导出 / 分享）；admin 恒全权、default-deny
- **da-asst 数据分析引擎**：BI 右栏只读报表解读（独立模型槽 + 成本控制平面 + 审计）

**语义层**（v0.7 · `KNOT_SEMANTIC_LAYER` flag · **激活门达标已启用**：eval-live 命中 ≥90%∧误判 0 + 真环境双证达标；代码默认仍 off，生产/本地设 `env=true` 开）

- **指标注册表** + **NL → LogicForm → SQL 编译**（编译七刀）+ **混合路由**（语义命中走 LogicForm，未命中回退 3-agent SQL）；flag 未开时全走 ASK 3-agent 链

### ❌ 当前不能做（OOS 范畴 / 推迟）

- **归因分析**（"为什么下降"）— 5 层语义中**事件 + 规则层未建**
- **跨业务域聚合**（不同 catalog 跨域分析）— **对象语义层跨对象聚合仍窄**（维度派生续做）
- **主动数据合理性反检**（"这个数对吗"）— 语义层有编译期 guard，**主动校验段未建**
- **动作触发**（通知 / 工单 / 审批 / 写回）— **动作语义层未建**（v1.x+）；BI 报表定时刷新调度器（②c）已交付 v0.8.17（仅刷新 MVP，定时推 IM 顺延）
- **多租户隔离 / SSO** — OOS-1（单租户死线）/ OOS-2；BI RBAC 已建但**限单租户内 user × resource，0 tenant_id**
- **国际化 i18n** — v1.x+ 公测准备
- **大规模向量 / RAG / 多模态** — 不在 knot 范围（Doris/SelectDB 4.0 这类是 DB 厂商课题）

### 当前阶段定位

- **v0.6.x "更好的 ChatBI"**（DAU 5-20 人内部工具）→ **v0.7.x 跨入 "Data Agent"**（5 层语义建模 + LogicForm 中间层）→ **v0.8.x = BI / ASK 双模报表平台**（仪表盘 builder + 目录 RBAC + da-asst）
- **1.0 团队公测**前：语义层激活（真实 corpus + eval-live 达标）+ BI 报表调度器 + da-asst 洞察替代

> 详 v0.6→v0.7 整体审核 LOCKED 结论：[`docs/plans/v0.6-to-v0.7-overall-review-2026-06-20.md`](docs/plans/v0.6-to-v0.7-overall-review-2026-06-20.md)（定向 v0.7 = 5 层语义层 + LogicForm）；v0.8 逐 PATCH 路线见 [CHANGELOG.md](CHANGELOG.md)。

## 4-Step 流式管线（v0.5.39 起 Trace 加入）

```
Clarifier (K Knowledge) → SQL Planner (N Nexus) → Presenter (O Objective) → Trace (T)
   （理解问题）            （ReAct 生成 SQL）       （洞察 + 异常 + 追问）     （信任度推导：源表数 / SQL 数 / JOIN / 聚合 / 可信度）
```

- 支持多轮上下文（代词「这些用户」「上述」会自动回指上一题口径）
- SQL 只读 guardrail：sqlglot AST 解析 + DB 端 SHOW GRANTS 探测；LLM 输出的 markdown 围栏自动剥离
- 结构化日志：每个请求带 request_id，grep 即可串起完整 agent 链
- **日期口径**（v0.2.3）：Asia/Shanghai 时区 + 完整日期枚举块（今天/昨天/最近7天/本周/上月 → 绝对日期），避免 LLM 把"昨天"映射到训练截止时间
- **多源跨组检测**（v0.2.3）：跨连接组 SQL 直接报错，不再让 MySQL 回 Access denied 误导 LLM 报权限错
- **Schema 检索 v2**（v0.2.3）：BM25 + 业务词典命中加分 + 主题重合 + 高优先表强制纳入，单次 prompt 上限 25 表 → 选 12 表
- **隐私脱敏**（v0.2.4）：业务 catalog / few-shots / eval cases / fake schema 采用 `.example` 模板模式，真实文件 `.gitignore`；缺失时自动回退 `.example`
- **业务目录可视化编辑**（v0.2.5 → v0.5.44 4 字段全维度）：admin 后台「业务目录」tab 直接编辑表目录 / 业务词典 / 业务规则 / **表关系 RELATIONS**，DB 覆盖文件默认；不编辑则用仓库默认（`_template_catalog.py`）
- **笛卡尔积 6 层防御**（v0.4.1.1 → v0.5.44）：catalog RELATIONS 注入 / prompt JOIN 硬约束 / sql_validator AST C1-C4 / R-91 retry counter / prompt 专家身份 ✓ ✗ 对照 / RELATIONS admin UI 根因解
- **思考过程 4 step 可追溯**（v0.5.39）：K Knowledge → N Nexus → O Objective → T Trace；Trace 前端从 SQL FROM/JOIN regex + presenter confidence 推导信任度（高 / 中 / 低）
- **预算单 global 配置**（v0.5.42）：admin 后台 5 字段（月度 token 上限 / 单次对话上限 / 告警阈值 / 默认模型 / 限流策略）+ Hero card 实时 token 用量进度条
- **demo 1:1 视觉复刻**（v0.5.6 → v0.5.44）：18 屏全部对照 Claude Design demo；OKLCH 单色空间 brand 195° + HarmonyOS / PingFang / Inter / JetBrains Mono 字体

## 5 分钟全新部署快速开始（内测）

> 适用场景：团队 5-10 人小范围内测；服务器在 VPN 或可信网络内。
> 公开对外部署请待 Phase B 后另起 runbook（HTTPS / 监控 / 防 brute force 等）。
>
> **📘 完整部署手册 + 升级 + 故障排查 + 监控**：[DEPLOY.md](DEPLOY.md)（运维必读）

### 1. 克隆 + .env 模板（30 秒）

```bash
git clone <repo-url> knot && cd knot && cp .env.example .env
```

### 2. 单行命令生成 2 个 secret 追加到 .env（10 秒）

```bash
{ echo ""; echo "# Generated by quick-start at $(date)"; \
  echo "KNOT_MASTER_KEY=$(python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"; \
  echo "JWT_SECRET=$(openssl rand -hex 32)"; } >> .env
```

> ⚠️ **KNOT_MASTER_KEY 必须异地备份**（服务器 + 个人密码管理器 + 团队加密备份三处） — 丢失 → 所有加密 API key / DB 密码永久不可读。

### 3. 编辑 .env 删除模板空行 + 填 LLM API key（2 分钟）

```bash
nano .env
# 删除文件中原 KNOT_MASTER_KEY= / JWT_SECRET= 空行（步骤 2 已追加新值）
# 填一个 LLM API key（OpenRouter / Anthropic / OpenAI / DeepSeek 任选）：
#   OPENROUTER_API_KEY=sk-or-...
```

### 4. Docker 启动（15 分钟首次构建）

```bash
docker build -t knot . && docker run -d -p 8000:8000 \
  -v $(pwd)/data:/app/knot/data --env-file .env \
  --name knot --restart unless-stopped knot
```

### 5. 验证启动（30 秒）

```bash
docker logs knot | tail -10
# 期望见：
#   KNOT_MASTER_KEY 已加载（Fernet）
#   anyio threadpool tokens = 32
#   Uvicorn running on http://0.0.0.0:8000
```

### 6. 浏览器首次操作（5 分钟）

1. `http://<server-ip>:8000` → Login 屏出现
2. **admin 初始口令**（v0.8.20 起）：设 `KNOT_INITIAL_ADMIN_PASSWORD` 则用之；未设则**首次启动随机生成并打印在日志一次**（`docker logs knot | grep "seed admin"`）。用 `admin` + 该口令登录 — ⚠️ **首登强制改密**（must_change_password=1）。遗失可 `python -m knot.scripts.reset_admin_password` 重置。
   - 🛡️ **v0.6.5.0 起 2FA 默认强制**：改密后即被引导**绑定 TOTP**（Authenticator 扫码 + 存恢复码；含 admin，无豁免）。快速评估可设 `KNOT_TOTP_REQUIRED=false` 关闭（详 [DEPLOY](DEPLOY.md) §5）。
3. 「API & 模型」tab：填 LLM provider key（与 .env 一致或独立）+ 给 3 个 agent 选模型
4. 「数据源」tab：配置 1 个业务库（Doris / MySQL / HTTP 数据源；db_type ∈ doris|mysql|http）
5. 回 Chat 屏提问 — 看到 SQL + 图表 + 洞察

### 7. 内测期硬约束（仅 2 条 — 不可推迟）

1. **KNOT_MASTER_KEY 异地备份** — 服务器 + 个人密码管理器 + 团队加密备份三处
2. **DB 文件 volume 挂载** — 步骤 4 `-v` 参数；container 删除后数据不丢

### 8. 可选优化（团队反馈驱动）

- **HTTPS**：加 Caddy 反代（5 分钟）`caddy reverse-proxy --from yourdomain.com --to localhost:8000`
- **CORS 收紧**（v0.6.0.15）：`.env` 加 `KNOT_CORS_ORIGINS="https://your-domain.example.com"`（逗号分隔多 origin）；未设时启动期会打印 WARNING + 兜底 `*`
- **监控**：UptimeRobot 拨测 `/healthz` 端点
- **业务目录定制**：admin 后台「业务目录」tab 编辑 lexicon / tables / business_rules / RELATIONS 四字段适配你的真实业务库（**推荐第 2-3 天做** — 默认 generic 模板体验受限）

## 版本升级

> **新部署**（v0.6.0+）无需迁移步骤，按上方 5 分钟快速开始即可。
> **同版本内升级**（拉新镜像 / 代码）：`docker restart knot`，DB schema 启动期幂等 migrate。
> **早期 dev 用户**（v0.4.x → v0.6.0 的 DB 文件 rename + env 改名，v0.5.0 双源兼容已于 v0.6.0 Phase A 撤回）详见 [CHANGELOG v0.6.0 (Phase A)](CHANGELOG.md) 与 [DEPLOY.md](DEPLOY.md)。

## 部署私有数据（可选）

仓库默认带通用电商模板（`*.example.*`），可直接跑通。要接入业务，**有两种方式**：

**A. admin 后台编辑（推荐 · v0.2.5）**：登录 → 侧边栏「业务目录」直接改表目录 / 词典 / 规则；保存即生效。

**B. 文件部署**（持久 / git 管理）：复制 `.example` → 真实文件（已 `.gitignore`）：

```bash
cp knot/services/agents/_template_catalog.py  knot/services/agents/_local_catalog.py
cp knot/services/few_shots.example.yaml       knot/services/few_shots.yaml
cp tests/eval/cases.example.yaml         tests/eval/cases.yaml
cp tests/eval/fake_schema.example.txt    tests/eval/fake_schema.txt
```

加载优先级：DB（A）> `_local_catalog.py`（B）> `_template_catalog.py`（仓库默认）。

## 技术栈

- **后端**：Python 3 + FastAPI + SQLAlchemy + SQLite + loguru；124 routes（smoke 下限 80）；9 import-linter contracts KEPT
- **前端**：React 19 + Vite 8（构建产物输出至 `knot/static/`）；OKLCH 单色空间 brand 195°；BI / ASK 双模共用 `<AppShell>`
- **LLM**：OpenRouter 统一路由（Claude 4.x / GPT-4o / Gemini / DeepSeek V3+R1 / Qwen / GLM / MiniMax — 15 OpenRouter models，v0.6.5.4 起 OR-only；max_context 字段 v0.6.0.6 起 OR live API 实测）；3-agent + da-asst 异步并行
- **语义层**（v0.7 · flag `KNOT_SEMANTIC_LAYER`）：指标注册表 + LogicForm 中间层（NL→LogicForm→SQL 编译七刀）+ 混合路由（语义命中 ∥ 未命中回退 3-agent）
- **BI 报表**（v0.8）：`bi_reports` + `bi_report_tiles`（结构化 tile：每 tile 只读 SQL + 冻结快照 + 逐 tile 脱敏）+ `bi_permissions`（按用户 × 目录/报表 × 4 权限 RBAC）+ 零 eval `formula.js` 覆盖层公式
- **业务库**：Apache Doris / MySQL（多源按 `host:port:user` 分组合并）
- **RAG**：BM25 + embedding cosine + RELATIONS 元数据注入 prompt
- **SQL 安全**：sqlglot AST 校验 + DB grants 探测 + **6 层笛卡尔积防御**（v0.5.44 + v0.6.0.1 R-PA-9 收官）
- **加密**：Fernet 字段级（API key / DB 密码）+ KNOT_MASTER_KEY env fail-fast（v0.4.5+）+ **JWT_SECRET fail-fast**（v0.6.0.13 MUST-1）
- **审计**：INSERT-only audit_log + 9 类 mutation 自动记录 + PII 三层防御 + 90 天 retention + **auto-purge 7 天阈值**（v0.6.0.5 F-C）
- **反馈观测**：用户回答 👍/👎 + 评论（F-A）/ 前端 JS 错误自动上报（F-B PII 三层防御 + 1h hash dedupe）
- **测试**：pytest + yaml 驱动的 eval 集（111 example cases / 9 contracts / **routes smoke ≥80**）

## 项目结构

详见 [CLAUDE.md](./CLAUDE.md)（包含路径职责、协作规则、版本约定、技术债清单）。

## Loop Protocol v3 — 迭代循环协议

KNOT 每个 PATCH 都按 **三阶段评审 + 4 级角色 + MINOR 滚动整体审核** 推进，不允许单 Agent 闭门写业务代码。v0.5.0 起 v3 协议生效，v0.5.4 起对外公开。

**4 级角色**（角色按 MINOR 滚动 — 当前 MINOR 的执行者会在下一 MINOR 自动转为守护者，再下一 MINOR 转为远古守护者；强调"规则治权"而非"人治层级"，不存在不可动摇的技术层级）：

| 角色 | 实体 | 职责 | 权限 |
|---|---|---|---|
| **执行者** | 当前 MINOR 的 Agent | 出方案 / 整合终审意见 / 写代码 / 跑闸门 / 提 PR | 读 + 写 |
| **守护者** | 上一 MINOR 的 Agent | PATCH 内 Stage 3 终审 + 闸门复核 | **只读** |
| **远古守护者** | 上上 MINOR 起的 Agent | **仅 MINOR 滚动前夕**整体审核 | **只读 + 默认沉睡** |
| **辅助 AI 初审组** | 资深工程师 + Codex + 其他辅助 AI | PATCH 内 Stage 2 给 Redline / 评分 / 风险点 | 评审建议 |
| **资深架构师** | User 本人 | 战略决策 + 拍板 + 召集整体审核 | 决策 |

**三阶段评审流程**：

```
执行者 (Stage 1 草案) → 辅助 AI 初审组 (Stage 2 Redline) → 守护者 (Stage 3 终审) → 执行者落地
```

每个 PATCH 都产出 `docs/plans/v0.X.Y-*.md` 锁定手册，含范围 / 决策点 D1-Dn / 红线 R-XX / 验收清单 / commit 序列。守护者**严禁**直接修改方案或代码，仅输出评审文本；执行者只拿 Stage 3 终审意见落地。

**MINOR 滚动整体审核**（v3 新增仪式）：每跨 MINOR 时由资深架构师明确 announce「整体审核」，执行者 + 守护者 + 所有存活的远古守护者独立提供意见，产出代码结构评估 / 奥卡姆剃刀清单 / 重命名重构提案 / 下一 MINOR 预期范围 4 份固定模板。

完整协议条款详见 [CLAUDE.md](./CLAUDE.md)「迭代循环协议」段落（含 v3 协议施行历史 + 例外治理条款 R-LP-v3-EX-1/2/3）。v3 自 v0.5.0 起每个 MINOR 逐 PATCH 施行，跨 v0.5 / v0.6 / v0.7 / v0.8 持续至今；业务模型重构级 PATCH（如 v0.7 语义层）一律走完整三阶段。

## 版本记录

见 [CHANGELOG.md](./CHANGELOG.md)。

格式 `vMAJOR.MINOR.PATCH`（+ 可选 build 号 `.N`，如 `v0.8.3`）：MAJOR 0=内测 / 1=团队公测；MINOR=阶段大节点；PATCH=每轮迭代 +1。v0.7.0 起 MINOR 边界打纯 3 位里程碑 tag（如 `v0.7.0`），PATCH 靠 squash-merge commit + CHANGELOG 追踪。

## License & Contributing

KNOT 采用 **Apache License 2.0**（v0.6.0.15 起 — 含明确专利授权 + 商标条款；详 [LICENSE](LICENSE) + [NOTICE](NOTICE)）。

- **贡献指南**：[CONTRIBUTING.md](CONTRIBUTING.md) — Loop Protocol v3 治理下的外部贡献者路径
- **安全报告**：[SECURITY.md](SECURITY.md) — **请勿提交公开 issue**（漏洞走 [GitHub Security Advisory](https://github.com/kkleonnnn/knot/security/advisories/new) 私密通报）
- **Service Level Expectations**：[docs/SLA.md](docs/SLA.md) — 生命周期 / 备份 / 性能 / OSS 治理（v0.6.0.25）
- **Privacy & Data Processing**：[docs/PRIVACY.md](docs/PRIVACY.md) — GDPR-lite 数据透明性（v0.6.0.25）
- **Issues**：https://github.com/kkleonnnn/knot/issues

