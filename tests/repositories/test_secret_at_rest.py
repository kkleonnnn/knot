"""tests/repositories/test_secret_at_rest.py — v0.9.12 静态明文敏感值守护（Sb1–Sb6）。

三年里「这些列必须静态加密」只是一条**散文规则** —— 写入路径会加密、有个一次性迁移脚本，
而**没有任何东西在问「现有数据里还有没有明文」**。后果：2 个敏感值明文躺了三个月。
本文件是那条规则的守护。
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from knot.core.crypto.fernet import ENC_PREFIX
from knot.repositories import secret_at_rest

# ─── Sb1 扫描面 == 字面期望集合（扫描面派生 + 期望值字面，PR#263 范式）──────

def test_Sb1_landing_spots_match_expected_literal_set():
    """扫描面**派生**自三个真相源，而期望值是**字面的** ⇒ 新增敏感列不改本测即红。

    这是刻意的：production 侧派生（新列自动进扫描面），test 侧字面（新列必须被**看见一次**）。
    """
    expected = {
        ("users", "api_key"), ("users", "doris_password"), ("users", "embedding_api_key"),
        ("users", "openrouter_api_key"), ("users", "totp_secret"),
        ("data_sources", "db_password"), ("data_sources", "http_config"),
        ("app_settings", "embedding_api_key"), ("app_settings", "lark_app_secret"),
        ("app_settings", "openrouter_api_key"), ("app_settings", "telegram_bot_token"),
    }
    actual = {
        (s.table, s.key_filter if s.key_filter is not None else s.col)
        for s in secret_at_rest.landing_spots()
    }
    assert actual == expected, (
        f"敏感落点集变了。新增：{sorted(actual - expected)}；消失：{sorted(expected - actual)}\n"
        "    ⇒ 若是**真的新增了敏感列**，把它加进本测的 expected（这一步是刻意的：让新列被看见一次）；\n"
        "    ⇒ 若是**列被删/改名**，检查三个真相源是否还指着已不存在的列（Sb5 也会红）。"
    )


# ─── Sb2 注入明文被扫出（含「注入真能产生它」的前置断言）──────────────────

def _mk_db(tmp_path: Path) -> sqlite3.Connection:
    c = sqlite3.connect(str(tmp_path / "t.db"))
    c.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, doris_password TEXT, totp_secret TEXT)")
    c.execute("CREATE TABLE app_settings (key TEXT PRIMARY KEY, value TEXT)")
    return c


def test_Sb2_injected_plaintext_is_found(tmp_path):
    """注入明文 ⇒ 必须被扫出。⚠️ 先断言**注入真的产生了要测的条件**（v3.1-B #2）。"""
    c = _mk_db(tmp_path)
    c.execute("INSERT INTO users (doris_password) VALUES ('P@ssw0rd-明文')")
    c.execute("INSERT INTO app_settings (key, value) VALUES ('openrouter_api_key', 'sk-plain')")
    c.commit()

    raw = c.execute("SELECT doris_password FROM users").fetchone()[0]
    assert not raw.startswith(ENC_PREFIX), "注入前提不成立：写进去的值竟带加密前缀 ⇒ 本测在空跑"

    found = secret_at_rest.scan_plaintext_secrets(c)
    got = {(f.table, f.col) for f in found}
    assert ("users", "doris_password") in got, f"漏扫 users.doris_password；实际扫到 {sorted(got)}"
    assert ("app_settings", "value") in got, f"漏扫 app_settings 敏感键；实际扫到 {sorted(got)}"
    c.close()


def test_Sb2b_encrypted_and_empty_values_are_not_flagged(tmp_path):
    """**反向守护**：已加密 / NULL / 空串**不得**被报为明文 —— 否则「全部拒绝」会假装成守护有效。"""
    c = _mk_db(tmp_path)
    c.execute("INSERT INTO users (id, doris_password, totp_secret) VALUES (1, ?, NULL)",
              (ENC_PREFIX + "gAAAAABfake",))
    c.execute("INSERT INTO users (id, doris_password) VALUES (2, '')")
    c.execute("INSERT INTO app_settings (key, value) VALUES ('openrouter_api_key', ?)",
              (ENC_PREFIX + "gAAAAABfake2",))
    c.commit()
    assert secret_at_rest.scan_plaintext_secrets(c) == [], "已加密/NULL/空串不该被报为明文"
    c.close()


