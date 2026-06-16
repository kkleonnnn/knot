# KNOT 上手导航（onboarding hub）

> 一个入口，三个视角 —— 按你的角色选对应指南。
> KNOT = 自然语言 BI 助手（NL → 只读 SQL → 图表 + 洞察）。当前阶段 = 团队内部工具（日活 5-20 人）。

---

## 按角色选

| 你是… | 看这里 | 一句话 |
|---|---|---|
| **业务方 / 运营 / 分析师**（analyst）| [业务方使用指南](ANALYST_GUIDE.md) | 怎么提问、读懂结果、收藏导出、能做不能做 |
| **管理员**（admin）| [管理员指南](ADMIN_GUIDE.md) | day-1 走查：数据源 / API Key / 业务目录 / 用户 / 预算 / 审计 |
| **运维 / SRE**（ops）| 见下方「运维视角」 | 部署 / 升级 / 监控 / 排障 / SLA / 隐私 |
| **贡献者**（contributor）| [CONTRIBUTING](../CONTRIBUTING.md) · [行为准则](../CODE_OF_CONDUCT.md) | 开发环境 / PR 流程 / Loop Protocol v3 |

---

## 运维视角（ops）

KNOT 的运维资料已在以下文档，按需查阅（不在此重复）：

| 主题 | 文档 |
|---|---|
| 部署 / 升级 / 排障 / 监控 / 环境变量 | [DEPLOY.md](../DEPLOY.md)（运维主手册）|
| 服务级别预期（best-effort / 备份 / RTO·RPO）| [SLA.md](SLA.md) |
| 数据处理透明度 / 第三方 LLM 数据流 | [PRIVACY.md](PRIVACY.md) |
| 安全姿态 / 漏洞上报 / 已知限制 | [SECURITY.md](../SECURITY.md) |
| 容器 / K8s 升级 checklist | [docker checklist](plans/v0.6.1.x-ops-deploy-checklist.md) · [k8s checklist](plans/v0.6.1.x-ops-deploy-checklist-k8s.md) |
| 5 分钟内测快速部署 | [README §5 分钟全新部署](../README.md) |

> ⚠️ KNOT 当前定位为团队内网内测工具。**公开对外部署**前请落实 HTTPS / 监控 / 防暴力破解（见 DEPLOY.md + SECURITY.md）；服务无 uptime SLA 承诺（best-effort，详 SLA.md）。

---

## 能力边界（所有角色先知道）

- ✅ 自然语言 → 只读 SELECT（单/多表 JOIN、GROUP BY、时间、TopN、子查询、CTE）+ 7 种可视化 + 同比环比 + 收藏/导出
- ❌ 归因分析 / 跨业务域聚合 / 数据反检 / 动作触发 —— 均为 v0.7+（5 层语义建模后）
- ❌ 多租户隔离 / SSO / 权限分级（RBAC）/ 国际化

完整边界见 [业务方指南 §6](ANALYST_GUIDE.md)。
