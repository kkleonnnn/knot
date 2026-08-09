"""**stdlib `logging` 必须被转发进 loguru**（v0.9.19 C0'' —— 修一个既有的观测缺陷）。

## 缺陷
`logging_setup.py` 配了 loguru 的 sink，但**从不配置 stdlib root**
（全仓 `InterceptHandler` / `basicConfig` / `dictConfig` **命中 0 次**）。
而全仓有 **6 个模块 / ~19 处**用 stdlib `logging`：
`adapters/http/executor` · `adapters/http/url_allowlist` · `agents/catalog_loaders` ·
`agents/catalog` · `services/query_helper` · `core/crypto/fernet`。

⇒ 那些记录落到 `logging.lastResort`。实测（`KNOT_LOG_FORMAT=json`，即容器非 tty 的默认）：

    loguru → {"time":…, "level":"WARNING", "msg":"…", …}   ← 结构化，Kibana 可索引
    stdlib → 裸消息                                          ← **无 JSON、无 level 字段**

## 为什么它不是「格式不统一」这种整齐问题
那 6 个模块里包含**运维唯一观测口**的那几条启动 WARN
（v0.9.7 的 allowlist 未配置 WARN · v0.9.16 的私有 catalog 未挂载 WARN）。

⚠️ **实证**：`DEPLOY.md` 记录升级排练用 `docker logs knot 2>&1 | grep -i warn`
认定「v0.9.7 那条 WARN **真的响了**」—— 而那条消息**原文里没有 "warn" 字样**，
`lastResort` 又不加 level 前缀 ⇒ **那次验证复现不出来**。
⇒ **两条被当成「同形」的 WARN（stdlib 的与 loguru 的）其实不同形**，
而 v0.9.18 写下「启动日志有没有这一行就是答案」时**默认了它们一样**。

## 判据锚在「日志真的长什么样」，不是「有没有装 handler」
⚠️ 断言 `logging.root.handlers` 里有个 `InterceptHandler` 是**弱判据** ——
它锚在「配置写成什么样」。真正要问的是：**这条日志出来是不是一条结构化 WARNING**。
（本仓自诊断：判据要问「跑出来是什么」。）
"""
from __future__ import annotations

import json
import subprocess
import sys
import textwrap

import pytest


def _run_and_capture(script: str, fmt: str = "json") -> list[str]:
    """在**子进程**里跑（干净的 logging 状态）并收 stderr 各行。

    ⚠️ **为什么必须子进程**：`logging_setup` 只在**首次 import** 时配置
    （`_knot_configured` 守卫），而测试进程早已 import 过它 ⇒ 同进程内改不动、
    也测不到「一个真实进程启动后是什么样」。⇒ 子进程是唯一能表示该事件的形状。
    """
    proc = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(script)],
        capture_output=True, text=True, timeout=60,
        # ⚠️ **刻意 `check=False`**：本测的 oracle 是 **stderr 的内容**，不是退出码。
        #    子进程若崩了，stderr 里的 traceback 会被下面的断言原样打出来（可读）；
        #    而 `check=True` 会先抛 `CalledProcessError`，把真正有用的那段**吞成一个类型名**。
        check=False,
        env={"PATH": "/usr/bin:/bin", "KNOT_LOG_FORMAT": fmt, "HOME": "/tmp",
             "PYTHONPATH": ".", "LOG_LEVEL": "INFO"},
    )
    return [ln for ln in proc.stderr.splitlines() if ln.strip()]


_SCRIPT = """
    import knot.core.logging_setup  # noqa: F401  —— 触发配置
    import logging
    logging.getLogger("knot.adapters.http.url_allowlist").warning("CANARY-STDLIB-WARN")
"""


