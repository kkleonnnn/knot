# KNOT 部署手册

> **当前版本** v0.9.19 · 内测期（v0.6.1.4→0.6.5.6 升级 runbook 见 [docs/plans/v0.6.5.6-upgrade-from-v0.6.1.4-k8s.md](docs/plans/v0.6.5.6-upgrade-from-v0.6.1.4-k8s.md)；v0.6.5.x→v0.7.x 为纯内测迭代，无强制迁移步骤）
> **预估时长** 首次部署 10-15 分钟（docker build ~10 min + 配置 ~3 min）

本文档面向**运维 / 部署人员**。若有问题不清楚直接问 AI 助手并附上本文链接即可。

---

## 👥 角色边界（先看这一段）

KNOT 涉及 3 类"密钥"，分属不同角色——**别搞混**：

| 类别 | 在哪 | 谁负责 | 何时设 | 用途 | UI 可见？ |
|---|---|---|---|---|---|
| **`KNOT_MASTER_KEY`** | 服务器 `.env` 文件 | **运维** | 部署前（`deploy_checklist.sh` 自动生成）| Fernet 加密 DB 里的"数据源密码 / API Key"6 类敏感字段 | ❌ 看不见，admin 永不接触 |
| **`JWT_SECRET`** | 服务器 `.env` 文件 | **运维** | 部署前（同上）| 给登录 token 签名 | ❌ 看不见 |
| **admin 登录密码** | DB `users` 表（bcrypt 哈希）| **admin 本人** | 首次浏览器登录后改 | 浏览器认证 | ✅ admin 自己设 |

### 流程图

```
                运维 在服务器上
                       ↓
        ┌──── bash scripts/deploy_checklist.sh ────┐
        │  · 生成 KNOT_MASTER_KEY → 写 .env       │  ← 这俩 env
        │  · 生成 JWT_SECRET     → 写 .env       │     admin 永不接触
        └──────────────────────────────────────────┘
                       ↓
                  docker run ...
                       ↓
            应用从 .env 读取，启动
                       ↓
        ╔══════════════════════════════════════╗
        ║  浏览器：admin + 初始口令(见日志)登录 ║
        ║  → 进设置 → 改密码 + 改用户名         ║  ← 这是 admin 的事
        ╚══════════════════════════════════════╝
                       ↓
        admin 在 UI 里配置数据源 / API Key 等
                       ↓
        应用用 KNOT_MASTER_KEY 在后台加密落库
        （admin 输入明文，应用透明加密）
```

### 一句话总结

- **运维要做的**：跑 `deploy_checklist.sh`（自动生成两个 env 密钥）+ `KNOT_MASTER_KEY` 存密码管理器 + `chmod 600 .env`
- **admin 要做的**：浏览器登录后立即改密码 + 改用户名 + 填 OpenRouter Key + 配数据源
- **两者完全不重叠** — admin 在浏览器里**没有任何方式**接触 `KNOT_MASTER_KEY` / `JWT_SECRET`

---

## 📋 配置加载与 12-Factor 合规

### 配置优先级（高 → 低）

KNOT 用 `python-dotenv` 默认行为：

1. **OS 系统环境变量**（`export DB_HOST=...` / `docker run -e DB_HOST=...` / k8s ConfigMap / Secret）
2. **`.env` 文件**（仓库根目录，由 `deploy_checklist.sh` 生成）
3. **代码 fallback 默认值**（`os.getenv("DB_HOST", "localhost")` 的第二个参数）

**举例**：
```bash
# .env 内：DB_HOST=from-dotenv.local
$ docker run -e DB_HOST=from-system-env.prod ... knot
→ 应用读到 DB_HOST=from-system-env.prod   ← 系统 env 优先
```

部署玩法：
- **本地 dev**：用 `.env` 文件最方便
- **生产**：`.env` 兜底 + `docker run -e` 临时覆盖（不改文件）
- **k8s**：直接 ConfigMap / Secret 注 env，不用 `.env`

### `DB_HOST` env 的实际作用范围（特别说明）

KNOT 有**两层**业务 DB 配置 — 别搞混：

| 层级 | 来源 | `DB_HOST` env 影响？ |
|---|---|---|
| 1. **首次 `init_db` seed admin 账户** | env 默认值 | ✅ admin 用户的 `doris_host` 字段被写入 |
| 2. **运行时业务连接** | `data_sources` 表（admin UI 加） | ❌ 走表里的 `db_host` 字段，与 env 无关 |
| 3. **legacy fallback** | env 默认值 | ✅ 极少触发 |

**使用判断**：
- 🟢 **全新部署**：env 设 `DB_HOST=db.your-cluster.com` → admin UI 数据源 tab 预填该值
- 🔴 **已部署改 DB 地址**：进 admin UI → 数据源 tab → 编辑现有数据源（**不要靠改 env**，运行时数据源在 DB 里）
- 🔴 **k8s 重启换 DB**：env 改了但 `data_sources` 表里老记录不动

### 12-Factor 合规清单

KNOT 基础设施层 ✅ 完全符合 12-Factor "Config" 原则：

| 配置项 | 来源 | env 名 | 12-Factor 合规 |
|---|---|---|---|
| Fernet 加密主密钥 | env | `KNOT_MASTER_KEY` | ✅ + fail-fast |
| JWT 签名密钥 | env | `JWT_SECRET` | ✅ + fail-fast |
| 默认业务 DB 连接 | env | `DB_HOST` / `DB_PORT` / `DB_USER` / `DB_PASSWORD` / `DB_DATABASE` | ✅ |
| LLM 默认模型 | env | `DEFAULT_MODEL` | ✅ |
| LLM API Key（env 兜底）| env | `OPENROUTER_API_KEY` / `ANTHROPIC_API_KEY` / ... | ✅ |
| SQLite 路径 | env | `SQLITE_DB_PATH` | ✅ |
| Agent 调优参数 | env | `AGENT_MAX_STEPS` / `RAG_TOP_K` / `SCHEMA_FILTER_MAX_TABLES` | ✅ |

### 业务配置走 DB，不走 env（混合模式说明）

以下配置**不走 env** — 由 admin 在浏览器 UI 配置 + DB 持久化：

| 配置 | 表 | 加密 |
|---|---|---|
| 多数据源连接（host/port/user/pwd/database）| `data_sources` | `db_password` Fernet 加密 |
| LLM API Key（admin UI 加，覆盖 env 兜底） | `app_settings` | Fernet 加密 |
| 3 个 Agent 模型分配 | `app_settings` | — |
| 用户账号 + 角色 | `users` | bcrypt 哈希 |
| 业务目录 / 表关系 / 业务规则 | `app_settings` | — |
| Few-shot 示例 | `few_shots` | — |
| Prompt 模板 | `prompt_templates` | — |
| 预算配置 | `app_settings` | — |
| 收藏报表 | `saved_reports` | — |

**为什么不全走 env**：
- 需要 admin 浏览器**即时**改 / 加 / 删（不可能每次重启容器）
- 多用户多数据源场景下 env 不适合（多条同类配置无法表达）
- 业务变更要**审计追溯**（`audit_log` INSERT-only + 9 类 mutation 自动记录 + Fernet 加密敏感字段）

### 一句话总结（12-Factor）

> 12-Factor 没有要求"每条 config 都 env"，强调的是 **"环境无差异"** + **"config 与代码分离"** + **"严格隔离 build / release / run"**。KNOT 这三条都满足：
> - 基础设施 config 走 env（dev / staging / prod 同一份代码）
> - 业务运行时 config 走 DB（admin UI 即时管理 + audit 追溯）
> - 镜像与配置完全分离（同一镜像跑任意环境，靠 env + DB 区分）

---

## 🛡️ 生产安全 — 数据库写库风险评估

**核心问题**：KNOT 接入生产数仓后，**会不会写库 / DROP / 改数据 / 拖垮 DB**？

**结论**：✅ **几乎不可能写库**（两层独立守护 + 推荐第三层 DBA 权限隔离）；⚠️ 有**少量计算资源占用风险**（OLAP SELECT 仍消耗 BE 资源）。

### 防护层级

#### 🛡️ Layer 1 — 应用层 SQL 守护（`_is_safe_sql`）

[`knot/adapters/db/doris.py`](knot/adapters/db/doris.py) — **每次 SQL 执行前必跑**：

- **sqlglot AST 解析**（不是正则黑名单 — 更稳，骗不过）
- ✅ **允许的根节点**：`SELECT` / `WITH` / `UNION` / `INTERSECT` / `EXCEPT` / `SHOW` / `DESCRIBE`
- ❌ **AST 内任意位置出现这些节点全拒**：`Insert` / `Update` / `Delete` / `Merge` / `Drop` / `Create` / `Alter` / `TruncateTable` / `Set` / `Use` / `Grant` / `Command`（兜底未知操作）
- ❌ **多语句直接拒**（防 SQL 注入 stacked query — `SELECT 1; DROP TABLE...` 这种）
- ❌ sqlglot 解析失败 → 拒绝执行（fail-closed）
- ❌ sqlglot 未安装 → 退回严格字符串前缀检查（仍只允许 `SELECT/WITH/SHOW/DESCRIBE/EXPLAIN`）

**实战**：即使 LLM 抽风生成 `DROP TABLE users; SELECT 1`，会被前置拦截，**不会到 DB**。

#### 🛡️ Layer 2 — DB 层账号权限检查（`check_readonly_grants`）

[`knot/adapters/db/doris.py:39`](knot/adapters/db/doris.py) — **加数据源时检测**：

- `SHOW GRANTS` 解析账号权限
- 状态：`readonly` / `writable` / `unknown`
- 默认 `STRICT_READONLY_GRANTS=0`（信任模式，只警告 admin）
- **设 `STRICT_READONLY_GRANTS=1` → writable 账号直接拒绝构建 engine**（无法接入非只读账号）

#### 🛡️ Layer 3 — DBA 侧专用只读账号（生产强烈建议）

```sql
-- DBA 在 Doris / MySQL 侧创建
CREATE USER 'knot_ro'@'%' IDENTIFIED BY '<生成的强密码>';
GRANT SELECT ON your_business_db.* TO 'knot_ro'@'%';
FLUSH PRIVILEGES;
-- ⛔ 故意不给：INSERT / UPDATE / DELETE / DROP / CREATE / ALTER / GRANT
```

KNOT admin UI 加数据源时填这个账号 + env 设 `STRICT_READONLY_GRANTS=1` → **3 层独立守护，任一层挡住都不会写库**。

