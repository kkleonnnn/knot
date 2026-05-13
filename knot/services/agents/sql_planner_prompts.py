"""knot/services/agents/sql_planner_prompts.py — v0.5.2 起从 sql_planner.py 抽出。

源行号区间（v0.5.1 final 状态）：
- L21-22  `_business_rules`
- L25-44  `_relations_for_schema`
- L80-154 `_AGENT_SYSTEM_TEMPLATE`

R-106 单向依赖：本模块仅依赖 stdlib + knot.services.agents.catalog（同层叶子）；
严禁反向 import sql_planner.py / sql_planner_tools.py / sql_planner_llm.py。

v0.6.0 F2.5：`_AGENT_SYSTEM_TEMPLATE` 默认值从 `knot/prompts/sql_planner.md` lazy load。
fail-soft：.md 缺失返空字符串（prompt_service.get_prompt 走 DB 兜底；R-PA-2.2）。
"""
import pathlib
import re

try:
    from knot.services.agents import catalog as _cl
except Exception:
    _cl = None


_PROMPT_DIR = pathlib.Path(__file__).resolve().parents[2] / "prompts"


def _load_default_prompt(name: str) -> str:
    """v0.6.0 F2.5：读 knot/prompts/{name}.md 作为默认 system prompt。
    缺失或异常 → 空字符串（fail-soft；上层 prompt_service 走 DB 兜底）。"""
    try:
        return (_PROMPT_DIR / f"{name}.md").read_text(encoding="utf-8").rstrip("\n")
    except OSError:
        return ""


def _business_rules() -> str:
    return getattr(_cl, "BUSINESS_RULES", "") if _cl else ""


def _relations_for_schema(schema_text: str) -> str:
    """v0.4.1.1：从 schema_text 解析出 selected 表全名，调 catalog.get_relations_for_tables
    按需渲染 RELATIONS 段（仅相关表的关联），避免 token 预算挤压（R-S4）。

    schema_text 格式约定（与 schema_filter / db_connector.get_schema 输出一致）：
      ## demo_dwd.dwd_user_reg
      - created_at ...
      ## demo_dwd.dwd_order
      ...
    """
    if not _cl:
        return ""
    try:
        get_rels = getattr(_cl, "get_relations_for_tables", None)
        if not callable(get_rels):
            return ""
    except Exception:
        return ""
    selected = re.findall(r"^##+\s*([\w.]+)\s*$", schema_text or "", re.MULTILINE)
    return get_rels(selected)


_AGENT_SYSTEM_TEMPLATE = _load_default_prompt("sql_planner")
