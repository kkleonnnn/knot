# chore（Stage 1'）：路由级策略哨兵 + 载体名派生 + 结构守护

> **性质**：0 行业务行为改动的**闸门加固** chore。**但它动的是闸门本身** —— 写错会给后面所有片子**假绿**，
> 故照 Loop Protocol v3 走完整三阶段。**回看这个判断是对的**：Stage 2（Codex）+ Stage 3（守护者）
> 合计指出**两条核心哨兵都有机制级假绿**，其中一条（D5）**按设计不可能通过**。
> **动因**：v0.9.5 要动 90 处 admin 依赖 ⇒ 先架安全网（kk 2026-07-29 拍板）；并入 v0.9.3 遗留的载体名 backlog。
>
> **本稿 = Stage 1' LOCKED**（守护者复核 **PASS — 放行实施**，2026-07-29）：整合 Codex Stage 2
> （major-revise / 9 redline / 3 blocking）+ 守护者 Stage 3（concur major-revise / MF1-11 / 三开放点裁定）
> + 守护者 Stage 1' 复核的**两条实施条件**（R-C3 改写 · IV-4 走 (c)）。
> **执行者已逐条实验复核，不照信评审文本**（§0）。

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

> **守护者 Stage 1' 复核补（关乎实施优先级）**：执行者的 R8 复核比守护者的实验精确 ——
> 守护者只比了 `__name__`，执行者在**真 app** 上验了「override 后快照仍见 `require_admin` **本体**（`is` 为 True）」。
> 这直接堵住一个很可能发生的误推：**「D2' 用了 `is` 比较，所以对 override 旁路免疫」—— 不成立**。
> dependant 树在**注册期**构建、持的是原对象；override 在**请求期**解析。**D2' 与 D7' 正交，谁也替代不了谁。**
> ⇒ **验收 #6（`D7' 红而 D1' 仍绿`）比两个守护本身更值钱** —— 它防的是后人删掉 D7'。实施时不得省略。

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
- **R-C3（守护者 Stage 1' 复核改写）**：**每条哨兵必须被证明在「违规状态」下转红。**
  违规状态**从哪取材只是手段**，不构成例外：
  - 对应一个**已做的修** → **revert** 那个修；
  - 是**尚不存在的未来状态** → **注入**构造它。
  ⇒ 消掉「revert 型 vs 注入型」的伪对立 —— 否则下一片又会来一次「这条没法 revert，是不是就不用证了」。
  两条附加条件：
  1. revert **必须语法有效**（v0.9.4 三次坏 revert：引用不存在的函数名 / 只插 `pass` 没真挪 / 改的名字有冗余覆盖）。
  2. ⭐ **注入必须走真实注册 API**（`app.get(...)` / `add_api_route(...)` / `add_api_websocket_route(...)`），
     **严禁**手搓 route 对象塞进 `app.routes` —— 否则哨兵可能因「对象形状不对」而红，
     而不是因「重复 / WebSocket」而红，**那又是一个假证明**。
- **R-C4**：`ruff --fix` **只对本片改过的文件**跑（v0.9.4 两次夹带 26 个无关文件）。
- **R-C5**：不动被守护的路由/依赖；不动 `== 53`（只加注释）。
- **R-C6**：新哨兵**不得引入测序依赖**（D7' 的 fixture 是硬条件，不是建议）。

---