### 其他保护机制

| 风险 | 保护机制 |
|---|---|
| **笛卡尔积大查询拖垮 DB** | 6 层防御（v0.5.1 R-80~93）：catalog RELATIONS 注入 / prompt JOIN 硬约束 / sqlglot AST C1-C4 / R-91 retry counter / prompt 专家身份 / RELATIONS admin UI 根因解 |
| **全表扫描占资源** | `LIMIT 10000` 默认追加（无 LIMIT 自动加） |
| **LLM 失控狂跑** | 预算告警 + 月度 token cap + 单次对话 cap + 限流（v0.4.3+） |
| **重试无限循环** | `recovery_attempt` 计数器 cap 3 次 |
| **审计追溯** | `audit_log` INSERT-only + 9 类 mutation 自动记录 + PII 三层脱敏 + 7 天 retention 自动清理 |
| **业务表名爆破探测** | 业务目录 admin UI 显式配置 + few-shot 引导（LLM 看不到表名不会瞎猜） |
| **SQL 注入 stacked query** | 多语句直接拒（Layer 1 守护）|
| **加密敏感字段** | Fernet 字段级加密（`db_password` / `api_key` 等 6 类） + `KNOT_MASTER_KEY` fail-fast |

### ⚠️ 不能 100% 保证的边界（透明披露）

| 风险 | 说明 | 缓解建议 |
|---|---|---|
| **复杂 SELECT 短时占 IO** | 即使只读也消耗 Doris BE 计算资源 | 给 KNOT 用 **OLAP 从库副本**（与业务 OLTP 资源隔离） |
| **大表 SELECT 拖慢业务 DB** | LIMIT 10000 兜底；但 5-10 用户同时跑重 OLAP 仍可能 P99 飙升 | Doris BE 资源组（resource_tag）隔离 KNOT 流量 |
| **LLM 数据解读错** | 数据**不准** ≠ DB 写坏 | presenter `confidence=low` 时自动标 ⚠️ banner |
| **业务目录配错** | RELATIONS 错填让 LLM 误 JOIN | 只是查不准；不会写库；admin 进 UI 改 catalog 即可 |

### 生产部署 checklist（DBA / 运维必读）

```bash
# 1. DBA 在 Doris/MySQL 侧创建专用只读账号
mysql -h <doris-fe> -u root -p <<'SQL'
CREATE USER 'knot_ro'@'%' IDENTIFIED BY '<openssl rand -hex 16>';
GRANT SELECT ON <business_db>.* TO 'knot_ro'@'%';
FLUSH PRIVILEGES;
SQL

# 2. KNOT 服务器 .env 设强约束
echo "STRICT_READONLY_GRANTS=1" >> .env

# 3. 推荐生产部署模式
#    - 单独 OLAP 从库副本（避免与业务 OLTP 竞争资源）
#    - 或 Doris 计算节点 BE 资源组隔离 KNOT 流量

# 4. 监控（Doris 侧）
#    SELECT * FROM mysql.audit_log WHERE user='knot_ro' AND
#           UPPER(stmt) NOT LIKE 'SELECT%' AND
#           UPPER(stmt) NOT LIKE 'WITH%' AND
#           UPPER(stmt) NOT LIKE 'SHOW%';
#    应永远 0 行（如果有任何非 SELECT 被尝试，Doris 侧能 catch 到）

# 5. 监控（KNOT 侧）
#    admin → 审计日志 → 看 KNOT user 的 query 历史（每条都有完整 SQL + cost）
```

### 一句话总结（生产安全）

> 三层独立守护（应用 AST + DB 权限 + DBA 账号），KNOT 接入生产数仓**几乎不可能写库**。最大风险是 **OLAP 计算资源占用**，强烈建议用从库副本或 Doris 资源组隔离 KNOT 流量。

---

## 🚀 一键部署（推荐流程）

```bash
git clone https://github.com/kkleonnnn/knot.git && cd knot

# 1. 自动生成 KNOT_MASTER_KEY + JWT_SECRET + 切 OR-only 默认模型
bash scripts/deploy_checklist.sh

# 2. 编辑 .env 填 OpenRouter API Key（admin UI 也可填，env 是兜底）
nano .env   # 找到 OPENROUTER_API_KEY=  填值

# 3. 构建 + 启动
docker build -t knot .
docker run -d -p 8000:8000 \
  -v $(pwd)/data:/app/knot/data \
  -v $(pwd)/_local_catalog.py:/app/knot/services/agents/_local_catalog.py:ro \
  --env-file .env \
  --restart unless-stopped \
  --name knot knot
#   ⚠️ 第 2 个挂载 = **私有 catalog**（v0.9.16 起不再进镜像）—— 详见下文「私有 catalog」段。
#      **只用 SQL 数据源的部署可以省掉它**（启动日志会有一条 WARN 提示，不影响功能）。

# 4. 验证启动（10 秒后）
sleep 10 && docker logs knot | tail -10
# 必须见:
#   "prompt seed: {'sql_planner': 'seeded', ...}"
#   "KNOT_MASTER_KEY 已加载（Fernet）"
#   "Uvicorn running on http://0.0.0.0:8000"
```

浏览器访问 `http://<server-ip>:8000` → 用 `admin` + 初始口令登录（v0.8.20：设 KNOT_INITIAL_ADMIN_PASSWORD 则用之，未设则首启随机生成打印在日志一次 `docker logs knot | grep "seed admin"`）。

---

## ⚠️ 部署必读 — 5 条硬约束

### 1. KNOT_MASTER_KEY 是**终身密钥** 🔐

- 由 `deploy_checklist.sh` 自动生成（Fernet 32-byte base64）
- **务必备份到密码管理器** — 丢失或更改 = 历史加密数据（数据源密码 / API Key）**永久无法解密**
- 写到 `.env` 后建议 `chmod 600 .env`
- 重新部署 / 迁移服务器时**必须用同一个 key**

### 2. 首次登录立即改密码 🔑

- **admin 初始口令（v0.8.20 F7 起）**：seed 逻辑在 `knot/repositories/base.py:213`（原文档误引 `:94`）—— 设 `KNOT_INITIAL_ADMIN_PASSWORD` 则用之；**未设则首启随机强口令 + 日志打印一次**（`docker logs knot | grep "seed admin"`）。**不再有跨部署同一 admin123**（旧硬编默认已废，R-LP-v3-EX-3-1）。
- 首登 `must_change_password=1` 强制改密（服务端硬门：改密前只能调 `/api/auth/*`）。
- **必做**：登录后改密码 + 改用户名（不叫 admin，防字典爆破）；口令遗失 → `python -m knot.scripts.reset_admin_password --tenant <slug|id>`（**`--tenant` v0.9.15 起必填** —— 破坏性工具不得有默认目标；单租户部署传 `--tenant 1`）。
- 首启竞态提醒：随机口令仅在日志一次性可见，**部署后尽快首登占位**（防他人抢先首登）。

### 3. 公网部署必加 HTTPS 反向代理

内测内网可跳；公网必加 nginx / caddy + HTTPS。

**nginx 推荐配置**：

```nginx
location / {
    proxy_pass http://localhost:8000;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $https;
    # SSE 流式响应必须
    proxy_buffering off;
    proxy_read_timeout 300s;
}
```

✅ `audit_log` 已支持 `X-Forwarded-For` / `X-Real-IP` — 反代不会污染真实客户端 IP。

### 4. 必做备份策略

```bash
# crontab -e
# 每日 02:00 自动备份（v0.9.0 起业务库在 data/tenants/ + 平台库 data/platform.db → 整目录打包）
0 2 * * * cd /path/to/knot && tar czf data/backup.$(date +\%Y\%m\%d).tgz data/tenants data/platform.db data/uploads.db 2>/dev/null && find data/ -name "backup.*.tgz" -mtime +30 -delete
```

✅ `audit_log` 自动 7 天 retention + timestamped 备份（F-C 已内置 — 无需额外）。

### 5. TOTP 2FA — 默认强制（admin 不豁免）🛡️（v0.6.5.0+）

**v0.6.5.0 起 2FA 默认强制**（资深 2026-06-19 提前 R-PA-8 公测门）：所有用户（含 admin）
改密后首次登录即被强制绑定 TOTP。删除了 v0.6.2.0 的「0 admin enrolled → bootstrap 自动豁免」
（该 bootstrap + 无自愿 enroll UI ⟹ 唯一 admin 永远无法被 enroll，2FA 形同虚设）。

**env 开关**：

```bash
# 默认（unset）= on：所有未 enroll 用户登录被强制跳 Enroll
# 快速评估 / demo 显式关闭：
export KNOT_TOTP_REQUIRED=false
```

> **升级既有部署 rollout**（v0.6.5.0+ 默认 on）：从旧版（2FA off）升级后，**所有未 enroll 的存量用户下次登录立即被强制 enroll**。若不想打断在测用户 → 升级前先 `export KNOT_TOTP_REQUIRED=false` 分阶段，待用户备好 Authenticator 再移除该 env 重启启用。

**应急后门**（仅此一条豁免路径，防唯一 admin 永久锁死）：

```bash
# admin 弄丢 authenticator + 恢复码时临时 export → admin 跳过 2FA 进系统重置/重绑；用完即撤
export KNOT_TOTP_BYPASS_ADMIN=true
```

| 路径 | 行为 |
|---|---|
| 默认（两 env 都不设）| admin + 普通用户**一律强制 enroll**（未 enroll → 受保护端点 403 → 前端跳 Enroll 屏）|
| `KNOT_TOTP_BYPASS_ADMIN=true` | **仅 admin** 应急豁免（非 admin 不享 → 由 admin reset 救援）|
| `KNOT_TOTP_REQUIRED=false` | 全局关闭强制（eval / demo）|

**首次部署 checklist**：

1. `admin` + 初始口令（见启动日志 / KNOT_INITIAL_ADMIN_PASSWORD）登录 → **强制改密** → **强制 Enroll**（Authenticator 扫码 + 存 10 个恢复码）
2. 验证 enrolled admin 登录 → 输入 6 位码后进业务屏
3. （可选）邀其他用户：各自首登强制 enroll

**锁死风险 + 缓解**（透明披露）：

- 风险：唯一 admin 弄丢 authenticator **且** 弄丢 10 个恢复码 → 无第二 admin reset → 锁死
- 缓解三层：① 应急后门 `KNOT_TOTP_BYPASS_ADMIN=true`（ops 逃生口）② enroll 发 10 个恢复码 ③ enroll 流程 `/api/totp/*` 白名单可达（强制 ≠ 锁死，admin 能走完绑定）

