"""
db_connector.py — 数据库层（连接 + Schema 加载 + 安全查询执行）
"""

import re
import sqlalchemy
from sqlalchemy import text

from config import (
    DEFAULT_DB_HOST, DEFAULT_DB_PORT,
    DEFAULT_DB_USER, DEFAULT_DB_PASSWORD, DEFAULT_DB_DATABASE,
    MAX_RESULT_ROWS, MAX_TABLES_IN_SCHEMA,
)


def build_connection_url(host, port, user, password, database) -> str:
    from urllib.parse import quote_plus
    encoded_password = quote_plus(password)
    return f"mysql+pymysql://{user}:{encoded_password}@{host}:{port}/{database}?charset=utf8mb4"


def create_engine(host, port, user, password, database):
    primary_db = database.split(',')[0].strip()
    url = build_connection_url(host, port, user, password, primary_db)
    return sqlalchemy.create_engine(
        url,
        connect_args={"ssl_disabled": True, "connect_timeout": 3},
        pool_recycle=3600,
        pool_pre_ping=True,
    )


def test_connection(engine) -> tuple:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True, "连接成功"
    except Exception as e:
        error_msg = str(e)
        if "Access denied" in error_msg:
            return False, "用户名或密码错误"
        elif "Unknown database" in error_msg:
            return False, "数据库不存在"
        elif "Connection refused" in error_msg or "Can't connect" in error_msg:
            return False, "无法连接到服务器，请检查 Host 和端口"
        else:
            return False, f"连接失败: {error_msg[:200]}"


def get_schema(engine, databases: list = None, max_tables: int = MAX_TABLES_IN_SCHEMA) -> str:
    try:
        with engine.connect() as conn:
            if not databases:
                result = conn.execute(text("SHOW TABLES"))
                raw_tables = [(None, row[0]) for row in result.fetchall()]
                total = len(raw_tables)
                truncated = total > max_tables
                raw_tables = raw_tables[:max_tables]
            else:
                # v0.2.1 修复跨库失衡：按 DB 平均配额（向上取整），保证每个库都进入 schema
                per_db: dict = {}
                total = 0
                for db in databases:
                    rows = [r[0] for r in conn.execute(text(f"SHOW TABLES FROM `{db}`")).fetchall()]
                    per_db[db] = rows
                    total += len(rows)

                if total <= max_tables:
                    raw_tables = [(db, t) for db, ts in per_db.items() for t in ts]
                    truncated = False
                else:
                    quota = max(max_tables // max(len(databases), 1), 1)
                    picked = []
                    leftover = []
                    for db, ts in per_db.items():
                        picked.extend((db, t) for t in ts[:quota])
                        leftover.extend((db, t) for t in ts[quota:])
                    # 余额按顺序补齐到 max_tables
                    remaining = max_tables - len(picked)
                    if remaining > 0:
                        picked.extend(leftover[:remaining])
                    raw_tables = picked
                    truncated = True

            if not raw_tables:
                return "（数据库中没有找到任何表）"

            schema_parts = []
            for db, table_name in raw_tables:
                display = f"{db}.{table_name}" if db else table_name
                try:
                    if db:
                        col_rows = conn.execute(text(
                            "SELECT COLUMN_NAME, COLUMN_TYPE, COLUMN_COMMENT "
                            "FROM information_schema.COLUMNS "
                            "WHERE TABLE_SCHEMA=:db AND TABLE_NAME=:tbl "
                            "ORDER BY ORDINAL_POSITION"
                        ), {"db": db, "tbl": table_name}).fetchall()
                    else:
                        col_rows = conn.execute(text(
                            "SELECT COLUMN_NAME, COLUMN_TYPE, COLUMN_COMMENT "
                            "FROM information_schema.COLUMNS "
                            "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=:tbl "
                            "ORDER BY ORDINAL_POSITION"
                        ), {"tbl": table_name}).fetchall()
                    lines = [f"### {display}", "| 字段名 | 类型 | 注释 |", "|--------|------|------|"]
                    for row in col_rows:
                        field, type_, comment = row[0], row[1], str(row[2]) if row[2] else ""
                        lines.append(f"| {field} | {type_} | {comment} |")
                    schema_parts.append("\n".join(lines))
                except Exception:
                    schema_parts.append(f"### {display}\n（无法读取表结构）")

            if truncated:
                schema_parts.append(f'---\n> 库内表总数 > {max_tables}，已按库平均抽样加载 {len(raw_tables)} 张。')

            return "\n\n".join(schema_parts)
    except Exception as e:
        return f"（Schema 加载失败: {str(e)[:200]}）"


def execute_query(engine, sql: str, max_rows: int = MAX_RESULT_ROWS) -> tuple:
    import datetime
    from decimal import Decimal
    ok, reason = _is_safe_sql(sql)
    if not ok:
        return [], f"安全检查未通过: {reason}"

    sql_upper = sql.upper().strip()
    if "LIMIT" not in sql_upper:
        sql = sql.rstrip(";").strip() + f" LIMIT {max_rows}"

    try:
        with engine.connect() as conn:
            result = conn.execute(text(sql))
            columns = list(result.keys())
            rows = []
            for row in result.fetchall():
                d = {}
                for col, val in zip(columns, row):
                    if isinstance(val, Decimal):
                        val = float(val)
                    elif isinstance(val, (datetime.datetime, datetime.date, datetime.time)):
                        val = str(val)
                    elif isinstance(val, bytes):
                        val = val.decode("utf-8", errors="replace")
                    d[col] = val
                rows.append(d)
        return rows, ""
    except Exception as e:
        error_msg = str(e)
        if "1064" in error_msg:
            return [], f"SQL 语法错误: {error_msg[:300]}"
        elif "1146" in error_msg:
            return [], f"表不存在: {error_msg[:200]}"
        elif "1054" in error_msg:
            return [], f"字段不存在: {error_msg[:200]}"
        else:
            return [], f"查询失败: {error_msg[:300]}"


def create_sqlite_engine(db_path: str):
    return sqlalchemy.create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )


