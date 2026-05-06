"""
schema_filter.py — Schema 精准过滤（v0.2.3 改造）

从全量 Schema 中过滤出与问题最相关的表，减少 Prompt token 用量。
v0.2.3 改造点：
  - 引入 ohx_catalog.LEXICON：业务词命中 → 指定表得高分（同时支持 db.tbl 全名 / 仅 tbl 名匹配）
  - 引入 ohx_catalog.TABLES.topics：表元数据中的主题与问题词重合 → 加分
  - 关键词命中的"指向表"作为兜底强制入选（min_floor），即便 BM25 重合度低也保留
  - max_tables 提到 12（兼顾 token 预算），仍可由调用方覆盖

兼容：未在 catalog 中的表（其它项目复用）走原 BM25 / 字面命中算法，不会被淘汰；
catalog 命中只是"加分项"，不是"白名单"。
"""

import re

from bi_agent.services.rag_retriever import _tokenize

try:
    from bi_agent.services.knot import catalog as _cl
except Exception:
    _cl = None


def _lex():
    return getattr(_cl, "LEXICON", {}) if _cl else {}


def _ohx_tables():
    return getattr(_cl, "TABLES", []) if _cl else []


def _ohx_lookup():
    """每次调用重建（轻量），admin 改后立即生效。"""
    return {f"{t['db']}.{t['table']}": t for t in _ohx_tables()}


def _ohx_by_basename():
    return {t['table']: t for t in _ohx_tables()}


def parse_schema_tables(schema_text: str) -> list[tuple[str, str]]:
    """切分 schema 文本为 [(table_name, table_md_block), ...]。
    table_name 可能带 db.tbl 前缀或纯表名（取决于 db_connector.get_schema 输出）。
    """
    tables: list[tuple[str, str]] = []
    parts = re.split(r'\n(?=### )', schema_text)
    for part in parts:
        part = part.strip()
        if not part:
            continue
        lines = part.split('\n')
        first = lines[0].strip()
        if first.startswith('### '):
            table_name = first[4:].strip()
            tables.append((table_name, part))
    return tables


_METADATA_PATTERNS = [
    r"有哪些表", r"多少张表", r"表结构", r"字段列表",
    r"show\s+tables", r"information.schema",
]


def _is_metadata_query(question: str) -> bool:
    q_lower = question.lower()
    return any(re.search(p, q_lower) for p in _METADATA_PATTERNS)


def _basename(name: str) -> str:
    """db.tbl → tbl；纯表名原样返回。"""
    if "." in name:
        return name.split(".", 1)[1]
    return name


def _catalog_targets(question: str) -> dict:
    """扫问题文本，返回 {table_full_name: priority_score} —— 词典命中带来的"目标表"加分。
    同一个词典 entry 的多张表按位置递减：第 0 张 +12，第 1 张 +8，第 2+ 张 +5。
    多个词命中累加。
    """
    targets: dict = {}
    lex = _lex()
    if not lex:
        return targets
    q = question
    q_lower = question.lower()
    for term, table_list in lex.items():
        if (re.search(r"[\u4e00-\u9fff]", term) and term in q) or term.lower() in q_lower:
            for i, full in enumerate(table_list):
                bonus = 12 if i == 0 else (8 if i == 1 else 5)
                targets[full] = max(targets.get(full, 0), bonus)
    return targets


def _topic_overlap(table_full_or_base: str, question: str) -> float:
    """表 catalog 中的 topics 与问题片段的重合 → 每命中 +3。"""
    meta = _ohx_lookup().get(table_full_or_base) or _ohx_by_basename().get(_basename(table_full_or_base))
    if not meta:
        return 0.0
    score = 0.0
    for topic in meta.get("topics", []):
        if topic in question:
            score += 3.0
    return score


def score_table_for_question(table_name: str, table_md: str, question: str, targets: dict = None) -> float:
    targets = targets or {}
    q_lower = question.lower()
    table_lower = table_name.lower()
    base = _basename(table_name)
    score = 0.0

    if table_lower in q_lower or base.lower() in q_lower:
        score += 10.0

    q_tokens = set(_tokenize(question))
    t_tokens = set(_tokenize(table_md))
    overlap = len(q_tokens & t_tokens)
    score += overlap * 1.5

    # 词典加分：精确 db.tbl 优先，否则 basename 兜底
    if table_name in targets:
        score += targets[table_name]
    else:
        for full, bonus in targets.items():
            if _basename(full) == base:
                score += bonus
                break

    # 主题重合
    score += _topic_overlap(table_name, question)

    return score


def filter_schema_for_question(schema_text: str, question: str, max_tables: int = 12) -> str:
    """主入口。返回过滤后的 schema 字符串。
    - 元数据问题（"有哪些表"）→ 只列表名
    - 否则按上述算法评分排序，取 top max_tables
    - 词典命中的高优先级表（priority >= 12）即便排名靠后也强制纳入
    """
    tables = parse_schema_tables(schema_text)

    if len(tables) <= max_tables:
        return schema_text

    if _is_metadata_query(question):
        names = [name for name, _ in tables]
        return "### 所有表名\n" + "\n".join(f"- {n}" for n in names)

    targets = _catalog_targets(question)

    scored = [
        (name, md, score_table_for_question(name, md, question, targets))
        for name, md in tables
    ]
    scored.sort(key=lambda x: x[2], reverse=True)
    selected = scored[:max_tables]

    selected_names = {n for n, _, _ in selected}
    forced = []
    for full, prio in targets.items():
        if prio < 12 or full in selected_names:
            continue
        if any((n == full or _basename(n) == _basename(full)) for n, _ in tables):
            forced.append(full)

    if forced:
        name2md = {n: md for n, md in tables}
        for full in forced:
            match = None
            if full in name2md:
                match = (full, name2md[full])
            else:
                base = _basename(full)
                for n, md in tables:
                    if _basename(n) == base:
                        match = (n, md)
                        break
            if match is None:
                continue
            selected.sort(key=lambda x: x[2])
            selected[0] = (match[0], match[1], 99.0)
            selected.sort(key=lambda x: x[2], reverse=True)

    note = (
        f"\n> 共 {len(tables)} 张表，已按问题相关性过滤至 {len(selected)} 张"
        f"{'（含词典强制纳入）' if forced else ''}\n"
    )
    return note + "\n\n".join(md for _, md, _ in selected)
