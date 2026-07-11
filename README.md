# DevVault — a developer's AI second brain

Ingest the docs, blog posts, YouTube talks, and notes you actually learn from,
then **ask questions and get answers grounded in your own material — with real
citations back to the source.** Built on Retrieval-Augmented Generation (RAG),
a local vector database, and Claude.

> This is the portfolio-grade version of "AI second brain": narrowed to the
> developer use case, with **grounded citations**, **local-first embeddings**,
> and a clean, dependency-light stack that shows off exactly the skills the
> trend is about — RAG, vector DBs, and LLM orchestration.

---

## ✨ What it does

| Feature | How |
| --- | --- |
| **Save anything** | PDFs, YouTube transcripts, web pages, and freeform notes |
| **Ask your vault** | Semantic retrieval + Claude, answered **only** from your sources |
| **Real citations** | Uses the Anthropic Citations API — every answer links to the exact source text it used |
| **Auto summaries** | Each source gets a TL;DR + key bullets on ingest |
| **Auto-organize** | Each source is auto-tagged so your vault stays browsable |
| **Flashcards** | Turn any source into Q&A flashcards for active recall |
| **Scoped search** | Ask across everything, or narrow to a single source |

**Local-first:** embeddings run on your machine (Chroma's bundled MiniLM model),
so ingestion and semantic search need **no API key**. Only the Claude-powered
features (Q&A, summaries, flashcards) use `ANTHROPIC_API_KEY`.

---

## 🏗️ Architecture

```
                        ┌────────────────── Frontend (vanilla JS SPA) ──────────────────┐
                        │  add sources · browse vault · ask · citations · flashcards     │
                        └───────────────────────────────┬───────────────────────────────┘
                                                         │ REST /api/*
┌──────────────────────────────── FastAPI (backend/) ───┴───────────────────────────────┐
│  ingest.py     loaders: pypdf · youtube-transcript-api · httpx+BeautifulSoup           │
│  chunking.py   boundary-aware overlapping chunks                                        │
│  vectorstore.py  ChromaDB (persistent, local MiniLM embeddings)  ── semantic search    │
│  db.py         SQLite registry: titles, summaries, tags, full text                     │
│  llm.py        Claude: grounded Q&A w/ Citations API · summaries · tags · flashcards    │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

**Retrieval → generation flow for a question:**
1. Embed the question locally and pull the top-K chunks from ChromaDB.
2. Pass each chunk to Claude as a `document` content block with citations enabled.
3. Claude answers strictly from those documents; the response carries citation
   spans that map back to the exact source and text.

Tech: **Python · FastAPI · ChromaDB · Anthropic Claude (`claude-opus-4-8`) ·
pypdf · BeautifulSoup**. No build step on the frontend.

---

## 🚀 Quickstart

```bash
# 1. (recommended) create a virtualenv
python -m venv .venv
# Windows:  .venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate

# 2. install
pip install -r requirements.txt

# 3. add an LLM key (Q&A/summaries/flashcards). Ingestion + search work without it.
#    Groq is free (no credit card): https://console.groq.com -> API Keys
cp .env.example .env      # then edit .env: set GROQ_API_KEY (or ANTHROPIC_API_KEY)

# 4. run
python run.py
#   or:  uvicorn backend.main:app --reload
```

Open **http://127.0.0.1:8000**.

> First run downloads Chroma's small embedding model (~80 MB, one time).

---

## 🔌 API

| Method | Path | Purpose |
| --- | --- | --- |
| `GET`  | `/api/health` | status, model, key presence, source count |
| `GET`  | `/api/sources` | list sources |
| `GET`  | `/api/sources/{id}` | source detail (summary, tags) |
| `DELETE` | `/api/sources/{id}` | remove a source |
| `POST` | `/api/ingest/pdf` | multipart PDF upload |
| `POST` | `/api/ingest/youtube` | `{ "url": "…" }` |
| `POST` | `/api/ingest/web` | `{ "url": "…" }` |
| `POST` | `/api/ingest/note` | `{ "title": "…", "text": "…" }` |
| `POST` | `/api/ask` | `{ "question": "…", "source_ids": ["…"]? }` → answer + citations |
| `POST` | `/api/sources/{id}/flashcards` | `{ "count": 8 }` → flashcards |
| `POST` | `/api/sources/{id}/resummarize` | regenerate summary + tags |

Example:

```bash
curl -X POST http://127.0.0.1:8000/api/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "How does the retrieval flow use citations?"}'
```

---

## ⚙️ Configuration

All optional except the key. See `.env.example`.

DevVault supports two LLM backends — pick one:

| Variable | Default | Notes |
| --- | --- | --- |
| `DEVVAULT_PROVIDER` | auto | `groq` (free) or `claude`; empty = auto-detect from the key present |
| `GROQ_API_KEY` | — | **free**, no card: https://console.groq.com |
| `DEVVAULT_GROQ_MODEL` | `llama-3.3-70b-versatile` | any Groq-hosted model |
| `ANTHROPIC_API_KEY` | — | Claude; requires purchased credits |
| `DEVVAULT_MODEL` | `claude-opus-4-8` | Claude model (e.g. `claude-haiku-4-5`) |
| `DEVVAULT_DATA_DIR` | `./data` | where ChromaDB + SQLite live |
| `DEVVAULT_TOP_K` | `6` | chunks retrieved per question |
| `DEVVAULT_CHUNK_SIZE` / `_OVERLAP` | `1200` / `150` | chunking |

---

## 🧭 Roadmap ideas

- Streaming answers (SSE) for a live typing effect
- Ingest GitHub repos / issues and Stack Overflow threads
- Spaced-repetition scheduling on flashcards
- Optional fully-offline mode with a local LLM (Ollama)

---

Built as a learning + portfolio project. PRs and forks welcome.
