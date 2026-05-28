# OVERRIDE 累计治理记录（独立 source-of-truth）

> **创建依据**：v0.4 远古守护者第 3 次激活三任务合并评审 §X.1 + 资深决策 α8（维度 A 时间线粒度）
> **维护者**：资深架构师（亲自维护，与 PATCH 路线图脱钩）
> **更新规则**：每次 OVERRIDE 事件必须 explicit 归档（事件 + 日期 + 归档文件路径 + R-LP-v3-EX-2/2.1 触发判定）
> **维度选择**：**维度 A 时间线粒度**（PATCH 内嵌 OVERRIDE 不重复计数；否则一个 PATCH 内 N 个 OVERRIDE = 触发倍数惩罚反激励集中决策）

---

## §1 OVERRIDE 累计表（时间线粒度，维度 A）

| # | 日期 | OVERRIDE 事件 | PATCH | 归档文件 | R-LP-v3 触发 |
|---|---|---|---|---|---|
| 1 | 2026-05-21 | R-PA-5 buffer Day 7 提前评估（override LOCKED Day 28+ 缓冲期）| (between v0.6.0 & v0.6.1) | `docs/plans/phase-b-early-review-2026-05-21.md` | 未触发（首次）|
| 2 | 2026-05-24 | Phase B 二刀 HTTP adapter PATCH 启动（override ②-revised §V Q4 narrow 下限）— 内嵌 4 个子决策（CHANGELOG L113-115 OVERRIDE #1-#4）| v0.6.1.4 | `docs/plans/phase-b-narrow-2-http-adapter-2026-05-24.md` | R-LP-v3-EX-2 ≥3 次召集预备（累计 2 次未触发）|
| 3 | 2026-05-25 | 方向 ① announce override ②-revised 推荐 → Phase B 完整版路线图启动 | (planning v0.6.2.0+) | `docs/plans/v0.6.2.0-phase-b-roadmap-v3.md` §0.3 | **R-LP-v3-EX-2 触发 ≥3 次召集 v0.4 远古守护者** — 已履约 2026-05-25 第 3 次激活 |

**累计 = 3 次**
**R-LP-v3-EX-2.1 触发条件 ≥4 次 — 未触发** ✓
**R-LP-v3-EX-2 触发条件 ≥3 次 — 已触发 + 已履约**（v0.4 远古守护者第 3 次激活 2026-05-25 三任务合并评审）✓

---

## §2 v0.6.1.4 PATCH 内嵌子 OVERRIDE 附录（不参与全局计数）

OVERRIDE #2（2026-05-24）= v0.6.1.4 PATCH 启动决定本身。PATCH 施行期内累计 4 个子 OVERRIDE 决策（CHANGELOG L113-115）：

| 子 # | 子 OVERRIDE 决策 | CHANGELOG 段 |
|---|---|---|
| 2.1 | 跨源 JOIN 守护从 SQL planner 上移至 query.py 路由层 | CHANGELOG OVERRIDE #1 |
| 2.2 | hardcoded 业务方 adapter → 通用 catalog-driven HTTP executor | CHANGELOG OVERRIDE #2 |
| 2.3 | endpoint 路径不写死代码，从 catalog spec 注入（OSS-friendly）| CHANGELOG OVERRIDE #3 |
| 2.4 | catalog 后端 textarea → admin UI first-class（数据源升格）| CHANGELOG OVERRIDE #4 |

**归档原则**：PATCH 内嵌子 OVERRIDE 在 CHANGELOG + PATCH plan 文档已留痕，**不重复计入全局 §1 计数**（远古守护者 §1.3 维度 A 立约）。

---

## §3 治理纪律

### 3.1 维度选择（资深 2026-05-25 决策 α8）

**维度 A — 时间线粒度（已选）**：
- 一个 PATCH 启动决定 = 1 个 OVERRIDE（无论 PATCH 内部含几个子决策）
- PATCH 内嵌子 OVERRIDE 在 CHANGELOG + plan 文档归档，不重复计数
- 优点：治理友好；不反激励"集中决策"
- 缺点：单一 PATCH 内大量 OVERRIDE 时 risk 低估

**维度 B — 决策粒度（未选）**：
- 每个 OVERRIDE 决策（无论是否同 PATCH）= 1 个全局计数
- 优点：决策风险全量暴露
- 缺点：倍数惩罚集中决策 PATCH

### 3.2 R-LP-v3-EX 触发条件（sustained）

| 条款 | 触发条件 | 动作 |
|---|---|---|
| **R-LP-v3-EX-2** | 累计 ≥ 3 次 OVERRIDE | 强制召集远古守护者参与 retroactive review |
| **R-LP-v3-EX-2.1** | 累计 ≥ 4 次 OVERRIDE | 强制 Q-quarter 暂停 OVERRIDE 1 个 PATCH 周期 + retroactive audit |
| **R-LP-v3-EX-3** | 承诺推迟 ≥ 3 PATCH 未兑现 | 升级为正式红线 |

