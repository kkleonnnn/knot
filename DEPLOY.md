# KNOT 部署手册

> **当前版本** v0.6.0.10 · 内测期（R-PA-5 缓冲 2026-05-15 → 2026-06-12）
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
        ║  浏览器：admin / admin123 登录       ║
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

浏览器访问 `http://<server-ip>:8000` → 用 `admin / admin123` 登录。

---

## ⚠️ 部署必读 — 4 条硬约束

### 1. KNOT_MASTER_KEY 是**终身密钥** 🔐

- 由 `deploy_checklist.sh` 自动生成（Fernet 32-byte base64）
- **务必备份到密码管理器** — 丢失或更改 = 历史加密数据（数据源密码 / API Key）**永久无法解密**
- 写到 `.env` 后建议 `chmod 600 .env`
- 重新部署 / 迁移服务器时**必须用同一个 key**

### 2. 首次登录立即改密码 🔑

- 默认账号：**admin / admin123**（写在源代码 `knot/repositories/base.py:94`）
- 任何能访问 8000 端口的人都能 admin/admin123 登录
- **必做**：登录后进「设置」→ 个人 → 改密码 + 改用户名（不叫 admin，防字典爆破）
- 改完用新账号验证旧 admin123 已失效

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
# 每日 02:00 自动备份
0 2 * * * cd /path/to/knot && cp data/knot.db data/knot.db.$(date +\%Y\%m\%d).bak && find data/ -name "knot.db.*.bak" -mtime +30 -delete
```

✅ `audit_log` 自动 7 天 retention + timestamped 备份（F-C 已内置 — 无需额外）。

---

## 📋 上线后 5 分钟 admin 配置 checklist

| 路径 | 操作 | 必要性 |
|---|---|---|
| 设置 → 个人 | 改密 + 改用户名 | 🔴 必做 |
| 设置 → API & 模型 | 填 OpenRouter Key（1 个 key 通所有 14 个 OR 模型） | 🔴 必做 |
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
- ✅ `./data/knot.db` 不动 → 所有用户配置 / 历史对话 / audit 全保留
- ✅ `KNOT_MASTER_KEY` env 不动 → 历史加密数据可解密
- ✅ `init_db()` 启动期幂等迁移 schema（新表新列自动加，旧数据不动）

---

## 📊 内测期运维监控项

| 信号 | 怎么看 | 该关注啥 |
|---|---|---|
| **boot 日志** | `docker logs knot` | "已加载（Fernet）" + "Uvicorn running" |
| **错误日志** | `docker logs knot 2>&1 \| grep -i error` | 极少；持续报错需诊断 |
| **DB 增长** | `du -sh data/knot.db` | 5-10 人内测预期 < 50MB / 周 |
| **F-A 用户反馈** | admin 浏览器 → API `/api/admin/feedback` | 👍/👎 数量 + 评论质量集中点 |
| **F-B 前端错误** | admin 浏览器 → API `/api/admin/frontend-errors` | 应极少；持续上报需修 |
| **F-C audit 自动清理** | `docker logs knot \| grep audit_auto_purge` | 7 天阈值后自动跑 |
| **LLM 成本** | admin → 预算 + Recovery 屏 | 实际 spend vs 阈值，超阈值会发 banner |
| **DataSources 心跳** | admin → 数据源 tab Hero 卡片 | "上次心跳 < 5 min" 表示连接正常 |

---

## 🆘 故障排查

### 启动失败

| 现象（docker logs knot 错误） | 排查 |
|---|---|
| `KNOT 启动失败 — JWT_SECRET 配置无效` | `.env` 没设 `JWT_SECRET=` 或仍是默认占位 → 重跑 `bash scripts/deploy_checklist.sh` |
| `KNOT 启动失败 — 缺少加密主密钥` | `.env` 没设 `KNOT_MASTER_KEY=` → 同上 |
| `cryptography.fernet.InvalidToken` | `KNOT_MASTER_KEY` 被改了 → 必须用历史那个 key（密码管理器找） |
| `sqlite3.OperationalError: no such column` | DB schema 不兼容（极少见）→ 联系开发 |

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
1. 先 `bash scripts/deploy_checklist.sh` 之前**备份** `data/knot.db`
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

### Q5: 默认 admin123 多久必须改？
**部署完 5 分钟内**改完。R-PA-5 内测期 4 周内全员检查 admin 账号是否还在 admin123（v0.6.1.0+ 会加强制改密 middleware）。

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
