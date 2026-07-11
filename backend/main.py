"""DevVault FastAPI app: ingestion, retrieval, Q&A, summaries, flashcards, quiz.

Sources are scoped to an owner — an anonymous per-device id sent in the
`X-Vault-Id` header — so files ingested on one device are private and not shown
to others. Seeded sample sources use owner "public" and are visible to everyone.
"""
from __future__ import annotations

import re
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import db, ingest, llm, seed, vectorstore
from .chunking import chunk_text
from .config import settings
from .models import AskIn, FlashcardsIn, NoteIn, UrlIn

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    seed.seed_if_empty_async()  # populate a fresh/empty vault in the background
    yield


app = FastAPI(title="DevVault", version="0.1.0", lifespan=lifespan)


def vault_id(x_vault_id: str | None = Header(default=None)) -> str:
    """Per-device privacy scope. Falls back to the shared 'public' vault."""
    v = (x_vault_id or "public").strip()
    return v if re.fullmatch(r"[A-Za-z0-9_-]{1,64}", v) else "public"


# --------------------------------------------------------------------------- #
# Ingestion helper
# --------------------------------------------------------------------------- #
def _ingest(owner: str, title: str, source_type: str, url: str | None, text: str) -> dict:
    text = (text or "").strip()
    if not text:
        raise HTTPException(
            400,
            "No extractable text was found. If this is a scanned or image-only PDF, "
            "it has no selectable text to index (OCR isn't supported yet).",
        )
    chunks = chunk_text(text, settings.CHUNK_SIZE, settings.CHUNK_OVERLAP)
    if not chunks:
        raise HTTPException(400, "This source produced no indexable content.")

    source_id = uuid.uuid4().hex[:12]
    vectorstore.add_chunks(source_id, title, source_type, url, chunks)

    summary, tags = "", []
    try:
        analysis = llm.analyze_document(text, title)
        summary, tags = analysis["summary"], analysis["tags"]
    except llm.LLMNotConfigured:
        summary = "_Add an LLM key to auto-generate a summary._"
    except Exception as exc:
        summary = f"_Summary unavailable: {exc}_"

    return db.add_source(
        id=source_id,
        owner=owner,
        title=title,
        source_type=source_type,
        url=url,
        summary=summary,
        tags=tags,
        content=text,
        chunk_count=len(chunks),
    )


# --------------------------------------------------------------------------- #
# Health & sources
# --------------------------------------------------------------------------- #
@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "provider": settings.provider(),
        "model": settings.active_model(),
        "has_key": settings.has_llm(),
        "source_count": db.count_sources(),
    }


@app.get("/api/sources")
def list_sources(owner: str = Depends(vault_id)) -> dict:
    return {"sources": db.list_sources(owner)}


@app.get("/api/sources/{source_id}")
def get_source(source_id: str, owner: str = Depends(vault_id)) -> dict:
    source = db.get_source(source_id, owner)
    if not source:
        raise HTTPException(404, "Source not found.")
    return source


@app.delete("/api/sources/{source_id}")
def delete_source(source_id: str, owner: str = Depends(vault_id)) -> dict:
    if not db.delete_source(source_id, owner):
        raise HTTPException(404, "Source not found, or it's a shared sample you can't delete.")
    vectorstore.delete_source(source_id)
    return {"deleted": source_id}


# --------------------------------------------------------------------------- #
# Ingestion
# --------------------------------------------------------------------------- #
@app.post("/api/ingest/pdf")
async def ingest_pdf(file: UploadFile = File(...), owner: str = Depends(vault_id)) -> dict:
    data = await file.read()
    if not data:
        raise HTTPException(400, "Empty file.")
    try:
        text = ingest.load_pdf(data)
    except Exception as exc:
        raise HTTPException(400, f"Failed to read PDF: {exc}")
    title = (file.filename or "Untitled PDF").rsplit(".", 1)[0]
    return _ingest(owner, title, "pdf", None, text)


@app.post("/api/ingest/web")
def ingest_web(body: UrlIn, owner: str = Depends(vault_id)) -> dict:
    try:
        title, text = ingest.load_web(body.url)
    except Exception as exc:
        raise HTTPException(400, f"Failed to load page: {exc}")
    return _ingest(owner, title, "web", body.url, text)


@app.post("/api/ingest/note")
def ingest_note(body: NoteIn, owner: str = Depends(vault_id)) -> dict:
    return _ingest(owner, body.title.strip(), "note", None, body.text)


# --------------------------------------------------------------------------- #
# Q&A and study tools
# --------------------------------------------------------------------------- #
@app.post("/api/ask")
def ask(body: AskIn, owner: str = Depends(vault_id)) -> dict:
    allowed = set(db.list_source_ids(owner))
    if body.source_ids:
        ids = [i for i in body.source_ids if i in allowed]
    else:
        ids = list(allowed)
    retrieved = vectorstore.query(body.question, settings.TOP_K, ids) if ids else []
    try:
        return llm.answer_question(body.question, retrieved)
    except llm.LLMNotConfigured as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        raise HTTPException(502, f"Model call failed: {exc}")


@app.post("/api/sources/{source_id}/flashcards")
def flashcards(source_id: str, body: FlashcardsIn, owner: str = Depends(vault_id)) -> dict:
    source = db.get_source(source_id, owner, include_content=True)
    if not source:
        raise HTTPException(404, "Source not found.")
    try:
        cards = llm.make_flashcards(source["content"], source["title"], body.count)
    except llm.LLMNotConfigured as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        raise HTTPException(502, f"Model call failed: {exc}")
    return {"flashcards": cards}


@app.post("/api/sources/{source_id}/quiz")
def quiz(source_id: str, body: FlashcardsIn, owner: str = Depends(vault_id)) -> dict:
    source = db.get_source(source_id, owner, include_content=True)
    if not source:
        raise HTTPException(404, "Source not found.")
    try:
        questions = llm.make_quiz(source["content"], source["title"], body.count)
    except llm.LLMNotConfigured as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        raise HTTPException(502, f"Model call failed: {exc}")
    return {"questions": questions}


@app.post("/api/sources/{source_id}/resummarize")
def resummarize(source_id: str, owner: str = Depends(vault_id)) -> dict:
    source = db.get_source(source_id, owner, include_content=True)
    if not source:
        raise HTTPException(404, "Source not found.")
    try:
        analysis = llm.analyze_document(source["content"], source["title"])
    except llm.LLMNotConfigured as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        raise HTTPException(502, f"Model call failed: {exc}")
    db.update_analysis(source_id, analysis["summary"], analysis["tags"])
    return db.get_source(source_id, owner)


# --------------------------------------------------------------------------- #
# Frontend (served last so /api/* wins)
# --------------------------------------------------------------------------- #
if FRONTEND_DIR.exists():

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(FRONTEND_DIR / "index.html")

    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="static")
