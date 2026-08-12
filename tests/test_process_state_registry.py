"""⭐ 哨兵：`knot/` 的**进程级可变状态清单必须是派生的**（v0.9.23 R10'-E）。

## 它守什么
「多副本安全」这件事的作业面 = **每个副本各有一份、且会在运行期变化的东西**。
本仓已实证：**手写这份清单必然漏** —— R10' Stage 1 逐条实读后发现
`v0.9-lift-arc-remaining-plan.md` / `DEPLOY.md` 那张（**抄了两处的**）表
**5 行里 4 行要改、另漏 3 项、多 1 项**。
⇒ 本哨兵把清单变成**派生的**：扫出来的集合必须与下面那张**具名登记表逐一相等**。
**新增一个进程级可变状态而不登记 ⇒ 红；登记表里留着已删除的条目 ⇒ 也红。**

## ⚠️⚠️ 四支扫描面（按**行为**，不按形态 —— v0.9.18 P-a 的教训）
| 支 | 判据 | 为什么单列 |
|---|---|---|
| ① 被改写的模块级名字 | 模块里存在 `x[k]=v` / `del x[k]` / `x[k]+=v` / `x.append(...)` 等 / `global x` | 最直接的形态 |
| ② **fail-closed 构造** | 模块级 `x = SomeCall(...)`，且 callee 不在 `_PURE_FACTORIES` 里 | ⭐ **① 抓不到 `_bucket = _Bucket()`** —— 它的改写发生在**对象自己的方法内**（`self._d`），模块级那个名字从没被赋值过（实施期实测漏掉） |
| ③ `@lru_cache` / `@cache` | 装饰器 | 它**连赋值语句都没有** |
| ④ `global` 语句 | `global x` | 运行期改模块级名字的显式形态 |

⚠️ ② **必须 fail-closed**（未知 callee 一律要求登记）：白名单是「已判定为纯」的工厂，
而**新出现的构造默认可疑** —— 反过来（黑名单）会让「换个类名」成为逃逸口。

## ⚠️ 本哨兵**不覆盖**什么（诚实边界，Stage 3 守护者指出的盲区）
它扫的是**模块级状态**，**看不见 DB 层的 read-then-write**（那类多副本缺陷在 SQL 里，不在模块里）。
R10' 实施期已按行为扫过一遍全仓：累加写法**全是原子的**（`x = x + ?`，3 处），
其余 `SET x=? WHERE` 是 `sort_order`/`title` 之类的 last-writer-wins 非计数字段。
⇒ **别把本哨兵的绿读成「多副本安全」**，它只保证「没有未登记的进程内状态」。
"""
from __future__ import annotations

import ast
import pathlib

_REPO = pathlib.Path(__file__).resolve().parents[1]

#: 已判定为**纯**（构造出来的东西不持有跨请求可变状态）的工厂。⚠️ 加条目 = 明确声明「它是纯的」。
_PURE_FACTORIES = {
    "re.compile", "frozenset", "tuple", "int", "float", "str",
    "logging.getLogger", "_log.getLogger",          # logger 由 stdlib 管，非业务状态
    "APIRouter", "FastAPI", "HTTPBearer",           # 路由/依赖声明，注册期一次性
    "os.getenv", "object",
    "contextvars.ContextVar", "ContextVar",         # **请求级**上下文，不是跨请求状态
}

#: 被改写就算命中的方法名（形态①）。
_MUT_METHODS = {"append", "add", "pop", "clear", "update", "extend", "setdefault", "insert", "remove", "discard"}