---

## 📋 上线后 5 分钟 admin 配置 checklist

| 路径 | 操作 | 必要性 |
|---|---|---|
| 设置 → 个人 | 改密 + 改用户名 | 🔴 必做 |
| 设置 → API & 模型 | 填 OpenRouter Key（1 个 key 通所有 15 个 OR 模型） | 🔴 必做 |
| 设置 → API & 模型 | 配置 3 个 Agent 模型（推荐 OR 默认 claude-haiku-4.5） | 🔴 必做 |
| 设置 → 数据源 | 填 Doris/MySQL 连接（host/port/user/pwd/database） | 🔴 必做 |
| 设置 → 业务目录 | 填表关系 RELATIONS + 业务规则（防笛卡尔积 / 防业务理解错） | 🟡 强烈建议 |
| 设置 → 预算 | 月度 token 上限 + 单次对话上限 + 告警阈值 | 🟡 强烈建议 |
| Chat 屏 | 提问 "今天的合约交易总量是多少？" 端到端验证 4-step 思考过程 | 🟡 验证 |

---

## 📦 升级流程（任何 micro PATCH 通用）

```bash
cd /path/to/knot

# 1. 拉最新代码
git pull origin main

# 2. 重建镜像
docker build -t knot .

# 3. 停旧容器 + 启新容器（数据自动保留）
docker stop knot && docker rm knot
docker run -d -p 8000:8000 \
  -v $(pwd)/data:/app/knot/data \
  --env-file .env \
  --restart unless-stopped \
  --name knot knot

# 4. 验证
sleep 10 && docker logs knot | tail -5
```

**关键不变量**：
- ✅ 业务库不丢 → 所有用户配置 / 历史对话 / audit 全保留（v0.9.0 起业务库 = `./data/tenants/1/knot.db`；见下「多租户存量迁移」）
- ✅ `KNOT_MASTER_KEY` env 不动 → 历史加密数据可解密
- ✅ `init_db()` 启动期幂等迁移 schema（新表新列自动加，旧数据不动）

> ⚠️ **首次从 v0.8.x（或更早）升到 v0.9.x 例外**：这是**一次性存量迁移**（`data/knot.db` → `data/tenants/1/knot.db` + 新建 `data/platform.db`），不是普通 micro PATCH。**升级前务必读下一节**。

### 📌 Python 依赖版本从哪来（v0.9.14 起 · `requirements.lock`）

`docker build` 装的**不再是「当天最新」** —— `Dockerfile` 用
`pip install -r requirements.txt -c requirements.lock`：roots 走 `requirements.txt`（extras 意图不丢），
**精确版本由 `requirements.lock` 钉住**（**51 个包** = 21 直接 + 30 传递）。
⇒ 同一个 commit 在任何日期构建，装出的 Python 版本集合相同。

**什么时候需要重新生成 lock**（三种，都是**有意动作**）：
1. 改了 `requirements.txt`（加/删依赖、动区间）；
2. 换了 `Dockerfile` 运行 stage 的基础镜像（Python 版本变了）；
3. 想吸收上游安全更新。

**在哪生成 —— 必须在容器里，不能拿本机 `pip freeze`**：

```bash
./scripts/regen_lock.sh          # 写入 requirements.lock
./scripts/regen_lock.sh --check  # 只比对，不写（查 lock 是否已过期）
```

脚本会在 **`Dockerfile` 运行 stage 的同一个基础镜像**里 `pip freeze`
（镜像名**从 `Dockerfile` 最后一个 `FROM` 派生**，不在脚本里另写一份），
目标平台默认 `linux/amd64`（与 CI runner 和 K8s 一致）。
生成后**必看文件头部**：它记录了 base-image / `--platform` / python / platform / machine / pip
—— 这是**这份 lock 在哪儿有效**的唯一凭据。改完 `requirements.txt` 后若忘了重生成，
CI 的 `locked runtime lane` 会直接红（集合等值不成立）。

⚠️ 若改了依赖，`requirements.txt` 的上下界也要跟着改（哨兵 `Sd3` 会告诉你确切该写什么）：
上界取「上游版本契约能支撑的最紧那个」—— `1+` → 下个 major · `0.x` → 下个 minor ·
`0.0.x` → 下个 patch。

⚠️ **本机 `.venv` 与生产不同步是正常的**（本机 3.12、装得早；生产 3.11 + lock）。
想让本机也用锁定版本：`pip install -r requirements.txt -c requirements.lock`。

🔴 **不要因为有了 lock 就以为镜像整体可复现** —— `python:3.11-slim` / `node:20-slim`
这些基础镜像的 tag **会移动**，本项目**不钉它们的摘要**。
⇒ 只能声称「Python 运行时的版本集合可复现」。**升级前 `docker save` 仍是唯一可靠的回滚物**
（见上「升级前必做」）。

---

## 🔀 v0.9.0 多租户存量迁移（一次性 · 现网 rollout 前必读）

v0.9.0 引入多租户 C 方案（每租户独立 SQLite 文件）。业务库从单库锚点 `data/knot.db` 迁入
tenant#1 目录 `data/tenants/1/knot.db`，并新建平台库 `data/platform.db`（存 `tenants` 表）。

### 自动迁移（启动期，幂等 · 抗中途 crash 续跑）

首次启动 v0.9.x 容器时，启动序在 per-tenant `init_db()` **之前**自动执行迁移：

1. `PRAGMA wal_checkpoint(TRUNCATE)` 折 WAL + 关连接 → **COPY** `data/knot.db` → `data/tenants/1/knot.db`
2. **强校验**：表集合一致 + 关键表（users/audit_log/data_sources/conversations）行数一致 + 抽 1 条加密凭据解密烟测（证 `KNOT_MASTER_KEY` 未变）
3. 校验通过 → 把旧锚点 rename 为 `data/knot.db.pre-tenancy.bak`（**保留作回滚源**）
4. **校验不通过 → 删半成品 target，保锚点 `data/knot.db` 不动（last-good），并中止启动**（fail-closed，绝不带残缺库起服务）
5. **（v0.9.2 起）uploads.db relocation**：knot.db 迁移后同一启动内，data-root `uploads.db`（上传问数表库）**移入** `data/tenants/1/uploads.db`（crash-safe copy+校验+last-good；源备份 `data/uploads.db.pre-v0.9.2-relocation.bak`）。**独立无条件跑** —— 即使 knot.db 已在早前 v0.9.0 迁走（本次 `skip:migrated`），uploads 仍会迁（否则上传问数指向空库、旧上传数据孤儿）。无 data-root uploads.db（从未上传）→ `skip:fresh`。

**验证成功**（`docker logs knot | grep -E 'C4|uploads-reloc'`）：
```
[C4] 存量迁移完成（migrated）：…/data/knot.db → …/data/tenants/1/knot.db；旧库备份 …/data/knot.db.pre-tenancy.bak
[C4] tenant#1 存量迁移: migrated
[uploads-reloc] 完成（relocated）：…/data/uploads.db → …/data/tenants/1/uploads.db
```
全新部署（无 `data/knot.db`）会打印 `skip:fresh`（无存量可迁，正常）。

### 🔴 铁律：C4 迁移必先于现网 rollout

**严禁跳过迁移直接上 v0.9.x 现网**。生产 tenant#1 的 `db_dir='tenants/1'` ≠ 旧锚点 `data/knot.db`；
若旧数据仍在锚点而迁移未跑，`init_db()` 会在 `tenants/1/` 建**空库**起服务，旧数据在锚点**孤儿**（表面「数据没了」）。
自动迁移已内建，正常升级即闭合；此铁律针对**手动改 `SQLITE_DB_PATH` / 手动摆库文件**的运维场景。

> 安全阀：若 `data/tenants/1/knot.db` **已有用户业务数据**（>1 用户 / 有会话 / 配了数据源/知识/报表等）而旧锚点
> `data/knot.db` **仍在**，迁移会**拒绝覆盖并中止启动**（疑似在迁移前已上过现网写入了新库）。此时**人工核对**两库后手动处置，勿强迁。

### ⚠️ 多副本 / 多 worker 首次升级注意（v0.9.9 排练**实测**过，不再是推测）

迁移在启动期跑，并用数据根 `.c4-migration.lock`（`flock`）串行化**同节点**的多 worker/多进程启动。但
**跨节点共享卷（K8s RWM/NFS PVC）上的 `flock` 不保证跨节点互斥**。故首次从 v0.8.x 升 v0.9.x 时：

- **先以单副本迁移**（`replicas: 1`）确认日志出现 `[C4] tenant#1 存量迁移: migrated`（或 `skip:fresh`）后再扩容；
- 或把迁移放进 **init-container / 一次性 Job**（单实例先跑），应用副本再起。

（单 uvicorn / 单副本部署——KNOT 内测默认——无此问题；迁移是一次性操作，迁完后 `skip:migrated` 恒等幂等。）

#### 违反上面顺序时**具体会看到什么**（2026-08-01 本地 Docker 排练实测 · 3 副本同时首启共享卷）

排练刻意选了一个 **`flock` 不互斥**的挂载层（macOS bind-mount；**已直接验证**：两容器同时拿到同一把
`flock` 且等待 0.00s）—— 即上文「跨节点 RWM/NFS」的最坏形态。**实测结果**：

| 观察项 | 实测 |
|---|---|
| 3 副本结局 | 副本1 `resumed` ✅ · **副本2 exit=1 崩溃** ❌ · 副本3 `skip:migrated` ✅ |
| 崩溃报错 | `sqlite3.OperationalError: disk I/O error`，栈底 `tenancy_migration.py` `_backup_db` → `s.backup(d)`（备份快照进行中，源文件被另一副本 rename 走） |
| **业务数据** | ✅ **完好** —— `PRAGMA integrity_check=ok`，逐表行数与升级前**逐条相符** |
| **回滚源备份** | ✅ **完好** —— `knot.db.pre-tenancy.bak` 同样 `integrity=ok` + 行数相符 |
| 崩掉的副本重启后 | ✅ **一次即自愈** —— `skip:migrated` → startup complete → HTTP 200（K8s 表现为 `RESTARTS: 1`，**不是** CrashLoopBackOff） |
| 按规定顺序（先 1 副本迁完再扩 3） | ✅ **0 traceback**，3 副本全 `migrated`/`skip:migrated`，`platform_audit` **恰 1 条**（seed 与其审计一同幂等） |

