# chore —— 破坏性 CLI 的审计留痕（`BL-v0915-3`）

> **触发**：v0.9.15 合并后，kk 的口令与我报的对不上。查得动的：5 次 `auth.login_fail`
> （`attempted_username: "admin"` / `reason: "bad_password"`）+ 上次成功登录 7-22。
> **查不动的**：那个哈希**是什么时候被谁写的** —— 因为 `reset_admin_password` 写库**不写审计**。
> ⇒ 「同一件事经端点做有痕、经 CLI 做无痕」这处**不对称**就是本片要修的东西。

## §0 grounded 事实（全部实读，非记忆）

| 事实 | 出处 |
|---|---|
| 端点侧**有**审计：`user.password_reset` 成功/失败都记 | 真实库审计表实读（08:30:39 ok=0 / 08:30:57 ok=1） |
| `reset_admin_password` / `migrate_encrypt_v045` **零**审计 | 三脚本实读 |
| `purge_audit_log` 只在 `deleted > 0` 时记 `audit.purge` | `purge_audit_log.py` `if not dry_run and deleted > 0:` |
| 文档声明的 `trigger="cli"` **无生产者** | 全仓 `trigger=` 只有 `"auto"`（main.py）与默认 `"manual"` |
| `audit_repo.insert` **自己开连接 + commit + close** | `audit_repo.py:18,28,29` |
| `audit_service.log` R-47 **fail-soft 吞异常**（仅 `TenantContextError` 重抛） | `audit_service.py:115-140` |
| `audit_repo.insert` 生产调用方**只有** `audit_service.py:101` | 全仓 grep（其余是 `platform_audit_repo.insert`，不同函数） |
| `platform_audit_repo.insert(conn, ...)` **连接由调用方注入** = v0.9.8 同事务范式 | `platform_audit_repo.py:56-57` |
| R-13 哨兵只禁「自建 ctx 的**前缀**」里碰 ctx；审计写在 `set_active_tenant` **之后** ⇒ 不违规 | `tests/test_self_built_ctx_prefix.py` docstring |
| 现成可复用 Literal：`user.password_reset`、`audit.purge` | `models/audit.py` |
| 凭据迁移**无**对应 Literal / resource_type | 同上（`AuditResourceType` 无 crypto 类） |

## §1 设计

1. **`audit_repo.insert` 加可选 `conn=None`**：给了就用调用方的连接、**不 commit 不 close**（调用方拥有事务）；
   不给则完全走今天的路径 ⇒ 唯一生产调用方 `audit_service.log` **行为 byte-equal**。
   ⭐ **为什么必须这样而不是「加一个 `audit_service.log` 调用」**：后者做不到它声称的事 ——
   自开连接 + fail-soft 吞异常 ⇒ 「动作成了、审计没写、还打印 ✓」原样保留。
2. **`reset_admin_password`**：`UPDATE users` 与审计 INSERT **同连接、同事务、单次 commit**
   ⇒ 「做了但没记」/「记了但没做」结构上不存在。detail 只含 `via/script/tenant_id/tenant_slug`，
   ⛔ 绝不含口令或哈希片段。
3. **`purge_audit_log`**：CLI 真跑**无条件**记（含 `deleted == 0`）；`auto` 保持 `deleted > 0` 条件。
   ⚠️ **这是刻意的策略分叉**（v3.1-B #10 自查）：判别式是「**谁触发的**」——
   CLI 是人的破坏性动作，不论结果都要可追溯；auto 每次启动都跑，无条件记会把审计表刷满噪声
   （v0.9.9 同款判断：预期路径刻意不记）。同时补上 `trigger="cli"`（文档声明已久、**从无生产者**）。
4. **`migrate_encrypt_v045`**：新 Literal `crypto.migrate_encrypt` + 新 resource_type `crypto`，
   按租户逐个记（真跑；dry-run 不记），detail 只含计数与租户标识。

## §2 v3.1-B 承重面枚举（命中：审计 · 凭据/加密 · 删除数据）

