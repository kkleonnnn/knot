"""闸门：`GET /api/admin/catalog` 的响应契约（v0.9.5 D4' —— 删死 `defaults` + file fallback 反向测）。

## 本文件为什么存在（顺序承重）
v0.9.5 删掉响应里的 `defaults` 字段（它把**部署级** `_local_catalog` 全文吐给任何**租户** admin，
而前端零处渲染 = 死载荷）。守护者 Stage 1' 复核末段点名的**实施顺序铁律**：
> 反向测（file fallback 仍在）**必须先写、再删字段** —— 顺序反了会有一段窗口
> **分不清「删对了」和「踩了 v0.7.29b」**。

## 两条测的分工，别合并
- `test_defaults_key_is_gone`：**只**断言顶层 `defaults` 键消失。
  ⚠️ **刻意不**断言「响应零 `_local_catalog` 内容」—— 那**不成立且不允许成立**（见下）。
- `test_current_still_carries_file_layer_http_tables`：反向守护 —— `current` 里的 **file 层 HTTP 虚拟表仍在**。

## ⭐ 为什么「让 `current` 不含 file 内容」是**被禁止**的（不是「没排上」）
`catalog.reload()` 里 file HTTP 表**始终【权威覆盖】同名 DB 条目**（v0.7.29b merge 权威）。
把 file 层从槽里摘掉 ⇒ HTTP 虚拟表消失 ⇒ `pick_http_route` Layer 1（catalog `source:http` 表
+ lexicon 命中）恒不命中 ⇒ **HTTP 查询静默落 SQL = v0.7.29b bug 复发**。
⇒ 本片只做**部分减暴露**（删死字段），**不是** blocker 关闭；
per-tenant file catalog 仍在 R-T-GATE 清单（B-3 三项之一）。

## 与既有测的分工（不重复造）
槽 / loader 层已有覆盖（v0.9.3 写的）：`tests/services/test_catalog_loaders.py:208`（merge 权威）+
`tests/test_catalog_tenant_isolation.py:228`（§6-4 防造槽方式导致 HTTP 表消失）。
**本文件补的是端点层** —— 残余风险正在这里：若后人「顺手修干净」**只改端点**把 file 内容从
`current` 里滤掉，槽层那两条测**照绿**。
"""
from __future__ import annotations

_URL = "/api/admin/catalog"


def test_current_still_carries_file_layer_http_tables(client, auth_headers):
    """⭐ 8b（**先写、后删字段**）：`current.tables` 必须仍含 **file 层的 HTTP 虚拟表**。

    HTTP 虚拟表**只能**来自 file 层（`reload()` 从 `f_tables` merge 进来）⇒ 它们在 `current` 里
    出现，就证明 file fallback 活着。
    ⚠️ **断言用「子集/存在」而非计数** —— file 层内容因环境而异（主仓有部署方 `_local_catalog.py`
    实测 2 条 http；CI / 全新 worktree 只有 `_template_catalog.py` 实测 5 条）。
    这是 v0.9.3 §III-1 的教训：**环境相关的量不能写成数字断言**。
    取材=revert：把 `reload()` 的 file fallback 摘掉
    （`base_tables = list(db_tables) if db_tables else list(f_tables)` → `else []`）→ **本测红**（实测）
    = 有人「顺手修干净」时立刻响，而不是等到 HTTP 查询静默落 SQL 才发现。

    ⚠️ **本测覆盖的边界（诚实声明）**：它走的是 **file fallback 路径**（`db_tables` 空 → 直接取 `f_tables`）。
    reload 里那条 `base_tables.extend(http_from_file)` 只在 **`db_tables` 非空**时执行，
    而本测环境无 DB catalog ⇒ **本测结构上覆盖不到 v0.7.29b 的 merge-权威分支**
    （初次取材我正是打错了那一行 → 仍绿；改打 fallback 才红）。
    merge-权威分支由 `tests/services/test_catalog_loaders.py:208` 覆盖 —— 两条测**分工不重叠**。
    """
    from knot.services.agents.catalog_loaders import _load_from_files

    _f_lex, f_tables, _f_rules, _f_rel, _f_src = _load_from_files()
    file_http = {f"{t.get('db')}.{t.get('table')}"
                 for t in (f_tables or []) if t.get("source_type") == "http"}
    if not file_http:
        import pytest
        pytest.skip("本环境的 file 层无 HTTP 虚拟表（既非 _local_catalog 也非 template 提供）")

    r = client.get(_URL, headers=auth_headers)
    assert r.status_code == 200, r.text
    got = {f"{t.get('db')}.{t.get('table')}" for t in r.json()["current"]["tables"]}
    missing = sorted(file_http - got)
    assert not missing, (
        f"file 层 HTTP 虚拟表未出现在 `current` 里：{missing}\n\n"
        "⚠️ 若你刚「顺手把 file 内容从 current 里清干净」—— **停下**：\n"
        "  file HTTP 表在 `reload()` 里【权威覆盖】同名 DB 条目（v0.7.29b merge 权威）；\n"
        "  摘掉它们 ⇒ `pick_http_route` Layer 1 恒不命中 ⇒ **HTTP 查询静默落 SQL**（v0.7.29b 复发）。\n"
        "  v0.9.5 只删了死的 `defaults` 字段（部分减暴露）；per-tenant file catalog 仍在 R-T-GATE 清单。"
    )


def test_defaults_key_is_gone(client, auth_headers):
    """8：响应**顶层不再含 `defaults`**（v0.9.5 D4'）。

    背景：`defaults` = `get_defaults_from_files()` = **部署级** `_local_catalog` 全文，
    **绕过 per-tenant 槽**直吐给任何**租户** admin；而前端**零处渲染**
    （仅 `Admin.jsx:51,108` 存进 state，「恢复默认」走服务端 `POST /api/admin/catalog/reset`）
    ⇒ 删它是**零 UI 影响**的减暴露。
    ⚠️ **本测刻意只断顶层键消失**，**不**断「响应零 `_local_catalog` 内容」—— 后者不成立
    （`current` 仍含 file 层，见上一条测），也**不允许**成立（v0.7.29b）。
    取材=revert：把 `"defaults": catalog_loader.get_defaults_from_files(),` 加回 → 本测红。
    """
    r = client.get(_URL, headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "defaults" not in body, (
        "响应里又出现了 `defaults` —— 它是部署级 `_local_catalog` 全文（绕过 per-tenant 槽），"
        "且前端零处渲染。v0.9.5 已删；要加回请先过评审（R-T-GATE / OOS-1v2）。"
    )
    # 契约其余部分不变（防「顺手把别的键一起删了」）
    assert {"source", "current", "db_overrides"} <= set(body), f"响应契约漂移：{sorted(body)}"
