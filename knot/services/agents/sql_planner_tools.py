"""knot/services/agents/sql_planner_tools.py — v0.5.2 起从 sql_planner.py 抽出。

源行号区间（v0.5.1 final 状态）：
- L157-163 `_strip_sql`
- L166-181 `_parse_agent_output`
- L187-191 `_AGG_FUNC_RE` / `_LEFT_JOIN_NAMED_TABLE_RE`（fan-out 常量）
- L194-227 `_is_fan_out`（v0.4.1.1 fan-out runtime 静态守护）
- L230-303 `_run_tool`（含 v0.5.1 cartesian + v0.4.1.1 fan-out 双层守护）

R-106 单向依赖：本模块依赖 stdlib + knot.adapters.db.doris + knot.services.sql_validator；
严禁反向 import sql_planner.py / sql_planner_prompts.py / sql_planner_llm.py。
R-107 Private 前缀保留：所有 helper `_` 前缀不变（sql_planner.py re-export 给测试）。
"""
import json
import re

from knot.adapters.db import doris as db_connector
from knot.services import sql_validator


def _strip_sql(s: str) -> str:
    """剥掉 LLM 常见的 markdown 围栏：```sql ... ``` / ``` ... ``` / 单反引号。"""
    s = s.strip()
    m = re.match(r"^```(?:sql)?\s*([\s\S]*?)\s*```$", s, re.IGNORECASE)
    if m:
        s = m.group(1)
    return s.strip().strip("`").strip()


def _parse_agent_output(text: str) -> tuple[str, str, str]:
    thought = action = action_input = ""

    m = re.search(r'Thought:\s*(.*?)(?=\nAction:|\Z)', text, re.DOTALL)
    if m:
        thought = m.group(1).strip()

    m = re.search(r'Action:\s*(\S+)', text)
    if m:
        action = m.group(1).strip().lower()

    m = re.search(r'Action Input:\s*(.*)\Z', text, re.DOTALL)
    if m:
        action_input = m.group(1).strip()

    return thought, action, action_input


# ── Fan-Out 静态检测（v0.4.1.1 实战补丁 C 升级：runtime 守护）─────────────
# 检测语义错误的 SUM 膨胀反模式：≥ 2 个 LEFT JOIN 到具名表（非子查询）+ 外层 SELECT
# 含 ≥ 2 个聚合函数。CTE / 子查询 join 模式由前置启发式跳过避免误杀。
_AGG_FUNC_RE = re.compile(r"\b(?:sum|count|avg|min|max)\s*\(", re.IGNORECASE)
_LEFT_JOIN_NAMED_TABLE_RE = re.compile(
    r"\bleft\s+join\s+(?!\()(?:\w+\.)?\w+",  # LEFT JOIN <ident>(.<ident>)?，但不接 (
    re.IGNORECASE,
)


def _is_fan_out(sql: str) -> tuple[bool, str]:
    """返 (是否 fan-out, 原因)。
    跳过的合法场景（避免误杀）：
    - 顶层是 WITH（CTE 预聚合）
    - 没有 ≥ 2 个 LEFT JOIN 到具名表
    - 顶层 SELECT 没有 ≥ 2 个聚合函数
    """
    if not sql:
        return False, ""
    s = sql.strip()
    # 1. CTE：顶层是 WITH 关键字 → 跳过（CTE 通常已做预聚合）
    if re.match(r"^\s*with\s+", s, re.IGNORECASE):
        return False, ""

    # 2. 顶层 SELECT...FROM 提取（找第一个 SELECT 到第一个 FROM 之间的字段列表）
    sl = s.lower()
    m = re.search(r"\bselect\b(.*?)\bfrom\b", sl, re.DOTALL)
    if not m:
        return False, ""
    outer_select = m.group(1)
    # 3. 顶层 SELECT 中聚合函数计数（≥ 2 才有 fan-out 风险）
    aggs = _AGG_FUNC_RE.findall(outer_select)
    if len(aggs) < 2:
        return False, ""

    # 4. LEFT JOIN 到具名表的次数（不计 LEFT JOIN ( ... ) 子查询）
    direct_left_joins = _LEFT_JOIN_NAMED_TABLE_RE.findall(sl)
    if len(direct_left_joins) < 2:
        return False, ""

    return True, (
        f"外层 SELECT 含 {len(aggs)} 个聚合函数 + {len(direct_left_joins)} 个 LEFT JOIN 到具名明细表，"
        f"行数相乘会让聚合结果膨胀"
    )


