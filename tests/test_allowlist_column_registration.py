"""凡进入 `_MUTABLE_TENANT_FIELDS` 的 `allowed_*` 列，必须在**五处**同时登记（v0.9.18 P-a · Stage 3 must-1）。

⭐ **为什么是一条派生断言，而不是一份五项清单**（守护者 Stage 3 原话）：
> **C3 的理由适用于全部六处，而执行者只用在了第四处。**

Stage 1 初稿把「加一列要同步的地方」写成一张**六项、跨 5 文件、「缺一即坏」**的手写表。
那正是本弧反复证明会漂的形状 —— 同一份 Stage 1 的 §5-2 还把 R-T-GATE 清单
记成「**清单必须派生**的第四个数据点」，然后在 §2 里又手写了一张新清单。

⇒ 本测把那张表**派生掉**：清单不再是待办，**断言才是**。
第三份 allowlist 来的时候，**五处一起**被逼着登记，而不是只有审计那一处。

## 判据锚在「系统真的产出了什么」，不是「文件里写了什么」（R-SENTINEL-AST 的一般化）
五个来源里 **3 个取运行期真值**、2 个**结构化解析**（它们不是 Python，取不到运行期值）：

| # | 来源 | 取法 | 为什么不是 grep |
|---|---|---|---|
| 1 | `platform_schema.sql` | 解析 `CREATE TABLE tenants (...)` **的列名集合** | 该文件的注释里**大量出现**列名（三态语义说明）⇒ 「字符串出现过」恒真 |
| 2 | `platform_migrations.py` | AST 取 `ALTER TABLE tenants ADD COLUMN <名>` 里的**列名** | 同上：迁移函数的注释也在讨论这些列名 |
| 3 | `TenantCreate` | `model_fields`（pydantic **运行期**） | 声明可能被注释掉而字面仍在 |
| 4 | `create_tenant` | `inspect.signature`（**运行期**） | 同上 |
| 5 | `_REDACTED_IN_AUDIT` | 模块属性（**运行期**） | 同上 |

⇒ 与 v0.9.12 那条自诊断同源：**问「跑出来是什么」，不是问「写着是什么」。**

## revert-to-bad（五问②，kk 立的放行硬条件）
往 `_MUTABLE_TENANT_FIELDS` 加一个 `allowed_xxx` 而不做五处登记 ⇒ 本测红，且**逐处点名**缺哪一处。
（实施期实证见 CHANGELOG / 手册 §8。）
"""
import ast
import inspect
import pathlib
import re

import pytest

from knot.api import platform_admin
from knot.repositories import tenant_provisioning, tenant_repo

_REPO = pathlib.Path(__file__).resolve().parent.parent

#: 本测管辖的字段 = 写口里所有 `allowed_` 开头的列。**不硬编具体列名** —— 那就是被派生掉的那张清单。
_MANAGED = tuple(f for f in tenant_repo._MUTABLE_TENANT_FIELDS if f.startswith("allowed_"))


def _create_request_model():
    """开通端点的**请求体模型**，从路由签名派生 —— 不硬编类名。

    ⚠️ **实施期实证（写下来因为它正是本测要防的形状）**：初版硬编了 `TenantCreate`，
    而真名是 `TenantCreateRequest` —— 那个名字是**从 Stage 2 评审转述里抄的，没有自己核**。
    硬编类名等于在一条「反对硬编清单」的测里又开了一份手写清单。
    ⇒ 改从路由派生：端点改名/换模型时本测**跟着走**，而不是红在一个与被测性质无关的地方。
    """
    import typing as _t

    for route in platform_admin.router.routes:
        if getattr(route, "path", "").endswith("/tenants") and "POST" in getattr(route, "methods", set()):
            # ⚠️ 该模块有 `from __future__ import annotations` ⇒ `inspect.signature` 拿到的是**字符串**
            #    （实施期实测：`'TenantCreateRequest'`, type=str）⇒ 必须 `get_type_hints` 解析成真类。
            for ann in _t.get_type_hints(route.endpoint).values():
                if hasattr(ann, "model_fields"):          # pydantic BaseModel
                    return ann
    raise AssertionError(
        "没能从 `POST …/tenants` 的签名里找到 pydantic 请求体模型 —— 本测的派生假设已过期。"
    )


def test_there_is_at_least_one_managed_column():
    """⚠️ 空集上做「每个都…」的断言**恒真** —— 先证明管辖集非空（五问③；本仓已踩 3 次）。"""
    assert _MANAGED, (
        "`_MUTABLE_TENANT_FIELDS` 里一个 `allowed_*` 列都没有 —— "
        "要么写口被改坏了，要么本测的前缀约定过期了。两种情况都不该静默通过。"
    )


