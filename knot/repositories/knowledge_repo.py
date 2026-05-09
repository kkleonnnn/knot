"""knowledge_repo — knowledge_docs + doc_chunks。"""
from __future__ import annotations

from knot.repositories.base import get_conn


def create_knowledge_doc(name: str, filename: str, chunk_count: int) -> int:
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO knowledge_docs (name, filename, chunk_count) VALUES (?,?,?)",
        (name, filename, chunk_count),
    )
    doc_id = cur.lastrowid
    conn.commit()
    conn.close()
    return doc_id


def list_knowledge_docs() -> list:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM knowledge_docs ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_knowledge_doc(doc_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM doc_chunks WHERE doc_id=?", (doc_id,))
    conn.execute("DELETE FROM knowledge_docs WHERE id=?", (doc_id,))
    conn.commit()
    conn.close()


def save_doc_chunks(doc_id: int, chunks: list, embeddings: list):
    """embeddings[i] 为 bytes blob 或 None。"""
    conn = get_conn()
    conn.executemany(
        "INSERT INTO doc_chunks (doc_id, chunk_text, embedding_blob) VALUES (?,?,?)",
        [(doc_id, chunks[i], embeddings[i]) for i in range(len(chunks))],
    )
    conn.commit()
    conn.close()


def list_doc_chunks() -> list:
    conn = get_conn()
    rows = conn.execute("SELECT chunk_text, embedding_blob FROM doc_chunks").fetchall()
    conn.close()
    return [dict(r) for r in rows]
