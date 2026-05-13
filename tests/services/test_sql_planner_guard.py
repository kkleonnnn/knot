"""tests/services/test_sql_planner_guard.py — v0.6.0-hotfix sql_planner 守护测试。

LOCKED 终稿盲区补救 #5 + #6：

R-PA-9（漏洞 #5）：execute_sql 路径笛卡尔积/fan-out 守护（v0.5.1 设计漏洞）
  - 现版仅 final_answer 分支 (sql_planner_tools.py:144) 拦截 cartesian
  - LLM 用 execute_sql 工具直接执行的路径完全裸奔
  - DeepSeek/OpenRouter 倾向 execute_sql 路径触发

R-PA-10（漏洞 #6）：CTE (WITH...) 识别为可执行查询（pre-existing v0.4.x/v0.5.x）
  - sql_planner.py:140/286 用 startswith("SELECT") 跳过 CTE 执行
  - final_rows 保持 [] → 用户看到空结果（DB 实际能返回数据）
"""
from knot.services.agents.sql_planner import _is_executable_query
from knot.services.agents.sql_planner_tools import _run_tool


# ── R-PA-9: execute_sql 路径笛卡尔积/fan-out 守护 ──────────────────────────

def test_R_PA_9_execute_sql_blocks_cross_join():
    """CROSS JOIN 在 execute_sql 路径必须被 sql_validator 拦截。

    回归 v0.5.1 R-80~93 4 层防御契约 — execute_sql 路径补防。
    """
    result = _run_tool("execute_sql", "SELECT * FROM a CROSS JOIN b",
                       engine=None, schema_text="")
    assert result.startswith("__REJECT_CARTESIAN__:"), \
        f"CROSS JOIN 应被 execute_sql 路径拦截；实际：{result[:80]}"


def test_R_PA_9_execute_sql_blocks_implicit_comma_join():
    """旧式逗号缺 ON 在 execute_sql 路径必须被拦截。"""
    result = _run_tool("execute_sql", "SELECT * FROM a, b WHERE a.x = 1",
                       engine=None, schema_text="")
    assert result.startswith("__REJECT_CARTESIAN__:"), \
        f"旧式逗号缺 ON 应被 execute_sql 路径拦截；实际：{result[:80]}"


def test_R_PA_9_execute_sql_allows_explicit_join_on():
    """显式 JOIN ON 不应被守护拦截（validator 通过）。

    engine=None 会让 db_connector 报错（AttributeError），但应在 validator
    之后 — 即不应出现 __REJECT_ 前缀，否则说明误判。
    """
    result = _run_tool("execute_sql",
                       "SELECT * FROM a JOIN b ON a.id = b.aid",
                       engine=None, schema_text="")
    assert not result.startswith("__REJECT_"), \
        f"显式 JOIN ON 不应被守护拦截；实际：{result[:80]}"


# ── R-PA-10: CTE (WITH) 识别为可执行查询 ───────────────────────────────────

def test_R_PA_10_cte_is_executable():
    """CTE (WITH ... SELECT) 必须被识别为可执行查询。

    pre-existing v0.5.x bug：startswith("SELECT") 错过 CTE → 跳过 db_connector
    → final_rows 保持 []。修复后 _is_executable_query 同时识别 SELECT + WITH。
    """
    # CTE 经典写法
    assert _is_executable_query("WITH x AS (SELECT 1) SELECT * FROM x")
    assert _is_executable_query("with x AS (select 1) select * from x")  # 小写
    # 前导空格
    assert _is_executable_query("  WITH x AS ...")
    assert _is_executable_query("\n\tWITH x AS ...")
    # 简单 SELECT
    assert _is_executable_query("SELECT 1")
    assert _is_executable_query("  SELECT 1  ")  # 前后空格
    assert _is_executable_query("select 1")  # 小写


def test_R_PA_10_non_select_rejected():
    """非 SELECT/WITH 必须被拒（防止 DDL/DML 误执行）。"""
    assert not _is_executable_query("INSERT INTO x VALUES (1)")
    assert not _is_executable_query("UPDATE x SET y = 1")
    assert not _is_executable_query("DELETE FROM x WHERE y = 1")
    assert not _is_executable_query("DROP TABLE x")
    assert not _is_executable_query("CREATE TABLE x (id INT)")
    assert not _is_executable_query("")
    assert not _is_executable_query(None)
