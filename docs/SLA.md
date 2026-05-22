# Service Level Expectations (SLE)

> **本文不是法律意义上的 SLA 合同**——KNOT 当前处于 v0.6.0 内测期（MAJOR=0），
> 项目方不签订生产 SLA 责任书。本文是**期望管理 + best-effort 承诺的透明声明**，
> 帮助潜在用户判断是否在自身场景下采用 KNOT。
>
> Codex §APPENDIX D D-2 落实（v0.6.0.25 立约归档）。
> 关联文件：[`SECURITY.md`](../SECURITY.md) · [`PRIVACY.md`](PRIVACY.md)

---

## §1 当前生命周期阶段

| 阶段 | 版本 | 时间窗 | SLE 等级 |
|---|---|---|---|
| **内测**（当前）| v0.6.0.x | R-PA-5 4 周（2026-05-15 → 2026-06-12）| 无 SLE — 仅 best effort |
| 公测候选 | v0.6.2.x ~ v0.7.x | 2026-06 起 | best-effort 99% uptime（无赔偿） |
| 1.0 稳定 | v1.0.0+ | 视真实需求 | 视部署形态再议 |

**MAJOR=0** 在 semver 语义下表示"API 与行为可能 breaking change"。请勿用于：
- 生产关键业务依赖
- 签订对外服务承诺的下游系统
- 替代有审计要求的 BI 工具（Tableau / Power BI / 帆软等）

KNOT 当前定位为"**内部 dogfood + 早期采用者实验**"工具。

---

## §2 可用性与故障响应

### 2.1 不承诺

- **Uptime SLA**：v0.6.0.x 不承诺；自部署用户运维责任自负
- **响应时间承诺**：bug 报告无 RTO（response time objective）合同
- **数据丢失赔偿**：磁盘损坏 / 数据库腐坏 → 项目方零赔偿义务
- **第三方依赖故障**：OpenRouter / LLM 厂商 outage → 项目方无控制权

### 2.2 best-effort 承诺

- **致命 bug**（启动失败 / 数据损坏 / 安全漏洞）：作者 72h 内响应（GitHub issue / email）
- **CHANGELOG 透明性**：每个版本 release 必同步更新 [`CHANGELOG.md`](../CHANGELOG.md)
- **CI 不破**：main 分支始终 CI 全绿（7 contracts KEPT + 500+ tests + R-PA-8 自验）
- **向下兼容性**：MINOR bump 内禁止 schema breaking change（migration 必带）

---

## §3 数据持久化与备份

### 3.1 存储位置

- **SQLite DB**：`knot/data/knot.db`（用户 / 会话 / 消息 / audit / saved_reports）
- **Vite 构建产物**：`knot/static/`（git 跟踪；不可丢但易重建）

### 3.2 备份责任

**用户自负**——KNOT 不内置自动备份。建议运维：

```bash
# 定期 cron 任务示例（每天凌晨 3 点）
0 3 * * * cp /path/to/knot/data/knot.db /backup/knot-$(date +\%Y\%m\%d).db
```

### 3.3 恢复 RPO/RTO（自部署语境）

- **RPO**（数据丢失容忍）：由你的备份频率决定（建议 ≤24h）
- **RTO**（恢复时间）：替换 `knot.db` 文件 + 重启 → 数秒级
- 加密字段（API key / DB password）通过 `KNOT_MASTER_KEY` 解密；**丢失 master key
  = 加密字段永久无法恢复**（详 [`SECURITY.md`](../SECURITY.md)）

---

## §4 性能与容量承诺

### 4.1 性能基线（v0.6.0.x 内测期实测）

| 指标 | 实测范围 | 备注 |
|---|---|---|
| LLM 单次查询延迟 P50 | 8-15s | OpenRouter Claude 3.5 Sonnet typical |
| LLM 单次查询延迟 P95 | 20-40s | 含 fix_sql retry |
| 业务库 SQL 执行 | 取决于业务库 | KNOT 不优化业务库性能 |
| 前端首屏 | 1-2s | Vite 构建 + gzip 469KB |

### 4.2 容量上限（部署时调整）

- **schema 表数上限**：40（`MAX_TABLES_IN_SCHEMA`；v0.6.0.21 起）
- **结果行数上限**：500（`MAX_RESULT_ROWS`）
- **query rate limit**：30 次/分钟/user（v0.6.0.24）
- **login rate limit**：10 次/分钟/IP（v0.6.0.23）

容量需求更大请通过 env 或 PR 提交。

---

## §5 安全披露承诺

详 [`SECURITY.md`](../SECURITY.md) §响应承诺：

- **72h** 确认收到漏洞报告
- **2 周** 给出初步评估
- 修复后 CHANGELOG 致谢

---

## §6 OSS 治理承诺

v0.6.0.15 落地 + 资深 HQ-4 拍板：

- **LICENSE**：Apache-2.0（永不撤回；fork / 商用 / 二次分发自由）
- **主干公开**：`main` 分支始终公开可见（不会移到私有仓）
- **issue 开放**：GitHub Issues + Discussions 永久开放
- **PR 接受**：社区 PR 经 CI + 代码评审通过即可 merge（无 CLA 要求）
- **不承诺**：业务功能 PR 的 review SLA（best-effort）

---

## §7 自部署用户的合规责任

KNOT 是**自部署工具**——project owner 不持有用户数据。这意味着：

- **数据保护合规**（GDPR / 个保法 / HIPAA 等）由部署方承担
- **审计要求**（金融 / 医疗 / 政企）由部署方自评是否满足
- **加密强度**（Fernet AES-128 + HMAC-SHA256）是否符合行业标准由部署方判断

如部署到欧盟 / 加州等强数据法辖区，请咨询本地合规专家。

---

## §8 变更与撤回

本文件随项目演进；任何重大变更（如 OSS LICENSE 变动 / 承诺收紧）会：

1. PR 显式说明
2. CHANGELOG 标注 `BREAKING SLE CHANGE`
3. 内测期 announce 给用户群

**v0.6.0.25 立约**：在 KNOT 仍是 OSS + MAJOR=0 期间，§6 OSS 治理承诺不可降级。

---

> **联系方式**：kk@100xex.com（主题前缀 `[KNOT SLE]`）
