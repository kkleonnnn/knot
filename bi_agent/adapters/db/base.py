"""bi_agent.adapters.db.base — 业务库适配器契约（v0.3.2）

行为契约（Protocol，非 ABC），1:1 对应 Go 重写时的 interface：

    type BusinessDBAdapter interface {
        Query(sql string) ([]Row, error)
        GetSchema(databases []string, maxTables int) (string, error)
        ProbeReadonlyGrants() (bool, []string, error)
        TestConnection() (bool, error)
    }

具体实现（doris / clickhouse / bigquery / ...）只需满足此 Protocol；
adapters/db/factory.py 按 DataSource.db_type 路由。
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class BusinessDBAdapter(Protocol):
    """业务库读路径契约：解决 Doris / TiDB / ClickHouse 方言差异。"""

    def execute_query(self, sql: str, max_rows: int = 500) -> tuple[list[dict], str | None]:
        """执行只读 SQL；返回 (rows, error_message)。
        error_message 非空表示执行失败（不抛异常，给上层做 SSE 友好处理）。"""
        ...

    def get_schema(self, databases: list | None = None, max_tables: int = 20) -> str:
        """以 markdown 形式返回 schema（schema_filter 服务的输入）。"""
        ...

    def check_readonly_grants(self) -> tuple[bool, list[str]]:
        """探测当前账号是否仅有 SELECT 权限。
        返回 (is_readonly, warnings) — STRICT_READONLY_GRANTS=1 时非 readonly 拒绝构建。

        ⚠️ 方言差异（v0.3.2 R-8）：
        Doris/MySQL 用 `SHOW GRANTS`，但 ClickHouse / BigQuery 没有等价语法。
        若适配的数据库无法可靠探测 grants，实现方可直接返回 ``(True, [])`` 表示
        "信任模式"，由 SQL guardrail（is_safe_sql）兜底拦截写操作；
        STRICT_READONLY_GRANTS=1 时 admin 应改用专用只读账号绕开此探测。
        """
        ...

    def test_connection(self) -> tuple[bool, str | None]:
        """ping 一下；返回 (ok, error_message)。"""
        ...


def is_safe_sql(sql: str) -> tuple[bool, str]:
    """sqlglot AST 解析的只读 guardrail —— 与 SQL 方言无关，
    所有 BusinessDBAdapter 实现都应在 execute_query 前调用此函数。

    实现位于 adapters/db/safety.py（v0.3.2 后续迭代再独立文件）；
    当前临时复用 adapters.db.doris._is_safe_sql。"""
    from bi_agent.adapters.db.doris import _is_safe_sql
    return _is_safe_sql(sql)