### 3.3 归档完整性义务

每次 OVERRIDE 事件**必须**在 7 天内归档独立 plan 文档；归档文件路径在本表登记。

**断裂污点**（远古守护者 2026-05-25 发现）：
- #1 (R-PA-5 buffer Day 7) — 原归档文件名引用但实地不存在 → v0.6.2.0 commit 0 内补建 ✓
- #2 (Phase B 二刀 HTTP adapter) — 同上 ✓

补建任务：v0.6.2.0 commit 0 docs 段落落地（与 R-LP-v3-EX-2.1/3 立约同 PATCH）。

---

## §4 历史回顾 — 未来累计预期

| 触发条件 | 预期时点 |
|---|---|
| 累计 ≥ 4 次 → R-LP-v3-EX-2.1 Q-quarter 暂停 | 第 4 次 OVERRIDE 发生时（未知）|
| Phase B 收官 → MINOR 滚动整体审核 | v0.6.3.x 末尾（约 2026 Q3 末）|

---

**资深架构师签字**：2026-05-25
**v0.4 远古守护者 ack**：第 3 次激活 2026-05-25 维度 A 首选立场已采纳 ✓

---

## §5 新立治理纪律记录

### R-PB-GOV-1（2026-05-25 立约）

**工期指导性预估非硬承诺纪律**

- **触发**：资深决策 β2（Stage 2 整合 Stage 4 LOCKED）
- **背景**：v0.5 守护者第 11 次 active + Stage 2 评审整合后工期重估 4.5-6.5 月 → 5-7 月；资深拒绝硬性工期承诺
- **内容**：详 `docs/plans/v0.6.2.0-phase-b-roadmap-v4.md` §0.4
- **影响**：所有 v0.6.2.0+ PATCH 节奏（不锁 1.0 公测时间窗 / 工期重估仅作参考 / 按业务方实际节奏推进）
- **例外**：单 PATCH 内部 commit 序列工期可硬预估（守护者 Stage 3 终审依据）

---

## §6 v0.6.2.0 新立 R-PB-B1-3 修订纪律记录（2026-05-28 立约）

### R-PB-B1-3 修订版（守护者第 14 次 active explicit ack）

**admin 三层防御 — 简化版**

| 优先级 | 条件 | 行为 |
|---|---|---|
| 1（最强）| `KNOT_TOTP_BYPASS_ADMIN=true` env | 全局跳过 admin TOTP 验证 |
| 2（兜底）| KNOT_TOTP_BYPASS_ADMIN 未设 + **0 admin 已 enroll** | admin 跳过（每次登录 logger.warn 提示）|
| 3（自动失效）| **≥ 1 admin enroll 完成** | 上述两个 fallback 自动失效 |

**v2 LOCKED 原版**："启动期前 24h admin 登录跳过 TOTP" — **commit 3 实际落地简化为业务条件触发**

**简化决策依据**（v0.5 守护者第 14 次 active §II.4 explicit ack）：
1. **工程实现复杂度**：24h 启动期追踪需 `_startup_time` 全局状态机 + service restart 重置 — vs `_admin_bypass_active` 纯查询 DB 业务条件无状态
2. **测试稳健性**：24h 窗口测试需 mock `datetime.utcnow()` 或 freeze_time → CI 间歇失败；业务条件测试稳定
3. **设计哲学一致性**：与 v0.4.5 R-37 master_key + v0.5.0 R-74 双 key 探针"业务条件触发"同精神
4. **实际安全姿态**：24h 后强制 lock out admin（即使未 enroll）→ 业务方紧急情况安全债增加；简化版 admin enroll 完成 = 正式建立才失效，更稳健

**风险声明**（透明披露）：
- admin 永不 enroll + KNOT_TOTP_REQUIRED=true → bypass 优先级 2 永久 on
- **兜底机制 1**：R-PB-B1-4 公测启动闸门（KNOT_TOTP_REQUIRED 默认 unset）→ 整个 TOTP enforcement off
- **兜底机制 2**：公测启动前资深必须 enroll + ack 才 `export KNOT_TOTP_REQUIRED=true`

**文档落地**：`DEPLOY.md` "5. TOTP 2FA — admin 三层防御 + 公测启动闸门" 段（完整 checklist）

**性质判定**：此修订**不属于 OVERRIDE**（治理纪律合规 + Stage 2 + 守护者 + 资深拍板共识 + R-LP-v3-EX-1 简化协议适用），不计入 §1 OVERRIDE 累计表。属"PATCH 内简化决策守护者 explicit ack" 类别。
