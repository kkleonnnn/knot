"""
schema_filter.py — Schema 精准过滤
从全量 Schema 中过滤出与问题最相关的表，减少 Prompt token 用量。
"""

import re
from typing import List, Tuple

from rag_retriever import _tokenize


def parse_schema_tables(schema_text: str) -> List[Tuple[str, str]]:
    tables: List[Tuple[str, str]] = []
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


_KEYWORD_TABLE_HINTS: dict = {
    "订单":   ["order", "trade", "transaction", "purchase"],
    "用户":   ["user", "member", "customer", "account"],
    "商品":   ["product", "goods", "item", "sku", "spu", "catalog"],
    "支付":   ["pay", "payment", "charge", "billing"],
    "渠道":   ["channel", "source", "campaign", "medium"],
    "gmv":    ["order", "trade", "pay", "transaction"],
    "活跃":   ["active", "login", "session", "event", "log"],
    "新增":   ["user", "register", "signup", "new"],
    "留存":   ["retention", "user", "active"],
    "物流":   ["shipping", "delivery", "logistics", "waybill"],
    "退款":   ["refund", "return", "reverse"],
    "优惠券": ["coupon", "discount", "promo", "voucher"],
}

_METADATA_PATTERNS = [
    r"有哪些表", r"多少张表", r"表结构", r"字段列表",
    r"show\s+tables", r"information.schema",
]


def _is_metadata_query(question: str) -> bool:
    q_lower = question.lower()
    return any(re.search(p, q_lower) for p in _METADATA_PATTERNS)


def score_table_for_question(table_name: str, table_md: str, question: str) -> float:
    q_lower = question.lower()
    table_lower = table_name.lower()
    score = 0.0

    if table_lower in q_lower:
        score += 10.0

    q_tokens = set(_tokenize(question))
    t_tokens = set(_tokenize(table_md))
    overlap = len(q_tokens & t_tokens)
    score += overlap * 1.5

    for keyword, hints in _KEYWORD_TABLE_HINTS.items():
        if keyword in q_lower:
            for hint in hints:
                if hint in table_lower:
                    score += 5.0
                    break

    return score


def filter_schema_for_question(schema_text: str, question: str, max_tables: int = 10) -> str:
    tables = parse_schema_tables(schema_text)

    if len(tables) <= max_tables:
        return schema_text

    if _is_metadata_query(question):
        names = [name for name, _ in tables]
        return "### 所有表名\n" + "\n".join(f"- {n}" for n in names)

    scored = [
        (name, md, score_table_for_question(name, md, question))
        for name, md in tables
    ]
    scored.sort(key=lambda x: x[2], reverse=True)
    selected = scored[:max_tables]
    note = f"\n> 共 {len(tables)} 张表，已按问题相关性过滤至 {len(selected)} 张\n"
    return note + "\n\n".join(md for _, md, _ in selected)
