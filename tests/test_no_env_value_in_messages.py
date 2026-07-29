"""SECURITY —— 报错/日志**只许出现 env 名，绝不许出现 env 值**（形状级守护）。

## 这条守护为什么存在（一个真实漏洞的形状）
`adapters/http/executor.py` 曾把读到的 env **明文**插进 `HTTPAuthError` 消息
（`f"auth env 缺失: {auth_header_env}={header_name!r} {auth_value_env}={header_value!r}"`）。
它单独看只是「日志写多了」，但接上另外三段就成了**可利用的机密外泄链**：

1. http 表的 `http_spec` 里的 **env 名由 catalog 提供，而 catalog 可由 admin 经
   `PUT /api/admin/catalog` 写入，服务端对 env 名零校验**；
2. admin 填 `auth_value_env="JWT_SECRET"` + `auth_header_env="<不存在的名>"` ⇒ 上面那个条件成立
   ⇒ 异常消息含 `JWT_SECRET` 明文（**此处在 egress allowlist 守护之前**，出境限制挡不住）；
3. `services/http_planner.run_http_step` 把 `str(e)` 原样放进 `result["error"]`；
4. `api/query.py` 把该字段**原样 yield 给客户端**。

⇒ **任意 admin 可读出进程内任意 env**。后果不是「admin 本来就有权」那么轻：
拿到 `JWT_SECRET` 可给任意用户伪造**完整** token，而伪造的完整 token 没有 `totp_pending`
⇒ **绕过 2FA**（2FA 的意义正是约束「口令已泄露的 admin」，且 R-LP-v3-EX-3-1 登记了全新部署
存在已知默认口令）；拿到 `KNOT_MASTER_KEY` 可解密全部已存数据源凭据。

## 为什么守「形状」而不只修那一行
修一行只解决这一处；本测扫**全仓**，让同形状的下一处在 CI 就红 —— 与本项目
「修机制不修实例」的既有教训一致（v0.9.3 载体名 / v0.9.4 哨兵别名两次踩过）。
"""
import ast
import pathlib

_REPO = pathlib.Path(__file__).resolve().parents[1]

# 例外按 **(文件, 被插入的变量名)** 精确登记 —— **刻意不按文件豁免**：
# 初版写成整文件豁免，随即发现 `deps.py` 里既有可豁免的 `val`，也有 `_get_secret()` 这种真敏感面
# ⇒ 文件级豁免会把该文件将来的真泄漏一起放过。用 (文件, 名) 对：粒度窄，且不随行号漂移。
# 每条都必须写明理由。
_ALLOWED = {
    # 运维自己在本机跑的 CLI，其输出**正是运维索取的东西**（不打印这个新口令，脚本就没用了）
    ("knot/scripts/reset_admin_password.py", "pwd"),
    # 启动期 fail-fast：仅在 `val in _BLOCKED_DEFAULTS` 分支打印，即那三个**源码里公开写着的**
    # 历史默认占位串（不是机密）；输出到 stderr 后 `sys.exit(1)`，非客户端可达路径。
    # 另两个分支只打印 `len(val)`，不打印值。
    ("knot/api/deps.py", "val"),
    # anyio 线程池大小（整数，来自 ANYIO_TOKENS），不是机密
    ("knot/main.py", "tokens"),
    # v0.9.5：`reason` 来自 `rejection_reason(os.environ.get(...))` ⇒ 被启发式判为 env 派生，
    # 但它**按契约只描述形状**（缺前缀 / 含 `.` / 长度不足），**永不含密钥值**。
    # ⚠️ **allowlist 会掩盖将来的改坏** ⇒ 配一条**直接守该 sanitizer 契约**的测：
    # `test_rejection_reason_never_echoes_input`。没有那条测，这条豁免就是个洞。
    ("knot/api/platform_admin.py", "reason"),
}


def _env_derived_names(tree) -> set:
    """本文件里「值来自 os.environ / os.getenv 的局部名」。"""
    out = set()
    for n in ast.walk(tree):
        if not isinstance(n, ast.Assign):
            continue
        dumped = ast.dump(n.value)
        if "environ" in dumped or "getenv" in dumped:
            for t in n.targets:
                if isinstance(t, ast.Name):
                    out.add(t.id)
    return out