# ─── Sb3 Finding / WARN 永不含值（#262 族）────────────────────────────────

def test_Sb3_findings_and_summary_never_contain_the_value(tmp_path):
    """⛔ 只有表/列/主键，**没有值**。注入一个特征串，断言它不出现在任何输出里。"""
    marker = "ZZ-marker-secret-9F3K-ZZ"
    c = _mk_db(tmp_path)
    c.execute("INSERT INTO users (doris_password) VALUES (?)", (marker,))
    c.commit()
    found = secret_at_rest.scan_plaintext_secrets(c)
    assert found, "前提：应扫出 1 处"
    for f in found:
        assert marker not in repr(f), f"Finding 含值：{f!r}"
    summary = secret_at_rest.format_findings(found)
    assert marker not in summary, f"摘要含值：{summary}"
    c.close()


def test_Sb3b_summary_sample_is_bounded(tmp_path):
    """摘要**有界** —— 无界枚举在大库上会刷满日志（守护者 R7）。"""
    findings = [secret_at_rest.Finding("users", "doris_password", i) for i in range(50)]
    s = secret_at_rest.format_findings(findings, sample=5)
    assert s.count("pk=") == 5, f"样本应恰 5 条；实际 {s.count('pk=')} 条 —— 摘要未有界"
    assert "50 处" in s and "等 50 处" in s, f"应给出总数与省略提示；实际：{s}"


# ─── Sb4 豁免表的理由必须**具名指向一个片/决策**（不接受只有一段话）──────

def test_Sb4_every_exemption_names_a_patch_or_decision():
    """b7 的「写明理由」本身没有守护 ⇒ 会退化成新的散文规则（本弧在治的形状）。

    ⇒ 判据机械化：理由必须含 `vX.Y(.Z)` / `ADR-nnnn` / `docs/plans/` 之一。
    """
    bad = {k: v for k, v in secret_at_rest.NOT_ENCRYPTED_BY_DESIGN.items()
           if not secret_at_rest.exemption_reason_ok(v)}
    assert not bad, (
        f"以下豁免项的理由没有具名指向任何片/决策：{sorted(bad)}\n"
        "    ⇒ 「豁免」必须可追溯到一个具体决策，否则它就是一条新的无守护散文规则。"
    )


# ─── Sb5 结构哨兵：schema 里「敏感形状」的 TEXT 列必须已登记 ───────────────

_SENSITIVE_NAME = re.compile(r"password|secret|token|key|credential", re.I)


