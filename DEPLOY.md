# KNOT 部署手册

> **当前版本** v0.9.4 · 内测期（v0.6.1.4→0.6.5.6 升级 runbook 见 [docs/plans/v0.6.5.6-upgrade-from-v0.6.1.4-k8s.md](docs/plans/v0.6.5.6-upgrade-from-v0.6.1.4-k8s.md)；v0.6.5.x→v0.7.x 为纯内测迭代，无强制迁移步骤）
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
  --env-file .env \
  --restart unless-stopped \
  --name knot knot

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
- **必做**：登录后改密码 + 改用户名（不叫 admin，防字典爆破）；口令遗失 → `python -m knot.scripts.reset_admin_password`。
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

### ⚠️ 多副本 / 多 worker 首次升级注意

迁移在启动期跑，并用数据根 `.c4-migration.lock`（`flock`）串行化**同节点**的多 worker/多进程启动。但
**跨节点共享卷（K8s RWM/NFS PVC）上的 `flock` 不保证跨节点互斥**。故首次从 v0.8.x 升 v0.9.x 时：

- **先以单副本迁移**（`replicas: 1`）确认日志出现 `[C4] tenant#1 存量迁移: migrated`（或 `skip:fresh`）后再扩容；
- 或把迁移放进 **init-container / 一次性 Job**（单实例先跑），应用副本再起。

（单 uvicorn / 单副本部署——KNOT 内测默认——无此问题；迁移是一次性操作，迁完后 `skip:migrated` 恒等幂等。）

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
                - "http://knot-svc:8000/api/bi/scheduler/tick"   # 集群内 Service 名（单外部触发→只打一个 pod）
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
v0.8.20 起**无固定默认 admin123**：设 `KNOT_INITIAL_ADMIN_PASSWORD` 则用之，未设则首启随机生成、**在启动日志打印一次**（`docker logs knot | grep "seed admin"`）。**部署后尽快首登**（must_change_password 强制改密 + 强制 enroll）；随机口令仅一次可见，遗失用 `python -m knot.scripts.reset_admin_password` 重置。

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
**当前单租户部署可继续用不带 `?c=` 的旧链接**（后端回退到唯一 active 租户）；但这是 R-T-GATE 锁死
单租户期间的临时允许，**开通第二租户前 `company` 会改为必填**，届时必须换成带代号的链接。

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
- **`_local_catalog.py` 是部署级、全体租户共享**：其中的真实业务表名/方言/HTTP endpoint 对**每个**租户可见；
  且空-DB 租户会 fallback 到它（含 business_rules）。开通第二租户前必须先做 per-tenant file catalog。
- ✅ **HTTP 虚拟表凭据 + 出网白名单已 per-tenant 化**（v0.9.7 B-3 ②③ —— 原「走进程 env、租户盲」已闭合）：
  - **凭据**：`http_spec` 必须带 `source_id` → 指向**该租户库**的 `data_sources` 行（`http_config` 走 Fernet）。
    env 引用形态（`base_url_env` / `auth_*_env`）已**物理删除**；`adapters/http/executor.py` 现在**零 env 读取**
    （配 AST 哨兵）。⚠️ **升级影响**：若你的 `_local_catalog.py` 里还有 env 形态的 http 表，
    升级后它会**软降级落 SQL**（并记日志 `[http_route] spec 未绑租户数据源`）—— 改法：在 admin UI 建
    一个 `db_type='http'` 数据源，把 `http_spec` 改成 `{"source_id": <该源 id>, …}`。
  - **出网白名单**：改读平台库 `tenants.allowed_http_hosts`（逗号分隔）。**起源租户（tenant#1）在该列为
    `NULL` 时回退 `KNOT_HTTP_ALLOWED_HOSTS`** ⇒ **现网 ConfigMap 不动即可继续工作**（启动期会 WARN 提示迁移）。

  ### 🔧 配置某租户的出网白名单（**唯一途径** —— 该列无写端点）

  ```bash
  # platform.db 位置 = 数据根 / platform.db（数据根 = SQLITE_DB_PATH 的父目录）
  sqlite3 /app/knot/data/platform.db \
    "UPDATE tenants SET allowed_http_hosts='api.example.com,api2.example.com' WHERE id=2;"

  # 查看当前配置（NULL = 未配置；'' = 显式全拒绝）
  sqlite3 /app/knot/data/platform.db \
    "SELECT id, slug, quote(allowed_http_hosts) FROM tenants;"
  ```

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

- **每个新租户 seed 的初始 admin 口令目前来自同一个 `KNOT_INITIAL_ADMIN_PASSWORD`**（v0.9.4 登记）：
  开通第二租户前必须改成 per-tenant 初始口令 / 一次性邀请流，否则「A 公司的人能进 B 公司」有现成入口。
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
