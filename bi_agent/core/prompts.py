"""
prompts.py — 4 个 agent 的 system prompt 加载器
admin 在 DB（prompt_templates）维护，不存在时回退到硬编码 default。
渲染采用「安全替换」：只替换显式传入的 key，其它 `{...}` 字面保留，避免 KeyError。
"""

import re


def _safe_format(template: str, mapping: dict) -> str:
    """只替换 mapping 中存在的占位符；未知占位符原样保留。"""
    def repl(m):
        key = m.group(1)
        if key in mapping:
            return str(mapping[key])
        return m.group(0)
    return re.sub(r"\{(\w+)\}", repl, template)


def get_prompt(agent_name: str, default: str, mapping: dict = None) -> str:
    """读 DB；DB 为空回退 default。再用 mapping 做安全格式化。"""
    content = ""
    try:
        import persistence
        content = persistence.get_prompt_template(agent_name) or ""
    except Exception:
        content = ""
    template = content if content.strip() else default
    if mapping:
        return _safe_format(template, mapping)
    return template