def _schema_columns() -> set[str]:
    """`platform_schema.sql` 里 `tenants` 表**真正声明的列名集合**（非「字符串出现过」）。"""
    sql = (_REPO / "knot/repositories/platform_schema.sql").read_text(encoding="utf-8")
    m = re.search(r"CREATE TABLE IF NOT EXISTS tenants\s*\((.*?)\n\);", sql, re.S | re.I)
    assert m, "没能在 platform_schema.sql 里定位 `CREATE TABLE ... tenants (...)` —— 本测的解析假设已过期"
    cols = set()
    for line in m.group(1).splitlines():
        line = line.split("--", 1)[0].strip()               # ⚠️ 先剥注释：注释里满是列名
        if not line or line.upper().startswith(("PRIMARY", "UNIQUE", "FOREIGN", "CHECK", "CONSTRAINT")):
            continue
        if tok := re.match(r"([A-Za-z_][A-Za-z0-9_]*)", line):
            cols.add(tok.group(1))
    return cols


def _migration_added_columns() -> set[str]:
    """平台迁移里 `ALTER TABLE tenants ADD COLUMN <名>` 真正加的列名（AST 取字面量，非 grep）。"""
    src = (_REPO / "knot/repositories/platform_migrations.py").read_text(encoding="utf-8")
    added = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if m := re.search(r"ALTER\s+TABLE\s+tenants\s+ADD\s+COLUMN\s+([A-Za-z_][A-Za-z0-9_]*)",
                              node.value, re.I):
                added.add(m.group(1))
    return added


@pytest.mark.parametrize("column", _MANAGED)
def test_managed_allowlist_column_is_registered_in_all_five_places(column):
    """⭐ 五处缺一即红，且**点名缺的是哪一处**（诊断要可操作 —— v0.9.10 那条「消息在撒谎」的教训）。"""
    missing = []

    if column not in _schema_columns():
        missing.append("① platform_schema.sql 的 CREATE TABLE tenants —— 新库不会有这一列")
    if column not in _migration_added_columns():
        missing.append("② platform_migrations.py 的 ALTER TABLE —— **存量库**不会有这一列")
    if column not in _create_request_model().model_fields:
        missing.append("③ platform_admin.TenantCreate —— 开通端点收不到它 ⇒ 新租户该列恒 NULL")
    if column not in inspect.signature(tenant_provisioning.create_tenant).parameters:
        missing.append("④ tenant_provisioning.create_tenant 签名 —— 开通时写不进去")
    if column not in tenant_repo._REDACTED_IN_AUDIT:
        missing.append("⑤ tenant_repo._REDACTED_IN_AUDIT —— **allowlist 内容会原样进平台审计并可经端点读出**")

    assert not missing, (
        f"`{column}` 进了 `_MUTABLE_TENANT_FIELDS`，但下列登记缺失：\n"
        + "\n".join(f"  - {x}" for x in missing)
        + "\n\n⇒ 这五处「缺一即坏」，所以它们由本断言强制，而不是由一份会漂的手写清单强制。"
    )


def test_new_tenant_create_field_is_required_not_defaulted():
    """③ 那一处**必须无默认值**（否则开通动作替部署方静默选了一种语义）。

    理由不是本测发明的 —— `platform_admin.py` 自己写着「必填且允许空串…否则开通动作就替部署方
    静默选了一种语义」。⇒ 把那句散文变成断言（v3.1-B #5：只写 docstring 而无守护的规则）。
    """
    model = _create_request_model()
    # ⚠️ **判据只能是 `is_required()`**（实施期实测）：必填字段的 `.default` 是 `PydanticUndefined`
    #    而**不是** `None` ⇒ 初版写的 `default is not None` 对**所有**必填字段恒真 = 把正确的实现判成错
    #    （一条恒红的判据和一条恒绿的判据一样没用 —— 它测的不是被测性质）。
    # ⚠️ **只看「已登记进模型」的那些**（实施期跑 revert 时发现）：未登记的列由上一条测负责，
    #    本条若也去 `model_fields[c]` 会抛 `KeyError` ⇒ 两条测同时红，而其中一条红得**没有信息**
    #    （五问④：消息要说对事）。⇒ 各守各的：上一条守「登记齐全」，本条守「登记了的必须必填」。
    bad = [c for c in _MANAGED if c in model.model_fields and not model.model_fields[c].is_required()]
    assert not bad, (
        f"这些 allowlist 字段在开通请求体里**非必填**：{bad}\n"
        "⇒ 开通动作会替部署方静默选一种 egress 语义（三态里的哪一态？没人知道）。\n"
        "理由不是本测发明的 —— `platform_admin.py` 自己写着「必填且允许空串…否则开通动作就替"
        "部署方静默选了一种语义」。"
    )