## §4 验收（逐条自证；「型」= **违规状态的取材方式**，非两类不同要求 —— 见 R-C3）

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
- **IV-4 ⭐ 裁定：走 (c)** —— 执行者提出（§0.1②）、守护者**穷举漂移组合**后**两个原方向都否**。

  **漂移组合穷举**（守护者 Stage 1' 复核补 —— 这是判断前提，此前双方都没做）：

  | 情形 | 后果 | 抓得到？ |
  |---|---|---|
  | ① 只改注册表 | published 缺该 slot | ✅ MF5 不变量红 |
  | ② **只加 publish 签名参数** | 参数被接受后**静默忽略** | ❌ 不变量成立（registry 也没它） |
  | ③ 只改 dict 字面 | 引用未定义局部名 → **NameError** | ✅ 响亮 |
  | ④ 注册表+签名，漏 dict | published 缺 slot | ✅ 不变量红 |
  | ⑤ 注册表+dict，漏签名 | reload 传参 → **TypeError** | ✅ 响亮 |
  | ⑥ 三处齐改 | 正确 | — |

  ⇒ **唯一漏网的是 ②，而 ② 是良性的**（死参数，无人消费）。
  执行者原描述「二者同时漏改则不变量仍成立」**过宽**：那种情形下注册表若也没改则什么都没坏；
  若注册表改了就是 ① / ④，都会红。
  - **(a) 不做** —— 为消除重复而让位 v0.9.3 刻意的 keyword-only 防错（防「位置参数把 lexicon 灌进 tables」），不值。
  - **(b) 不必** —— 整套 AST 签名↔字面比对，只为买情形 ②。
  - **(c) 采纳：一行运行期断言** ——
    `{publish 的 KEYWORD_ONLY 参数名} == set(_ATTR_TO_SLOT.values())`（`inspect.signature`，守护者已实测相等）。
    同时优于两方向：不动 keyword-only 形状（优于 a）· 不需要 AST 机器（优于 b）·
    **并且把注册表变成 publish 形状的唯一权威**，顺手覆盖 ②。
  - ⚠️ **定性必须写准（写进 docstring + CHANGELOG）**：这是**廉价的纵深，不是补洞** ——
    唯一漏网的 ② 良性。**不得**写成「修了一个漂移洞」，否则下一个人会以为它在守一个真洞而**不敢碰 publish 形状**。

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

---

## §8 实施记录（4 步落地 · 供 Stage 4 复核）

**分支** `chore/route-guard-sentinel-and-carrier-derive` · **4 commit** `e7353c7`..(本 commit) ·
**全量 1560 passed 0 failed** · **生产码仅 commit 2 的 2 文件**（行为不变，全量与前一 commit 逐字相同）。

| # | commit | 内容 | 全量 |
|---|---|---|---|
| 1 | `e7353c7` | `test(guard)` 路由授权策略哨兵（D1'~D3' + D7'）+ fixture + 再生成脚本 + conftest 复原 fixture | 1554 |
| 2 | `c2b2a77` | `refactor(catalog)` 注册表移入 `catalog_state` + `carrier_names()` + 删 `_SLOT_KEYS`（**唯一动生产码**） | 1554（逐字相同） |
| 3 | `b69c9f3` | `test(guard)` D5'/D6'/D8' + IV-4(c) + 两处测清单改派生 + 移交一条被包含的哨兵 | 1560 |
| 4 | 本 commit | `docs` D10' 23 条意图复核 + D12' 注释 + CHANGELOG + 本段 | 1560 |

### §8.1 偏离 Stage 1' 之处（逐条列，请裁）

1. **D2' 的 `dep.call is X` 对 `require_report_perm` 按构造不可能成立** —— 它是**依赖工厂**，
   每条路由拿到不同闭包（实测 `factory("a") is factory("b")` → False）；且评审双方给的名字
   `require_report_permission` 在仓里**不存在**（真名 `require_report_perm`，`bi_reports.py:100`）。
   **照字面实现会把 10 条有 RBAC 细粒度权限的报表路由错标成 `AUTHENTICATED`，快照再把这个错祝福成正确。**
   改用 **`__code__` 身份**（同工厂闭包共享 compile-time 唯一 code 对象；**不可被 `__name__` 伪装**）
   ⇒ 仍守 D2' 实质。已在 commit 1 报过，kk 判「继续做完」。
2. **IV-4 (c) 放测不放生产**：守护者原文「一行**运行期**断言」，我理解为「用 `inspect.signature` **反射**」
   （相对 (b) 的 AST 机器），**不是** import 期生产断言 —— 放生产会给 commit 2 引入非 0 行为改动，
   且裸 `assert` 可被 `python -O` 剥离（v0.9.3 教训：用显式 raise）。**此解读若有误，改动一行。**
3. **移交（而非保留）一条哨兵**：`test_catalog_loaders::test_catalog_py_has_no_global_statement_on_carrier_names`
   是**按名过滤**版，而按名过滤正是 MUTANT-E 的逃逸口；D6' 版不看名字 ⇒ **严格更强**
   （实测：`global TABLES` 两版皆红 / `global XNEW` 仅新版红）。留一份在原处 = 重新引入
   「同一件事两处判据」= 本片要治的病。原 docstring 的失效机制 + 时序真相已整段随迁。