def test_stdlib_warning_becomes_a_structured_json_record():
    """⭐ 核心：经 **stdlib logging** 打的 WARNING，在生产 JSON 模式下必须是**结构化的一条**。

    revert-to-bad：去掉 `logging_setup` 里的 `basicConfig(handlers=[_InterceptHandler()]…)`
    ⇒ 本测红 —— 拿到的是裸字符串 `CANARY-STDLIB-WARN`，`json.loads` 失败。
    """
    lines = _run_and_capture(_SCRIPT)
    canary = [ln for ln in lines if "CANARY-STDLIB-WARN" in ln]
    assert canary, f"stdlib WARNING 根本没出现在 stderr：{lines!r}"

    try:
        rec = json.loads(canary[-1])
    except json.JSONDecodeError:
        pytest.fail(
            f"stdlib WARNING 不是一条 JSON 记录，而是裸消息：{canary[-1]!r}\n"
            "⇒ stdlib logging 没被转发进 loguru ⇒ 它在 Kibana 里不是一条 WARNING\n"
            "⇒ 那几条「运维唯一观测口」的启动 WARN 实际上看不见。"
        )
    assert rec.get("level") == "WARNING", (
        f"记录里没有 level=WARNING（实际 {rec.get('level')!r}）——\n"
        "⇒ 按 level 过滤日志时它不会出现。"
    )
    assert rec.get("msg") == "CANARY-STDLIB-WARN", f"消息被改写了：{rec!r}"


def test_intercepted_record_points_at_the_real_caller_not_stdlib_internals():
    """⭐ **provenance 也要对** —— 否则「有 level 了但指不出是谁打的」= 修了一半。

    ⚠️ **实施期实证**：初版 depth 算法写错，得到的是
    `logger="logging", func="callHandlers", line=1762`（stdlib 内部帧）。
    改用 loguru 官方范式（从本帧起走到跳出 `logging.__file__`）后才指向真实调用点。
    revert-to-bad：把 depth 起点改回 `currentframe(), 2` ⇒ 本测红并打印那三个字段。
    """
    lines = _run_and_capture(_SCRIPT)
    rec = json.loads([ln for ln in lines if "CANARY-STDLIB-WARN" in ln][-1])
    assert rec.get("func") != "callHandlers" and "logging" != rec.get("logger"), (
        f"记录指向 stdlib 内部帧而非真实调用点：logger={rec.get('logger')!r} "
        f"func={rec.get('func')!r} line={rec.get('line')!r}\n"
        "⇒ 排障时看不出这条日志是**哪个模块**打的。"
    )


def test_every_module_using_stdlib_logging_is_covered_by_the_intercept():
    """⭐ 派生：**任何**用 stdlib logging 的模块都受这道转发保护，不是只有我测的那个。

    ⚠️ 这条不是「再断言一遍上面那条」——它守的是**扫描面**：
    今天是 6 个模块，将来有人给第 7 个模块加 `import logging` 时，
    本测让「它是否也被覆盖」这个问题**自动被回答**（因为转发是全局 root 级的）。
    ⇒ 判据 = 那 6 个模块**确实存在**（非空集，五问③）+ 转发是 **root 级**（覆盖全部 logger）。
    """
    import ast
    import pathlib

    users = []
    for f in sorted(pathlib.Path("knot").rglob("*.py")):
        tree = ast.parse(f.read_text(encoding="utf-8"))
        if any((isinstance(n, ast.Import) and any(a.name == "logging" for a in n.names))
               or (isinstance(n, ast.ImportFrom) and n.module == "logging")
               for n in ast.walk(tree)):
            users.append(str(f))
    assert users, "全仓没有模块用 stdlib logging —— 本测在空集上恒真（五问③）"

    # ⭐ 用**其中一个真实模块的 logger 名**打日志，证明覆盖不限于我挑的那个
    for name in ("knot.adapters.http.executor", "knot.services.query_helper"):
        lines = _run_and_capture(f"""
            import knot.core.logging_setup  # noqa: F401
            import logging
            logging.getLogger({name!r}).warning("CANARY-{name}")
        """)
        hit = [ln for ln in lines if f"CANARY-{name}" in ln]
        assert hit, f"{name} 的 WARNING 没出现：{lines!r}"
        json.loads(hit[-1])          # 能解析即证明它也走了转发（解析失败会抛，测即红）
