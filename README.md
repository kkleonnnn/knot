# KNOT

[![CI](https://github.com/kkleonnnn/knot/actions/workflows/ci.yml/badge.svg)](https://github.com/kkleonnnn/knot/actions/workflows/ci.yml)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

公司内部用的 AI 取数助手：自然语言 → SQL → 图表 + 洞察。

> ⚠️ **内测阶段**（MAJOR=0 · 团队内部工具，日活 5-20 人）。无 uptime SLA 承诺（best-effort，详 [docs/SLA.md](docs/SLA.md)）；公开对外部署前请落实 HTTPS / 监控 / 防暴力破解（见 [DEPLOY.md](DEPLOY.md) + [SECURITY.md](SECURITY.md)）。

## Demo

https://github.com/user-attachments/assets/008c1ba2-aea8-4f71-9f2a-e3c5c17e3ea3

> 40 秒产品演示 · v0.6 · 1920×1080 · 3.3 MB · 由 [HyperFrames](https://hyperframes.heygen.com) 渲染

> **当前版本** v0.8.18 · **③ da-asst 洞察嵌入**：BI 右栏「数据分析」助手 system prompt **.md 化 + 真嵌入**（6 只读/安全铁律 + da-asst 7 应答原则），纳入 prompt seed → admin 可覆盖（对齐 3-agent）；presenter 洞察对齐 da-asst 分析纪律（突出杠杆 / 【假设待验】 / 不确定就直说）——纯 prompt 层，0 新端点、0 契约改动。<br>**上版** v0.8.17 **②c BI 报表定时刷新调度器**（K8s CronJob → 内部 tick 端点 `KNOT_SCHEDULER_TOKEN` 守 + 原子认领去重 + `can_schedule` RBAC + fire 台账 + 玻璃 ScheduleModal；纯只读刷新 0 LLM，仅刷新 MVP）。<br>**更早** v0.8.16 修 sparkline 宽屏折线消失（clipping bug）· v0.8.15 **BI 报表分享**（快照 PNG → Lark / Telegram，三重出境控制 + ⭐手写 foreignObject 截图引擎）· v0.8.14 **UI 视觉升级**（玻璃 chrome + 外观预设 雾面/极光 × 青/紫/翡翠/琥珀 + 自托管字体 Inter/Noto Sans SC/JetBrains Mono + 玻璃确认框）。<br>**更早** v0.8.13 admin 批量运维 · v0.8.12 **BI 设置 + 目录权限 RBAC**：BI 模式独立设置面板（数据源 / 用户 / API&模型 / 报表目录 / 目录权限）；新 `bi_permissions` = **按用户 × 目录/报表 × 4 权限**（定时 / 编辑 / 导出 / 分享，admin 恒全权，default-deny）—— 单租户内 user×resource（⚠️ OOS-1 死线 sustained，0 tenant_id）；da-asst 升为**第一类数据分析引擎**（独立模型槽 + BI 右栏只读报表解读 + 成本控制平面）。<br>**更早** v0.8.10~.11 **BI 仪表盘 12 列组件网格 builder**（6 类型 tile：KPI / 折线 / 圆盘 / 横条 / 表 / donut + 拖拽占列 + 冻结快照）+ 逐图视觉打磨。<br>**更早** v0.8.5~.9 **BI / ASK 双模**（共用 `<AppShell>` + 分段 ModeToggle + 共享 RightPanel；报表模式 = 仪表盘 tile / 多页 tabbed 报表 / 宽表 + 零 eval `formula.js` 覆盖层公式）· v0.7.x **5 层语义层 + LogicForm**（指标注册表 → NL→LogicForm→SQL 编译 → 混合路由；`KNOT_SEMANTIC_LAYER` flag 默认 off，待填真实 corpus + eval-live 达标后开）。

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

**语义层**（v0.7 · `KNOT_SEMANTIC_LAYER` flag，默认 off）

- **指标注册表** + **NL → LogicForm → SQL 编译**（编译七刀）+ **混合路由**（语义命中走 LogicForm，未命中回退 3-agent SQL）；flag 未开时全走 ASK 3-agent 链

### ❌ 当前不能做（OOS 范畴 / 推迟）

- **归因分析**（"为什么下降"）— 5 层语义中**事件 + 规则层未建**
- **跨业务域聚合**（不同 catalog 跨域分析）— **对象语义层跨对象聚合仍窄**（维度派生续做）
- **主动数据合理性反检**（"这个数对吗"）— 语义层有编译期 guard，**主动校验段未建**
- **动作触发**（通知 / 工单 / 审批 / 写回）— **动作语义层未建**（v1.x+）；BI 报表定时刷新调度器（②c）在建
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
2. 默认账号 **`admin` / `admin123`** 登录 — ⚠️ **首次登录立即改密码**（个人设置 / admin 后台用户管理）
   - 🛡️ **v0.6.5.0 起 2FA 默认强制**：改密后即被引导**绑定 TOTP**（Authenticator 扫码 + 存恢复码；含 admin，无豁免）。快速评估可设 `KNOT_TOTP_REQUIRED=false` 关闭（详 [DEPLOY](DEPLOY.md) §5）。
3. 「API & 模型」tab：填 LLM provider key（与 .env 一致或独立）+ 给 3 个 agent 选模型
4. 「数据源」tab：配置 1 个业务库（Doris / MySQL / ClickHouse / SQLite local 测试用）
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