1. **fail-open 面**：判据写错会 fail-open 吗？—— **不会，且方向相反**：审计与动作同事务
   ⇒ 审计写不进去 ⇒ 动作**也不发生**（fail-closed）。⚠️ 代价要说清：审计层的 bug 会挡住运维动作。
   这是刻意选择 —— 破坏性动作宁可做不了，也不要**做了查不到**（本片的起因就是后者）。
   ⭐ 与本仓刚立的「破坏性工具不得有默认目标」同族：**破坏性动作也不得有沉默的执行**。
2. **oracle 能力**：判据能表示「做了但没记」吗？—— 能，且**注入真能产生它**：
   monkeypatch `audit_repo.insert` 抛错 ⇒ 若非同事务，口令哈希会**变**（旧行为）；同事务则**不变**。
   ⇒ oracle = 哈希是否变，**不是** 有没有抛异常（v3.1-B #2 后半）。
3. **「那一行」族**：记录与被记录的动作是**同一个事件**（同连接、同事务、单次 commit）——
   这正是 v0.9.8 platform_audit 的承重设计，本片把它用到租户侧 CLI。
4. （并入 #3）
5. **散文规则无守护？**——「detail 不得含凭据」配 AST + 行为双守护；「同事务」配注入测。
6. **声明 vs 生产者**：新 Literal `crypto.migrate_encrypt` **有 emit**（配 per-prefix 守护，
   与 metric/bi 两处同形）；新 resource_type `crypto` 有消费者（该 emit）。
   ⭐ 反向：本片顺手补上 `trigger="cli"` —— 它是**有声明无生产者**的现成实例。
7. **顶班**：摘掉同事务后会不会有别的门顶班让测继续绿？——
   ⇒ 故 oracle 取「哈希变没变」（唯一能区分）而非「有没有审计行」（旧行为下也会有，只是另一个事务）。
8. **既有测的绿是真的吗**：`tests/scripts/test_purge_audit_log.py` 现有断言依赖 `deleted > 0` 才记吗？
   —— 实施时逐条读，**改条件必须同时改它的理由，不是只让它继续绿**（v3.1-B #8 扫两侧）。
9. **契约冲突**：`audit_repo.insert` 加参数会不会破 R-47 fail-soft 契约？——
   不会：fail-soft 在 `audit_service.log` 里，本片**不动它**；CLI 直调 repo 是**刻意绕开 fail-soft**
   （R-47 的原意是「请求路径业务不阻断」，CLI 没有这个需求，且它的正确行为恰恰相反）。
10. **策略题的影子**：#3 的「CLI 无条件记 / auto 仍带条件」是策略分叉 ⇒ 已给判别式（谁触发）并写明理由。
11. **诚实收窄**：本片**不声称** —— 平台侧 `platform_audit` 不收这些行（动作在租户库，跨库无法同事务）·
    运维直接 `sqlite3 UPDATE` 仍无痕（同 v0.9.8 的诚实边界）· 不改 `audit_service.log` 的 fail-soft ·
    不给 `scan_secrets_at_rest` 加审计（只读）。

## §3 验收

- 三个脚本真跑各写一条审计行；`--dry-run` **零审计行**（反向守护）。
- **注入 `audit_repo.insert` 抛错 ⇒ 口令哈希一个字节不变**（同事务的唯一判据）。
- detail 里搜不到口令/哈希片段。
- 新 Literal 有 emit（per-prefix 守护）。
- 四闸门 + 全量绿。

---

## §4 实施记录

### §4.1 落地形态（与 §1 的偏离都在此）

| 件 | 实际做法 | 与 §1 的差 |
|---|---|---|
| `audit_repo.insert` | 加可选 `conn=`；给了就用调用方连接、**不 commit 不 close** | 同 §1 |
| **新** `knot/services/cli_audit.py` | 三个 CLI 的**唯一**审计写口（93 行） | §1 没提 —— 见下 |
| `reset_admin_password` | `record_password_reset(conn, …)` 与 `UPDATE` **同事务单次 commit** | 同 §1 |
| `purge_audit_log` | `trigger != "auto"` 时无条件记 + `_main` 传 `trigger="cli"` | 同 §1 |
| `migrate_encrypt_v045` | `record_migration(t, stats, dry_run=…)` | 同 §1 |

