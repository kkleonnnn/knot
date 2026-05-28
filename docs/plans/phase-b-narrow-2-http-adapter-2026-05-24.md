# OVERRIDE #2 归档 — Phase B 二刀 HTTP adapter PATCH 启动

> **事件日期**：2026-05-24
> **归档创建**：2026-05-25（追溯重建 — 原事件未及时独立归档；v0.4 远古守护者 2026-05-25 第 3 次激活发现归档断裂 → v0.6.2.0 commit 0 内补建）
> **状态**：补建 / 追溯归档
> **OVERRIDE 全局编号**：#2（详 `docs/governance/override-cumulative-log.md`）
> **关联 PATCH**：v0.6.1.4（CHANGELOG L106-118）

---

## §0 事件性质

### 0.1 触发条件
v0.6.1.4 推动者：撮合 admin 持仓查询业务需求 + 老板 demo 跨源能力展示。

### 0.2 实际发生
override ②-revised §V Q4 narrow 下限：
- 原 ②-revised 立约：v0.6.x narrow scope 仅做时间语义 / 不引入新数据源 adapter
- 实际：v0.6.1.4 引入 HTTP adapter（撮合 admin futures positions API）
- **OVERRIDE 决策**：业务需求拉动 → 必做 → override narrow 下限

### 0.3 OVERRIDE 性质
- **违反对象**：②-revised narrow scope §V Q4 立约
- **OVERRIDE 类型**：范围扩张（新增 HTTP adapter 适配层）
- **决策权重**：高 — 引入新数据源类别 + Fernet 加密扩展 + admin UI first-class 升格
- **审议轨迹**：v0.6 执行者 Stage 1 LOCKED 终稿 + v0.5 守护者 Stage 3 终审 + Codex 等效初审 → 资深拍板

---

## §1 OVERRIDE 决策内容

### 1.1 主决策（PATCH 启动本身）
启动 v0.6.1.4 PATCH — 引入 HTTP adapter 通用层（OSS-friendly）+ 业务方撮合 admin futures 查询窄域接入。

### 1.2 内嵌 4 个子 OVERRIDE 决策（CHANGELOG OVERRIDE #1-#4）

施行期内累计 4 次决策升级（详 CHANGELOG L106-118）：

| 子 # | 子决策 | CHANGELOG 段 |
|---|---|---|
| **#1** | 跨源 JOIN 守护从 SQL planner 上移至 query.py 路由层 | R-PB2-4 实施定位上移 |
| **#2** | hardcoded 业务方 adapter → 通用 catalog-driven HTTP executor | adapters/http/executor.py [NEW 184 行] |
| **#3** | endpoint 路径不写死代码，从 catalog spec 注入（OSS-friendly）| catalog source_type=http first-class |
| **#4** | catalog 后端 textarea → admin UI first-class（数据源升格）| modals.jsx + tab_access.jsx + base.py ALTER TABLE |

**归档纪律**（远古守护者 §1.3 维度 A 立约）：
- 4 子决策**不参与全局 OVERRIDE 计数**（避免单 PATCH 内倍数惩罚）
- 在 CHANGELOG + 本文档归档；OVERRIDE 全局表（`docs/governance/override-cumulative-log.md`）仅计 1 次（v0.6.1.4 PATCH 启动决定本身）

---

## §2 产出 — v0.6.1.4 PATCH 落地

### 2.1 commit 序列（7 commit 全部 merged 2026-05-22 ~ 25）
1. F1 — adapters/http Protocol + executor + url_allowlist
2. F2 — catalog source_type=http + admin UI first-class（OVERRIDE #4 关键 commit）
3. F3 — http_planner.py + clarifier.md HTTP section
4. F4 — api/query.py HTTP route dispatching
5. F5 — guardian tests（18 R-PB2 tests + smoke updates）
6. F6 — docs + version sync 0.6.0.25→0.6.1.4 + CHANGELOG OVERRIDE
7. F9 — 业务方 sign-off（post-demo 2026-05-25）

### 2.2 业务效果
- 2026-05-25 prod 上线（v0.6.1.11 含 v0.6.1.4 累计）
- 撮合 admin futures 查询 demo 跑通 + 业务方 sign-off ✓
- KNOT 首次跨源能力（SQL + HTTP API）落地

### 2.3 18 条新立红线
R-PB2-1 ~ R-PB2-18（详 v0.6.1.4 plan 文档；含 R-PB2-3 URL allowlist / R-PB2-4 跨源 JOIN 禁止 / R-PB2-9 Fernet 加密 / R-PB2-10 PII 防御 / R-PB2-13 catalog reload 立即生效 / R-PB2-14 ERROR_KIND 8 keys byte-equal）

---

## §3 治理后果

### 3.1 立约延伸
- **R-LP-v3-EX-2 召集义务预备**：本次 = 累计第 2 次（未达 ≥3 触发）
- **R-PB2 18 条红线**：v0.6.1.4 + 后续 Phase B PATCH sustained

### 3.2 后续 OVERRIDE 累计
- 本次 = 累计第 2 次（OVERRIDE 全局计数）
- + 累计 #1（R-PA-5 buffer）= 2 次
- 距 R-LP-v3-EX-2 ≥3 次触发 1 次之差

### 3.3 归档断裂污点（2026-05-25 v0.4 远古守护者发现）
原 v2 roadmap §0.3 引用本文件路径但实地不存在 → 治理诚实度污点 → v0.6.2.0 commit 0 内补建（本文档）。

---

## §4 资深拍板复核（2026-05-25）

- 维度 A（时间线粒度）确认 — 本事件 + 内嵌 4 子决策 = 1 个全局 OVERRIDE 计数 ✓
- 归档断裂偿还 — 本文档创建 ✓
- R-LP-v3-EX-2 ≥3 次召集触发于下一次 OVERRIDE（OVERRIDE #3 方向 ① announce 2026-05-25）✓

---

**资深架构师签字**：2026-05-25（追溯）
**v0.4 远古守护者 ack**：第 3 次激活 §1.2 v0.6.1.4 PATCH 内嵌 4 子决策立场采纳 ✓
**v0.5 守护者 ack**：第 10 次 active §IV OVERRIDE 治理记录污点识别采纳 ✓