#: ⭐⭐ **具名登记表** —— key = `文件:名字`，value = **多副本后果 + 为什么可接受 / 已怎么处置**。
#: ⚠️ 加新条目时**必须回答那个问题**，别只填「cache」。这张表就是 R10' 的作业面真相源。
_REGISTRY: dict[str, str] = {
    # ── 承重（R10' 处置过或明确登记的）──────────────────────────────
    "knot/services/engine_cache.py:_engine_cache":
        "数据源引擎+schema 缓存。v0.9.23 R10'-A：连接指纹进键尾部 ⇒ 配置变则键变（陈旧结构性消除）；"
        "TTL 仍管远端 schema 陈旧；换指纹时旧条目被淘汰并 dispose 旧连接池。",
    "knot/api/_rate_limit.py:_bucket":
        "⚠️ **限流桶，每副本一份 ⇒ 有效限额 ×N**（爆破防护被削弱 N 倍）。"
        "R10' 的 B 项（共享计数器 + 可信 IP 来源）**已拆成独立片**，本片未处置 —— 见 "
        "docs/plans/v0.9.23-R10prime-multi-replica-safety.md §1-B。"
        "另登记既有缺陷：`_MAX_KEYS` 在**活跃**喷射下无效（实跑：15000 活跃 key 时上限形同不存在）。",
    "knot/services/upload_engine.py:_upload_engines":
        "到本租户 uploads.db 的 engine，键 (tid, 绝对路径)、**无陈旧语义**（路径由 ctx 派生）。"
        "R10' 裁定**不动**；⚠️ 真实风险是 uploads.db 用的是 **rollback-journal**（`create_sqlite_engine` "
        "不设 WAL）⇒ 提交阶段阻塞读（实测 135ms/40 万行），一行 `PRAGMA journal_mode=WAL` 可消除，本片不做。",
    "knot/services/upload_engine.py:_uploads_path_owner":
        "⚠️ **fail-closed 安全 tripwire**（同物理路径被两 tid claim 即 raise），**每副本一份** ⇒ "
        "副本 A 触发、副本 B 不触发；今天由 `idx_tenants_db_dir` UNIQUE 兜住。",
    # ── 有界 / 自愈 / 可接受 ────────────────────────────────────────
    "knot/services/totp_service.py:_TOKEN_VERSION_CACHE":
        "JWT 吊销版本 TTLCache(ttl=60) ⇒ 改密/重置后**别的副本最多晚 60 秒**才拒旧 token。有界，可接受。",
    "knot/services/agents/catalog_state.py:_state":
        "per-tenant catalog 槽。`pick_http_route` **每 query 无条件 reload** ⇒ 跨副本陈旧**当场自愈**。",
    "knot/adapters/notification/lark.py:_token_cache":
        "Lark tenant-token 缓存（v0.9.18 已按租户键化）⇒ 跨副本只是各自 miss 一次，无正确性影响。",
    "knot/api/admin/datasources.py:_DS_STATS_CACHE":
        "数据源统计缓存 ⇒ 各副本各自探测，cosmetic（admin 面板数字可能不同）。",
    "knot/api/admin/datasources.py:_DS_STATUS_CACHE":
        "数据源健康探测缓存 ⇒ 各副本各自探测、各自缓存，admin 面板上的健康状态可能不同步，cosmetic。",
    "knot/adapters/http/url_allowlist.py:_BAD_ENTRY_WARNED":
        "坏 allowlist 条目的**告警去重集**（`_parse` 每次调用都重跑，不去重会每请求刷一条）⇒ "
        "跨副本各自打一次 WARN，无正确性影响。",
    "knot/adapters/http/url_allowlist.py:_PORT_WARNED":
        "异常端口告警的去重集 ⇒ 跨副本各打一次 WARN（日志略重复），无正确性影响。",
    "knot/adapters/notification/webhook.py:_BAD_ENTRY_WARNED":
        "webhook allowlist 坏条目的告警去重集 ⇒ 跨副本各打一次 WARN，无正确性影响。",
    "knot/services/auth_service.py:_dummy_hash":
        "登录失败路径的 dummy bcrypt（防用户枚举时序侧信道）**惰性初始化、只写一次** ⇒ 各副本各算一次，无影响。",
    # ── ⚠️ 可观测性：多副本下会**变回静默**（本片只登记，见 §6 D3）────────
    "knot/services/audit_service.py:_audit_write_failures_total":
        "⚠️ **审计写入失败计数器**，由 admin metrics 路由读。**每副本一份** ⇒ admin 查到的是"
        "**随机某个副本的数** ⇒ 可能读到 0 而另一个副本已累计 50。它的存在理由就是让静默失败可见，"
        "而多副本把它变回静默。R10' 裁定：**只登记，不在本片修**（需要真 metrics 通路）。",
    "knot/core/tenant_context.py:_drift_state":
        "⚠️ **租户漂移计数器**（R-10）。同上：每副本一份 ⇒ 跨副本不可聚合。只登记。",
    "knot/core/tenant_context.py:_drift_lock":
        "上面那个计数器的锁。进程内互斥即可（它保护的状态本身就是进程内的）。",
    "knot/services/agents/catalog_state.py:_lock":
        "catalog 槽的 RLock。同上 —— 它保护的状态是进程内的，锁不需要跨副本。",
    # ── 不可变 / 启动期一次性（登记以证明「已核过」）──────────────────
    "knot/core/crypto/fernet.py:get_crypto_adapter":
        "`@lru_cache(maxsize=1)` 的 Fernet adapter：各副本从**同一个 env** 建同一个 adapter；"
        "主密钥轮换本就需要重启 ⇒ 无害。",
    "knot/services/source_fingerprint.py:_PROC_SALT":
        "指纹用的**进程随机 salt**（v0.9.23 R10'-A）。**刻意每副本不同** —— 缓存本就进程内，"
        "跨进程不需要可比；它的作用是让指纹不是「明文口令的字典可查摘要」。",
    "knot/api/admin/or_catalog.py:_OPENER":
        "装了 `_NoRedirect` 的 urllib opener（v0.9.22）。无状态、各副本等价。",
    "knot/api/deps.py:JWT_SECRET":
        "⚠️ import 期从 env 读的 JWT 签名密钥。**多副本必须同值** —— 各副本 env 不同则"
        "A 签的 token 在 B 上验签失败（表现为随机 401）。⇒ 部署侧约束，不是代码可修的。",
    "knot/core/logging_setup.py:_LEVEL":
        "import 期从 env 读的日志级别（不可变）⇒ 各副本 env 相同则等价。",
    "knot/core/logging_setup.py:_FORMAT_MODE":
        "import 期从 env 读的日志格式（不可变）⇒ 同上。",
    "knot/main.py:_cors_env":
        "import 期从 env 读的 CORS 配置串（不可变）⇒ 同上。",
    "knot/repositories/base.py:_SCHEMA_SQL":
        "import 期读入的租户库 `schema.sql` 文本（不可变）⇒ 各副本等价。",
    "knot/repositories/platform_migrations.py:_PLATFORM_SCHEMA":
        "import 期读入的 `platform_schema.sql` 文本（不可变）⇒ 各副本等价。"
        "⚠️ 但**并发首启**时多副本同时 `executescript` 它会撞 `database is locked` —— "
        "那是另一片（首启建库竞态），不是本条目的问题。",
    "knot/config/settings.py:settings":
        "配置单例，import 期从 env 读一次、之后只读 ⇒ 各副本等价（env 相同）。",
    "knot/adapters/llm/anthropic_native.py:_check":
        "import 期的 Protocol 一致性自检对象（`_check: LLMAdapter = XxxAdapter(...)`），不参与请求。",
    "knot/adapters/llm/openai_compat.py:_check":
        "同 anthropic_native：import 期 Protocol 一致性自检对象，不参与请求、各副本等价。",
    "knot/adapters/llm/openrouter.py:_check":
        "同 anthropic_native：import 期 Protocol 一致性自检对象，不参与请求、各副本等价。",
    "knot/services/agents/clarifier.py:_CLARIFIER_SYS":
        "启动期从 `knot/prompts/*.md` lazy load 的 system prompt 字符串（不可变）。",
    "knot/services/agents/presenter.py:_PRESENTER_SYS":
        "启动期从 `knot/prompts/presenter.md` 读的 system prompt（不可变；DB 覆盖走另一条路径）。",
    "knot/services/agents/da_asst.py:_DA_ASST_SYS":
        "启动期从 prompts 目录读的 system prompt（不可变）。",
    "knot/services/agents/sql_planner_prompts.py:_AGENT_SYSTEM_TEMPLATE":
        "启动期从 `knot/prompts/sql_planner.md` 读的 system prompt 模板（不可变）。",
}


