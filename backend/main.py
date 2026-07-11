"""DevVault FastAPI application: ingestion, retrieval, Q&A, summaries, flashcards."""
from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
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


# --------------------------------------------------------------------------- #
# Ingestion helpers
# --------------------------------------------------------------------------- #
def _ingest(title: str, source_type: str, url: str | None, text: str) -> dict:
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

    # Analysis (summary + tags) is best-effort: retrieval still works without a key.
    summary, tags = "", []
    try:
        analysis = llm.analyze_document(text, title)
        summary, tags = analysis["summary"], analysis["tags"]
    except llm.LLMNotConfigured:
        summary = "_Add an ANTHROPIC_API_KEY to auto-generate a summary._"
    except Exception as exc:  # don't let a model hiccup lose the ingested source
        summary = f"_Summary unavailable: {exc}_"

    return db.add_source(
        id=source_id,
        title=title,
        source_type=source_type,
        url=url,
        summary=summary,
        tags=tags,
        content=text,
        chunk_count=len(chunks),
    )


# --------------------------------------------------------------------------- #
# API — health & sources
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
def list_sources() -> dict:
    return {"sources": db.list_sources()}


@app.get("/api/sources/{source_id}")
def get_source(source_id: str) -> dict:
    source = db.get_source(source_id)
    if not source:
        raise HTTPException(404, "Source not found.")
    return source


@app.delete("/api/sources/{source_id}")
def delete_source(source_id: str) -> dict:
    if not db.get_source(source_id):
        raise HTTPException(404, "Source not found.")
    vectorstore.delete_source(source_id)
    db.delete_source(source_id)
    return {"deleted": source_id}


# --------------------------------------------------------------------------- #
# API — ingestion
# --------------------------------------------------------------------------- #
@app.post("/api/ingest/pdf")
async def ingest_pdf(file: UploadFile = File(...)) -> dict:
    data = await file.read()
    if not data:
        raise HTTPException(400, "Empty file.")
    try:
        text = ingest.load_pdf(data)
    except Exception as exc:
        raise HTTPException(400, f"Failed to read PDF: {exc}")
    title = (file.filename or "Untitled PDF").rsplit(".", 1)[0]
    return _ingest(title, "pdf", None, text)


@app.post("/api/ingest/web")
def ingest_web(body: UrlIn) -> dict:
    try:
        title, text = ingest.load_web(body.url)
    except Exception as exc:
        raise HTTPException(400, f"Failed to load page: {exc}")
    return _ingest(title, "web", body.url, text)


@app.post("/api/ingest/note")
def ingest_note(body: NoteIn) -> dict:
    return _ingest(body.title.strip(), "note", None, body.text)


# --------------------------------------------------------------------------- #
# API — Q&A and study tools
# --------------------------------------------------------------------------- #
@app.post("/api/ask")
def ask(body: AskIn) -> dict:
    retrieved = vectorstore.query(body.question, settings.TOP_K, body.source_ids)
    try:
        return llm.answer_question(body.question, retrieved)
    except llm.LLMNotConfigured as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        raise HTTPException(502, f"Model call failed: {exc}")


@app.post("/api/sources/{source_id}/flashcards")
def flashcards(source_id: str, body: FlashcardsIn) -> dict:
    source = db.get_source(source_id, include_content=True)
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
def quiz(source_id: str, body: FlashcardsIn) -> dict:
    source = db.get_source(source_id, include_content=True)
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
def resummarize(source_id: str) -> dict:
    source = db.get_source(source_id, include_content=True)
    if not source:
        raise HTTPException(404, "Source not found.")
    try:
        analysis = llm.analyze_document(source["content"], source["title"])
    except llm.LLMNotConfigured as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        raise HTTPException(502, f"Model call failed: {exc}")
    db.update_analysis(source_id, analysis["summary"], analysis["tags"])
    return db.get_source(source_id)


# --------------------------------------------------------------------------- #
# Frontend (served last so /api/* wins)
# --------------------------------------------------------------------------- #
if FRONTEND_DIR.exists():

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(FRONTEND_DIR / "index.html")

    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="static")
