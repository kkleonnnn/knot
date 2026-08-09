"""`show_tenant_allowlists` 是**只读**的，且三态判读**不留给人**（v0.9.19 C0'''）。

## 它为什么存在
`sqlite3` CLI **此前不在镜像里**（实测 `docker run --rm python:3.11-slim which sqlite3` → 无）
⇒ DEPLOY 里所有 `sqlite3 …` 运维指令**自 v0.9.7 写下之日起就跑不了**。
v0.9.19 已在 Dockerfile 装上它 —— 但那只让**既有文档不再撒谎**，
本脚本解决的是另一半：**判读**。

⚠️ 三态里 `NULL`（未配置）与 `''`（部署方明确的「禁」）**语义相反**，
而裸 `SELECT` 把两者都显示成空白 ⇒ 靠 `quote()` 分辨要人**记得加**、还要**逐字判读**。
⇒ 本脚本直接打印语义，**把判读这一步消掉**。
"""
from __future__ import annotations

import ast
import pathlib

_SCRIPT = pathlib.Path(__file__).resolve().parents[2] / "knot/scripts/show_tenant_allowlists.py"


def test_script_is_read_only():
    """⭐ **只读**：全文不得出现任何写 SQL。

    ⚠️ **为什么它可以没有 `--tenant` 必填**（对照 v0.9.15 那条「破坏性 CLI 不得有默认目标」）：
    那条规矩的理由是「缺目标时静默作用于起源租户 = 不可见的破坏」。
    **只读工具没有可破坏的东西** ⇒ 它可以（也应该）默认列出全部租户 ——
    运维恰恰需要「一眼看全」。⇒ **本测就是那条规矩的另一面：只读是这个豁免的前提，故必须被守。**

    revert-to-bad：往脚本里加一句 `UPDATE tenants …` ⇒ 本测红。
    """
    src = _SCRIPT.read_text(encoding="utf-8")
    tree = ast.parse(src)
    bad = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Constant) and isinstance(n.value, str):
            up = n.value.upper()
            for verb in ("UPDATE ", "INSERT ", "DELETE ", "ALTER ", "DROP ", "CREATE "):
                # ⚠️ 只看**SQL 字面量**，不看散文 —— docstring 里讨论「不得 UPDATE」不该判红
                #    （R-SENTINEL-AST 的教训：讨论一个名字的文件必然含有那个名字）
                if up.lstrip().startswith(verb):
                    bad.append(n.value[:60])
    assert not bad, f"只读脚本里出现了写 SQL：{bad}\n⇒ 它的「无需显式目标」豁免建立在只读之上。"


def test_three_state_semantics_are_spelled_out_not_left_to_the_reader():
    """⭐ 三态各自被翻成**语义**，且 `NULL` 与 `''` 的输出**必须不同**。

    ⚠️ 这条不是「测文案」——它测的是**本脚本存在的理由**：
    若两者输出相同，运维就回到了「看空白猜是哪一种」，而那正是 `quote()` 方案的毛病。
    revert-to-bad：把 `_describe` 的 `''` 分支删掉（让它掉进 `NULL` 分支或通用分支）⇒ 本测红。
    """
    import importlib
    mod = importlib.import_module("knot.scripts.show_tenant_allowlists")

    null_out = mod._describe(None)
    empty_out = mod._describe("")
    blank_out = mod._describe("   ")
    set_out = mod._describe("a.example, b.example")

    assert null_out != empty_out, (
        f"`NULL` 与 `''` 的输出相同（{null_out!r}）—— 而它们**语义相反**：\n"
        "  NULL = 未配置（起源租户回退 env）· '' = 部署方明确的「禁」（不回退）\n"
        "⇒ 运维又回到了「看空白猜是哪一种」。"
    )
    assert empty_out == blank_out, f"`''` 与纯空白应同义（分别得到 {empty_out!r} / {blank_out!r}）"
    assert "2" in set_out and "a.example" in set_out, f"非空态没给出条目数与内容：{set_out!r}"


def test_managed_columns_are_derived_from_the_write_gate():
    """⭐ 复核的列**从写口派生** ⇒ 第三份 allowlist 落地时本脚本**自动**开始复核它。

    revert-to-bad：把 `_managed_columns` 改成硬编 `("allowed_http_hosts",)` ⇒
    本测红（它与 `tenant_repo._MUTABLE_TENANT_FIELDS` 的派生结果不再一致）。
    """
    import importlib

    from knot.repositories import tenant_repo
    mod = importlib.import_module("knot.scripts.show_tenant_allowlists")

    expected = tuple(f for f in tenant_repo._MUTABLE_TENANT_FIELDS if f.startswith("allowed_"))
    assert expected, "写口里没有 allowlist 列 —— 本测在空集上恒真（五问③）"
    assert mod._managed_columns() == expected, (
        f"脚本复核的列与写口不一致：脚本={mod._managed_columns()} 写口={expected}\n"
        "⇒ 新增一份 allowlist 时，运维复核会**看不到它**。"
    )
