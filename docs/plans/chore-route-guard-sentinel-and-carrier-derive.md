# chore（Stage 1'）：路由级策略哨兵 + 载体名派生 + 结构守护

> **性质**：0 行业务行为改动的**闸门加固** chore。**但它动的是闸门本身** —— 写错会给后面所有片子**假绿**，
> 故照 Loop Protocol v3 走完整三阶段。**回看这个判断是对的**：Stage 2（Codex）+ Stage 3（守护者）
> 合计指出**两条核心哨兵都有机制级假绿**，其中一条（D5）**按设计不可能通过**。
> **动因**：v0.9.5 要动 90 处 admin 依赖 ⇒ 先架安全网（kk 2026-07-29 拍板）；并入 v0.9.3 遗留的载体名 backlog。
>
> **本稿 = Stage 1'**：整合 Codex Stage 2（major-revise / 9 redline / 3 blocking）+ 守护者 Stage 3
> （concur major-revise / MF1-11 / 三开放点裁定）。**执行者已逐条实验复核，不照信评审文本**（§0）。

---

## §0 执行者独立复核（**实验坐实，非转述**）

| 条 | 评审主张 | 我的实验 | 判 |
|---|---|---|---|
| **R3** | `CARRIER_NAMES = tuple(_ATTR_TO_SLOT)` import 期冻结 ⇒ D5 按设计不可能通过 | 注入第 7 名后：`tuple(REG)` → `('A','B')` **不含**；`REG.keys()` → `('A','B','XLEX')` **含** | ✅ 成立 |
| **R2** | 基于 `__name__` 的匹配可被一行伪装骗过 | `weak.__name__='require_admin'` → 名字匹配 **True（被骗）** / `weak is require_admin` **False** | ✅ 成立 |
| **R8** | `dependency_overrides` 旁路：快照绿而守护已换 | 真 app：override 后快照仍见 `require_admin` **本体**（`is` 为 True），而 `overrides[require_admin].__name__=='weak'` | ✅ 成立 |
| **R1** | 中间层 44 条无身份快照 | 实跑：**138 总 / 134 有 `get_current_user` / 90 受 `require_admin` ⇒ 44** | ✅ 与守护者独立推导逐字一致 |
| **R5** | `_SLOT_KEYS` 死常量 + publish 手写 slot | `catalog_state.py:41` 定义、**全仓无其它引用** ✅；publish **签名(:56-57) 与 dict 字面(:65-66) 各手写一遍** | ✅ 成立（另见 §0.1②） |
| **§IV-3** | `== 53` 路径待核准 | `tests/api/test_admin_package.py:36` **存在**；`tests/services/test_admin_package.py` **不存在** ⇒ **Codex 路径对**，守护者预核找错目录 | ✅ 已核准 |

### §0.1 ⭐ 执行者补的两点（评审双方都没点）

**① R6 / R7 今天「0 实例」⇒ 它们是防御性加固，不是修现存缺陷。这改变验收的写法。**
实跑：`(method,path)` 共 **138 对、去重后 138、重复 0 项**；`APIWebSocketRoute` **0 条**。
⇒ 这两条**没有可 revert 的现存物**。若验收写「revert-to-bad」会找不到坏例，
进而误判条目多余，或**写出一个假 revert**（本弧已犯三次坏 revert）。
**必须写成「注入 bad case」**：造一条重复 `(method,path)`、造一条 WebSocket 路由，验哨兵红。

**② MF5 的不变量抓不到 `publish` 内部的漂移 —— 提为新开放点（§IV-4）。**
第 7 个**真 slot** 今天要同步 **4 处**：`_ATTR_TO_SLOT` · `publish()` **签名** · `publish()` 内 **dict 字面** ·
`_SLOT_KEYS`（死，MF5 要删）。删掉死常量后仍剩 **3 处**，而 MF5 的
`set(_ATTR_TO_SLOT.values()) == set(published_state)` 只能抓「注册表 vs 实际发布」的不一致 ——
**抓不到 publish 的「签名 ↔ dict 字面」漂移**（二者同时手写、同时漏改则不变量仍成立）。

