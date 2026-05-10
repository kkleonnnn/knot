"""knot/services/llm_prompt_builder.py — v0.5.2 起从 llm_client.py 抽出。

源行号区间（v0.5.1 final 状态 llm_client.py 574 行）：
- L132-209 `build_system_prompt`

R-106 单向依赖：本模块依赖 stdlib + knot.core.date_context + knot.services.few_shots
+ delayed knot.services.agents.catalog；严禁反向 import knot.services.llm_client / 其他兄弟。
R-107：build_system_prompt 是 public 函数（llm_client 主文件 re-export 给业务用）。
"""
from knot.services.few_shots import get_few_shot_examples


def build_system_prompt(schema_text: str, business_context: str = "", question: str = "") -> str:
    section_role = """你是一个 Text-to-SQL 专家助手。
你的唯一任务是把用户的自然语言问题转换成可执行的 SQL 查询语句。
不要解释你自己，不要打招呼，只输出要求格式的 JSON。"""

    from knot.core import date_context
    section_db = f"""## 数据库环境
{date_context.date_context_block()}
- 数据库类型: Apache Doris（完全兼容 MySQL 5.7 语法）
- 时间函数: DATE_SUB(CURDATE(), INTERVAL N DAY) 或 CURRENT_DATE - INTERVAL N DAY
- 字符串函数: CONCAT(), SUBSTRING(), LENGTH()
- 聚合函数: COUNT(), SUM(), AVG(), MAX(), MIN()"""

    section_schema = f"""## 数据库表结构
以下是可以查询的表和字段:

{schema_text}"""

    # v0.4.1.1：RELATIONS 注入（按需 — 仅当 schema_text 中出现的表有登记关联时）
    section_relations = ""
    try:
        import re as _re

        from knot.services.agents import catalog as _cl
        selected = _re.findall(r"^##+\s*([\w.]+)\s*$", schema_text or "", _re.MULTILINE)
        section_relations = _cl.get_relations_for_tables(selected) if hasattr(_cl, "get_relations_for_tables") else ""
    except Exception:
        section_relations = ""

    section_safety = """## 安全规则（必须严格遵守）
- 只允许生成 SELECT 语句
- 严禁生成 INSERT / UPDATE / DELETE / DROP / TRUNCATE / ALTER / CREATE
- 多表查询必须显式 `JOIN ... ON 关联字段`；严禁 `FROM a, b WHERE ...` 旧式写法（隐式笛卡尔积）
- 关联字段优先参考下方「## 表关系 RELATIONS」段；该段未列出明确关联时，
  在 JSON error 字段说明"无法确定 JOIN 条件"，不要瞎猜
- **Fan-Out 防御**：当 SELECT 含 ≥ 2 个聚合（SUM/COUNT/AVG）且 LEFT JOIN ≥ 2 张
  不同明细表时，每个聚合源表必须先用子查询/CTE 按 JOIN 主表的 grain 预聚合再 JOIN，
  否则行数相乘会让聚合结果数倍膨胀（即使 JOIN+ON 看似合规）。
  错误：FROM u LEFT JOIN deposits d ON u.id=d.uid LEFT JOIN deals t ON u.id=t.uid
        SELECT SUM(d.amt), SUM(t.amt) GROUP BY u.id  ❌ 双向膨胀
  正确：LEFT JOIN (SELECT uid, SUM(amt) FROM deposits GROUP BY uid) d
        LEFT JOIN (SELECT uid, SUM(amt) FROM deals    GROUP BY uid) t
- 如果用户的问题无法用已知表结构回答，在 JSON 的 error 字段说明原因"""

    section_format = """## 输出格式（严格遵守）
只输出以下格式的 JSON，不输出任何其他文字、解释或 markdown:
{"sql": "SELECT ...", "explanation": "这条 SQL 查询了...", "confidence": "high 或 medium 或 low", "error": ""}

如果无法生成有效 SQL:
{"sql": "", "explanation": "", "confidence": "low", "error": "原因说明"}"""

    examples_text = get_few_shot_examples(question, max_examples=4)
    if examples_text:
        section_examples = f"## 示例（参考这些模式生成 SQL）\n\n{examples_text}"
    else:
        section_examples = """## 示例
问题: 查看有哪些表
输出: {"sql": "SHOW TABLES", "explanation": "列出当前数据库所有表名", "confidence": "high", "error": ""}

问题: 昨天的订单总金额是多少
输出: {"sql": "SELECT SUM(pay_amount) AS gmv FROM orders WHERE DATE(created_at) = DATE_SUB(CURDATE(), INTERVAL 1 DAY)", "explanation": "过滤昨天日期，对支付金额求和", "confidence": "medium", "error": ""}"""

    section_confidence = """## 置信度（confidence）含义
- high:   Schema 中明确包含所需表和字段
- medium: 需要推断字段含义，建议执行前确认
- low:    Schema 信息不足，SQL 可能需要修改"""

    section_ordering = """## 排序规则
- 当查询结果包含日期/时间列时，必须加 ORDER BY 该列 ASC，确保时序排列
- 当结果用于趋势分析时，按时间升序排列"""

    sections = [section_role, section_db, section_schema]
    if section_relations:
        sections.append(section_relations)
    if business_context.strip():
        sections.append(f"## 业务术语与表关系（优先参考）\n{business_context.strip()}")
    sections += [section_safety, section_ordering, section_format, section_examples, section_confidence]
    return "\n\n".join(sections)