4. **D5' 加了一条对照组** `test_D5_alias_mutant_is_weaker`：把「mutant 必须是**真 slot** 不得别名」
   从注释变成可执行证明（否则后人照抄 v0.9.3 的别名形，测照样绿、以为覆盖了）。
5. **D12' 注释内容与我的初稿相反** —— 见 §8.2。

### §8.2 我自己在本片犯的错（全部自查发现并已修）

1. **D12' 初稿的恒等式是错的**：我写「53 route 对象展开 method 得 67」，实测 **admin 包 0 条多 method
   路由**（53 对象 == 53 个 (method,path)）。真相是**三个不同的轴**：包归属 53 / 路径前缀 67
   （= 53 + **14 条定义在 admin 包之外**：`catalog` 7 · `audit` 5 · `feedback` 1 · `frontend_errors` 1）
   / 守护 90。**这个纠正比原注释有用得多** —— 它直接给出 v0.9.5 的作业面：
   **要动的是 90 条、横跨 5 个模块，只改 admin 包会漏 37 条。**
2. **差点造一个假发现**：见 `catalog.py:253` 自述「无 catalog 级 RBAC」，而 CLAUDE.md 说 v0.8 上了
   「**目录** RBAC」→ 疑其陈旧。查实：`bi_reports.set_permission` 只收 `folder_id`/`report_id`
   ⇒ 「目录」= folder 粒度，**不是** catalog 粒度 ⇒ 那句自述**实质仍准确**，只有版本指针陈旧。
   （教训重复：CLAUDE.md 的措辞不能当 grounded 事实用。）
3. **R2 revert 锚点写错**（`source: str,` 命中 0 次）→ 脚本报 `BADMUT` 而非假红，用正确锚点重跑。
   （v0.9.4 教训生效：坏 revert 的假红与绿测的假绿同样没用，故脚本对锚点命中数硬校验。）
4. **D5' 的注入手法第一版触发了被测代理**：`monkeypatch.setattr(mod, x, raising=False)` 也会先
   `getattr` 探一次 → 命中 PEP 562 代理 → `KeyError: 'xnew_slot'`。改走 `__dict__` setitem。
   踩出来的**副产物**已记 CHANGELOG（代理裸下标 ⇒ `hasattr` 会炸而非返 False；今天不可能发生，只记不修）。

### §8.3 R-C3 取材汇总：**12 组逐条实跑，12/12 符合期望**

R1 冻结 revert · R2 签名加未登记参 · R2' 签名删已登记参 · R3 去派生 · R4 别名→真 slot 反证 ·
R5 `global XNEW`（未登记名） · R6 `global TABLES`（已登记名，证包含关系） · R7 `_CACHE={}` ·
R8 `_CACHE=dict()`（调用形） · R9 抄 4 名清单 · **R10 抄 3 名边界（刻意 green）** · R11 派生链路复合
（注册表加第 7 名 + 别处 from-import 它 → 派生的哨兵真红）。
commit 1 的 D1'/D2'/D3'/D7' 取材见该 commit message。mutation 后 `git diff knot/` 实测零残留。

### §8.4 Stage 4 请重点看

1. **§8.1-2 那条解读**（IV-4(c) 放测不放生产）—— 若判我理解错，是一行改动。
2. **§8.1-3 移交一条哨兵**是否可接受（我认为包含关系已实测坐实，但删/移交哨兵该由你裁）。
3. **`__code__` 身份**这个 LOCKED 洞的补法是否守住了 D2' 的实质。
4. **D10' 的 23 条理由**有没有哪条其实是**误挂**而我替它编了理由 —— 这是本片最该被对抗的地方
   （「快照会把今天的状态祝福成正确」的风险，在我这一层同样成立）。
5. **镜像面扫描**（34 条 AUTHENTICATED + 10 条 REPORT_PERMISSION）我只发现 1 条已登记开放项，
   请核有没有漏 —— 我的分类器**看不见函数体内的守护**，这个盲区已写进两处 docstring。