def _fstring_leaks(py: pathlib.Path):
    """[(行号, [被插入的 env 派生名])] —— f-string 里直接插了 env 派生值的地方。"""
    try:
        tree = ast.parse(py.read_text(encoding="utf-8"))
    except SyntaxError:
        return []
    env_names = _env_derived_names(tree)
    if not env_names:
        return []
    hits = []
    for n in ast.walk(tree):
        if not isinstance(n, ast.JoinedStr):
            continue
        used = {v.value.id for v in n.values
                if isinstance(v, ast.FormattedValue) and isinstance(v.value, ast.Name)}
        leak = sorted(used & env_names)
        if leak:
            hits.append((n.lineno, leak))
    return hits


def _brace_log_leaks(py: pathlib.Path):
    """[(行号, [env 派生名])] —— **loguru 花括号 + 位置参数**形态的泄漏（v0.9.5 must-fix #1④ 扩）。

    ⭐ **为什么必须单独加这一支**：`_fstring_leaks` 只看 `ast.JoinedStr`
    ⇒ `logger.warning("平台密钥不合规: {}", tok)` **完全不经 f-string** ⇒ 原哨兵**看不见**。
    实测（扩之前）：一次注入三形态（花括号+位置参数 / `%`-格式 / 字符串拼接）**全部逃逸，测仍 3 passed**。

    ⚠️ **缺口真而窄**（AST 实测本仓 logger 首参形态）：**f-string 59 处（主流写法，原哨兵已覆盖）**·
    花括号+位置参数 **2 处**（均 `catalog_state.py:97,129`，不泄漏 env）· `%`-格式 **0** · 拼接 **0**。
    ⇒ 本函数补上唯一有实例的那一支。**`%`-格式与字符串拼接零实例、暂不覆盖**（登记 backlog）——
    刻意写在这里而不是假装已覆盖：哨兵的边界必须是**已知的**，否则下一个人会以为它管全部。
    """
    try:
        tree = ast.parse(py.read_text(encoding="utf-8"))
    except SyntaxError:
        return []
    env_names = _env_derived_names(tree)
    if not env_names:
        return []
    hits = []
    for n in ast.walk(tree):
        if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)):
            continue
        recv = n.func.value
        if not (isinstance(recv, ast.Name) and recv.id in ("logger", "log")):
            continue
        if not n.args or not isinstance(n.args[0], ast.Constant):
            continue
        used = {a.id for a in n.args[1:] if isinstance(a, ast.Name)}
        used |= {kw.value.id for kw in n.keywords if isinstance(kw.value, ast.Name)}
        leak = sorted(used & env_names)
        if leak:
            hits.append((n.lineno, leak))
    return hits


def test_SEC_no_env_value_passed_as_log_argument():
    """⭐ 全仓：`logger.x("... {} ...", <env 派生值>)` 形态也不得泄漏（must-fix #1④）。

    与 `test_SEC_no_env_value_interpolated_into_messages` 同源风险、不同语法形态。
    v0.9.5 的平台密钥 WARN 走的正是 loguru 花括号形态 ⇒ 不扩这一支，那条 WARN 无守护。
    取材=injection：在 `platform_admin.warn_if_noncompliant` 里把 `configured` 当参数传进 WARN → 本测红。
    """
    violations = []
    for py in sorted((_REPO / "knot").rglob("*.py")):
        rel = str(py.relative_to(_REPO))
        for lineno, names in _brace_log_leaks(py):
            flagged = [n for n in names if (rel, n) not in _ALLOWED]
            if flagged:
                violations.append(f"{rel}:{lineno} 把 env 派生值传进日志参数 {flagged}")
    assert not violations, (
        "日志参数泄漏 env 值（#262 形状 —— 只报 env **名**，绝不报 env **值**）：\n  "
        + "\n  ".join(violations)
    )


def test_SEC_no_env_value_interpolated_into_messages():
    """⭐ 全仓：f-string 不得插入「从 env 读出的值」（例外见 `_ALLOWED`，附理由）。

    revert-to-bad：把 `executor.py` 的报错改回 `f"...{auth_value_env}={header_value!r}"` → 本测转红。
    """
    violations = []
    for py in sorted((_REPO / "knot").rglob("*.py")):
        rel = str(py.relative_to(_REPO))
        for lineno, names in _fstring_leaks(py):
            flagged = [n for n in names if (rel, n) not in _ALLOWED]
            if flagged:
                violations.append(f"{rel}:{lineno} 插入了 env 派生值 {flagged}")
    assert not violations, (
        "报错/日志里出现了从 env 读出的**值** —— 只许出现 env **名**：\n  "
        + "\n  ".join(violations)
        + "\n\n为什么这不是小事：http 表的 env 名由 admin 可写的 catalog 提供、服务端零校验，"
          "而报错文本会经 `http_planner.run_http_step` → `api/query.py` 原样回到客户端 "
          "⇒ 任意 admin 可读出进程内任意 env（`JWT_SECRET` → 伪造完整 token **绕过 2FA**；"
          "`KNOT_MASTER_KEY` → 解密全部已存凭据）。"
          "\n处置：只列 env **名**（缺哪个报哪个 —— 对运维更有用且不含任何值）。"
          f"\n若确属非机密/运维自取的输出，把 (文件, 变量名) 加进本文件 `_ALLOWED` 并写明理由"
          f"（现有 {len(_ALLOWED)} 条）。"
    )


