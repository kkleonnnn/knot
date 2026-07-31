"""闸门：v0.9.7 B-3 ② —— HTTP 凭据**只能**来自租户自己的数据源（`source_id`）。

## 本文件守什么
`adapters/http/executor.execute` 此前有**两条**凭据路径：
- 模式 A「直填」：spec 自带 `base_url` / `auth_*`；
- 模式 B「env 引用」：spec 自带 `base_url_env` / `auth_*_env` → **executor 读进程 env**。

模式 B 是 R-T-GATE 清单 **B-3 ②** 那条缺口的入口：进程 env 是**租户盲**的
⇒ 租户#2 能用租户#1 的凭据读其实时接口 = **跨租户数据出境**。
v0.9.7 删掉模式 B；凭据一律经 `source_id` → **本租户库** `data_sources` 行（Fernet 解密）。

## ⚠️ 「② 不是造机制，是退役一条路径」
per-tenant 凭据这个能力**本来就在**（`resolve_spec` → `get_datasource` → `get_conn`）。
缺的是把绕过它的路封死。**零真实生产者** —— 部署方真实 `_local_catalog.py` 的 http 表
全走 `source_id`（`base_url_env|auth_value_env` 实测 0 命中）⇒ 退役无兼容代价。

## 分层：门在**能力处**，降级在**决策处**
- **能力处**（本文件测的）= `executor.execute` —— 唯一发出网络请求的函数。
  spec 没有可用 `base_url` ⇒ `HTTPAuthError`，**不依赖上游是否降级**。
  这是必需的：`run_http_step` 是**公开函数、自带 spec、不重新求 route** ⇒
  monitor / 定时报表 / 混合路由任何直呼者都必须在这里被拦。
- **决策处** = `pick_http_route` / `resolve_spec` 的软降级（优雅落 SQL + 记日志）⇒ 见本文件后半。
（这个分工是 v0.9.6 守护者四轮统一诊断：**门装在能力被行使的那一行**。）
"""
from __future__ import annotations

import pytest

from knot.core.tenant_context import reset_active_tenant, set_active_tenant


def _owner_ctx():
    """起源租户 ctx —— 本文件测的是 ② 的边界，不是租户门（那条在 owner-gate 文件）。"""
    return set_active_tenant({"id": 1, "db_dir": "."})


_ENV_FORM_SPEC = {                              # ⛔ v0.9.7 起结构上不可表达
    "method": "GET",
    "url_template": "{base_url}/v1/items",
    "base_url_env": "KNOT_TEST_API_BASE_URL",
    "auth_header_env": "KNOT_TEST_API_AUTH_HEADER",
    "auth_value_env": "KNOT_TEST_API_AUTH_VALUE",
    "response_path": "data.records",
}