**⇒ 运维要点（看到那个 traceback 时）**：
1. **不要去恢复备份、不要回滚** —— 数据和备份都是完整的，这是**启动期竞态**而非数据损坏；
2. **让它重启**（K8s 自动做）—— 迁移已被别的副本完成，重启即 `skip:migrated` 起来；
3. 事后仍应改成上面的规定顺序，因为 `disk I/O error` 这个报错**看起来像磁盘坏了**，会误导值班判断。

> ⚠️ **一处自我订正**：v0.9.8 设计论证里曾把这个场景描述为「并发写 ⇒ `database is locked` ⇒ **崩溃循环**」。
> 实测是**崩一次然后自愈，不循环**，且报错也不是 `database is locked`。那条论证的**结论**仍成立
> （同事务审计的价值在于它根本不需要在 raise 与吞之间选策略），但**严重性被我说过头了**——记此以免被后续引用。

### 🧪 内测服 v0.6.1.4 → v0.9.x 升级实操手册（**2026-08-01 本地 Docker 排练真走过一遍**）

内测服现网 = **v0.6.1.4**（无 2FA、无多租户），跨 v0.8（2FA 分水岭）+ v0.9（多租户）两道大坎。
下表每一行的产物都是**实测抄下来的**，不是照 spec 写的。

**排练怎么搭的**（可复现）：用 v0.6.1.4 **自己的代码**建一个忠实的旧库（而非手写 schema）→ 灌入
2 条 Fernet 加密数据源 + 3 用户 + 1 张上传问数表 → 停旧容器 → 用当前版本挂**同一个数据卷**起。

| 步骤 | 命令 / 观察点 | 排练实测 |
|---|---|---|
| 0. 备份 | `tar czf knot-data-$(date +%F).tgz data/`（含 `data/`**整目录**） | — |
| 1. 停旧版 | `docker stop knot && docker rm knot`（**必须关掉再起**，见上文硬前提 2） | 0s |
| 2. 起新版 | 同一个 `-v .../data:/app/knot/data` + 同一个 `KNOT_MASTER_KEY` | **4s** 到 `Application startup complete` |
| 3. 看迁移 | `docker logs knot 2>&1 \| grep -E 'C4\|uploads-reloc'` | `[C4] 存量迁移完成（migrated）：…/knot.db → …/tenants/1/knot.db；旧库备份 …/knot.db.pre-tenancy.bak`<br>`[uploads-reloc] tenant#1 uploads: skip:fresh`（从未上传过 ⇒ 正常） |
| 4. 核行数 | 逐表 `SELECT COUNT(*)` 与升级前对比 | `users 3` · `data_sources 2` · `audit_log 8` · 上传表 `3` · `file_uploads 0` —— **逐条相符** |
| 5. 核凭据 | 抽 1 条加密数据源比对密文前缀 | **逐字节相同**（迁移不重新加密 ⇒ `KNOT_MASTER_KEY` 没变就一定能解） |
| 6. 平台库 | `sqlite3 data/platform.db '.tables'` | 新建，含 `tenants` + `platform_audit`；tenant#1 行 `allowed_http_hosts=NULL` / `updated_at=NULL` |
| 7. 平台审计 | `SELECT * FROM platform_audit` | **恰 1 条**：`platform.tenant_create` / `system:boot` / `startup` / `{"db_dir":"tenants/1","seed":true}` |
| 8. 存量 token | 拿升级前的 token 打任意端点 | **401 `JWT_NO_TID`** ⇒ 全员被登出一次（**预期**，见硬前提 1） |
| 9. 重新登录 | 登录后解 JWT payload | `{"sub":"1","ver":1,"tid":1,…}` —— `tid` 已注入，正常工作 |
| 10. 启动 WARN | `docker logs knot 2>&1 \| jq -c 'select(.level=="WARNING")'` | ⚠️⚠️ **本行于 v0.9.19 订正** —— 原记录写「用 `grep -i warn` 认定它**真的响了**」，而**那次验证复现不出来**：该 WARN 走 **stdlib logging**，而当时 `logging_setup` **从不接管 stdlib root** ⇒ 它落 `logging.lastResort` = **裸消息、无 level 前缀**，且消息原文**没有 "warn" 字样** ⇒ `grep -i warn` **命中 0 行**。⇒ **那条「运维唯一观测口」当时在机制层就看不见。** v0.9.19 已加 `InterceptHandler` 把 stdlib 转发进 loguru（`tests/test_stdlib_logging_intercepted.py` 守）⇒ **从此按 `level` 过滤才是可靠判据**，`grep -i warn` 不是。 |
| 11. 备份文件 | `ls data/*.bak` | 两个 `.bak` **留在数据根不动**，且**不被当成数据库加载**（实测无副作用） |

**⚠️ 升级后必须补的一步（否则埋一个「以后才炸」的雷）**：给 tenant#1 显式配 `allowed_http_hosts`。
现在 NULL = 未配置 ⇒ 起源租户**回退** env `KNOT_HTTP_ALLOWED_HOSTS`（所以现网能正常跑），
但这条回退**只对起源租户成立**；SQL 原文见下文「多租户运维门」。

**🔒 本排练验证不到的一件事（诚实边界）**：从 v0.6.1.4 升级会**全新创建** `platform.db`
⇒ 两条平台迁移（`allowed_http_hosts` / `updated_at` 加列）都是 **no-op**，排练**没有真跑到它们**。
这一面由 v0.9.8 的「构造老平台库」单测覆盖（人工造一个缺列的 `platform.db` 再跑迁移），
不要因为排练全绿就以为平台迁移链被验证过了。

### 🔒 镜像的保密等级（v0.9.13 起 · **push / save / 分享前必读**）

**v0.9.13 之前**：仓库没有 `.dockerignore` 而 `Dockerfile` 是 `COPY . .`
⇒ **从工作树 build 的镜像里含 `.env`（master key / JWT / DB 密码 / LLM key）、`.git` 全历史、
`knot/data` 全部租户库与备份**。⚠️ **2026-08-01 实测复现过两次**（那两个镜像已销毁 + build cache 已清）。
⇒ **v0.9.13 之前构建的任何镜像都按「含活凭据」处置**：不得 push 到任何 registry、不得外发。

**v0.9.13 起**：`.dockerignore` 已排掉凭据 / 历史 / 租户库 / 备份 / venv / node_modules
（构建上下文实测由 ~640M 降到 **17M**），由**阻断 CI job** `build context leak guard` 守
（`FROM scratch` + tar exporter，零 registry 拉取；含 8 族 canary 的逐族 mutant）。

⚠️⚠️ **但镜像仍不是「可公开」的** —— **截至本片，镜像内仍含业务私有 catalog**
（`knot/services/agents/_local_catalog.py`：**真实库表名 / 字段 / 业务口径**）。
它 `.gitignore` 标了业务隐私，却仍随 `COPY . .` 进镜像。
⇒ **镜像的 `docker push` / `docker save` / 对外分享，仍有保密要求，须按业务私有数据对待。**
（下一片改 bind-mount 后才会从镜像里消失 —— 本片刻意不排它：直接排会让 file 层落模板
⇒ HTTP 查询静默落 SQL，那是 R-v096-4 明禁的后果。）

---

### 🔴 回滚前置：**升级前必须 `docker save` 现网镜像**（v0.9.9 排练发现 · 高优先级）

**「重新 build 旧 tag」不能回到现状，因此它不是一条可靠的回滚路径。**

根因：`requirements.txt` **全部用 `>=` 不钉版本**（v0.6.1.4 与今天都一样）⇒ 今天重建旧 tag 装到的是
**今天的依赖**。**排练实测坐实**：v0.6.1.4 的代码 + 今天的 SQLAlchemy（2.0.51）⇒ **上传功能当场 500**
（`List argument must consist only of dictionaries` —— 那是 v0.8.19 才修的 bug）。
⇒ 重建旧 tag 得到的是「**代码是旧的、依赖是新的**」这个**从未存在过、也从未被测过**的组合。

**两个动作项**：

```bash
# 1. 升级之前，把现网正在跑的那个镜像导出留存 —— 这是唯一可靠的回滚物
docker save <现网镜像:tag> | gzip > knot-rollback-$(date +%F).tar.gz
#    K8s 下先在节点上 crictl/docker 找到实际在跑的 image digest，按 digest 存，别按 tag 存
```

2. **独立于升级的 backlog：给 `requirements.txt` 钉版本**（或产出一份 lock）。在此之前，
   **「重新部署当前版本」本身就是一个有风险的动作** —— 换节点 / 清了本地镜像 / CI 重跑都会触发重建，
   可能当场坏在**与升级完全无关**的地方。

### 回滚（v0.9.x → v0.8.x）

```bash
docker stop knot && docker rm knot
cd /path/to/knot/data
mv knot.db.pre-tenancy.bak knot.db     # 旧锚点复位（回滚源）
# v0.9.2 起 uploads.db 已迁进 tenants/1/ —— 反向快照回滚（用租户内最新版，非陈旧 root .bak）：
[ -f tenants/1/uploads.db ] && cp tenants/1/uploads.db uploads.db   # 租户内 uploads 回搬 data-root
rm -rf tenants platform.db             # 清多租户产物（旧版本不认）
# 再用 v0.8.x 镜像启动
```
> 回滚窗口内旧锚点 `.pre-tenancy.bak` 是完整业务库；迁移后若已在新库写入数据，回滚会丢失这部分增量 —— 故回滚应在**升级后尽早**决策。

---

## 📊 内测期运维监控项

| 信号 | 怎么看 | 该关注啥 |
|---|---|---|
| **boot 日志** | `docker logs knot` | "已加载（Fernet）" + "Uvicorn running" |
| **错误日志** | `docker logs knot 2>&1 \| grep -i error` | 极少；持续报错需诊断 |
| **DB 增长** | `du -sh data/tenants/1/knot.db data/platform.db` | 5-10 人内测预期 < 50MB / 周 |
| **F-A 用户反馈** | admin 浏览器 → API `/api/admin/feedback` | 👍/👎 数量 + 评论质量集中点 |
| **F-B 前端错误** | admin 浏览器 → API `/api/admin/frontend-errors` | 应极少；持续上报需修 |
| **F-C audit 自动清理** | `docker logs knot \| grep audit_auto_purge` | 7 天阈值后自动跑 |
| **LLM 成本** | admin → 预算 + Recovery 屏 | 实际 spend vs 阈值，超阈值会发 banner |
| **DataSources 心跳** | admin → 数据源 tab Hero 卡片 | "上次心跳 < 5 min" 表示连接正常 |

