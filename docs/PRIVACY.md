# Privacy & Data Processing (GDPR-lite)

> **本文是 KNOT 项目自身的数据处理透明声明**，不构成法律意义上的隐私政策合同。
> KNOT 是**自部署工具**——你部署的 KNOT 实例上的用户数据由你（部署方）承担处理者
> 责任，本文是技术事实的诚实披露，帮助部署方编写自己的 GDPR / 个保法合规文件。
>
> Codex §APPENDIX D D-3 落实（v0.6.0.25 立约归档）。
> 关联文件：[`SECURITY.md`](../SECURITY.md) · [`SLA.md`](SLA.md)

---

## §1 数据分类

### 1.1 收集的数据

| 类别 | 字段 | 存储位置 | 是否加密 |
|---|---|---|---|
| 用户身份 | `username` / `display_name` / `password_hash`（bcrypt）| SQLite `users` | password_hash bcrypt；其他明文 |
| 数据源凭据 | `db_host` / `db_user` / `db_password` / `db_database` | SQLite `data_sources` | **db_password Fernet 加密** |
| API 密钥 | `openrouter_api_key` / `embedding_api_key` | SQLite `api_keys` | **Fernet 加密** |
| 查询历史 | `question`（自然语言）/ `sql_text` / `rows_json` / `cost_usd` | SQLite `messages` | 明文 |
| 会话元数据 | `title` / `created_at` / `updated_at` | SQLite `conversations` | 明文 |
| 审计日志 | `actor_id` / `action` / `client_ip` / `user_agent` / `detail_json` | SQLite `audit_log` | 明文（PII 自动 redact）|
| 收藏报表 | `title` / `pin_note` / `sql_text` / `rows_json` | SQLite `saved_reports` | 明文 |
| 用户反馈 | `score` (+1/-1) / `comment` | SQLite `message_feedback` | 明文 |
| 前端错误 | `error_message` / `stack_trace` / `url` | SQLite `frontend_errors` | 明文 |

### 1.2 KNOT **不**收集的数据

- 浏览器指纹 / Cookie tracking
- 第三方分析 SDK（无 Google Analytics / Mixpanel / Sentry 等）
- 实际业务库行数据的副本（仅 `MAX_RESULT_ROWS=500` 行查询结果快照存 `rows_json`）
- 用户键盘 / 鼠标输入回放
- 用户地理位置（仅 `client_ip` 用于审计，无 GeoIP 解析）

---

## §2 数据流向

### 2.1 浏览器 → KNOT 后端

- HTTPS（部署方负责证书）
- JWT bearer token authn
- 仅 same-origin 或显式 `KNOT_CORS_ORIGINS` 白名单

### 2.2 KNOT 后端 → 业务库（自部署）

- 用户配置的 MySQL / Apache Doris 等只读账号
- SQLite 存储加密后的连接凭据（详 §1.1）
- 查询结果仅前 500 行落库（messages.rows_json）

### 2.3 KNOT 后端 → OpenRouter（LLM 第三方）

⚠️ **关键透明性披露**：用户自然语言问题 + 业务库 schema 元数据 **会发送给 OpenRouter**，
再由 OpenRouter 路由到具体 LLM 厂商（Anthropic / OpenAI / Google / Meta 等）。

发送内容包含：

- 用户原始问题（中文 / 英文 / 任何自然语言）
- 业务库 schema（表名 + 列名 + 类型 + 业务词典 lexicon + 业务规则 business_rules）
- few-shot 示例（如配置）
- 业务术语词典（如配置）

**不发送**：

- 实际业务库行数据（仅 schema 元数据）
- 用户密码 / API key 等敏感字段

