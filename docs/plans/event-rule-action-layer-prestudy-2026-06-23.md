# 事件/规则/动作层 — Stage 0 预研（2026-06-23）

> 执行者 v0.7 Agent · **Stage 0 预研**（非 PATCH · 0 代码 · 探索设计空间 + grounded 架构 + 风险分层 + 协议判断）
> base = main `94e88d6`（v0.7.6，LogicForm 七刀叙事完整）· 资深 announce + AskUserQuestion 拍方向 **A 事件/规则/动作层**
> 镜像 v0.7.0 启动前 `v0.7.0-semantic-layer-prestudy` 先例：大方向先预研，再由资深定第一刀范围 → 走完整 v3

---

## §0 一句话 + 本文目的

5 层语义模型已落 **指标层（v0.7.0 registry）+ 对象/维度层（v0.7.2 跨对象）+ LogicForm 编译/治理（v0.7.1~.6 七刀）**。
**事件/规则/动作层 = 上层** —— 从「被动查询」到「**主动监控 / 告警 / 自动化**」的**范式跃迁**（query-driven → event-driven）。

本预研**不锁设计**，只供资深定：① 是否 MINOR 跃迁（v0.8 + 整体审核）② 最小可行第一刀范围 ③ 切法序列。

---

## §1 grounded 架构现状（main 94e88d6 实测 · R-137）

| 维度 | 现状 | 对事件层的含义 |
|---|---|---|
| ⭐ 调度/触发 | **无调度器**（0 apscheduler/cron）；唯一后台 = startup `asyncio.create_task` fire-and-forget（`_audit_auto_purge_if_stale`，启动时跑一次）；查询 = 请求驱动 SSE | **承重缺口** —— 「主动监控」须周期/数据变更触发评估 → 全新触发机制（最高风险新件）|
| 规则→动作雏形 | `budget_service.check_user_monthly_budget` → `('ok'｜'warn'｜'block', threshold/action)`；budgets 表 scope/threshold/action（block/warn）| **可复用形状先例** —— 但**请求时评估**非定时主动；事件层 = 把此模式从 cost 推广到 metric + 加触发 |
| 动作层-通知 | `NotificationAdapter` Protocol（`send(Notification)`）**接口预留无实现**（v0.5.5 删 lark stub）| 动作层-通知有契约无 adapter → 需补具体实现（webhook/飞书/邮件）|
| 数据基础 | metrics registry（v0.7.0）+ semantic_query_audit（v0.7.3）+ recovery-stats / metrics 屏（read-only 观测）| 事件 = 「指标异动」可建在 metrics + 现有取数链上 |
| 自动执行 | 无（查询只读 DQL；`_is_safe_sql` 收口）| 动作层「自动执行」= 最高风险（写/触发副作用）→ 最后放 |

---

## §2 设计空间（事件 → 规则 → 动作 · 美团 BI 参考）

- **事件（Event）**：可被观测的「数据状态/变化」。候选：指标阈值突破（GMV < X）/ 环比异动（环比跌 >20%）/ 趋势反转 / 数据新鲜度告警。**建在 metrics registry 之上**（事件引用 metric + 比较算子 + 基准）。
- **规则（Rule）**：「事件 → 是否触发」的条件 + 评估时机。复用 budget threshold/action 形状；新增**触发时机**（请求时 piggyback / admin 手动「立即检查」/ 定时）。
- **动作（Action）**：触发后的响应。分级：① **通知**（webhook/飞书 — 补 NotificationAdapter 实现）② **记录/告警留痕**（侧表，类 semantic_query_audit）③ **自动执行**（重算/写回 — 最高风险，最后）。

---

## §3 ⭐ 承重判断（执行者预研结论）

### 判断 1 — 范式跃迁 + 无调度器 = 最高风险新件
事件层与 v0.7 七刀**本质不同**：v0.7 全程 **flag-gated query-path 内**（命中替代 sql_planner，0 新基础设施，read/append 为主，零生产风险）。事件层引入**调度/触发** = 系统第一次「主动做事」（非请求驱动）→ 跨调度 + 触发 + 通知 + 可能副作用，**风险量级跳变**。

