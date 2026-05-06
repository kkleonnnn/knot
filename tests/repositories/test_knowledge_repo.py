"""knowledge_repo happy-path 单测。"""
from bi_agent.repositories import knowledge_repo


def test_create_list_doc(tmp_db_path):
    did = knowledge_repo.create_knowledge_doc("name", "f.md", chunk_count=3)
    docs = knowledge_repo.list_knowledge_docs()
    assert len(docs) == 1
    assert docs[0]["id"] == did
    assert docs[0]["chunk_count"] == 3


def test_save_chunks_and_list(tmp_db_path):
    did = knowledge_repo.create_knowledge_doc("n", "f", chunk_count=2)
    knowledge_repo.save_doc_chunks(did, ["chunk1", "chunk2"], [None, b"\x00\x01"])
    chunks = knowledge_repo.list_doc_chunks()
    assert len(chunks) == 2
    assert {c["chunk_text"] for c in chunks} == {"chunk1", "chunk2"}


def test_delete_doc_cascades_chunks(tmp_db_path):
    did = knowledge_repo.create_knowledge_doc("n", "f", chunk_count=1)
    knowledge_repo.save_doc_chunks(did, ["c"], [None])
    knowledge_repo.delete_knowledge_doc(did)
    assert knowledge_repo.list_knowledge_docs() == []
    assert knowledge_repo.list_doc_chunks() == []
