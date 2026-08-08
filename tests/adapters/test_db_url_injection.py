"""连接 URL 必须**按组件构造** —— `db_database` 不得改写连接目标（v0.9.19 安全修复）。

## 缺陷
`build_connection_url` 原用 **f-string** 拼接：
```
f"mysql+pymysql://{user}:{pwd}@{host}:{port}/{database}?charset=utf8mb4"
```
而 `db_database` 与 `db_host` 是**同一个表单里的自由文本**（`DataSourceRequest`），
租户 admin 两者都能填。填入 `db1?host=evil.example.com&charset=utf8mb4#` ⇒
那段 `?host=` 成为 URL 的**查询参数**，而 pymysql 方言把查询参数当**连接实参**：

| | 值 |
|---|---|
| `url.host` —— **任何门会校验的** | `allowed.corp` |
| `create_connect_args(url)` 的 `host` —— **真正连过去的** | `evil.example.com` |

⇒ **校验 `host` 形参的门，校验的是一个不决定去哪的值。**

## 为什么这条测在「还没有 allowlist」的今天就要立
今天 `db_host` 本来就自由填 ⇒ 从 `db_database` 绕**没有额外收益** ⇒ **今天不是可利用的洞**。
⛔ **但它会让将来那道 host allowlist 从第一天起可绕过** ——
而那道门正是 P-a' 要建的东西。⇒ **先把地基修正，再在上面装门。**

## 判据锚在「真正的连接实参」，不是「URL 字符串长什么样」
⚠️ 断言 URL 字符串里没有 `?host=` 是**错的判据** —— 它锚在「写着什么」。
正确锚点 = `dialect.create_connect_args(url)` 的输出，**那是 driver 真正拿到的东西**。
（本仓自诊断：判据要问「跑出来是什么」，不是「写着是什么」。）
"""
from __future__ import annotations

import sqlalchemy

from knot.adapters.db.doris import build_connection_url


def _connect_args(url) -> dict:
    """driver **真正拿到**的连接实参 —— 本文件唯一合法的 oracle。"""
    if isinstance(url, str):                       # 兼容「万一有人把它改回返字符串」
        url = sqlalchemy.engine.url.make_url(url)
    return url.get_dialect()().create_connect_args(url)[1]


def test_database_field_cannot_override_the_connect_host():
    """⭐ 核心：`db_database` 里塞 `?host=` **改不动**真正的连接目标。

    revert-to-bad：把 `build_connection_url` 改回 f-string 拼接 ⇒ 本测红，
    且消息直接给出「门看到的 host」与「真正连过去的 host」两个值。
    """
    payload = "db1?host=evil.example.com&charset=utf8mb4#"
    url = build_connection_url("allowed.corp", 9030, "u", "p", payload)

    gate_sees = url.host if not isinstance(url, str) else sqlalchemy.engine.url.make_url(url).host
    really_connects_to = _connect_args(url).get("host")

    assert gate_sees == really_connects_to == "allowed.corp", (
        f"`db_database` 改写了连接目标：\n"
        f"  门会校验的 host      = {gate_sees!r}\n"
        f"  真正连过去的 host    = {really_connects_to!r}\n"
        "⇒ 任何校验 host 形参的 allowlist 都是装饰品（判据锚在了不决定去哪的值上）。"
    )


def test_database_payload_stays_literal_and_does_not_become_query_args():
    """`database` 里的怪字符只是**数据库名的字符**，不得变成连接参数。

    ⚠️ 与上一条分开：上一条守「host 没被改」，本条守「**它也没变成别的参数**」——
    `?ssl_disabled=false` / `?read_timeout=99999` 同样是可注入的连接实参，
    只断 host 的话那些**表示不出来**（同一个洞的不同出口）。
    """
    payload = "db1?ssl_disabled=false&read_timeout=99999#x"
    args = _connect_args(build_connection_url("allowed.corp", 9030, "u", "p", payload))
    assert args.get("database") == payload, f"database 被拆解了：{args.get('database')!r}"
    assert "ssl_disabled" not in args or args["ssl_disabled"] is not False, (
        f"`database` 里的 `?ssl_disabled=false` 变成了真的连接参数：{args!r}"
    )
    assert args.get("read_timeout") != 99999, f"`database` 里的 `?read_timeout` 生效了：{args!r}"


def test_normal_inputs_produce_unchanged_connect_args():
    """⭐ **正对照**：正常输入的连接实参与旧实现**逐字一致** ⇒ 本修复零行为变化。

    ⚠️ 没有这一条的话，「把 URL 构造整个换掉」可能悄悄改了口令转义 / 端口 / charset，
    而那类回归**不会有任何测红**（它们都还是「能连上」）。
    ⚠️ 特意含**特殊字符口令** —— 旧实现靠 `quote_plus` 手工转义，新实现交给 `URL.create()`，
    这正是最容易出偏差的地方。
    """
    from urllib.parse import quote_plus

    def _old_style(host, port, user, password, database) -> str:
        return f"mysql+pymysql://{user}:{quote_plus(password)}@{host}:{port}/{database}?charset=utf8mb4"

    cases = [
        ("db.corp", 9030, "u", "p", "mydb"),
        ("db.corp", 9030, "u", "p@ss:w/rd#1", "mydb"),        # 特殊字符口令
        ("10.0.0.5", 3306, "root", "", "test"),               # 空口令
        ("db.corp", 9030, "user_x", "pw", "db_with_underscore"),
    ]
    for c in cases:
        old = _connect_args(_old_style(*c))
        new = _connect_args(build_connection_url(*c))
        assert old == new, f"正常输入 {c!r} 的连接实参变了：\n  旧={old!r}\n  新={new!r}"


def test_builder_does_not_use_string_interpolation():
    """⭐ 结构性守护：该函数**不得**再出现 f-string / `%` / `+` 拼 URL。

    ⚠️ **为什么行为测不够**：行为测只能挡住**我想到的那些 payload**。
    而 URL 解析的歧义面很大（`@` in password · IPv6 host · unicode · 百分号编码…）——
    「按组件构造」是一个**结构性质**，它挡的是**整类**，所以要有一条结构性判据钉住它。

    ⇒ 判据 = AST：函数体内不得有 `JoinedStr`（f-string），且必须调用 `URL.create`。
    revert-to-bad：改回 f-string ⇒ 本测红（且与上面那条行为测**各自独立地**红）。
    """
    import ast
    import inspect

    src = inspect.getsource(build_connection_url)
    tree = ast.parse(src.lstrip())
    fn = tree.body[0]

    fstrings = [n for n in ast.walk(fn) if isinstance(n, ast.JoinedStr)]
    # docstring 里的示例不算（它是 Constant，不是 JoinedStr）⇒ 命中即真的在拼
    assert not fstrings, (
        "`build_connection_url` 里出现了 f-string —— URL 必须按**组件**构造。\n"
        "⇒ f-string 会让 `database` / `user` 等字段里的 `?` `#` `@` 改变 URL 的解析结果，"
        "而那正是 v0.9.19 修掉的洞。"
    )
    calls = {
        f"{getattr(n.func.value, 'attr', '')}.{n.func.attr}"
        for n in ast.walk(fn)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
    }
    assert any("create" in c for c in calls), (
        f"没找到 `URL.create(...)` 调用（实际调用：{sorted(calls)}）—— 组件构造是本修复的载体。"
    )