def test_SEC_allowlist_entries_are_all_still_live():
    """例外清单每一条都必须**仍然命中** —— 否则它是死条目，会静默扩大未来的豁免面。

    （哨兵最常见的死法不是判错，而是目标集/例外集与代码脱节而无人察觉。）

    ⚠️ **v0.9.5：本条必须同时按两个探测器判活** —— 扩了 `_brace_log_leaks` 之后，
    只按 `_fstring_leaks` 判活会把「只被花括号形态命中」的合法豁免误判成死条目
    （实测：加 `("knot/api/platform_admin.py","reason")` 时本测立刻红）。
    **教训**：加探测器就得同步扩「判活」的口径，否则守护之间会互相打脸。
    """
    dead = []
    for rel, name in sorted(_ALLOWED):
        py = _REPO / rel
        if not py.exists():
            dead.append(f"{rel}（文件已不存在）")
            continue
        live = any(name in names for _ln, names in _fstring_leaks(py)) or \
            any(name in names for _ln, names in _brace_log_leaks(py))
        if not live:
            dead.append(f"{rel}:{name}（两个探测器均已不命中，例外可删）")
    assert not dead, f"`_ALLOWED` 有死条目，请清理：{dead}"


def test_SEC_http_auth_error_reports_names_not_values(monkeypatch):
    """⭐ 端到端（服务层）：auth env 缺失时，**返给客户端的 `error` 字段**含 env 名、不含 env 值。

    覆盖的是真实链路终点（`run_http_step` 的返回值就是 `api/query.py` 原样 yield 的那个）。
    revert-to-bad：恢复带值的报错 → 本测转红。
    """
    import asyncio

    from knot.services.http_planner import run_http_step

    monkeypatch.setenv("PROBE_BASE_URL", "https://example.invalid")
    monkeypatch.setenv("PROBE_SECRET_VALUE", "TOP-SECRET-MUST-NOT-LEAK-42")
    spec = {
        "base_url_env": "PROBE_BASE_URL",
        "url_template": "/x",
        "auth_header_env": "PROBE_NO_SUCH_ENV",     # 故意不设 → 触发 auth 缺失分支
        "auth_value_env": "PROBE_SECRET_VALUE",     # 已设 → 旧写法会把它的值插进消息
    }
    res = asyncio.run(run_http_step("任意问题", "probe.tbl", spec))
    err = res.get("error") or ""
    assert res.get("success") is False and res.get("error_kind") == "http_auth", res
    assert "TOP-SECRET-MUST-NOT-LEAK-42" not in err, f"env 值泄漏到客户端可见字段：{err}"
    assert "PROBE_NO_SUCH_ENV" in err, f"env 名丢了，运维无法诊断该配哪个：{err}"


def test_rejection_reason_never_echoes_input():
    """⭐ 守 `_ALLOWED` 里 `("knot/api/platform_admin.py", "reason")` 那条豁免的**前提**。

    豁免的理由是「`reason` 按契约只描述形状、永不含值」。**契约必须自己有测** ——
    否则有人把 `rejection_reason` 改成 `f"值 {raw!r} 不合规"`，allowlist 会让它一路绿到生产
    （这正是 #262 的形状：env 明文进消息）。
    取材=revert：把 `rejection_reason` 的任一 problem 串改成含 `raw` → 本测红。
    """
    from knot.api.platform_admin import rejection_reason

    probes = [
        "SUPERSECRET-abcdefghijklmnopqrstuvwxyz-0123",   # 缺前缀
        "kpa_SUPERSECRET.with.dots.abcdefghijklmnop",     # 含 `.`
        "kpa_SHORT",                                      # 太短
        "kpa_" + "x" * 40,                                # 合规（应返 None）
    ]
    for raw in probes:
        got = rejection_reason(raw)
        if got is None:
            continue
        assert raw not in got, f"rejection_reason 回显了输入：{got!r}"
        for frag in ("SUPERSECRET", "SHORT"):
            assert frag not in got, f"rejection_reason 泄漏了输入片段 {frag!r}：{got!r}"
