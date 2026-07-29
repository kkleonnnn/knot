# chore（Stage 1 草案）：路由级守护哨兵 + 载体名清单派生

> **性质**：0 行业务行为改动的**闸门加固** chore。**但它动的是闸门本身** —— 写错会给后面所有片子**假绿**，
> 故照 Loop Protocol v3 走完整三阶段（不套用 R-LP-v3-EX-1 的方向决策例外：本片有代码改动）。
> **动因**：kk 2026-07-29 拍板 —— v0.9.5 要动 90 处 admin 依赖，**先架安全网再动**；
> 并把 v0.9.3 遗留的载体名 backlog 并入本片（同一类问题，评审时可互相印证）。

---

## §1 两条的今日实况（**执行者自核，非转述**）

### A. 路由 × 守护：只数条数，从不断言身份

| 今天有的 | 断言了什么 |
|---|---|
| `test_tenant_isolation.py:172` | `len(flatten_app_routes(app)) == 144`（**条数**） |
| `test_admin_package.py:36` | `len(admin_routes) == 53`（`/api/admin/` 前缀 **且**来自 `knot/api/admin/` 包） |
| `test_api_smoke.py:35` | `>= 80`（软下限） |
| 行为 403 spot check | **8 条**不同 admin 路由（users / recovery-stats / cost-stats / datasources ×2 / monitors / audit config / audit list） |

**缺口（我实跑确认）**：
- **全仓 0 处** introspect 路由的 `dependant` ⇒ **没有任何测断言「某条路由仍受 `require_admin` 守护」**。
  90 处依赖换门时**漏一个不会红**。
- **没有测钉住「恰 4 条无鉴权路由」** —— v0.9.4 只写了行为测（`test_noauth_get_paths_no_5xx` 断言不 5xx），
  没有结构断言。新增一条无鉴权路由今天**静默通过**。

**我自己数出的基线（与测绘 agent 逐字一致）**：
```
APIRoute 总数 = 138 · 受 require_admin 守护 = 90 · 其中不在 /api/admin/ 前缀下 = 23
无 get_current_user = 4：/api/auth/login · /api/bi/scheduler/tick · /api/totp/verify · /{full_path:path}
23 条的模块分布：bi_reports 7 · few_shots 5 · prompts 5 · knowledge 3 · database 1 · templates 1 · totp 1
```
⚠️ **`53` 与 `90` 不是同一个量**：前者是「`/api/admin/` 前缀且来自 admin 包」，后者是「实际受
`require_admin` 守护」。二者差 37，正是「按前缀/按包判据会漏掉的那片」。

### B. 载体名：4 份硬编清单，改一漏一不会红

| # | 位置 | 形态 | 内容 |
|---|---|---|---|
| 1 | `knot/services/agents/catalog.py:28` `_ATTR_TO_SLOT` | dict（**唯一含 slot 映射**，事实上的真相源） | 6 名 → slot key |
| 2 | `knot/services/agents/catalog_state.py:39` `CARRIER_NAMES` | tuple（生产，复活检测用） | 同 6 名 |
| 3 | `tests/test_catalog_tenant_isolation.py:25` `_CARRIER` | tuple（测） | 同 6 名 |
| 4 | `tests/services/test_catalog_loaders.py:16` `_MUTABLE_GLOBALS` | set（测，4 条哨兵都用它） | 同 6 名 |

**MUTANT-E 实证（v0.9.3 守护者 §IV-1）**：加第 7 个载体名 + 在 `reload()` 里 `global` 它
→ **26 测全绿逃逸**，代理对该名静默死。`FIELD_LABELS` 自 v0.7.27 起就长期在哨兵外，正是同机制。
⇒ **v0.9.3 修了实例（补 FIELD_LABELS）未修机制。**

**承重约束（决定注册表该放哪）**：`catalog.py:18` **import** `catalog_state`
⇒ `catalog_state` **不得** import `catalog`（循环）。故注册表必须落在 `catalog_state`（载体的所有者），
由 `catalog.__getattr__` 消费 —— 依赖方向不变。

---

## §2 决议（待 Stage 2/3 裁定）

### D1 路由哨兵：**扫描面派生、期望值钉住**
- **扫描面 = 派生**：`flatten_app_routes(app)` 全量 + 逐条 introspect `dependant`（递归收集依赖 `__name__`）。
  ⇒ 新增路由**自动纳入**，不需要人往清单里加。
- **期望值 = 钉住快照**：受 `require_admin` 守护的 **90 条** `"METHOD /path"` 排序列表 + 无鉴权的 **4 条**。
  失败信息给 **added / removed 差集**（不是「90 != 91」这种不可行动的数字）。
- ⚠️ **与 v0.9.4 MF2 的「漂移清单」形状不同，须说清**：MF2 的坑是**扫描面**硬编（漏端点就漏检）；
  这里硬编的是**期望值**（快照），而快照**本就必须**被钉住，否则无从检测漂移。二者不可混为一谈。

### D2 守护者身份**精确等值**，不做名字模糊匹配
断言依赖集合里含 `require_admin` **这个函数对象/精确名**，而非「名字里带 admin」。
理由：防有人把某条路由换成一个**更弱**的自定义 admin 依赖而哨兵仍绿。