def _mutated_names(tree: ast.AST) -> set[str]:
    """形态①/④：模块里被改写的名字。⚠️ **必须含 `AugAssign`** —— 实施期实测漏过
    `_drift_state["count"] += 1`（它是 `AugAssign` 而不是 `Assign`）。"""
    out: set[str] = set()
    for n in ast.walk(tree):
        tgts = []
        if isinstance(n, ast.Assign):
            tgts = list(n.targets)
        elif isinstance(n, ast.AugAssign | ast.AnnAssign):
            tgts = [n.target]
        elif isinstance(n, ast.Delete):
            tgts = list(n.targets)
        for t in tgts:
            if isinstance(t, ast.Subscript) and isinstance(t.value, ast.Name):
                out.add(t.value.id)
            elif isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name):
                out.add(t.value.id)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) \
                and n.func.attr in _MUT_METHODS and isinstance(n.func.value, ast.Name):
            out.add(n.func.value.id)
        if isinstance(n, ast.Global):
            out.update(n.names)
    return out


def derive_process_state() -> dict[str, str]:
    """→ {`文件:名字`: 命中的支}。**这就是那份「派生的清单」。**"""
    found: dict[str, str] = {}
    for py in sorted((_REPO / "knot").rglob("*.py")):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        rel = py.relative_to(_REPO).as_posix()
        mut = _mutated_names(tree)
        for node in tree.body:
            names, val = [], None
            if isinstance(node, ast.Assign):
                names = [t.id for t in node.targets if isinstance(t, ast.Name)]; val = node.value
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                names = [node.target.id]; val = node.value
            for name in names:
                if val is None:
                    continue
                key = f"{rel}:{name}"
                if isinstance(val, ast.Dict | ast.Set | ast.List) and name in mut:
                    found[key] = "①被改写的容器"
                elif isinstance(val, ast.Call):
                    fn = ast.unparse(val.func)
                    if fn in _PURE_FACTORIES or fn.split("(")[0].endswith(
                            (".read_text", ".strip", ".lower", ".upper", ".split", ".decode")):
                        continue
                    found[key] = "②fail-closed 构造"
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                for d in node.decorator_list:
                    s = ast.unparse(d)
                    if "lru_cache" in s or s.endswith(("functools.cache", ".cache")):
                        found[f"{rel}:{node.name}"] = "③装饰器缓存"
            if isinstance(node, ast.Global):
                for nm in node.names:
                    found.setdefault(f"{rel}:{nm}", "④global 语句")
    return found