def _live_columns(db_path: str) -> list[tuple[str, str, str]]:
    """**introspect 真实建出来的库**（`PRAGMA table_info`），返回 (表, 列, 类型)。

    ⚠️ **不解析 `schema.sql` 文本**（本片自捉的第一个错）：`users.api_key` /
    `openrouter_api_key` / `embedding_api_key` 是 `migrations.py` 用 `ALTER TABLE` 加的，
    **`schema.sql` 里 0 命中** ⇒ 文本解析会把它们误报成「真相源指着不存在的列」（实测 3 处假红）。
    ⇒ 判据必须问**代码真的建出了什么**，而不是问某个文件里写了什么（R-SENTINEL-AST 同精神）。
    附带收益：拿到**真实类型**，TEXT 收窄不再靠正则猜。
    """
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        out = []
        for (tbl,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table'"):
            for row in conn.execute(f"PRAGMA table_info({tbl})"):
                out.append((tbl, row[1], (row[2] or "").upper()))
        return out
    finally:
        conn.close()


def test_Sb5_sensitive_looking_text_columns_are_registered(tmp_db_path):
    """新增「名字像凭据」的 TEXT 列 ⇒ 要么进落点集、要么进豁免表，否则红。

    ⚠️⚠️ **本哨兵是 tripwire，不是证明 —— 盲区已实测，连证据一起写在这里**：
    判据按**列名关键词**，因此它**看不见名字里没有关键词的敏感列**。
    **反例是真实存在的**：`data_sources.http_config` **是**一个真的 Fernet 加密列
    （在 `_DS_ENCRYPTED_COLS` 里），而它的名字里**没有任何关键词** ⇒ 本哨兵扫不到它。
    ⇒ 「忘登记」这个失效模式**只被部分覆盖**。别把本测的绿当成「敏感列都登记了」。

    ⚠️ **排除 INTEGER 是实测决定的**：实库 311 列里名字命中 **19 处，其中 10 处是 INTEGER**
    （`messages.*_tokens` 是 LLM token **计数**、`must_change_password` 是开关、
    `token_version` 是版本号）—— 全是必然误报。**秘密不会是 INTEGER。**
    排除后剩 9 处 = 落点集 6 + 豁免 3 + 未登记 0，信噪比可用。
    """
    landing = {(s.table, s.col) for s in secret_at_rest.landing_spots()}
    landing |= {(s.table, s.key_filter) for s in secret_at_rest.landing_spots()
                if s.key_filter is not None}
    exempt = set(secret_at_rest.NOT_ENCRYPTED_BY_DESIGN)

    unregistered = [
        (t, c) for t, c, ty in _live_columns(tmp_db_path)
        if _SENSITIVE_NAME.search(c) and not ty.startswith("INT")
        and (t, c) not in landing and (t, c) not in exempt
    ]
    assert not unregistered, (
        f"以下 TEXT 列名字像凭据，但既不在敏感落点集、也不在豁免表里：{sorted(unregistered)}\n"
        "    ⇒ 若确实是凭据：加进对应 repo 的 `_*_ENCRYPTED_COLS` / `_SENSITIVE_KEYS`（自动进扫描面）；\n"
        "    ⇒ 若不是：加进 `secret_at_rest.NOT_ENCRYPTED_BY_DESIGN`，**理由须具名指向一个片/决策**（Sb4 守）。"
    )


def test_Sb5b_registered_columns_still_exist_in_schema(tmp_db_path):
    """反方向（**零误报、可机械穷举**）：三个真相源指的列必须**真的存在**。

    捕的是「列被删/改名而常量还指着旧名」—— 那会让扫描静默漏掉一整列
    （`scan_plaintext_secrets` 对不存在的列**跳过而不抛**，因为它绝不能改变启动可用性
    ⇒ 这个方向的漂移只能靠本测抓）。
    """
    live = {(t, c) for t, c, _ty in _live_columns(tmp_db_path)}
    missing = [
        (s.table, s.col) for s in secret_at_rest.landing_spots()
        if s.key_filter is None and (s.table, s.col) not in live
    ]
    assert not missing, (
        f"真相源指着实库里不存在的列：{sorted(missing)}\n"
        "    ⇒ 扫描会静默跳过它们（探测器不抛错是刻意的）⇒ 只有本测能抓到这种漂移。"
    )


# ─── Sb6 廉价判据**不需要 master key**（探测器不得改变启动可用性）──────────

def test_Sb6_cheap_oracle_needs_no_master_key(tmp_path, monkeypatch):
    """启动期扫描必须在**没有 master key** 时也能跑 —— 否则一个非阻断探测器会崩掉 boot。

    ⭐ 这条性质来自 **oracle 的选择**（只比 `ENC_PREFIX` 前缀，不解密），不是来自放置位置；
    因此它必须被断言，否则将来有人把判据换成「解得开」时**没有任何东西会红**。
    """
    monkeypatch.delenv("KNOT_MASTER_KEY", raising=False)
    from knot.core.crypto.fernet import get_crypto_adapter
    get_crypto_adapter.cache_clear()

    c = _mk_db(tmp_path)
    c.execute("INSERT INTO users (doris_password) VALUES ('明文')")
    c.commit()
    found = secret_at_rest.scan_plaintext_secrets(c)   # 不得抛 CryptoConfigError
    assert len(found) == 1, f"无 key 时应正常扫出 1 处；实际 {found}"
    assert secret_at_rest.looks_plaintext("abc") is True
    assert secret_at_rest.looks_plaintext(ENC_PREFIX + "x") is False
    c.close()


# ─── Sb7 启动期**真的**会调用它并打出 WARN（消费者存在性 + 内容正确）──────────

def _loguru_sink():
    """挂 loguru sink 抓日志。

    ⚠️ **必须挂 loguru sink，不能用 `caplog`** —— 本仓 logger 是 loguru（`core/logging_setup`），
    `caplog` 只抓 stdlib logging ⇒ 用 caplog 写这类测是**同义反复**
    （本仓 v0.9.3 F-3' 已实证；本片初版又踩了一次，靠「先断必须有命中」才没空绿 ——
    那正是「跑 revert 前四问」的第 ③ 条：**oracle 会不会恒定**）。
    """
    from loguru import logger as _lg
    sink: list = []
    hid = _lg.add(lambda m: sink.append(str(m)), level="DEBUG", format="{message}")
    return sink, hid


def test_Sb7_startup_warn_fires_and_never_leaks_the_value(tmp_db_path):
    """`main.py` 的启动扫描不只是「定义了」—— 本测**真的调它**并断言日志内容。

    ⭐ 为什么不能只断「函数存在 / 名字出现在 main.py 里」（v0.9.9 那次教训）：
    删掉调用点后 import 与函数定义都还在 ⇒ 那种断言**不会红**。
    ⇒ 这里 ① 结构上断言 module 级**有调用点** ② 真跑一次并断 WARN 的**内容**。
    """
    import ast
    from pathlib import Path as _P

    from loguru import logger as _lg

    # ① 结构：module 级必须有 `_warn_plaintext_secrets_at_rest()` 调用（不是只有定义）
    tree = ast.parse(_P("knot/main.py").read_text(encoding="utf-8"))
    called = [
        n for n in tree.body
        if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call)
        and isinstance(n.value.func, ast.Attribute)
        and n.value.func.attr == "warn_all_tenants_at_startup"
    ]
    assert len(called) == 1, (
        f"main.py module 级应恰有 1 处 `warn_all_tenants_at_startup()` 调用；实际 {len(called)}\n"
        "    ⇒ 只有定义没有调用 = 一个永不运行的探测器（v0.9.9 同族教训）。"
    )

    # ② 行为：注入明文 → 真跑 → WARN 出现且**不含值**
    marker = "QQ-startup-marker-7T2X-QQ"
    conn = sqlite3.connect(tmp_db_path)
    conn.execute("UPDATE users SET doris_password=? WHERE id=1", (marker,))
    conn.commit()
    changed = conn.total_changes
    conn.close()
    assert changed >= 1, "注入前提不成立：没有 id=1 的用户可改 ⇒ 本测会空跑"

    import knot.main  # noqa: F401 — 确认 main 可 import（启动期调用点在此）
    sink, hid = _loguru_sink()
    try:
        secret_at_rest.warn_all_tenants_at_startup()
    finally:
        _lg.remove(hid)

    blob = "".join(sink)
    assert "secret-at-rest" in blob, (
        "启动扫描没有打出 WARN —— 明文存在却无人知晓。\n"
        f"    sink 抓到：{blob[:300]!r}"
    )
    assert "doris_password" in blob, f"WARN 应点名列；实际：{blob[:300]}"
    assert marker not in blob, f"⛔ WARN 泄露了值：{blob[:300]}"
    assert "migrate_encrypt_v045" in blob, f"WARN 应给出可操作的修法；实际：{blob[:300]}"
