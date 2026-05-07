"""知识库领域模型（PDF/MD/TXT 文档 → 向量检索）。

代表的真实实体：
  - KnowledgeDoc ：admin 上传的一份业务文档（操作手册/字典/SOP）
  - DocChunk     ：文档被切成的一个片段 + 它的 embedding 向量

services/rag_service 用 cosine 相似度从全部 chunks 检索 top_k 注入 prompt。
embedding_blob 为 None 时降级走 BM25 关键词检索（rag_retriever）。

Go 重写映射：internal/domain/knowledge.go。
"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class KnowledgeDoc:
    """一份知识库文档元数据。chunk_count 是上传时切片产生的总块数。"""
    id: int
    name: str
    filename: str
    chunk_count: int = 0
    created_at: Optional[str] = None


@dataclass
class DocChunk:
    """文档切片 + 向量。

    embedding_blob 是 OpenAI text-embedding-3-small 的 1536 维 float32 数组
    pickle 后的 bytes；上传时若 embedding API 调用失败则为 None。
    """
    chunk_text: str
    embedding_blob: Optional[bytes] = None
    doc_id: Optional[int] = None
