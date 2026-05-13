"""
prompts.py — 4 个 agent 的 system prompt 加载器
admin 在 DB（prompt_templates）维护，不存在时回退到硬编码 default。
渲染采用「安全替换」：只替换显式传入的 key，其它 `{...}` 字面保留，避免 KeyError。

v0.6.0 F2.8 — `seed_defaults_from_files()` 启动期幂等 seed：
  3-Agent system prompt 默认文本从 `knot/prompts/*.md` 注入 DB；
  仅 DB 行不存在时 INSERT，已有则跳过（不覆盖 admin 已编辑的 DB 值）。
"""

import pathlib
import re

_PROMPT_DIR = pathlib.Path(__file__).resolve().parents[1] / "prompts"

# v0.6.0 F2.8 — 3 agents 与 knot/prompts/*.md 文件映射
_DEFAULT_PROMPT_AGENTS = ("sql_planner", "clarifier", "presenter")


def _safe_format(template: str, mapping: dict) -> str:
    """只替换 mapping 中存在的占位符；未知占位符原样保留。"""
    def repl(m):
        key = m.group(1)
        if key in mapping:
            return str(mapping[key])
        return m.group(0)
    return re.sub(r"\{(\w+)\}", repl, template)


def get_prompt(agent_name: str, default: str, mapping: dict = None) -> str:
    """读 DB；DB 为空回退 default。再用 mapping 做安全格式化。

    DB content 内可包含 `{__default__}` 占位符 → 在该位置嵌入内置 default
    （便于 admin 在默认基础上"追加"业务约束而不必抄全文）。
    """
    content = ""
    try:
        from knot.repositories.prompt_repo import get_prompt_template
        content = get_prompt_template(agent_name) or ""
    except Exception:
        content = ""
    if content.strip():
        template = content.replace("{__default__}", default)
    else:
        template = default
    if mapping:
        return _safe_format(template, mapping)
    return template


def seed_defaults_from_files() -> dict:
    """v0.6.0 F2.8 — 启动期幂等 seed：3-Agent system prompt 默认值从 .md 文件注入 DB。

    幂等规则（R-PA-2.3）：
      - DB 行不存在（agent_name 未在 prompt_templates 表）→ INSERT .md 内容
      - DB 行已存在（admin 已编辑或前次 seed）→ **跳过**，不覆盖
      - .md 文件缺失 → 跳过该 agent（fail-soft）

    返回 dict — {agent_name: "seeded" / "skipped" / "no_file"}，用于 main.py 日志。
    """
    result: dict[str, str] = {}
    try:
        from knot.repositories.prompt_repo import (
            get_prompt_template,
            set_prompt_template,
        )
    except Exception:
        return {a: "skipped" for a in _DEFAULT_PROMPT_AGENTS}

    for agent in _DEFAULT_PROMPT_AGENTS:
        # 已有 DB 行 → 跳过（不覆盖 admin 编辑）
        existing = ""
        try:
            existing = get_prompt_template(agent) or ""
        except Exception:
            existing = ""
        if existing.strip():
            result[agent] = "skipped"
            continue

        # 读 .md 文件
        md_path = _PROMPT_DIR / f"{agent}.md"
        try:
            content = md_path.read_text(encoding="utf-8").rstrip("\n")
        except OSError:
            result[agent] = "no_file"
            continue
        if not content.strip():
            result[agent] = "no_file"
            continue

        # INSERT 默认值（updated_by=None 表示 system seed，非人工编辑）
        try:
            set_prompt_template(agent, content, updated_by=None)
            result[agent] = "seeded"
        except Exception:
            result[agent] = "skipped"
    return result