def load_rows_to_sqlite(engine, table_name: str, headers: list, rows: list) -> tuple:
    """Create table and insert rows. Infers REAL type for numeric columns."""
    import re

    def _is_numeric(col_idx):
        vals = [r[col_idx] for r in rows if r[col_idx] not in (None, "")]
        if not vals:
            return False
        try:
            [float(v) for v in vals]
            return True
        except (ValueError, TypeError):
            return False

    safe = [re.sub(r"[^\w]", "_", h) or f"col{i}" for i, h in enumerate(headers)]
    types = ["REAL" if _is_numeric(i) else "TEXT" for i in range(len(headers))]
    col_defs = ", ".join(f'"{s}" {t}' for s, t in zip(safe, types))

    try:
        with engine.connect() as conn:
            conn.execute(sqlalchemy.text(f'DROP TABLE IF EXISTS "{table_name}"'))
            conn.execute(sqlalchemy.text(f'CREATE TABLE "{table_name}" ({col_defs})'))
            for row in rows:
                vals = []
                for i, v in enumerate(row):
                    if v in (None, ""):
                        vals.append(None)
                    elif types[i] == "REAL":
                        try:
                            vals.append(float(v))
                        except (ValueError, TypeError):
                            vals.append(None)
                    else:
                        vals.append(str(v))
                placeholders = ", ".join("?" * len(safe))
                conn.execute(sqlalchemy.text(
                    f'INSERT INTO "{table_name}" VALUES ({placeholders})'
                ), vals)
            conn.commit()
        return True, ""
    except Exception as e:
        return False, str(e)[:300]


def get_sqlite_schema_text(engine, table_name: str) -> str:
    """Returns markdown schema text for a SQLite table (for LLM prompt)."""
    try:
        with engine.connect() as conn:
            rows = conn.execute(sqlalchemy.text(f'PRAGMA table_info("{table_name}")')).fetchall()
            lines = [f"### {table_name}", "| 字段名 | 类型 |", "|--------|------|"]
            for row in rows:
                lines.append(f"| {row[1]} | {row[2]} |")
            return "\n".join(lines) + "\n\n> 注意：这是 SQLite 数据库，日期函数使用 strftime()，字符串用 || 拼接。"
    except Exception as e:
        return f"（Schema 加载失败: {e}）"


def get_schema_structured(engine, databases: list = None) -> list:
    """Return schema as JSON-serializable list for the schema browser UI."""
    try:
        with engine.connect() as conn:
            if not databases:
                result = conn.execute(text("SHOW TABLES"))
                raw_tables = [(None, row[0]) for row in result.fetchall()]
            else:
                raw_tables = []
                for db in databases:
                    result = conn.execute(text(f"SHOW TABLES FROM `{db}`"))
                    raw_tables.extend((db, row[0]) for row in result.fetchall())

            tables_info = []
            for db, table_name in raw_tables:
                display = f"{db}.{table_name}" if db else table_name
                try:
                    if db:
                        col_rows = conn.execute(text(
                            "SELECT COLUMN_NAME, COLUMN_TYPE, COLUMN_COMMENT "
                            "FROM information_schema.COLUMNS "
                            "WHERE TABLE_SCHEMA=:db AND TABLE_NAME=:tbl "
                            "ORDER BY ORDINAL_POSITION"
                        ), {"db": db, "tbl": table_name}).fetchall()
                    else:
                        col_rows = conn.execute(text(
                            "SELECT COLUMN_NAME, COLUMN_TYPE, COLUMN_COMMENT "
                            "FROM information_schema.COLUMNS "
                            "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=:tbl "
                            "ORDER BY ORDINAL_POSITION"
                        ), {"tbl": table_name}).fetchall()
                    columns = [{"name": r[0], "type": r[1], "comment": str(r[2]) if r[2] else ""} for r in col_rows]
                    tables_info.append({"name": display, "columns": columns})
                except Exception:
                    tables_info.append({"name": display, "columns": []})
            return tables_info
    except Exception:
        return []


def _is_safe_sql(sql: str) -> tuple:
    cleaned = sql.strip()
    if not cleaned.upper().startswith("SELECT"):
        return False, "只允许执行 SELECT 查询"

    dangerous = [
        r"\bINSERT\b", r"\bUPDATE\b", r"\bDELETE\b",
        r"\bDROP\b", r"\bTRUNCATE\b", r"\bALTER\b",
        r"\bCREATE\b", r"\bGRANT\b", r"\bREVOKE\b",
    ]
    sql_upper = cleaned.upper()
    for pattern in dangerous:
        if re.search(pattern, sql_upper):
            keyword = pattern.replace(r"\b", "").replace("\\b", "")
            return False, f"包含危险关键词 {keyword}"

    return True, ""