---

## §1 两条的今日实况（基线）

### A. 路由 × 守护：只数条数，从不断言身份

| 今天有的 | 断言了什么 |
|---|---|
| `test_tenant_isolation.py:172` | `len(flatten_app_routes(app)) == 144`（条数） |
| `tests/api/test_admin_package.py:36` | `len(admin_routes) == 53`（`/api/admin/` 前缀**且**来自 admin 包） |
| `test_api_smoke.py:35` | `>= 80`（软下限） |
| 行为 403 spot check | **8 条**不同 admin 路由（users / recovery-stats / cost-stats / datasources ×2 / monitors / audit config / audit list） |

**缺口**：全仓 **0 处** introspect `dependant` ⇒ **没有任何测断言「某条路由仍受 `require_admin` 守护」**；
且**没有测钉住「恰 4 条无用户 JWT 依赖的路由」**（v0.9.4 只写了行为测）。

**基线（执行者与守护者各自独立算出、逐字一致）**：
```
138 APIRoute · 134 有 get_current_user · 90 受 require_admin · 中间层 44 · 无用户 JWT 依赖 4
90 里不在 /api/admin/ 前缀下的 23：bi_reports 7 · few_shots 5 · prompts 5 · knowledge 3 · database 1 · templates 1 · totp 1
无用户 JWT 依赖的 4：/api/auth/login · /api/bi/scheduler/tick · /api/totp/verify · /{full_path:path}
```
⚠️ **`53` 与 `90` 不是同一个量**（前者前缀+包判据，后者实际守护身份），差 37 正是「按前缀/按包拆会漏的那片」。

### B. 载体名：4 份硬编清单 + 一条更深的登记漂移

| # | 位置 | 形态 |
|---|---|---|
| 1 | `catalog.py:28` `_ATTR_TO_SLOT` | dict（唯一含 slot 映射） |
| 2 | `catalog_state.py:39` `CARRIER_NAMES` | tuple（生产复活检测） |
| 3 | `tests/test_catalog_tenant_isolation.py:25` `_CARRIER` | tuple |
| 4 | `tests/services/test_catalog_loaders.py:16` `_MUTABLE_GLOBALS` | set（4 条哨兵都用） |

**MUTANT-E（v0.9.3 §IV-1）**：加第 7 名 + `reload()` 里 `global` 它 → **26 测全绿逃逸**。
**承重约束**：`catalog.py:18` import `catalog_state` ⇒ 注册表必须落在 `catalog_state`（否则循环）。

---

## §2 决议（Stage 1' 定稿）

### D1' 全 138 条 **policy map**（MF1）
- 扫描面**派生**（`flatten_app_routes` 全量 + 递归 introspect `dependant`，带 `seen` 防环）。
- 期望值 = **单独 fixture 文件**里的 `{"METHOD /path": POLICY}`（§IV-1 裁定）。
- 策略四类：`PUBLIC_OR_OUT_OF_BAND` · `AUTHENTICATED` · `ADMIN` · `REPORT_PERMISSION`。
- 差集报 **added / removed / policy-changed** 三类（不是「90 != 91」）。
- ⚠️ **与 v0.9.4 MF2「漂移清单」的区别必须写进 docstring**：MF2 坑在**扫描面**硬编（漏端点即漏检）；
  这里硬编的是**期望值**，而期望值**本就必须**是字面 —— **从被检对象派生期望 = 自我实现的 tautology，测永远绿**（MF11①）。

### D2' 守护者身份 **`is` 比较**（MF2）
`dep.call is require_admin`，**不用 `__name__`**（§0 已证一行可伪装）。
mutant 必须**连 `__name__` 一起伪装**仍红，才算证明。