---

## ⏰ BI 报表定时刷新调度器（②c · v0.8.17）

BI 报表的定时刷新由**外部 K8s CronJob 敲钟**（应用内无常驻调度进程 → 多副本天然安全、无重复 fire）。

### 1. 设置调度 token

```bash
# 生成一个随机 token，写入 .env / K8s secret（与下面 CronJob Header 一致）
echo "KNOT_SCHEDULER_TOKEN=$(openssl rand -hex 24)" >> .env
```

> **未设 `KNOT_SCHEDULER_TOKEN` → tick 端点返回 503（调度 disabled）** —— 安全默认，不会误触发。

### 2. K8s CronJob（每 15 分钟敲一次）

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: knot-bi-scheduler-tick
spec:
  schedule: "*/15 * * * *"          # 每 15 分钟；tick 内部按各报表 next_run_at 判定是否到期
  concurrencyPolicy: Forbid          # 不重叠（原子认领也兜底防双打）
  jobTemplate:
    spec:
      template:
        spec:
          restartPolicy: Never
          containers:
            - name: tick
              image: curlimages/curl:latest
              args:
                - "-sS"
                - "-X"
                - "POST"
                - "-H"
                - "Authorization: Bearer $(KNOT_SCHEDULER_TOKEN)"
                - "http://knot-svc:8000/api/bi/scheduler/tick?tenant=default"   # 集群内 Service 名（单外部触发→只打一个 pod）
                # ⚠️⚠️ **v0.9.17 破坏性变更：`tenant` 必填**（缺它 → 422，一次刷新都不会跑）。
                #   单租户部署填 `default`（起源租户的 slug）即可。
                #   **多租户**：CronJob 需**逐租户各敲一次** —— 清单从 `GET /api/platform/tenants` 取
                #   （只读端点，用平台密钥）。⇒ 每次触发只作用于**一个**租户。
                #   ⭐ 为什么不让服务端「一次遍历所有租户」：那会把「**一个全局密钥能 fan-out 所有租户**」
                #     固化成设计（它是独立的跨租户操作权问题）。逐租户调用让触发的作用面是**一个**租户。
              env:
                - name: KNOT_SCHEDULER_TOKEN
                  valueFrom:
                    secretKeyRef:
                      name: knot-secrets
                      key: KNOT_SCHEDULER_TOKEN