### D3 反向：无鉴权路由集合也钉住（4 条）
今天没有这条 ⇒ 新增无鉴权路由静默通过。钉住集合 + 每条附「为何允许无鉴权」的一行理由。

### D4 载体注册表移入 `catalog_state`（单一 home）+ 三处派生
- `_ATTR_TO_SLOT` 从 `catalog.py` **移到** `catalog_state.py`（载体所有者），`catalog.__getattr__` 读它。
- `CARRIER_NAMES` = 从注册表**派生**（`tuple(_ATTR_TO_SLOT)`），不再独立字面。
- 两处测清单改为 **import 派生**（`from knot.services.agents.catalog_state import CARRIER_NAMES`）。
- ⇒ 4 份清单 → **1 份真相源 + 3 处派生**。

### D5 MUTANT-E 回归测（证明「机制」而非「实例」被修）
往注册表**注入第 7 个名字**（monkeypatch），断言：代理认它 · 生产复活检测认它 · 两处测哨兵的目标集自动含它。
⇒ 这是 v0.9.3 那次逃逸的**直接反例测**。

### D6 静态守护：`tests/` 内不得再出现硬编的载体名元组
防将来又抄第 5 份。做法：AST 扫 `tests/`，任何**字面**集合/元组同时含 ≥3 个载体名即红
（阈值 3 而非 6：抄一半也算抄）。

---

## §3 红线

- **R-C1**：本片 **0 行业务行为改动**。`knot/` 侧只允许「注册表搬家 + 派生」，`catalog.TABLES` 等
  13 个 importer 的**外部可见行为 byte-equal**。
- **R-C2**：哨兵的**扫描面必须派生**；只有**期望值**可以是字面快照（D1 的区分必须写进测的 docstring，
  否则下一个人会误以为这与 MF2 的坑同形）。
- **R-C3**：**每条哨兵都配 revert-to-bad**，且 revert 必须是**语法有效**的坏改（v0.9.4 三次坏 revert 教训）。
- **R-C4**：`ruff --fix` **只对本片改过的文件**跑（v0.9.4 两次夹带 26 个无关文件的教训）。
- **R-C5**：不得顺手改任何被守护的路由/依赖（本片只加守护，不动被守护物）。

---

## §4 验收（每条须 revert-to-bad 自证）

1. 把某条 admin 路由的 `Depends(require_admin)` 去掉 → **哨兵红**且失败信息**点名该路由**。
2. 把某条 admin 路由换成自定义的弱 admin 依赖（名字含 admin）→ **仍红**（D2 精确等值）。
3. 新增一条无鉴权路由 → **D3 红**。
4. 新增一条受守护路由 → 哨兵红（提示 added），确认「新增也要显式登记」。
5. 往注册表加第 7 名（不改任何测）→ **D5 绿**（代理/复活检测/两处哨兵自动覆盖）；
   而**回退 D4 派生**（恢复 4 份字面清单）后同一操作 → **D5 红**（复现 MUTANT-E 逃逸）。
6. 在 `tests/` 里抄一份含 3 个载体名的字面元组 → **D6 红**。
7. 全量绿 + `catalog` 外部行为 byte-equal（13 importer 0 改动）。

---

## §5 commit 序（草案）

1. `test(guard)`: 路由守护哨兵（D1+D2+D3）—— 纯新增测，0 生产码
2. `refactor(catalog)`: 载体注册表移入 `catalog_state` + `CARRIER_NAMES` 派生（D4 生产侧，行为不变）
3. `test(guard)`: 两处测清单改 import 派生 + MUTANT-E 回归（D5）+ 禁硬编哨兵（D6）
4. `docs`: CHANGELOG（riding 当前版本**不 bump** —— 0 业务行为改动）+ 兑现 v0.9.3 §IV-1 backlog 登记

---

## §6 待 Stage 2/3 裁定的三个点

1. **快照放哪**：内联在测里（90 行字面，仓内风格如 `== 53`）vs 单独 fixture 文件（diff 更好读）。
   我倾向**内联**（少一个文件、且 review 时与断言同屏），但 90 行确实长。
2. **D6 的阈值 3** 是否合适（抄 3 个算抄？会不会误伤某个只用到 3 个载体名的正当测）。
3. **要不要顺手把 `test_admin_package.py:36` 的 `== 53`** 改成从新哨兵派生 —— 它与 90 是不同的量，
   留着会让下一个人困惑；但改它超出「只加守护」的范围（R-C5 边界）。倾向**只加注释说明二者差别**，不动它。

---

## §7 自检（抗诱惑）

- 不动被守护的路由/依赖（R-C5）· 不顺手改 `== 53` 那条既有断言（§6.3 待裁）·
- 不引入新 npm/py 依赖 · 不顺手 i18n · `ruff --fix` 只跑改过的文件（R-C4）·
- 不把「扫描面派生」和「期望值钉住」混为一谈（R-C2）· 每条哨兵配语法有效的 revert（R-C3）。