@pytest.mark.parametrize("spec,why", [
    (_ENV_FORM_SPEC, "env 引用形态（模式 B，已退役）"),
    ({"method": "GET", "url_template": "{base_url}/x"}, "既无 source_id 也无 base_url"),
    ({"method": "GET", "url_template": "{base_url}/x", "base_url": ""}, "base_url 空串"),
    ({"method": "GET", "url_template": "{base_url}/x", "base_url": "   "}, "base_url 全空白"),
])
def test_execute_refuses_spec_without_resolved_base_url(spec, why, no_network, monkeypatch):
    """⭐ must #5（能力处那半）：`execute` 拿不到「已解析的 base_url」⇒ 拒绝，且**零出网**。

    ⚠️ **env 全部设好也必须拒**：本测把三个 env 都设上 —— 若 executor 还残留任何读 env 的分支，
    它就会「成功地」拼出 URL 并出网 ⇒ 探针记录非空 ⇒ 本测红。
    **这是「结构上不可表达」与「env 没配时会抛」的区别**：后者只在 env 缺失时才拦，
    前者无论 env 配成什么样都拦（而退役前那条路正是「env 配好了就能用」）。

    ⚠️ oracle 有**两个因子**：① 抛 `HTTPAuthError`；② 出网探针记录**为空**。
    只看 ① 不够 —— 上游 `except Exception` 会把探针的 AssertionError 折成普通失败
    ⇒ 「有没有真发请求」在「抛了异常」这个 oracle 里表示不出来（v0.9.6 实证）。
    取材=revert：把 env 模式加回 `execute` → 第一格的探针记录非空 ⇒ 本测红。
    """
    from knot.adapters.http import HTTPAuthError, execute

    monkeypatch.setenv("KNOT_HTTP_ALLOWED_HOSTS", "api.example.com")
    monkeypatch.setenv("KNOT_TEST_API_BASE_URL", "https://api.example.com")
    monkeypatch.setenv("KNOT_TEST_API_AUTH_HEADER", "X-Key")
    monkeypatch.setenv("KNOT_TEST_API_AUTH_VALUE", "token-value-must-not-be-used")

    tok = _owner_ctx()
    try:
        try:
            execute(dict(spec), {"q": "test"})
        except HTTPAuthError as e:
            msg = str(e)
        else:
            pytest.fail(
                f"spec（{why}）**未被拒绝** —— 能力处的硬边界失效。\n"
                "`execute` 是唯一发出网络请求的函数；它必须在拿不到「已解析的 base_url」时拒绝，\n"
                "而不能依赖上游 `pick_http_route` 的软降级 —— `run_http_step` 是公开函数、\n"
                "自带 spec、不重新求 route ⇒ monitor / 定时报表 / 混合路由都能绕过决策处。"
            )
    finally:
        reset_active_tenant(tok)

    assert no_network == [], (
        f"spec（{why}）被拒绝了，但**已经发出过网络请求**：{no_network}\n"
        "⇒ 拒绝发生在出网之后 = 门装错了位置（必须在 requests.* 之前）。"
    )
    for bad in ("KNOT_", "token-value-must-not-be-used", "_local_catalog"):
        assert bad not in msg, f"拒绝消息泄漏 {bad!r}：{msg!r}（#262 那条缝：str(e) 会被 yield 给客户端）"


def test_executor_does_not_read_process_env_at_all():
    """⭐ 结构哨兵：`adapters/http/executor.py` **零 env 读取**（AST，标识符级）。

    为什么要有这条（而不只依赖上面的行为测）：行为测证明「当前这些 spec 形态拿不到 env 凭据」，
    但**挡不住有人加一条新的 env 分支**（比如「给这个表加个兜底 env 就好了」）。
    结构哨兵直接钉住不变量：**这个适配器不读进程 env**。

    ⚠️ 用 AST 按**属性/函数名**判定，不做文本匹配 —— 本文件与 executor 都在**讨论** env
    （docstring / 注释里大量出现 `os.environ`、`base_url_env`），文本匹配必然自匹配
    （R-SENTINEL-AST：讨论一个名字的文件必然含有那个名字）。
    取材=injection：往 `execute` 里加一行 `os.environ.get("X")` → 本测红并点名 `lineno`。
    """
    import ast
    import pathlib

    src = pathlib.Path(__file__).resolve().parents[2] / "knot/adapters/http/executor.py"
    tree = ast.parse(src.read_text(encoding="utf-8"))

    hits = []
    for n in ast.walk(tree):
        # `os.environ...` / `os.getenv(...)`：Attribute 的 value 是名为 os 的 Name
        if isinstance(n, ast.Attribute) and n.attr in ("environ", "getenv"):
            hits.append(f"{n.attr} @ line {n.lineno}")
        # `from os import environ` / `from os import getenv`
        if isinstance(n, ast.ImportFrom) and n.module == "os":
            hits.append(f"from os import {[a.name for a in n.names]} @ line {n.lineno}")
        # 裸 `import os`（v0.9.7 已删；留着会诱使后人再用）
        if isinstance(n, ast.Import) and any(a.name == "os" for a in n.names):
            hits.append(f"import os @ line {n.lineno}")

    assert not hits, (
        "`adapters/http/executor.py` 又开始读进程 env：\n  " + "\n  ".join(hits)
        + "\n\n⛔ 进程 env 是**租户盲**的 —— 任何从它取凭据/URL 的分支都会让租户#2 用上租户#1 的凭据\n"
          "  = 跨租户数据出境（R-T-GATE 清单 B-3 ②，v0.9.7 关闭）。\n"
          "凭据一律经 spec 的 `source_id` → 本租户库 `data_sources`（Fernet）→ `resolve_spec` 注入。\n"
          "若确有 env 需求，请先过评审：docs/plans/v0.9.7-http-per-tenant-credentials-egress.md §7"
    )