**为什么多出一个 `cli_audit` 模块（§1 里没有）**：两个原因，都是实施期才成立的。
① `migrate_encrypt_v045.py` 原本 **299/300 行**，把 emit 直写进去会顶破 size gate ——
而**新增 ACK 条目**意味着「这个文件从此永久超默认 cap」，代价比抽一个 helper 大；
按本仓 ACK 惯例（`main.py` 那条写着「原先写在 main.py 里的版本要 +42 行，那不是 cap 该让路的理由」）
应当**先压到装配下限**：抽 helper 后调用点 **1 行** ⇒ 正好 300，**零新增 ACK**。
② 更重要的是它本来就该收敛：「actor 恒 None」「detail 白名单（⛔ `backup_path`）」「dry-run 不写」
这三条判断散在三处就是三份会漂的判断。

### §4.2 六次取材，逐条唯一抓住

| 取材 | 结果 |
|---|---|
| **A** 退回旧实现（审计自开连接 + fail-soft 吞） | `1 failed, 12 passed` —— **只有同事务那条抓住** |
| **B** purge 条件退回 `deleted > 0` | `1 failed, 12 passed` |
| **D** `backup_path` 塞进迁移 detail（#262 家族） | `1 failed, 12 passed` |
| **E** helper 吞掉审计写失败 | `3 failed`（两个参数化 + 连带） |
| **G** 表态清单塞过期条目 | 见 §4.3 —— **初版假通过，修后 `1 failed, 12 passed`** |
| **F** 签名加凭据参数 | 结构测直接拒（`record_password_reset` 参数集固定） |

⭐ **A 是本片最该读的一条**：它证明了「有没有审计行」这个直觉判据**没有判别力** ——
旧实现在正常路径上**也会**留下审计行；能区分两个实现的只有**注入失败时的行为**
（旧：哈希变了 + 打印 ✓；新：哈希没变 + 异常上抛）。
⇒ oracle 取「**哈希变没变**」，不是「有没有行」。

### §4.3 我这一片自己犯的四个错（都被自己的判据抓到）

1. **「加一个 `audit_service.log` 调用」做不到它声称的事**（这是我给 kk 的原始描述）——
   自开连接 + fail-soft ⇒ 事故形态原样保留。已在实施前就报给 kk 并改设计。
2. **哨兵先判错、再收窄**：初版要求三个 CLI 都不得直连底层写口 ⇒ 把 `purge_audit_log` 判成违规。
   实际它是**对的**：`purge()` 被服务端启动期 auto-purge 共用，改走 `cli_audit`（刻意抛异常）
   会让一次审计写失败**崩掉 boot** —— 而 R-47 fail-soft 在服务端路径上正是对的。
   ⇒ **一般化：「唯一写口」这类规则的作用面是「只有该形态会走的写者」**；
   强行统一会把两条**互斥**的正确策略混成一条。已改为带理由的表态清单。
3. ⭐ **反向判据用了裸子串，假通过** —— `q.rsplit(".")[-1] in text` 就是拿 **`log`** 搜文本；
   实测命中的是**我自己那行提到 `audit_service.log` 的注释**。
   ⇒ **R-SENTINEL-AST 的根因原话再一次应验：讨论一个名字的文件必然含有那个名字。**
   改成两测**共用一次 AST 测量**（正向找违规 / 反向找过期豁免）后，G 才真的抓住。
4. **我的字符串手术吃掉了两个测**（切片切到文件末尾）而**全绿** —— 13 → 10。
   靠 `pytest --collect-only` **节点 ID 集合**比对发现（不看数字看集合）。
   ⇒ 「验收的完整性也要检查」：我验的是绿，该验的是**形状**。

⭐ **这四个错里有三个是同一形状**：判据锚错了对象（锚在「有没有行」/锚在文本子串/锚在绿不绿），
而该锚的是：注入失败时的行为 / 那个调用是否存在 / 测试集合有没有变。