### D3' 反向钉住「无用户 JWT 依赖」4 条 + 改名（MF7）
名字改 **`NO_USER_JWT_DEPENDENCY`**（原「无鉴权」不实：tick 有共享密钥、verify 从 body 读 interim）。
四条各写**认证来源**一行。并断言**无未分类** `APIWebSocketRoute`（今天 0 条 → 注入式验收）。

### D4' 载体注册表移入 `catalog_state` + **函数**导出（MF3）
- `_ATTR_TO_SLOT` 移到 `catalog_state`，`catalog.__getattr__` 读它。
- **不导出 eager tuple** → 导出 **`carrier_names()` 函数**。
  理由（守护者，执行者复核认同）：`.keys()` 活视图能修 R3，但**把活视图挂在 `CARRIER_NAMES` 这种
  常量样的名字下是陷阱** —— 读者当它是 tuple，下一个人「顺手改回 `tuple(...)`」就**静默重新废掉 D5**，
  与本片要治的病同型。函数名把动态性写在**每个调用点**上。
- 三处消费方（生产复活检测 + 两处测）改调 `carrier_names()`。

### D5' MUTANT-E 回归：注入**真 slot**（MF5）
- 删死常量 `_SLOT_KEYS`；加不变量 `set(_ATTR_TO_SLOT.values()) == set(published_state)`。
- mutant **必须新增真 slot，不得别名到既有 slot** —— v0.9.3 原始 MUTANT-E 正是 `"XLEX": "lexicon"`
  （映到既有 slot），照抄就**触及不到 slot-schema 漂移**。
- 注入后须**真的看到第 7 名**（D4' 的函数导出使之可能）。

### D6' ⭐ 与注册表**无关**的结构守护（MF4 + 守护者 §II-1）
`catalog.py` **全文件禁任何 `ast.Global`**（不只禁注册表内的 6 名）+ 禁新增模块级可变载体状态。
**这条才是本片真正的安全性来源**；派生（D4'）只消除抄写。
> 守护者认账原文要点：他 v0.9.3 §IV-1 的处方「四份清单全派生」只修**抄写**漂移、留下**登记**漂移 ——
> 所有 oracle 都从注册表派生后，**没进注册表的东西对全部守护不可见** ⇒ 单独执行那个处方，
> 会把「4 个弱守护」变成「1 个强但盲的守护」，MUTANT-E 换形态（新加载体但不登记）照样逃逸。

### D7' overrides 旁路守护 + **防测序依赖**（MF8）
- 断言具名守护函数**不出现在** `app.dependency_overrides`。
- ⚠️ **配 per-test overrides 快照/复原 autouse fixture** —— 测自己会合法用 override，
  裸断言「overrides 为空」会让前面漏清的测把它变成**时绿时红**（v0.9.3 验收测 #2 踩过）。
- 断言**只**针对具名守护函数，不针对整个 overrides 字典。

### D8' D6 降级为「提醒」+ 阈值 4（§IV-2）
禁 `knot/ tests/ scripts/` 出现**字面**集合/元组同时含 **≥4** 个载体名。
明确标注「**防重复清单的提醒，非完备性保证**」；完备性由 **D6'** 承担。
（阈值理由：≥3 会误伤只验三属性的正当测；≥3 也能拆成两个二元组绕过 ⇒ 既然注定只是提醒，
就该**优先减少误报** —— 噪音大的提醒会被关掉。）

### D9' 再生成命令 + 可粘贴失败输出（MF10）
(a) documented **单命令**重生成 fixture；(b) 测失败时打印**可粘贴的新块**（含三类差集）。
理由：138 行手改 = 打字错，而**期望值里的打字错就是假绿**；且 v0.9.5 会整体重写这张表。

### D10' 意图复核（MF9 + 守护者 §II-2）
**打标签这个动作本身**强制回答「这条该是什么策略」。那 **23 条** admin 守护却在 admin 包外的
必须**逐条给一行理由**。
> **快照会把今天的状态祝福成正确；钉住之后就查不出来了。**

