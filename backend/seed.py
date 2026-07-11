"""Seed the vault with a few sample sources on first boot, so a fresh or
ephemeral deployment (e.g. a free-tier demo) is never empty for visitors.

Runs once, in a background thread, only when the vault has no sources.
Disable with DEVVAULT_SEED=false.
"""
from __future__ import annotations

import threading
import uuid

from . import db, llm, vectorstore
from .chunking import chunk_text
from .config import settings

_SAMPLES = [
    {
        "title": "What is Retrieval-Augmented Generation (RAG)?",
        "text": (
            "Retrieval-Augmented Generation (RAG) is a technique for making large "
            "language models answer from specific, up-to-date information instead of "
            "only their training data. A RAG system works in two phases. First, "
            "retrieval: the user's question is converted into an embedding (a numeric "
            "vector) and compared against a vector database of previously embedded "
            "document chunks; the most similar chunks are returned. Second, "
            "generation: those retrieved chunks are inserted into the prompt as "
            "context, and the model is instructed to answer using only that context. "
            "This grounds the answer in real sources, dramatically reduces "
            "hallucination, and lets the system cite exactly where each fact came "
            "from. RAG is usually preferred over fine-tuning for knowledge tasks "
            "because it is far cheaper, updates instantly when you add new documents, "
            "and keeps answers traceable to their source. Its quality depends heavily "
            "on retrieval quality: good chunking, strong embeddings, and how many "
            "chunks are retrieved (the top-k value)."
        ),
    },
    {
        "title": "Vector Databases and Embeddings, explained",
        "text": (
            "An embedding is a list of numbers (a vector) that captures the meaning of "
            "a piece of text. Texts with similar meaning have vectors that are close "
            "together, so a search for 'how do I cache results' can match 'storing "
            "computed values' even when they share no words. A vector database stores "
            "these embeddings and performs fast nearest-neighbor search to find the "
            "vectors most similar to a query, typically using cosine similarity and an "
            "index such as HNSW. In a RAG pipeline, documents are split into chunks, "
            "each chunk is embedded and stored, and at query time the question is "
            "embedded and used to retrieve the closest chunks. DevVault uses ChromaDB "
            "with a local MiniLM model, so embedding and search run entirely on-device "
            "with no external API. Popular alternatives include pgvector, Qdrant, "
            "Pinecone, and Weaviate. Choosing chunk size and overlap is a trade-off: "
            "smaller chunks give more precise retrieval, while overlap keeps ideas "
            "from being split across chunk boundaries."
        ),
    },
    {
        "title": "About DevVault",
        "text": (
            "DevVault is a developer's AI second brain. You add sources — PDFs "
            "(including scanned ones, via OCR), web pages, and notes — and DevVault "
            "ingests them, embeds them locally into a vector database, and lets you "
            "ask questions that are answered strictly from your own material, with "
            "citations back to the exact source text. Every source is automatically "
            "summarized and tagged. You can also turn any source into flashcards for "
            "revision, or take an auto-graded multiple-choice quiz to test your "
            "understanding. Under the hood it is built with FastAPI, ChromaDB for "
            "local semantic search, and a pluggable LLM backend (free Groq by default, "
            "or Anthropic Claude). Try it now: ask a question above, or open a source "
            "and click 'Quiz me'."
        ),
    },
]


def _ingest_sample(sample: dict) -> None:
    text = sample["text"].strip()
    chunks = chunk_text(text, settings.CHUNK_SIZE, settings.CHUNK_OVERLAP)
    if not chunks:
        return
    source_id = uuid.uuid4().hex[:12]
    vectorstore.add_chunks(source_id, sample["title"], "note", None, chunks)

    summary, tags = "", []
    try:  # best-effort: retrieval works even if the summary call fails
        analysis = llm.analyze_document(text, sample["title"])
        summary, tags = analysis["summary"], analysis["tags"]
    except Exception:
        pass

    db.add_source(
        id=source_id,
        owner=db.PUBLIC,
        title=sample["title"],
        source_type="note",
        url=None,
        summary=summary,
        tags=tags,
        content=text,
        chunk_count=len(chunks),
    )


def _run() -> None:
    try:
        if db.count_sources(owner=db.PUBLIC) > 0:
            return
        for sample in _SAMPLES:
            try:
                _ingest_sample(sample)
            except Exception:
                pass
    except Exception:
        pass


def seed_if_empty_async() -> None:
    """Kick off seeding in a daemon thread so startup isn't blocked."""
    if not settings.SEED_ON_START:
        return
    threading.Thread(target=_run, name="devvault-seed", daemon=True).start()