### 判断 2 — 这是 MINOR 级（建议 v0.8.0 + 整体审核 + 角色滚动）
按 CLAUDE.md MINOR 规则「业务能力大节点 / 范式跃迁 → MINOR」：事件层 = 业务能力大节点。
**建议**：v0.7 七刀收官 → **v0.7→v0.8 滚动整体审核仪式**（执行者 v0.7 + 守护者 v0.6 + 远古 v0.5/v0.4）→ **v0.8.0 = 事件层第一刀**（新 MINOR，§角色滚动规则：当前执行者→守护者，资深开新对话启 v0.8 执行者）。理由：① 范式跃迁应过整体审核（巨型文件/奥卡姆/协议增量 4 产物）② 调度基础设施是新依赖维度，宜整体审核盘 ③ 不在 v0.7.x 尾巴硬塞大方向。

### 判断 3 — 风险分层切法（高风险逐层放）
| 层 | 刀 | 风险 | 触发机制 |
|---|---|---|---|
| **最小可行第一刀** | 事件/规则**定义 registry** + **请求时/手动评估**（admin「立即检查」按钮 piggyback 取数链）+ 告警**留痕侧表** | 低（无调度器，复用 budget pattern + metrics 取数 + append 审计）| 手动/请求时 |
| 第二刀 | **定时评估**（周期触发 events）| 中-高（需调度器：apscheduler 进程内 / K8s CronJob 调 endpoint）| 定时 |
| 第三刀 | **通知动作**（NotificationAdapter webhook/飞书 实现）| 中（外部副作用 + 凭证 + 重试）| — |
| 最后 | **自动执行动作**（重算/写回）| 最高（写副作用，破 read-only 安全边界）| — |

→ **第一刀刻意不碰调度器**（最大风险件后置）：定义 + 手动评估 + 留痕 = 复用现有（budget rule→action 形状 + metrics 取数 + append 审计哲学），零新基础设施，可验证「事件/规则模型」对不对再加触发。

---

## §4 §4.5 不变量延续（事件/规则/动作 CRUD 须带 · 同址而生）

- **gate**：事件/规则/动作 registry CRUD = admin 面（require_admin + 2FA carrier）。
- **审计**：event/rule/action CRUD + 触发 → 新 AuditAction Literal（每-Literal-emit CI 守护）。
- **OOS-1**：事件/规则归 `catalog_id`（水平切分），**严禁 tenant_id**。
- **脱敏**：规则含 SQL/LogicForm → 非 admin 脱敏 sustained。
- **cost/async**：事件评估若调 LLM（异动解读）→ 归桶 + async；纯阈值评估 0 LLM。
- **加密**：通知凭证（webhook secret）= 机密 → Fernet 注册 + 存储侧 CI 守护。
- **调度安全**（新维度）：定时触发须幂等 + 不阻塞 + 失败 fail-soft（镜像 _audit_auto_purge create_task 模式 / K8s CronJob）。

---

## §5 待资深决策项

1. **协议层**：v0.7 七刀收官 → **v0.7→v0.8 整体审核 + 角色滚动**？（建议 是 —— 范式跃迁应过审核 + 事件层 = v0.8.0 新 Agent）
2. **第一刀范围**：最小可行（定义 registry + 手动评估 + 留痕，无调度器）？还是含定时？（建议 最小可行 —— 高风险逐层放，第一刀验模型不碰调度）
3. **整体审核时机**：现在 announce 整体审核（执行者 + 守护者 + 远古独立提 4 产物），还是先继续盘？

---

## §6 自检 + 协议

- **Stage 0 预研性质**：0 代码 / docs-only working-tree 探索（未入库，未升版本）；供资深定方向，非 PATCH。
- 镜像 v0.7.0 prestudy 先例（大方向先预研 → 资深定第一刀 → 走完整 v3）。
- R-137：grounded main 94e88d6 架构现状（§1：无调度器 + budget rule→action 雏形 + NotificationAdapter 预留无实现 + 查询请求驱动）；不臆造能力。
- **执行者立场**：事件层是真正的能力跃迁（v0.7 治理红利之上的主动智能），但风险量级跳变 + 引入调度新维度 → 强烈建议 **MINOR 跃迁 + 整体审核 + 高风险逐层放（第一刀不碰调度器）**。
