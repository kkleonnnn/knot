# Security Policy

## 项目状态

**KNOT 当前处于 v0.6.0 内测期**（R-PA-5 4 周窗口 2026-05-15 → 2026-06-12）。
本项目尚未公开发布稳定版本（MAJOR=0），生产部署需自行评估风险。

## 相关文档

- [`docs/SLA.md`](docs/SLA.md) — Service Level Expectations（生命周期 / 备份 / 性能 / OSS 治理）
- [`docs/PRIVACY.md`](docs/PRIVACY.md) — Privacy & Data Processing（GDPR-lite 数据透明性）

## 当前安全姿态

| 维度 | 实现 |
|---|---|
| 认证 | JWT bearer + 默认 admin/admin123（**首次登录后必须修改**）|
| 密钥加密 | Fernet 字段级（API key + DB 密码）+ `KNOT_MASTER_KEY` env fail-fast |
| JWT 签名 | `JWT_SECRET` env fail-fast（≥32 字符；v0.6.0.8 MUST-1）|
| SQL 注入防御 | sqlglot AST 校验 + DB grants 探测 + 6 层笛卡尔积防御 |
| 审计日志 | INSERT-only + 9 类 mutation + PII 三层防御 + 自动 purge 7 天阈值 |
| 数据脱敏 | audit 日志 redacted；非 admin sql_text strip + 业务表名 → 业务别名（v0.6.0.17~19 脱敏链 3 部曲完成）|
| Rate limit | login 10/min/IP + change_pwd 5/min/IP + query 30/min/user（v0.6.0.23~24）|
| 2FA | 暂未支持（v0.6.2.0 计划 TOTP；启动闸门 R-PA-8 自验已完成 v0.6.0.22）|
| CORS | env 配置 `KNOT_CORS_ORIGINS`（v0.6.0.15 起；未设兜底 `*` + warning）|

## 已知限制（公开声明）

- **MAJOR=0 内测阶段**：不承诺生产 SLA / 不签订安全责任书
- **默认凭据**：首次启动 `admin/admin123` — 必须修改，否则任何能访问端口的人都是 admin
- **CORS 默认开放**：dev 模式 `*` 兜底；生产必须显式配置 `KNOT_CORS_ORIGINS`
- **JWT 无 refresh token**：当前 access token 7 天有效；登出仅前端清 localStorage（无服务端撤销）
- **rate limit in-memory**：当前 per-worker；多 replica 时各自计数（v0.7+ 评估 Redis backend）

## 漏洞报告

如果你发现安全漏洞，**请勿提交公开 issue**。

请通过以下方式联系：

- **Email**：kk@100xex.com（主题前缀 `[KNOT SECURITY]`）
- **GitHub Security Advisory**：https://github.com/kkleonnnn/knot/security/advisories/new

报告时请尽量包含：

1. 受影响的版本（`knot/main.py` 中 `version=...`）
2. 漏洞分类（auth / SQL injection / XSS / SSRF / dependency CVE 等）
3. 复现步骤（curl 命令或最小代码片段）
4. 影响评估（数据泄漏 / 提权 / DoS）
5. 你期望的披露时间表

## 响应承诺（内测期 best-effort，不构成 SLA）

- **72 小时内** 确认收到报告
- **2 周内** 给出初步评估 + 修复 ETA
- **修复后** 在 CHANGELOG 致谢报告者（除非你要求匿名）

## 安全相关红线（项目内）

KNOT 内部使用 Loop Protocol v3 治理；以下为已沉淀的安全红线（不完整列表）：

- **R-37 / R-45**：master key fail-fast（启动期检查；缺失即 exit(1)）
- **R-48 / R-59 / R-62**：audit PII 三层防御（含密文 redact + 递归深度限制）
- **R-83 / R-84 / R-85**：SQL AST 笛卡尔积硬防御（4 类反模式检测）
- **R-91**：cartesian reject 计数器（≥3 次强制终止 ReAct 循环）
- **R-PA-7**：Docker COPY 三守护（prompts / catalog / static 部署完整性）

详见 [CLAUDE.md](CLAUDE.md) 完整红线索引。