def test_process_state_registry_is_exactly_the_derived_set():
    """⭐⭐ **派生集合 == 具名登记表**（双向）。

    - **多出来（未登记）** ⇒ 红：新增了进程级可变状态而没人回答「多副本后果是什么」；
    - **少了（登记表里有而代码里没了）** ⇒ 也红：过期条目会静默留在表里，
      而本仓的教训正是「清单会漂，而漂掉的条目不会让任何东西红」。
    """
    derived = derive_process_state()
    missing = {k: v for k, v in sorted(derived.items()) if k not in _REGISTRY}
    stale = sorted(set(_REGISTRY) - set(derived))

    assert not missing, (
        "⛔ 以下**进程级可变状态未登记**：\n  "
        + "\n  ".join(f"{k}  [{v}]" for k, v in missing.items())
        + "\n\n⇒ 请加进 `_REGISTRY`，并**回答那个问题**：**N 个副本各有一份时会发生什么？**"
          "（承重 / 有界可接受 / 自愈 / cosmetic —— 别只写「cache」。）"
    )
    assert not stale, (
        f"⛔ 登记表里有**代码里已不存在**的条目: {stale}\n"
        "⇒ 过期清单不会让任何东西红，这正是本哨兵要防的形状。请删掉它们。"
    )


def test_registry_entries_answer_the_multi_replica_question():
    """⭐ 每条登记必须**真的写了理由**，不是占位。

    ⚠️ 判据刻意不是「非空」（那太弱）：要求 ≥ 30 字符**且**不是纯占位词。
    """
    bad = [k for k, v in _REGISTRY.items()
           if len(v.strip()) < 30 or v.strip().lower() in {"cache", "缓存", "todo", "n/a"}]
    assert not bad, f"以下登记条目没有真正回答「多副本后果」: {bad}"


def test_pure_factory_allowlist_is_not_a_loophole():
    """⭐ 白名单只允许**已判定为纯**的工厂 —— 不得混进任何会持有可变状态的类型。

    ⚠️ 本条是防「为了让哨兵变绿，把自己的类塞进白名单」这条逃逸路径：
    白名单里出现**本仓自己定义的名字**（不含点号且首字母大写 / 以 `_` 开头）即红。
    """
    suspicious = [f for f in _PURE_FACTORIES
                  if "." not in f and (f.startswith("_") or (f[:1].isupper() and f not in
                                                             {"APIRouter", "FastAPI", "HTTPBearer", "ContextVar"}))]
    assert not suspicious, (
        f"纯工厂白名单里出现了可疑条目 {suspicious} —— "
        "白名单只放「构造出来的东西不持有跨请求可变状态」的工厂；"
        "把自己的类塞进来会让整个哨兵失效。"
    )
