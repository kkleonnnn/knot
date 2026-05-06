"""知识库领域模型。"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class KnowledgeDoc:
    id: int
    name: str
    filename: str
    chunk_count: int = 0
    created_at: Optional[str] = None


@dataclass
class DocChunk:
    chunk_text: str
    embedding_blob: Optional[bytes] = None
    doc_id: Optional[int] = None
