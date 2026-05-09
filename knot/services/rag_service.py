"""
doc_rag.py — 文档知识库 RAG（解析 / 分块 / embedding / 检索）

embedding 使用 OpenAI text-embedding-3-small（兼容 OpenRouter）；
无可用 API Key 时自动降级为关键词匹配（BM25-like）。
"""

import json
import re

import openai

from knot.config import PROVIDER_API_KEYS, PROVIDER_BASE_URLS

EMBED_MODEL   = "text-embedding-3-small"
CHUNK_SIZE    = 400   # chars
CHUNK_OVERLAP = 80


# ── Embedding ──────────────────────────────────────────────────────────

def embed_text(text: str, api_key: str = "", openrouter_api_key: str = "", embedding_api_key: str = "") -> list:
    """返回 embedding 向量（float list）；失败返回空列表。"""
    # 优先专用 embedding key，其次系统 OpenAI key，最后 OpenRouter
    openai_key = embedding_api_key or PROVIDER_API_KEYS.get("openai", "")
    or_key     = openrouter_api_key or PROVIDER_API_KEYS.get("openrouter", "")

    if openai_key:
        base_url = PROVIDER_BASE_URLS.get("openai") or None
        use_key  = openai_key
    elif or_key:
        base_url = "https://openrouter.ai/api/v1"
        use_key  = or_key
    else:
        return []

    try:
        client = openai.OpenAI(api_key=use_key, base_url=base_url)
        resp   = client.embeddings.create(model=EMBED_MODEL, input=text[:8000])
        return resp.data[0].embedding
    except Exception:
        return []


def emb_to_blob(vec: list) -> bytes:
    return json.dumps(vec).encode("utf-8")


def blob_to_emb(blob: bytes) -> list:
    return json.loads(blob)


def cosine_sim(a: list, b: list) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na  = sum(x * x for x in a) ** 0.5
    nb  = sum(x * x for x in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


# ── Text parsing ───────────────────────────────────────────────────────

def parse_document(file_bytes: bytes, filename: str) -> str:
    """从 PDF / Markdown / TXT 提取纯文本。"""
    fname = filename.lower()
    if fname.endswith(".pdf"):
        try:
            import io

            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(file_bytes))
            pages  = [p.extract_text() or "" for p in reader.pages]
            text   = "\n\n".join(t for t in pages if t.strip())
            if not text.strip():
                raise ValueError("PDF 未能提取到文字（可能是扫描件）")
            return text
        except ImportError:
            raise ValueError("缺少 pypdf 依赖，请运行: pip install pypdf")
        except ValueError:
            raise
        except Exception as e:
            raise ValueError(f"PDF 解析失败: {str(e)[:200]}")
    elif fname.endswith((".md", ".markdown", ".txt")):
        for enc in ("utf-8-sig", "utf-8", "gbk", "gb2312"):
            try:
                return file_bytes.decode(enc)
            except UnicodeDecodeError:
                continue
        raise ValueError("文件编码无法识别，请保存为 UTF-8")
    else:
        raise ValueError("仅支持 PDF、Markdown 和 TXT 文件")


# ── Chunking ───────────────────────────────────────────────────────────

def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list:
    """把长文本切成有重叠的块，优先在段落边界断开。"""
    text   = re.sub(r"\n{3,}", "\n\n", text.strip())
    paras  = text.split("\n\n")
    chunks = []
    buf    = ""

    for para in paras:
        para = para.strip()
        if not para:
            continue
        if len(buf) + len(para) + 2 <= chunk_size:
            buf = (buf + "\n\n" + para).strip()
        else:
            if buf:
                chunks.append(buf)
            # 若单段超长，按字符强切
            if len(para) > chunk_size:
                start = 0
                while start < len(para):
                    chunks.append(para[start: start + chunk_size])
                    start += chunk_size - overlap
                buf = ""
            else:
                buf = para

    if buf:
        chunks.append(buf)

    return [c for c in chunks if c.strip()]


# ── Search ─────────────────────────────────────────────────────────────

def search_docs(
    query: str,
    top_k: int = 3,
    api_key: str = "",
    openrouter_api_key: str = "",
    embedding_api_key: str = "",
    sim_threshold: float = 0.25,
) -> list:
    """
    检索知识库，返回最相关的 top_k 段文本。
    有 embedding key → 向量检索；无 key → 关键词降级。
    """
    from knot.repositories.knowledge_repo import list_doc_chunks

    chunks = list_doc_chunks()
    if not chunks:
        return []

    q_emb = embed_text(query, api_key, openrouter_api_key, embedding_api_key)

    if q_emb:
        # 向量检索
        scored = []
        for c in chunks:
            if not c.get("embedding_blob"):
                continue
            try:
                emb = blob_to_emb(c["embedding_blob"])
                sim = cosine_sim(q_emb, emb)
                scored.append((sim, c["chunk_text"]))
            except Exception:
                continue
        scored.sort(reverse=True)
        return [t for s, t in scored[:top_k] if s >= sim_threshold]
    else:
        # 关键词降级
        words = [w for w in re.split(r"\s+", query.lower()) if len(w) >= 2]
        scored = []
        for c in chunks:
            ct = c["chunk_text"].lower()
            hit = sum(1 for w in words if w in ct)
            if hit:
                scored.append((hit, c["chunk_text"]))
        scored.sort(reverse=True)
        return [t for _, t in scored[:top_k]]