请阅读：
- [OpenRouter Privacy Policy](https://openrouter.ai/privacy)
- [Anthropic Privacy Policy](https://www.anthropic.com/legal/privacy)
- [OpenAI Privacy Policy](https://openai.com/policies/privacy-policy)

---

## §3 数据留存

| 数据 | 默认留存 | 配置项 |
|---|---|---|
| `messages` / 查询历史 | 永久（用户手动删除）| 无内置 retention；可写 cron |
| `audit_log` | 90 天 | `audit.retention_change` admin 可调 7-3650 天 |
| `saved_reports` | 永久（用户手动 unpin / delete）| 无 |
| `conversations` | 永久（用户手动删除）| 删除 conversation 会级联删 messages |
| `frontend_errors` | 永久（admin 手动清理）| `/api/admin/frontend-errors/purge` |
| `message_feedback` | 永久 | 无 |

### 3.1 自动清理

仅 `audit_log` 内置自动清理（v0.6.0.5 F-C）：
- 启动时检查最后清理时间，超过 7 天且 `audit_log` 行数 > 10000 → 触发清理
- 详 [`knot/services/audit_service.py`](../knot/services/audit_service.py)

---

## §4 用户权利（GDPR-lite 风格）

### 4.1 查阅权（Right to Access）

- **admin 用户**：可通过 admin 屏看到所有用户的查询历史 / 收藏报表 / 审计日志
- **业务用户**：只能看自己的 conversations + saved_reports；查询历史的 `sql_text`
  字段不返回非 admin（v0.6.0.17 脱敏链 1/3）
- API endpoint：`GET /api/conversations/{id}/messages`、`GET /api/saved-reports`

### 4.2 导出权（Right to Data Portability）

- **CSV 导出**：单条 message 通过 `GET /api/messages/{id}/export.csv`
- **xlsx 导出**：v0.4.2 起支持（含 5000 行硬上限 + 截断元数据）
- **批量导出**：暂未支持（公测前评估）

### 4.3 删除权（Right to Erasure）

- 删除 conversation → 级联删 messages（含 sql / rows / cost 等元数据）
- 删除 saved_report → 即时删除快照
- 删除 user（admin 操作）→ 级联删该用户的 conversations / saved_reports / feedback
- audit_log **不会**因用户删除而清除（合规性 INSERT-only）

### 4.4 更正权（Right to Rectification）

- 业务用户：可改自己的 display_name / 密码
- admin：可改任何用户的 username / display_name / role / is_active
- 历史查询 `question` 字段不可修改（保留真实问询记录）

---

## §5 加密细节

详 [`SECURITY.md`](../SECURITY.md) §密钥加密 + `knot/core/crypto/fernet.py`：

- **算法**：Fernet（AES-128-CBC + HMAC-SHA256）
- **Master key**：`KNOT_MASTER_KEY` env（fail-fast；缺失 → exit(1)）
- **加密字段**：DB 密码 / OpenRouter API key / embedding API key
- **不加密字段**：用户问题 / SQL / 业务查询结果（自部署 trust boundary 内）

---

## §6 数据所有权声明

- **用户数据归用户所有**（包括 conversations / messages / saved_reports / feedback）
- **项目方无 ownership 主张**——KNOT 是自部署工具，项目方不持有任何用户实例的数据
- **OSS LICENSE 不构成数据授权**——Apache-2.0 仅授权代码使用，不涉及数据
- **fork / 商用 / 二次分发自由**（详 [LICENSE](../LICENSE)）

---

## §7 自部署方的合规义务

KNOT 是自部署工具，**实际持有用户数据的是部署方**。部署到欧盟 / 加州 / 任何
强数据法辖区时，部署方需自行承担：

- **DPIA**（数据处理影响评估）
- **DPO**（数据保护官）的法定义务
- **数据主体权利**（access / erasure / portability）的响应
- **跨境传输**（OpenRouter → US / EU LLM 厂商）的合法基础
- **数据泄露通知**（72h 通知监管机构 + 受影响用户）

KNOT 项目方**不提供**：
- 法律咨询
- 合规审计支持
- 数据处理协议（DPA）模板

请咨询本地合规专家。

---

## §8 变更通知

本文件随项目演进；隐私相关收紧 / 放松会：

1. PR 显式说明
2. CHANGELOG 标注 `BREAKING PRIVACY CHANGE`
3. 内测期 / 公测期 announce 给用户

**v0.6.0.25 立约**：本文件 §3 数据留存、§4 用户权利不可降级（除非 1.0+ 业务需要
且经资深拍板）。

---

> **联系方式**：kk@100xex.com（主题前缀 `[KNOT PRIVACY]`）
