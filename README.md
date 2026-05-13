# KNOT

公司内部用的 AI 取数助手：自然语言 → SQL → 图表 + 洞察。

> **当前版本** v0.5.44 · v0.5.x 视觉重构 + 业务功能完整收官（demo 1:1 复刻 + 42 项资深架构师反馈偿还）

## 角色

- **admin**：配置数据源、API key、3-agent 模型；维护 few-shot / prompt / 知识库 / 业务目录（表 / 词典 / 规则 / **表关系 RELATIONS** v0.5.44）/ 预算配置（单 global 5 字段 v0.5.42）
- **analyst**（运营 / 执行）：聊天提问，自动生成 SQL、图表、洞察 + 思考过程 4-step (Knowledge → Nexus → Objective → Trace) 透明可追溯

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
- **业务目录可视化编辑**（v0.2.5 → v0.5.44 4 字段全维度）：admin 后台「业务目录」tab 直接编辑表目录 / 业务词典 / 业务规则 / **表关系 RELATIONS**，DB 覆盖文件默认；不编辑则用仓库默认（`ohx_catalog.example.py`）
- **笛卡尔积 6 层防御**（v0.4.1.1 → v0.5.44）：catalog RELATIONS 注入 / prompt JOIN 硬约束 / sql_validator AST C1-C4 / R-91 retry counter / prompt 专家身份 ✓ ✗ 对照 / RELATIONS admin UI 根因解
- **思考过程 4 step 可追溯**（v0.5.39）：K Knowledge → N Nexus → O Objective → T Trace；Trace 前端从 SQL FROM/JOIN regex + presenter confidence 推导信任度（高 / 中 / 低）
- **预算单 global 配置**（v0.5.42）：admin 后台 5 字段（月度 token 上限 / 单次对话上限 / 告警阈值 / 默认模型 / 限流策略）+ Hero card 实时 token 用量进度条
- **demo 1:1 视觉复刻**（v0.5.6 → v0.5.44）：18 屏全部对照 Claude Design demo；OKLCH 单色空间 brand 195° + HarmonyOS / PingFang / Inter / JetBrains Mono 字体

## 快速开始

```bash
pip install -r requirements.txt
cp .env.example .env   # 填 JWT_SECRET、默认数据源
python3 -m uvicorn knot.main:app --reload --port 8000
# http://localhost:8000
```

首次启动后用 admin 账号登录 →「API & 模型」面板填 OpenRouter Key + 给 3 个 agent 选模型。

## Docker

```bash
docker build -t knot .
docker run -d -p 8000:8000 --env-file .env knot
```

## 部署私有数据（可选）

仓库默认带通用电商模板（`*.example.*`），可直接跑通。要接入业务，**有两种方式**：

**A. admin 后台编辑（推荐 · v0.2.5）**：登录 → 侧边栏「业务目录」直接改表目录 / 词典 / 规则；保存即生效。

**B. 文件部署**（持久 / git 管理）：复制 `.example` → 真实文件（已 `.gitignore`）：

```bash
cp knot/core/ohx_catalog.example.py  knot/core/ohx_catalog.py
cp knot/core/few_shots.example.yaml  knot/core/few_shots.yaml
cp tests/eval/cases.example.yaml         tests/eval/cases.yaml
cp tests/eval/fake_schema.example.txt    tests/eval/fake_schema.txt
```

加载优先级：DB（A）> `ohx_catalog.py`（B）> `ohx_catalog.example.py`（仓库默认）。

## 技术栈（v0.5.44）

- **后端**：Python 3 + FastAPI + SQLAlchemy + SQLite + loguru；77 routes；7 import-linter contracts KEPT
- **前端**：React 19 + Vite 8（构建产物输出至 `knot/static/`）；OKLCH 单色空间 brand 195°
- **LLM**：OpenRouter 统一路由（Anthropic Claude 4.6 / OpenAI / Google / DeepSeek / Qwen / 智谱 / MiniMax）；3-agent 异步并行
- **业务库**：Apache Doris / MySQL（多源按 `host:port:user` 分组合并）
- **RAG**：BM25 + embedding cosine + RELATIONS 元数据注入 prompt
- **SQL 安全**：sqlglot AST 校验 + DB grants 探测 + **6 层笛卡尔积防御**（v0.5.44 收官）
- **加密**：Fernet 字段级（API key / DB 密码）+ KNOT_MASTER_KEY env fail-fast（v0.4.5+）
- **审计**：INSERT-only audit_log + 8 类 mutation 自动记录 + PII 三层防御 + 90 天 retention（v0.4.6+）
- **测试**：pytest + yaml 驱动的 eval 集（111 cases / 7 contracts / 77 routes smoke）

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

完整协议条款详见 [CLAUDE.md](./CLAUDE.md)「迭代循环协议」段落（含 v3 协议施行历史；v0.5.0~v0.5.44 期间共 **25+ 次完整施行**，自 v0.5.22 起授权"自审简化协议"用于视觉冲刺 + bug fix 类小 PATCH）。

## 版本记录

见 [CHANGELOG.md](./CHANGELOG.md)。

格式 `vMAJOR.MINOR.PATCH.YYYYMMDDHHmm`：MAJOR 0=内测 / 1=团队公测；MINOR=阶段大节点；PATCH=每轮迭代 +1。
