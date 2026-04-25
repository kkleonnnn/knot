from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

import doc_rag
import persistence
from ..dependencies import require_admin

router = APIRouter()


@router.post("/api/knowledge/upload")
async def knowledge_upload(file: UploadFile = File(...), admin=Depends(require_admin)):
    fname = file.filename or "doc"
    ext = Path(fname).suffix.lower()
    if ext not in (".pdf", ".md", ".markdown", ".txt"):
        raise HTTPException(status_code=400, detail="仅支持 PDF、Markdown 和 TXT 文件")

    data = await file.read()
    if len(data) > 30 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="文件不超过 30 MB")

    try:
        text = doc_rag.parse_document(data, fname)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    chunks = doc_rag.chunk_text(text)
    if not chunks:
        raise HTTPException(status_code=400, detail="文件内容为空")

    embedding_api_key = admin.get("embedding_api_key") or ""
    or_key = admin.get("openrouter_api_key") or ""

    embeddings = []
    for chunk in chunks:
        vec = doc_rag.embed_text(chunk, openrouter_api_key=or_key, embedding_api_key=embedding_api_key)
        blob = doc_rag.emb_to_blob(vec) if vec else None
        embeddings.append(blob)

    doc_name = Path(fname).stem
    doc_id = persistence.create_knowledge_doc(doc_name, fname, len(chunks))
    persistence.save_doc_chunks(doc_id, chunks, embeddings)

    embedded = sum(1 for e in embeddings if e)
    return {"id": doc_id, "name": doc_name, "filename": fname,
            "chunk_count": len(chunks), "embedded_count": embedded}


@router.get("/api/knowledge")
async def knowledge_list(admin=Depends(require_admin)):
    return persistence.list_knowledge_docs()


@router.delete("/api/knowledge/{doc_id}")
async def knowledge_delete(doc_id: int, admin=Depends(require_admin)):
    persistence.delete_knowledge_doc(doc_id)
    return {"ok": True}
