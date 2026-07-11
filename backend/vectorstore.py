"""ChromaDB wrapper — local, persistent vector store with built-in embeddings.

Chroma's default embedding function (all-MiniLM-L6-v2, ONNX) runs locally, so
ingestion and semantic search work with no external API key. Only the Claude
calls (Q&A, summaries, flashcards) require ANTHROPIC_API_KEY.
"""
from __future__ import annotations

import chromadb

from .config import settings

_collection = None


def get_collection():
    global _collection
    if _collection is None:
        client = chromadb.PersistentClient(path=settings.CHROMA_DIR)
        _collection = client.get_or_create_collection(
            name=settings.COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )
    return _collection


def add_chunks(
    source_id: str,
    title: str,
    source_type: str,
    url: str | None,
    chunks: list[str],
) -> None:
    col = get_collection()
    ids = [f"{source_id}:{i}" for i in range(len(chunks))]
    metadatas = [
        {
            "source_id": source_id,
            "title": title,
            "source_type": source_type,
            "url": url or "",
            "chunk_index": i,
        }
        for i in range(len(chunks))
    ]
    col.add(ids=ids, documents=chunks, metadatas=metadatas)


def query(
    text: str, top_k: int, source_ids: list[str] | None = None
) -> list[dict]:
    """Return the top_k most semantically similar chunks, optionally filtered
    to a subset of sources."""
    col = get_collection()
    kwargs: dict = {"query_texts": [text], "n_results": top_k}
    if source_ids:
        kwargs["where"] = {"source_id": {"$in": source_ids}}

    res = col.query(**kwargs)
    docs = (res.get("documents") or [[]])[0]
    metas = (res.get("metadatas") or [[]])[0]
    dists = (res.get("distances") or [[]])[0]

    out: list[dict] = []
    for doc, meta, dist in zip(docs, metas, dists):
        item = {"text": doc, "distance": dist}
        item.update(meta or {})
        out.append(item)
    return out


def delete_source(source_id: str) -> None:
    get_collection().delete(where={"source_id": source_id})


def count() -> int:
    return get_collection().count()