```

### 3. 报表侧配置

analyst / admin 在 BI 报表工具栏点「定时」→ 设节奏（每天 / 每小时 / 每 N 小时）+ 触发时刻（Asia/Shanghai）。
需 `can_schedule` 权限（admin 恒有；analyst 由 admin 在「目录权限」授）。刷新纯重跑冻结 SQL（0 LLM 成本）；
失败在弹窗 fire 台账可见。**建议每日节奏落在上游数据 ETL 产出之后**（如 08:00 CST，报表本身是 D-1 窗口）。

> 时区：tick 用 Asia/Shanghai 墙钟计算 next_run（非容器 UTC）。CronJob 频率只需 ≤ 最细节奏（每小时→CronJob ≤1h）。

## 🔐 静态明文凭据巡检（v0.9.12 起）

**一条只读命令**（不改任何数据；退出码 0=干净 / 1=有发现 / 2=跑不起来，可直接进巡检脚本）：

```bash
docker exec knot python3 -m knot.scripts.scan_secrets_at_rest --all-tenants
```

加 `--verify-key` 会**额外**用当前 `KNOT_MASTER_KEY` 试解每个密文，回答「key 对不对」——
⚠️ **廉价判据看不出 key 错了**（混 key 库里所有值都是「某把 key 的合法密文」）。

**启动期也会自己扫一遍**，发现明文则每租户一条 WARN（**不阻断启动** —— 老数据带明文是合法状态，
拦启动等于升级即自造停机）：

```
⚠️ [secret-at-rest] tenant#1 存在**明文**敏感值 2 处：users.doris_password(pk=1)、… —— 修：…
```

**处置**：
```bash
docker exec knot python3 -m knot.scripts.migrate_encrypt_v045 --tenant 1     # 先 --dry-run 看会改什么
```
该脚本自带三道保护：**写前**全量试解密（key 不对则**零写入零备份**）· WAL-safe 备份（`0600`）·
跑完在同一次运行内核实，仍有明文则**报错不声称成功**。

### ⚠️ 历史 `.bak` 里可能有明文（加密只能往前修）

`data/` 下的历史备份（`*.audit-purge-*.bak` / `*.pre-tenancy.bak` / `*.v044-*.bak`）是**当时**的快照
⇒ 若当时有明文凭据，它们**至今仍是明文**。加密现网库**不会**改动这些文件。

**事故响应清单** —— ⚠️ **两件事，别混**（守护者 v0.9.12 Stage 4 §VI）：

### (甲) 减面 —— **现在就能做，不依赖任何轮换决定**

⭐ **不轮换 ≠ 不能减面。** 历史 `.bak` 里的明文是**现在就可以处理掉**的（删除或加密归档）。

```bash
cd /path/to/knot/data
# ⚠️ 必须 **递归** + 必须连旁文件一起（两个坑见下）
find . -name '*.bak' -o -name '*.bak-wal' -o -name '*.bak-shm' | sort
find . \( -name '*.bak' -o -name '*.bak-*' \) -exec du -ch {} + | tail -1   # 总体积
```

⚠️⚠️ **两个坑，都是实测踩出来的（v0.9.12）**：

**坑 1 —— 必须递归。** `.bak` **不只在数据根**：`tenants/<id>/` 里还有
（`knot.db.audit-purge-*.bak` 由启动期清理生成、`knot.db.v044-*.bak` 由加密迁移生成）。
**实测**：数据根 `ls *.bak` 看到 **10 个**，而 `find . -name '*.bak'` 是 **12 个** ——
漏掉的 2 个在 `tenants/1/`，**5.9M**。⇒ 用 `find`，别用 `ls *.bak`。

**坑 2 —— 旁文件看不见，而且会自己长回来。** `-wal` / `-shm` 是 SQLite 的 WAL 旁文件，
`*.bak` 通配符**匹配不到**它们；且**任何一次只读打开 `.bak` 都会重新生成 `-shm`**
（实测：备份刚建完**没有**旁文件；只读打开一次后就出现）。
⇒ **盘点动作本身会增加文件** —— 实测一次盘点（逐个打开 12 个 `.bak` 读表结构）就多造了 ~10 个旁文件。
⇒ **清理放在最后一步做，或做完盘点后再 `find` 一遍**。

- **恢复时只需 `.bak` 主文件**（旁文件是读产物，可直接删）；
- **删除/归档时连旁文件一起**（否则残留半套，且下次 `ls *.bak` 看不到它们）。

### (乙) 轮换 —— 需要账号持有人操作

对仍有效的凭据做轮换：**DB 密码 · LLM API key · 飞书/TG 凭据**（涉 3 张表：
`users` / `data_sources` / `app_settings`）。

> **当前决定（kk 2026-08-01）**：**暂不轮换，继续用现有凭据。**
> ⚠️ 如实登记残留风险（不是提醒，是防它静默蒸发）：加密**只能往前修** ——
> 那些值在历史 `.bak` 里的明文暴露**仍然存在**，直到按 (甲) 减面或按 (乙) 轮换。

### (丙) 收尾

两件做完后再跑一次上面的只读巡检，确认现网库干净（应报 `0 处明文` + 退出码 0）。

---

## 🆘 故障排查

### 启动失败

| 现象（docker logs knot 错误） | 排查 |
|---|---|
| `KNOT 启动失败 — JWT_SECRET 配置无效` | `.env` 没设 `JWT_SECRET=` 或仍是默认占位 → 重跑 `bash scripts/deploy_checklist.sh` |
| `KNOT 启动失败 — 缺少加密主密钥` | `.env` 没设 `KNOT_MASTER_KEY=` → 同上 |
| `cryptography.fernet.InvalidToken` | `KNOT_MASTER_KEY` 被改了 → 必须用历史那个 key（密码管理器找） |
| `sqlite3.OperationalError: no such column` | DB schema 不兼容（极少见）→ 联系开发 |
| `[uploads-reloc] … 拒绝以损坏库起服务` | 上传库 `data/tenants/1/uploads.db` 探针不健康（**fail-closed，故意不启动**）。① 错误信息里带 sqlite 原因：`OperationalError`（锁竞争/权限）→ **重启即恢复**，真损坏才持续复现；② 确损坏且有备份 → 还原到 **`tenants/1/uploads.db` 本身**（勿还原到 `data/`，那会撞下面那条安全阀）；③ 确损坏且不需历史上传 → 删除该文件后重启（走 `skip:fresh`，用户重新上传；上传元数据在 knot.db 内，源文件在用户本地） |
| `[uploads-reloc] … 疑似 C1-C3 在 relocation 前上了现网写入。拒绝覆盖` | `data/uploads.db` 与 `data/tenants/1/uploads.db` **同时存在且后者已有上传表** → 迁移拒绝覆盖现网数据。人工核对哪份是最新（比 `t_*` 表与行数），保留最新的那份到 `tenants/1/`、把 data-root 那份改名挪走，再启动 |
| `[C4] … 拒绝以空/损坏库起服务` | 租户主库 `data/tenants/1/knot.db` 空或损坏（同为 fail-closed）→ 若有 `data/knot.db.pre-tenancy.bak` 按「回滚」段人工恢复；否则排查掉电/磁盘故障 |
| `[uploads-reloc]`/`[C4]` 之外：catalog 相关 `TenantContextError` | v0.9.3 起 catalog 载体 per-tenant 且 **fail-closed**：任何无 tenant ctx 的路径读 catalog 会抛而非静默降级（刻意的 —— 降级会让脱敏 no-op / 把部署级 file catalog 当成该租户内容）。排查：该请求/脚本是否漏 set tenant ctx；CLI 见 `scripts/eval_*.py` 的 `_with_tenant_ctx()` 写法 |

### 运行时问题

| 现象 | 排查 |
|---|---|
| admin 登录失败 / 密码改了不生效 | 改 `.env` 后忘记 `docker restart knot` |
| 浏览器看到旧版本号 | 浏览器强缓存 — Cmd+Shift+R 硬刷新 |
| LLM 报 "429 rate limit" | OpenRouter 余额不足 / 单 key QPM 限流 → 充值或升级 plan |
| LLM 报 "401 unauthorized" | OPENROUTER_API_KEY 失效 → admin UI 重新填 |
| 数据源探测失败（红色 ●） | 检查 Doris/MySQL 网络可达 + 用户权限 + IP 白名单 |
| 启动慢 / 时不时卡顿 | 检查内存（推荐 ≥ 2GB） + SQLite WAL 文件大小 |
| docker logs 见 "audit_auto_purge 失败" | silent fail 不影响业务 — 但可启动 `docker exec knot python -m knot.scripts.purge_audit_log --dry-run` 诊断 |

### 体验类问题

| 现象 | 排查 |
|---|---|
| 切屏返回首页慢 | v0.6.1.2 已修（App.jsx 数据 lift）— 升级到 ≥ v0.6.1.2 |
| 数据源 / 用户 tab 显示"暂无 XXX" 久 | v0.6.1.2 已修（loading state）— 升级到 ≥ v0.6.1.2 |
| 收藏页与对话页的 icon 不一致 | v0.6.1.1 已修（统一 bookmark） |
| 问元数据问题（如"有哪些表"）误判空集 | v0.6.0.9 已修（presenter meta-query 规则） |

---

## 🔒 安全 / 密钥管理 FAQ

### Q1: 我能改 KNOT_MASTER_KEY 吗？
**不能** — 改了之后所有加密数据（数据源密码 / API Key）**永久无法解密**。如果一定要改：
1. 先**备份**整个 `data/` 目录（v0.9.0 起业务库在 `data/tenants/`、平台库 `data/platform.db`）
2. admin 进 UI 把所有数据源 / API Key **重新填一遍**
3. 再改 key 重启

### Q2: 我能换 JWT_SECRET 吗？
**可以** — 改完所有用户当前 token 失效（需要重新登录）。其他数据不影响。

### Q3: KNOT_MASTER_KEY 应该多复杂？
- 由 `Fernet.generate_key()` 生成，**44 字节 base64**，密码学安全
- 不要自己手写 / 用密码生成器 — 必须 Fernet 接受的格式

### Q4: 密码管理器存哪个？
- `KNOT_MASTER_KEY` — **必存**（终身密钥）
- `JWT_SECRET` — 可存（可换）
- admin 登录密码 — 必存
- OpenRouter API Key — 已经在 OR 后台，可不存

### Q5: admin 初始口令怎么拿 / 多久必须改？
v0.8.20 起**无固定默认 admin123**：设 `KNOT_INITIAL_ADMIN_PASSWORD` 则用之，未设则首启随机生成、**在启动日志打印一次**（`docker logs knot | grep "seed admin"`）。**部署后尽快首登**（must_change_password 强制改密 + 强制 enroll）；随机口令仅一次可见，遗失用 `python -m knot.scripts.reset_admin_password --tenant <slug|id>` 重置（**`--tenant` v0.9.15 起必填**，单租户部署传 `--tenant 1`）。

---

## 📖 v0.6.0.9 部署后可用功能

- ✅ **3-Agent 异步管线** — Knowledge → Nexus → Objective → Trace
- ✅ **OpenRouter 14 模型** + max_context 字段（OR live API 实测）
- ✅ **笛卡尔积 6 层防御** + execute_sql 路径守护
- ✅ **用户反馈 👍/👎** + 可选评论（F-A）
- ✅ **前端 JS 错误自动上报** + PII 三层防御（F-B）
- ✅ **audit_log INSERT-only + 7 天自动清理**（F-C）
- ✅ **OpenRouter live catalog 同步**（admin "从 OpenRouter 同步" 按钮 F-D）
- ✅ **时间语义引擎** — 5 类核心表达 + 同比基准 + 2026 节假日（v0.6.1）
- ✅ **数据加载预取**（v0.6.1.2 — 切屏不再重新 fetch）
- ✅ **DataSources Hero stats** 实时探测 + 5min cache（v0.6.1.3）
- ✅ **JWT_SECRET fail-fast** + 历史占位拒收（v0.6.0.8 MUST-1）
- ✅ **CI 3-job 精简**（v0.6.0.9 — 配额节省 60%）

---

## 📞 求助渠道

- **issue**: https://github.com/kkleonnnn/knot/issues
- **R-PA-5 内测追踪**: issue #75
- **AI 助手**: 直接把本文档 + 报错截图发给 AI 即可
- **资深架构师**: 内部联系

---

> 本文档跟随每次发版同步。最新版本通过 `git log -1 -- DEPLOY.md` 查看最近更新时间。

---

## ⚠️ 升级到 v0.9.4 的三条硬前提（部署策略 + 链接分发）

**1. 升级后全员须重登一次（预期行为，不是故障）。**
v0.9.4 起 JWT 必须带 `tid`（公司编号）claim；**升级前签发的存量 token 一律 401**（判别式是 tid 有无，
不是版本号）。前端 401 拦截器会自动清 token + 跳登录 ⇒ 用户体感 = **被登出一次**。请提前告知在测用户。

**2. ⚠️ 部署策略必须是「关掉再起」（K8s `Recreate` / `maxSurge=0`）。**
现网策略已确认为关掉再起 ⇒ 新旧版本**不会同时 serving**，本条已满足。**但这是本片的硬前置条件，
不是注释**：若将来把策略改成 `RollingUpdate` / `maxSurge≥1`，新旧 pod 对**同一枚 token 判定相反**
（旧 pod 签发无 tid 的 token、新 pod 拒收）⇒ **登录抖动循环**：新 pod 401 → 前端清 token + reload →
重登命中旧 pod → 又拿到无 tid token → 再打新 pod 又 401 …
→ **改策略前**必须先做「旧版本禁止继续签发无 tid token」或摘流（单次 bump `token_version` **不充分**：
判别式是 tid 有无，与版本号无关）。

**3. 每家公司的专属登录链接。**
v0.9.4 起登录支持 `?c=<公司代号>`（代号 = 平台库 `tenants.slug`）：

```
https://<你的域名>/?c=<公司代号>
```

登录页会回显该代号（只回显代号本身、**不显示公司名** —— 显示名字等于确认该代号存在，可被用来枚举客户）。

**代号从哪来**：`GET /api/platform/tenants`（只读端点，用平台密钥）返回每家的 `slug`。
⛔ **不要靠 `ls data/tenants/` 猜** —— `db_dir` 是服务端生成的不透明随机串，与代号无关。

### ⚠️ lift（放开第二家公司）之前必须做的一件运维事

**给每家公司发它自己的链接，并让所有人换掉旧书签。**（kk 2026-08-06 裁定：发专属链接，
**不在登录页加公司输入框** —— 前端不动。）

| 时点 | 不带 `?c=` 的旧链接 |
|---|---|
| **现在**（单租户） | ✅ 仍可用（后端回退到唯一 active 租户） |
| **lift 之后**（≥2 家 active） | ⛔ **一律 401** —— 见下 |

⭐ **lift 后旧链接失效是设计，不是 bug**：回退走 `resolve_single_tenant()`，它在 active **≠1** 时
**raise** ⇒ 无代号登录**全部 401**，**绝不会「挑一个」公司进**。
⇒ 所以这是**可用性**问题（老链接失效），**不是跨租户访问风险**
（该性质由 `tests/api/test_two_tenant_e2e_isolation.py::
test_no_slug_login_with_two_active_tenants_is_401` 守）。
⚠️ 代价是那时的报错是**统一的「账号或密码错误」**（防公司枚举，见下一节）——
运维会看到用户报「密码明明是对的」。**这就是为什么要提前发链接，而不是等 lift 之后再补。**

---

## 🔑 平台管理面密钥 `KNOT_PLATFORM_ADMIN_TOKEN`（v0.9.5 起）

平台面（跨租户视角）与租户 admin 是**两套互斥的凭证** —— 租户 admin 的 JWT **进不了**平台端点，
平台密钥也**进不了**任何租户端点（实测双凭证矩阵 4 格）。

| 项 | 说明 |
|---|---|
**是否必配** | **否**。未配置 = 平台面**禁用**（端点返 503）。单租户部署无需配置。 |
**格式要求（硬闸）** | `kpa_` 前缀 + **不含 `.`** + **≥32 字符**。任一不满足 → 端点 503 + **启动期 WARN**。 |
**为什么禁 `.`** | JWT（JWS compact）**恒含 2 个 `.`** ⇒ 禁 `.` 使平台密钥**在语法上不可能是一枚 JWT**，反之亦然。这封掉「误把一枚有效用户 JWT 配成平台密钥」的自我破坏路径。 |
**生成** | `echo "kpa_$(openssl rand -hex 24)"` |
**存放** | K8s Secret / `.env`（**不入 git**）。 |
**⚠️ 轮换** | **改 env + 重启**。 |
**⚠️⚠️ 无吊销机制** | 它**没有 `token_version` 等价物**（租户 JWT 有）⇒ **无法「注销所有会话」**。密钥一旦外泄，唯一手段是**换掉 env 并重启**；在那之前旧密钥一直有效。 |
**⚠️ 无「谁做的」身份** | out-of-band 共享密钥不携带身份 ⇒ 平台侧动作**无法审计到人**。这也是 v0.9.5 **刻意零平台写操作**的原因（只有一个只读端点 `GET /api/platform/tenants`）。 |
**不得进入的地方** | **日志 / 前端存储 / 报错响应**。服务端只记 env **名** + 不合规**原因**，**永不记值**（守护：`tests/test_no_env_value_in_messages.py`）；503 响应连「不合规原因」也不给（否则等于告知调用方本部署配了弱密钥 + 期望格式）。 |

> ⚠️ **平台端点不是运维逃生舱**：R-T-GATE 硬门在请求解析的**第一行** ⇒ 出现第二个 active 租户时
> **整站（含 `/api/platform/*`）全部 fail-closed**。故障预案**不要**依赖它。

---

## 🏢 开通一家新公司（v0.9.15 起 · `POST /api/platform/tenants`）

**前置**：平台密钥已配（`kpa_` 前缀 · 禁含 `.` · ≥32 字符），见上文平台面小节。

```bash
curl -sS -X POST http://<host>/api/platform/tenants \
  -H "Authorization: Bearer $KNOT_PLATFORM_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"slug":"acme","name":"Acme Inc","allowed_http_hosts":"api.acme.example","allowed_webhook_hosts":"hooks.acme.example"}'
```

**返回 201**：`{"tenant": {...}, "initial_password": "<仅此一次>", "resumed": false}`

### ⚠️ 四条必读

1. **开出来的租户是 `suspended`（不可服务）** —— 服务端强制，请求与登录两条解析路径**都看不见它**。
   「激活」是 **lift R-T-GATE 之后**的独立动作（且直接 `UPDATE` 前请读下文运维门）。
2. **`initial_password` 只给一次** —— 不入库（只存 bcrypt 哈希）、不进日志、不进审计。
   **丢了不能再查**，恢复路径是显式重置：
   ```bash
   python -m knot.scripts.reset_admin_password --tenant <slug>
   ```
3. **两份 allowlist 都必填，且 `""` 与「不传」语义不同**：
   - `allowed_http_hosts` —— **读**数据源（HTTP 实时接口）能连哪些主机；
   - `allowed_webhook_hosts` —— **发**告警（webhook）能发到哪些主机（v0.9.18 起）。

   `""` = 部署方明确的「**禁止出网**」；不传 = **422**（**刻意不给默认值** —— 否则开通动作
   就替你静默选了一种语义）。三态含义见 `platform_schema.sql` 的列注释。
   ⚠️ **两者方向相反、严禁混用**：一份管「往外读」、一份管「往外发」。
   ⚠️ **将来若再加第三份 allowlist，本段与上面那条 `curl` 都要同步** ——
   它们由 `tests/test_doc_invariants.py::test_deploy_provision_curl_covers_all_required_fields`
   从 `TenantCreateRequest` **派生校验**（漏一个即红），不必靠人肉记得。
   ⚠️ 本条 v0.9.18 加了 `allowed_webhook_hosts` 之后**手册漏改了一版** ——
   那版的 `curl` 照抄会直接 422，而文档写着「返回 201」。那次漏改正是本哨兵存在的理由。
4. ⛔ **别靠目录名认租户**（Stage 3 Q1）：`db_dir` 是服务端生成的**无意义随机串**
   （如 `tenants/43b658915072c9b2`），**刻意不可辨识、且不可更改**。
   要查「哪家公司对应哪个目录」请用 `GET /api/platform/tenants` 或 `GET /api/platform/audit`
   —— **不要** `ls data/tenants/` 然后自己发明一套猜法。
   ⚠️ 为什么不用公司代号当目录名：代号是调用方传的且**无格式校验** ⇒ `../` 就能让库建到
   数据目录之外；且 macOS/Windows 文件名**不分大小写**而 `UNIQUE(slug)` **分** ⇒
   `AcmeCo` 与 `acmeco` 会是两家公司**共用一个目录**。

### 幂等 / 续做（重复调用同一个 slug 会怎样）

| 状态 | 行为 |
|---|---|
| 该 slug 不存在 | 正常开通 |
| 行已存在 + `suspended` + **库还没建** | **续做**（补建库 + 返回**新**的初始口令 —— 库是全新的） |
| 行已存在 + `suspended` + **库已建好** | **409 拒绝**，消息指向 `reset_admin_password --tenant` |
| 行已存在 + `active` | **409 拒绝**（不碰在服务的租户） |

⚠️ 第三行「不续做」是**唯一不猜的选择**：此时无法区分「上次建库后被中断」与
「一个真实在用、只是被停用的租户」—— 续做会重置一个**可能在用**的租户的管理员口令。

### 起源租户（tenant#1）的两条禁令

- ⛔ **不得停用**（写口会拒）：它是 file catalog 层（部署方的真实库表/词典/业务口径）的唯一归属者。
  停用它 ⇒ 若另有 active 租户则**服务仍能起来**，而 file 层对被服务租户**静默变空**
  （查询不报错、只是什么都查不到）。真要下线整个部署请**停进程**。
- ⛔ **`db_dir` 不得修改**（写口会拒）：改指向而**数据不跟着搬** ⇒「租户还在、数据不见了」。
  要搬数据是一次显式迁移：停用 → 搬文件 → 校验 → 改指向。

---

## 🔒 私有 catalog（v0.9.16 起不进镜像）

**这是什么**：`_local_catalog.py` 是**部署方自己写的**业务 catalog（真实表名 / 字段词典 /
业务口径 / 表间关系），`few_shots.yaml` 同理（真实问法样例）。两者**从来不在仓库里**
（`.gitignore` 已排），但 v0.9.16 之前会被 `COPY . .` **烤进镜像** ——
镜像一旦分发/推仓库，业务口径就跟着走了。

**v0.9.16 起**：两个文件排出构建上下文，改为**运行时挂载**。

```bash
# 只读挂载（推荐 :ro —— 应用只读它，不写）
-v /opt/knot/_local_catalog.py:/app/knot/services/agents/_local_catalog.py:ro
-v /opt/knot/few_shots.yaml:/app/knot/services/few_shots.yaml:ro          # 可选
```

| 情形 | 后果 |
|---|---|
| **挂了** | 与 v0.9.15 之前**完全一致** |
| **没挂**（只用 SQL 数据源） | 正常工作 —— file 层退回仓内 `_template_catalog.py`；启动日志一条 WARN |
| **没挂**（但用 HTTP 数据源） | ⚠️ HTTP 虚拟表消失 ⇒ 实时接口查询**会落 SQL**。**启动日志会明确告警**，不是静默 |

⚠️ **最后一行是本片的承重点**：直接排除而不加告警 = 把一条泄漏换成一条**静默的正确性回归**
（R-v096-4 明禁）。所以排除与 WARN 是**同一个决定的两半**，别只做一半。
守护：`catalog_loaders.warn_if_private_catalog_missing`（缺则响 / 在则静默，双向实测）。

**k8s**：用 `ConfigMap` 或 `Secret` 挂同样两个路径（`subPath` 挂单文件）。

## ⛔ 破坏性 CLI 一律要显式 `--tenant`（v0.9.15 起 · **一次真实事故立的规矩**）

**规则一句话：破坏性工具不得有默认目标。**

**为什么**：这些脚本原先在缺目标时会回退「唯一 active 租户」。在只有一个租户的年代那无处可错；
**v0.9.15 起新开通的租户是 `suspended`** ⇒ 回退**恒选中起源租户（= 部署方自己）**，
而你此刻心里想的是那个新租户 ⇒ **动作静默作用在错误的库上，输出照样报「完成」**。
（这不是推理：v0.9.15 Stage 4 期间它真的发生过一次 —— 一个被静默吞掉的 flag
重置了起源租户的 admin 口令，且看不出任何异常。）

| 脚本 | 目标参数 | 只读模式 |
|---|---|---|
| `reset_admin_password` | `--tenant <slug\|id>` **必填** | 无（本就是写操作） |
| `migrate_encrypt_v045` | `--tenant <id>` 或 `--all-tenants`，**必填其一** | `--dry-run`（仍需目标） |
| `purge_audit_log` | `--tenant <id>` **真跑必填** | `--dry-run` **可不带目标**（0 副作用，且会打印它解析到了谁） |
| `scan_secrets_at_rest` | `--tenant` 可选 | **只读 CLI**，回退无害 |

⇒ 单租户部署一律传 **`--tenant 1`**（起源租户恒为 id=1）。
⇒ 列出租户 id / slug：`GET /api/platform/tenants`（**不要**靠 `ls data/tenants/` 猜 ——
`db_dir` 是服务端生成的不透明随机串，刻意不可辨识）。

## ⚠️ 多租户运维门（v0.9.3 起 · lift R-T-GATE 前）

- **`replicas=1`**（⚠️ **v0.9.7 订正了这条的理由** —— 原文写「不同副本可能停在**不同租户的** catalog 上」，
  那是 **v0.9.3 之前**的症状；v0.9.3 已把 catalog 改成**按租户分槽**，同一请求在任何副本上都用**本租户**的槽。
  原文与它自己那一片的改动矛盾，已按实读重写）：

  **多副本下真实的问题是「一个副本上的变更传不到其他副本」+「限流按副本各算一份」**，逐项实读如下：

  | 进程内状态 | 多副本后果 | 严重性 |
  |---|---|---|
  | catalog 槽 | `pick_http_route` **每 query 无条件 reload**（`http_planner.py:134`）⇒ 跨副本陈旧**当场自愈** | 很低 |
  | JWT 吊销版本缓存 | `TTLCache(ttl=60)` ⇒ 改密/重置后，**别的副本最多晚 60 秒**才拒旧 token | 低（有界） |
  | **数据源引擎缓存** | `_TTL_SEC = 3600` ⇒ admin 改了数据源连接信息后，**别的副本最多 1 小时**仍用旧连接/旧凭据 | **中**（会产生用户可见的失败） |
  | **限流桶** | 模块级 `_Bucket()` 每副本一份 ⇒ **有效限额 × 副本数**（登录爆破防护被削弱 N 倍） | **中** |
  | 数据源健康 / 统计缓存 | 各副本各自探测 | cosmetic |

  ⇒ **多租户场景仍请保持单副本**，但要修的其实只有**加粗那两项**；两项都有**零新依赖**的解法
  （引擎缓存改「比对数据源行的版本号」而不是靠 TTL；限流改共享计数器 —— 登录类本就低频，
  写平台库可接受，查询类另议）。**不需要引入 Redis**（详 `docs/plans/v0.9-lift-arc-remaining-plan.md` D-E）。
  单租户部署不受此限（今日 R-T-GATE 硬锁第二租户，故现网即单租户）。
- ✅ **file catalog 已归起源租户独占**（v0.9.4 登记 → **v0.9.6 已闭合**）：
  `_local_catalog.py`（部署方的真实业务表名 / 词典 / 业务口径 / 关系）只对**起源租户**可见；
  其余租户在唯一 choke point `catalog_loaders.load_file_layer()` 拿到**完整的空**五元组
  （**刻意不是半空** —— `business_rules` 若还回落文件层，等于继续泄漏部署方口径）。

  ⚠️ 原登记写的是「对**每个**租户可见…开通第二租户前必须先做」——**那句自 v0.9.6 起为假**，
  本手册漏改了。⇒ 它**不再是**开通第二租户的前置项。
- ✅ **HTTP 虚拟表凭据 + 出网白名单已 per-tenant 化**（v0.9.7 B-3 ②③ —— 原「走进程 env、租户盲」已闭合）：
  - **凭据**：`http_spec` 必须带 `source_id` → 指向**该租户库**的 `data_sources` 行（`http_config` 走 Fernet）。
    env 引用形态（`base_url_env` / `auth_*_env`）已**物理删除**；`adapters/http/executor.py` 现在**零 env 读取**
    （配 AST 哨兵）。⚠️ **升级影响**：若你的 `_local_catalog.py` 里还有 env 形态的 http 表，
    升级后它会**软降级落 SQL**（并记日志 `[http_route] spec 未绑租户数据源`）—— 改法：在 admin UI 建
    一个 `db_type='http'` 数据源，把 `http_spec` 改成 `{"source_id": <该源 id>, …}`。
  - **出网白名单**：改读平台库 `tenants.allowed_http_hosts`（逗号分隔）。**起源租户（tenant#1）在该列为
    `NULL` 时回退 `KNOT_HTTP_ALLOWED_HOSTS`** ⇒ **现网 ConfigMap 不动即可继续工作**（启动期会 WARN 提示迁移）。

  ### ⚠️ 先读这一条（v0.9.19 订正 —— 此前本手册的运维指令在容器里跑不了）

  **`sqlite3` CLI 此前不在镜像里** —— 基础镜像 `python:3.11-slim` 不带它，而 Dockerfile 也没装
  （实测 `docker run --rm python:3.11-slim which sqlite3` → 无）。
  ⇒ **下面这些 `sqlite3 …` 指令，自 v0.9.7 写下之日起就跑不了**，而手册一直照着写。
  **v0.9.19 已在 Dockerfile 装上它** ⇒ 现在可用。

  ⭐ **但复核请优先用这条**（不需要判读、也不需要 `sqlite3`）：

  ```bash
  kubectl exec -n <ns> <pod> -- python3 -m knot.scripts.show_tenant_allowlists
  ```

  它逐租户打印**每一列的语义**，而不是原始值：

  ```
  ── 租户 #1  slug='default'  status=active
     allowed_http_hosts       = 未配置（NULL）→ 起源租户回退 env；其他租户全部拒绝
     allowed_webhook_hosts    = 2 项：hooks.example.com, alt.example.com
  ```

  ⚠️ **为什么不让你自己看原始值**：`NULL`（未配置）与 `''`（明确的「禁」）**语义相反**，
  而裸 `SELECT` 把两者都显示成空白 —— 靠 `quote()` 分辨要你**记得加**、还要**逐字判读**。
  这个脚本**只读**（守护测钉死），把判读那一步消掉。

  ### 🔧 配置某租户的出网白名单（**两列**，唯一途径 —— 均无写端点）

  ⚠️ **两列是两个不同的出网方向，必须分别配**：
  | 列 | 管什么 | 回退 env（仅起源租户） |
  |---|---|---|
  | `allowed_http_hosts` | KNOT 从哪些 host **读**业务数据（HTTP 数据源） | `KNOT_HTTP_ALLOWED_HOSTS` |
  | `allowed_webhook_hosts` | KNOT 往哪些 host **发**告警（monitor webhook） | `KNOT_WEBHOOK_ALLOWED_HOSTS` |

  ⛔ **严禁混用**：把读取白名单里的 host 顺手抄进外发列，等于「允许读某内网 API」
  变成「允许往那儿推数据」—— 两个方向的攻击面完全不同。

  ```bash
  # platform.db 位置 = 数据根 / platform.db（数据根 = SQLITE_DB_PATH 的父目录）
  # ⭐ 一条 UPDATE 同时设两列 —— 分两条跑容易只跑了一条就被打断
  sqlite3 /app/knot/data/platform.db \
    "UPDATE tenants SET allowed_http_hosts='api.example.com,api2.example.com',
                        allowed_webhook_hosts='hooks.example.com' WHERE id=2;"

  # ⭐⭐ 跑完**必须**复核（quote() 是唯一能区分 NULL 与 '' 的显示法）
  sqlite3 /app/knot/data/platform.db \
    "SELECT id, slug, quote(allowed_http_hosts), quote(allowed_webhook_hosts) FROM tenants;"
  ```

  ⛔⛔ **漏 `WHERE` 会一次写全表** —— 把某个租户的 host 给了**所有**租户（含起源租户）。
  且直接 SQL **不经写口** ⇒ **不 stamp `updated_at`、不进 `platform_audit`** ⇒ **零留痕**，
  而症状是「别人的 webhook 忽然能发了」，没有人会为此报障。**跑完必须用上面那条 SELECT 复核。**

  ### ⚠️ 行为变化提示（v0.9.18 起 —— 配置前请先读这段）

  `allowed_webhook_hosts` **是 v0.9.18 新增的列**。在它之前，webhook 外发只看进程 env
  `KNOT_WEBHOOK_ALLOWED_HOSTS`，而该 env **此前从未在本手册或 README 中出现**
  （只在 `.env.example` 里被注释掉）⇒ **多数部署很可能从未设过它 ⇒ webhook 外发一直是静默全拒**。

  ⇒ **一旦你按上面配置了这一列，该租户的 webhook 会从「静默全拒」变成「真的发出去」。**
  这是**用户可感知**的变化 —— 配置前请确认目标 host 确实是你想接收告警的地方，
  否则运维会遇到「怎么突然开始发告警了」。

  - **三态语义**（改错会静默出事，务必看清）：
    | 值 | 起源租户（tenant#1） | 其他租户 |
    |---|---|---|
    | `NULL`（未配置） | 回退 env `KNOT_HTTP_ALLOWED_HOSTS` + 启动 WARN | **全部拒绝** |
    | `''`（显式空） | **全部拒绝，不回退 env** | 全部拒绝 |
    | `a.com,b.com` | 只允许这两台 | 只允许这两台 |
  - ⚠️ **每租户一份，永不取交集/并集** —— 不要为了「让某个租户能访问 X」而把 X 加进 env：
    env 是**起源租户自己的**白名单，那样做会**同时放宽起源租户的可达面**。
  - ⚠️ **开通新租户时漏配该列 ⇒ 该租户的 HTTP 数据源全部静默拒绝**（fail-closed 正确，
    但**与「接口挂了」不可区分**）。排查看日志 `egress 拒绝: host=… tenant=… allowlist 来源=unconfigured`
    —— `来源` 字段直接告诉你是「没配」还是「配了但不含这台」。
  - ⚠️ 白名单只比 **hostname 字面**（不含端口、不做子域/IP 归一化）—— 与 v0.9.7 之前一致；
    per-tenant 化后这个弱点**按租户放大**（每份列都带同一弱点），已登记 backlog。
- ✅ **平台侧动作现在有审计了**（v0.9.8）—— 建/停租户、改 `db_dir`、改出网白名单都会留痕。
  两种查法：

  ```bash
  # ① 只读端点（推荐 —— 事故现场最快）；需 KNOT_PLATFORM_ADMIN_TOKEN
  curl -sS -H "Authorization: Bearer $KNOT_PLATFORM_ADMIN_TOKEN" \
    'http://127.0.0.1:8000/api/platform/audit?limit=50' | jq .

  # ② 直接查平台库（端点不可用时，例如出现第二个 active 租户导致整站 fail-closed）
  sqlite3 /app/knot/data/platform.db \
    "SELECT id, ts, actor, action, tenant_slug, detail_json FROM platform_audit ORDER BY id DESC LIMIT 20;"
  ```

  - `actor` 口径：`system:boot`（首启 seed，无人参与）/ `cli:<显式传入>` / `NULL`（未知）。
    ⚠️ **别用容器 `whoami` 当 actor** —— `kubectl exec` 下它 = root/app user ⇒ 「谁改的」记成 root。
  - ⚠️ **审计只记「代码路径」上的变更**：你直接 `sqlite3 UPDATE tenants` **不会留痕、也不会更新
    `updated_at`** ⇒ 直接改库请视为**应急手段**，并自行记录。
  - ⚠️ **出网白名单的变更只记「已变更」不记内容**（那是内网主机清单，而端点会返回详情字段）。
  - ⚠️ **审计表 append-only** —— 无清理机制（量级极小：只记租户生命周期与元数据变更）。
    要加清理必须走一次显式评审（有 CI 哨兵挡着）。

- ✅ **每个租户的初始 admin 口令已 per-tenant 化**（v0.9.4 登记 → **v0.9.15 + v0.9.19 已闭合**）：
  seed 口令有**两个入口**，两个都已堵：
  - **开通端点**（v0.9.15）：`POST /api/platform/tenants` 恒生成 per-tenant 随机口令，只在响应里给一次；
  - **启动的逐租户 `init_db()` 循环**（v0.9.19 P-b）：`KNOT_INITIAL_ADMIN_PASSWORD` **只对起源租户生效**
    （`repositories/base.py` 的 `is_owner_tenant()` 判断），其余租户一律随机强口令。

  ⚠️ 原登记写的是「目前来自同一个 `KNOT_INITIAL_ADMIN_PASSWORD` ⇒『A 公司的人能进 B 公司』有现成入口」——
  **那句自 v0.9.19 起为假**，但本手册漏改了一版。⇒ 若你读到的是旧版本手册，以本条为准。
- **登录未带 `?c=` 时回退到唯一 active 租户**（v0.9.4 登记）：lift 前必须把 `company` 改为必填。
  ⚠️ **开通第二租户当天的症状形状（务必先知道，否则会被误诊为认证故障）**：第二租户一激活，
  **所有还在用老链接（无 `?c=`）的用户会同时收到「账号或密码错误」** —— 这是**预期的 fail-closed**
  （无代号时的回退走 `resolve_single_tenant()`，它在 active ≠1 时 raise ⇒ 统一 401，
  **绝不会「挑一个」租户**，所以不是数据风险）。但按 kk 决策②文案**不能区分**失败原因
  ⇒ 现象看起来就是「一次大规模密码错误事件」。
  **处置**：开通第二租户**之前**先把所有人的链接换成带 `?c=<代号>` 的专属链接（或同时把 `company`
  改必填并配好链接分发），别指望事后从日志区分 —— 日志里只有 `[login] 未知或停用的公司代号`
  这一条，而无代号的情况连它都不会打。
- **登录失败分支「公司代号不存在 / 租户停用」目前只落 INFO 日志、无审计**（v0.9.4 登记）：无租户库可写，
  平台侧审计尚不存在。排查这类失败请 grep 日志 `[login] 未知或停用的公司代号`。
- **租户漂移告警**（v0.9.4）：日志固定事件名 `tenant_ctx_drift`（WARN）。
  **【以下基线仅 R-T-GATE 锁死期间成立】** 单租户下**不应出现** ——
  出现即代表 tenant ctx 被污染 / 异步传播串了 / 有第二条设 ctx 的路径，请当作事故排查。