def _run_tool(action: str, action_input: str, engine, schema_text: str) -> str:
    if action == "execute_sql":
        sql = _strip_sql(action_input)
        rows, error = db_connector.execute_query(engine, sql)
        if error:
            return f"执行失败: {error}"
        if not rows:
            return "查询成功，返回 0 行"
        preview = json.dumps(rows[:5], ensure_ascii=False, default=str)
        return f"查询成功，共 {len(rows)} 行，前几行:\n{preview}"

    elif action == "describe_table":
        table_name = action_input.strip().strip("`")
        in_table = False
        result_lines = []
        for line in schema_text.split("\n"):
            if line.strip().startswith(f"### {table_name}"):
                in_table = True
            elif line.strip().startswith("### ") and in_table:
                break
            if in_table:
                result_lines.append(line)
        if result_lines:
            return "\n".join(result_lines)
        rows, err = db_connector.execute_query(engine, f"DESCRIBE `{table_name}`")
        if err:
            return f"无法获取表 {table_name} 的结构: {err}"
        return f"表 {table_name} 的字段:\n" + json.dumps(rows, ensure_ascii=False)

    elif action == "list_tables":
        rows, err = db_connector.execute_query(engine, "SHOW TABLES")
        if err:
            tables = re.findall(r'^### (.+)$', schema_text, re.MULTILINE)
            return "表名列表（来自 Schema）: " + ", ".join(tables)
        tables = [str(list(r.values())[0]) for r in rows]
        return "数据库中的表: " + ", ".join(tables)

    elif action == "search_schema":
        keyword = action_input.strip().lower()
        results = []
        current_table = ""
        for line in schema_text.split("\n"):
            if line.startswith("### "):
                current_table = line[4:].strip()
            if keyword in line.lower() and current_table:
                results.append(f"[{current_table}] {line.strip()}")
        if results:
            return "找到以下匹配:\n" + "\n".join(results[:10])
        return f"Schema 中没有找到包含 '{keyword}' 的内容"

    elif action == "final_answer":
        # v0.4.1.1 C 升级：final_answer 时 runtime 守护反模式
        # v0.5.1 R-85：cartesian 优先（更基础错误，先于 fan-out 细分聚合错误）
        candidate = _strip_sql(action_input)
        is_cart, cart_reason = sql_validator.is_cartesian(candidate)
        if is_cart:
            return (
                f"__REJECT_CARTESIAN__:{cart_reason} "
                f"Regenerate the SQL with explicit JOIN ... ON conditions."
            )
        is_fan, reason = _is_fan_out(candidate)
        if is_fan:
            return (
                f"__REJECT_FAN_OUT__:你提交的 SQL 是 fan-out 反模式（{reason}）。"
                f"必须重写：每个明细表先用 `LEFT JOIN (SELECT key, SUM/COUNT(...) FROM <table> "
                f"GROUP BY key) AS alias ON ...` 子查询/CTE 按 grain 预聚合后再 JOIN，"
                f"不要让外层 SELECT 直接对多个 LEFT JOIN 后字段聚合。重新生成 SQL。"
            )
        return f"__FINAL__:{action_input}"

    else:
        return f"未知工具 '{action}'，请使用 execute_sql/describe_table/list_tables/search_schema/final_answer"
