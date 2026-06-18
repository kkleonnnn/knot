# KNOT 管理员指南（admin onboarding · day-1 walkthrough）

> 面向：admin 角色（首次部署后的配置负责人）。
> 这是一份「第一天该做什么」的操作走查，按顺序过一遍即可让团队开始用 KNOT。
> 配套：[业务方指南](ANALYST_GUIDE.md) · [运维部署手册](../DEPLOY.md) · [文档导航](ONBOARDING.md)
>
> 各管理屏的字段级说明以 UI 内联 hint 为准；本指南给「做什么 + 在哪 + 注意什么」。

---

## 0. 登录 + 安全初始化（必做）

1. 用部署时的默认账号登录（默认 `admin` / `admin123` —— **首次登录立即改密**）
2. **改默认密码**（设置 → 修改密码）
3. **绑定两步验证（TOTP）— v0.6.5.0 起默认强制**：改密后首登即被引导进 Enroll（含 admin，无 bootstrap 豁免）。用 Authenticator App 扫码 → 输入 6 位码完成绑定 → **下载恢复码并妥善保存**（只显示一次，丢设备时登录用）。应急逃生口 `KNOT_TOTP_BYPASS_ADMIN=true`（防唯一 admin 锁死）；快速评估关闭 `KNOT_TOTP_REQUIRED=false`（详 [DEPLOY](../DEPLOY.md) §5）。

> 安全门槛见 [SECURITY.md](../SECURITY.md)；默认凭据 / CORS 等已知限制务必在公开部署前处理。

---

## 1. 数据源（admin → 访问 / Sources tab）

添加业务数据库连接（Apache Doris / MySQL）：主机 / 端口 / 库名 / 账号 / 密码。
- 密码以加密存储（Fernet `enc_v1:` 前缀，应用层加密）
- 连接状态实时显示 online / offline
- KNOT 只读查询：依赖 DB 端授权 + SQL AST 守护双保险

## 2. API Key + 3-Agent 模型（admin → 资源 tab）

- **API Keys**：填 LLM 供应商密钥（Anthropic / OpenAI 兼容 / OpenRouter）—— 遮罩存储，只显示后 4 位
- **模型表**：列出可用模型 + 输入/输出单价
- **Agent 模型分配**：为 Clarifier / SQL Planner / Presenter 三个 agent 分别指定模型（省钱可给轻 agent 配小模型）

## 3. 业务目录 catalog（admin → 系统 tab）

KNOT 准确率的核心。每个业务目录含 4 维度，可视化编辑：
- **表目录**：哪些表、各表用途
- **业务词典**：业务词 → 字段映射（如「GMV」「活跃用户」），命中提升语义层理解准确率
- **业务规则**：口径约定、计算规则
- **表关系 RELATIONS**（v0.5.44）：表间 JOIN 关系 —— **笛卡尔积防御的根因解**，务必配全

不编辑则用仓库默认模板。

**多 catalog 切换**（v0.6.2.5）：可建多个业务目录，每个用户有自己的当前激活目录（per-user active）。
- ⚠️ **重要边界**：一次查询只基于 **当前激活的一个目录**；KNOT **不做跨目录联合分析**（跨业务域聚合是 v0.7+ 对象语义层的能力）
- catalog 是语义层的水平切分，**不是多租户数据隔离**（数据库连接仍共享）—— 多租户隔离不在当前范围

## 4. 知识库 / few-shot / prompt（admin → 知识 tab）

- **知识库**：补充业务背景，注入 agent 上下文
- **few-shot 示例**：标注「好问题 → 正确 SQL」样例，显著提升相似问题准确率（结果不准时优先补这里）
- **prompt**：3-agent 的 system prompt 可覆盖默认（默认从 `knot/prompts/*.md` 启动期 seed）

## 5. 用户管理（admin → 访问 / Users tab）

新增 / 编辑 / 停用用户，设角色（admin / analyst）。新用户默认需首次改密。

## 6. 预算配置（admin → 预算屏 AdminBudgets）

成本治理：设月度 token 上限 / 单次对话上限 / 告警阈值 / 默认模型 / 限流策略。超阈值可告警或阻断。Hero 卡实时显示 token 用量进度。

## 7. 审计日志（admin → 审计屏 AdminAudit）

谁在何时做了什么（INSERT-only，敏感字段自动脱敏）。支持按操作人 / 动作 / 资源 / 时间筛选 + 详情抽屉。保留期默认 90 天，自动清理。

## 8. 可观测性屏（运维 / admin 共用，了解即可）

| 屏 | 看什么 |
|---|---|
| **AdminMetrics** | 内测指标：一次成功率 / 澄清率 / P95 延迟 / cost |
| **AdminQueryHistory** | 用户查询历史回溯 |
| **AdminErrors** | 前端错误上报汇总 |
| **AdminRecovery** | 系统自纠正统计（SQL 重试 / 修复率）|

这些屏偏可观测性/运维诊断，day-1 不必深配，上线后按需查看。

## 9. TOTP 重置（admin 帮用户解锁）

用户丢失 Authenticator 设备且无恢复码时，admin 在管理界面重置该用户 TOTP（重置后用户下次登录需重新绑定 + 旧 token 立即失效）。注意与 §0 的用户自助 Enroll（注册）区分。

---

## day-1 检查清单

- [ ] 改默认密码 + 绑定 TOTP + 存恢复码
- [ ] 配数据源（连接 online）
- [ ] 填 LLM API Key + 分配 3-agent 模型
- [ ] 配业务目录 4 维度（**表关系 RELATIONS 必配全**）
- [ ] 补 few-shot 示例（几条高频问题）
- [ ] 建 analyst 用户账号
- [ ] 设预算上限 + 告警
- [ ] 让 analyst 照 [业务方指南](ANALYST_GUIDE.md) 试问几个问题验证

---

## 注意事项

- KNOT 当前 = 团队内部工具（日活 5-20 人），**无多租户隔离 / SSO / 权限分级（RBAC）**
- 公开对外部署前请补 HTTPS / 监控 / 防暴力破解 —— 见 [运维部署手册](../DEPLOY.md) + [SLA](SLA.md) + [隐私说明](PRIVACY.md)
- 能力边界（归因 / 跨域 / 反检 / 动作均为 v0.7+）见 [业务方指南 §6](ANALYST_GUIDE.md)