### D11' 两条 docstring 防误修（MF11）
① 期望值必须是字面（从被检对象派生 = tautology）；
② **v0.9.5 拆 `require_admin` 时 D2' 会按设计必红** —— 那是**强制显式重登记**，
**严禁**用「放宽成子串/名字匹配」来修。

### D12' `== 53` 保留不动 + 加注释（§IV-3，三方一致）
注释写明「53 = admin **包聚合完整性** ≠ 90 = **实际守护身份**」并指向新哨兵为权威。
**不得**从新快照派生。路径已核准：`tests/api/test_admin_package.py:36`。

---

## §3 红线

- **R-C1**：0 行业务行为改动。`knot/` 侧只允许「注册表搬家 + 函数化导出 + 删死常量」，
  `catalog.TABLES` 等 13 个 importer **外部可见行为 byte-equal**。
- **R-C2**：哨兵**扫描面必须派生**；只有**期望值**可以是字面。该区分**必须写进 docstring**。
- **R-C3**：每条哨兵配 revert-to-bad，且 revert **必须语法有效**（v0.9.4 三次坏 revert）。
  **无现存实例的条目（R6/R7 类）改用「注入 bad case」**（§0.1①）。
- **R-C4**：`ruff --fix` **只对本片改过的文件**跑（v0.9.4 两次夹带 26 个无关文件）。
- **R-C5**：不动被守护的路由/依赖；不动 `== 53`（只加注释）。
- **R-C6**：新哨兵**不得引入测序依赖**（D7' 的 fixture 是硬条件，不是建议）。

---

## §4 验收（逐条自证；**注明 revert 型 vs 注入型**）

| # | 验收 | 型 |
|---|---|---|
| 1 | 去掉某条 admin 路由的 `Depends(require_admin)` → 哨兵红且**点名该路由** | revert |
| 2 | 换成 `weak` 且**连 `__name__` 一起伪装** → **仍红**（D2' `is` 比较） | revert |
| 3 | 新增一条无用户 JWT 依赖的路由 → D3' 红 | 注入 |
| 4 | 新增一条受守护路由 → 红（提示 added，强制显式登记） | 注入 |
| 5 | 改某条路由的策略类别（ADMIN→AUTHENTICATED）→ 红且报 **policy-changed** | revert |
| 6 | `app.dependency_overrides[require_admin] = weak` → D7' 红**而 D1' 仍绿** ⇒ 证明二者**不可互相替代** | 注入 |
| 7 | 造一条重复 `(method,path)` → D1' 红（**今天 0 重复**，必须注入） | 注入 |
| 8 | 造一条 `APIWebSocketRoute` → D3' 红（**今天 0 条**，必须注入） | 注入 |
| 9 | 往注册表注入**真 slot** 第 7 名（不改任何测）→ D5' 绿；**回退 D4' 成 eager tuple** → D5' **红** | 注入 + revert |
| 10 | `catalog.py` 里加任意 `global`（**即使不在注册表内**）→ D6' 红 | 注入 |
| 11 | `tests/` 抄含 **4** 个载体名的字面元组 → D8' 红；含 **3** 个 → **不红**（阈值边界证明） | 注入 |
| 12 | 全量绿 + `catalog` 外部行为 byte-equal（13 importer 0 改动）+ **无测序依赖**（打乱顺序跑两遍同结果） | — |

---

## §5 commit 序

1. `test(guard)`: D1'+D2'+D3'+D7' 路由策略哨兵（fixture 文件 + 再生成命令）—— 0 生产码
2. `refactor(catalog)`: D4' 注册表移入 `catalog_state` + `carrier_names()` + 删 `_SLOT_KEYS`（行为不变）
3. `test(guard)`: D5' MUTANT-E 真-slot 回归 + **D6' 结构守护** + D8' 提醒
4. `docs`: D10' 23 条意图理由 + D12' 注释 + CHANGELOG（riding 当前版本**不 bump**）+ 兑现 v0.9.3 §IV-1

---

## §IV 开放点

- **IV-1 快照位置** → **单独 fixture 文件**（Codex + 守护者同判；原草案「内联」两票否）。
- **IV-2 D8' 阈值** → **4** + 降级为提醒（守护者裁定；扫描面扩 `knot/ tests/ scripts/`）。
- **IV-3 `== 53`** → 保留 + 注释；路径 = `tests/api/test_admin_package.py:36`（**已核准**）。
- **IV-4 ⭐ 新开放点（执行者提 · §0.1②）**：删 `_SLOT_KEYS` 后第 7 个真 slot 仍需同步 **3 处**，
  而 MF5 的不变量**抓不到 `publish()` 签名 ↔ dict 字面之间的漂移**。两个方向请裁：
  **(a)** 让 `publish()` 也从注册表驱动（`**kwargs` + 校验键集）—— 但会**削弱 v0.9.3 刻意的 keyword-only
  防错设计**（防位置参数把 lexicon 灌进 tables）；
  **(b)** 保留手写签名，另加一条 **签名 ↔ dict 字面一致性** 的 AST 断言（不动生产码形状）。
  **执行者倾向 (b)**：keyword-only 是有意的安全设计，不该为消除重复而让位；且 (b) 让「重复」变成
  **被守护的重复**。

---

## §6 自检（抗诱惑）

不动被守护的路由/依赖 · 不动 `== 53`（只加注释）· 不引入新依赖 · `ruff --fix` 只跑改过的文件 ·
不把「扫描面派生」与「期望值钉住」混为一谈 · 每条哨兵配**语法有效**的 revert（无现存实例的用注入型）·
不让新哨兵产生测序依赖 · **不因为「派生了」就认为完备**（完备性只在 D6'）。

---

## §7 给守护者的复核指引（Stage 1' → 复核范围）

你上一轮的放行条件是「补 §III MF1-11 → 重出 Stage 1' → 回我复核 → 实施」。**代码一行未写。**

### 只需核这三块（其余是原文照落）
1. **§0** —— 我对你 4 条 + Codex 5 条的**独立实验复核**。若你认为某条我复核的方式不成立，请点名。
   其中一条**改判**：§IV-3 的路径分歧我判给 Codex（`tests/api/test_admin_package.py:36` 存在，
   `tests/services/test_admin_package.py` **不存在**）。
2. **§0.1① + §4 的型别标注** —— 我主张 R6/R7 今天 **0 实例**（实测 138 对无重复、0 WebSocket 路由）
   ⇒ 它们的验收**不能**写 revert-to-bad，必须写「注入 bad case」。
   **请裁这个改写是否可接受** —— 它改变了 R-C3 在这两条上的适用方式。
3. **§IV-4 新开放点** —— MF5 的不变量抓不到 `publish()` 签名 ↔ dict 字面的漂移。
   两方向请裁：(a) publish 也从注册表驱动（削弱 v0.9.3 刻意的 keyword-only 防错）
   vs (b) 加一条签名↔字面一致性 AST 断言（不动生产码形状）。**我倾向 (b)。**

### MF1-11 落点速查
MF1→D1' · MF2→D2' · MF3→D4' · MF4→**D6'** · MF5→D5' · MF6→D1'（list/Counter + 先断唯一）·
MF7→D3' · MF8→D7' · MF9→D10' · MF10→D9' · MF11→D11'。
三开放点：IV-1 单独 fixture 文件（两票否内联）· IV-2 阈值 4 + 降级提醒 · IV-3 保留 `== 53` + 注释。

### 我特意没做的事
- **没写任何代码**（放行前）。
- **没动** `== 53`、没动任何被守护的路由/依赖（R-C5）。
- **没把 D6' 与 D4' 混为一条** —— 你 §II-1 的要点是「派生只消除抄写、完备性另需结构守护」，
  我把它写成两条独立决议 + §6 自检末条「不因为『派生了』就认为完备」。
