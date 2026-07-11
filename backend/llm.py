"""LLM layer with a pluggable provider (Groq or Claude).

Public API — provider-agnostic:
    analyze_document(text, title) -> {"summary", "tags"}
    make_flashcards(text, title, count) -> [{"question", "answer"}]
    answer_question(question, retrieved) -> {"answer", "citations", "used_sources"}

Claude uses the native Citations API for grounded answers; Groq (OpenAI-compatible)
uses numbered-source prompting and [n] markers parsed back to sources. Select the
backend with DEVVAULT_PROVIDER / by which key is present (see config.py).
"""
from __future__ import annotations

import json
import re
import time

import httpx

from .config import settings


class LLMNotConfigured(RuntimeError):
    """Raised when an LLM call is attempted without a configured provider key."""


def _require() -> None:
    if settings.has_llm():
        return
    if settings.provider() == "groq":
        raise LLMNotConfigured(
            "GROQ_API_KEY is not set. Get a free key at https://console.groq.com "
            "(no credit card) and add it to your .env, then restart."
        )
    raise LLMNotConfigured(
        "No LLM key configured. Add GROQ_API_KEY (free) or ANTHROPIC_API_KEY to .env."
    )


def _first_text(resp) -> str:
    return "".join(b.text for b in resp.content if b.type == "text")


def _extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text).strip()
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1:
        text = text[start : end + 1]
    return json.loads(text)


# --------------------------------------------------------------------------- #
# Claude backend
# --------------------------------------------------------------------------- #
_anthropic = None


def _anthropic_client():
    global _anthropic
    if _anthropic is None:
        import anthropic

        _anthropic = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    return _anthropic


def _claude_json(system: str, prompt: str, schema: dict, max_tokens: int) -> dict:
    import anthropic

    c = _anthropic_client()
    try:
        resp = c.messages.create(
            model=settings.MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
            output_config={"format": {"type": "json_schema", "schema": schema}},
        )
        return json.loads(_first_text(resp))
    except (anthropic.BadRequestError, TypeError):
        resp = c.messages.create(
            model=settings.MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=[
                {
                    "role": "user",
                    "content": prompt
                    + "\n\nRespond with ONLY a JSON object matching this schema "
                    "(no prose, no code fences):\n" + json.dumps(schema),
                }
            ],
        )
        return _extract_json(_first_text(resp))


def _claude_answer(question: str, retrieved: list[dict]) -> dict:
    content: list[dict] = []
    for r in retrieved:
        content.append(
            {
                "type": "document",
                "source": {
                    "type": "content",
                    "content": [{"type": "text", "text": r["text"]}],
                },
                "title": r.get("title") or "Untitled",
                "citations": {"enabled": True},
            }
        )
    content.append({"type": "text", "text": question})

    resp = _anthropic_client().messages.create(
        model=settings.MODEL,
        max_tokens=2048,
        system=_QA_SYSTEM,
        messages=[{"role": "user", "content": content}],
    )

    parts, citations, seen = [], [], set()
    for block in resp.content:
        if block.type != "text":
            continue
        parts.append(block.text)
        for cit in getattr(block, "citations", None) or []:
            idx = getattr(cit, "document_index", None)
            if idx is None or idx >= len(retrieved):
                continue
            src = retrieved[idx]
            cited_text = (getattr(cit, "cited_text", "") or "").strip()
            key = (src.get("source_id"), cited_text[:80])
            if key in seen:
                continue
            seen.add(key)
            citations.append(_citation(len(citations) + 1, src, cited_text))
    return _finalize_answer("".join(parts), citations)


# --------------------------------------------------------------------------- #
# Groq backend (OpenAI-compatible)
# --------------------------------------------------------------------------- #
_GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
# Groq is fronted by Cloudflare, which can 403 (error 1010) on non-browser client
# signatures behind some proxies. A browser User-Agent avoids that.
_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
)


def _groq_post(messages: list[dict], max_tokens: int, json_mode=False, temperature=0.3) -> str:
    payload = {
        "model": settings.GROQ_MODEL,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    headers = {
        "Authorization": f"Bearer {settings.GROQ_API_KEY}",
        "Content-Type": "application/json",
        "User-Agent": _BROWSER_UA,
    }
    for attempt in range(3):
        try:
            r = httpx.post(_GROQ_URL, headers=headers, json=payload, timeout=120)
        except httpx.HTTPError as e:
            raise RuntimeError(f"Connection error contacting Groq: {e}")
        # Free-tier per-minute limits: back off and retry on 429.
        if r.status_code == 429 and attempt < 2:
            try:
                wait = float(r.headers.get("retry-after", "") or 8)
            except ValueError:
                wait = 8.0
            if wait <= 30:
                time.sleep(wait)
                continue
        if r.status_code >= 400:
            try:
                msg = r.json().get("error", {}).get("message") or r.text
            except Exception:
                msg = r.text
            raise RuntimeError(f"Groq API error {r.status_code}: {msg}")
        return r.json()["choices"][0]["message"]["content"] or ""
    raise RuntimeError(
        "Groq API error 429: rate limited (tokens per minute). Wait a moment and retry."
    )


def _groq_json(system: str, prompt: str, schema: dict, max_tokens: int) -> dict:
    sys = system + " Respond with ONLY a single JSON object — no prose, no code fences."
    user = prompt + "\n\nReturn JSON matching this schema:\n" + json.dumps(schema)
    content = _groq_post(
        [{"role": "system", "content": sys}, {"role": "user", "content": user}],
        max_tokens=max_tokens,
        json_mode=True,
        temperature=0.4,
    )
    return _extract_json(content)


def _groq_answer(question: str, retrieved: list[dict]) -> dict:
    blocks = []
    for i, r in enumerate(retrieved, 1):
        blocks.append(f"[{i}] {r.get('title') or 'Untitled'}\n{r['text']}")
    context = "\n\n".join(blocks)
    system = (
        _QA_SYSTEM + " The sources are numbered. Cite the ones you use inline with "
        "bracketed numbers like [1] or [2]. Only cite sources that actually support "
        "your statements."
    )
    user = f"Sources:\n{context}\n\nQuestion: {question}"
    answer = _groq_post(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        max_tokens=1024,
        temperature=0.2,
    )

    citations = []
    for m in re.findall(r"\[(\d+)\]", answer):
        n = int(m)
        if 1 <= n <= len(retrieved) and not any(c["number"] == n for c in citations):
            src = retrieved[n - 1]
            snippet = src["text"][:200] + ("…" if len(src["text"]) > 200 else "")
            citations.append(_citation(n, src, snippet))
    return _finalize_answer(answer, citations)


# --------------------------------------------------------------------------- #
# Shared helpers + prompts
# --------------------------------------------------------------------------- #
def _citation(number: int, src: dict, cited_text: str) -> dict:
    return {
        "number": number,
        "cited_text": cited_text,
        "title": src.get("title") or "Untitled",
        "url": src.get("url") or "",
        "source_type": src.get("source_type") or "",
        "source_id": src.get("source_id") or "",
    }


def _finalize_answer(answer: str, citations: list[dict]) -> dict:
    used: dict[str, dict] = {}
    for c in citations:
        used.setdefault(
            c["source_id"],
            {
                "source_id": c["source_id"],
                "title": c["title"],
                "url": c["url"],
                "source_type": c["source_type"],
            },
        )
    return {"answer": answer.strip(), "citations": citations, "used_sources": list(used.values())}


def _json_chat(system: str, prompt: str, schema: dict, max_tokens: int) -> dict:
    if settings.provider() == "groq":
        return _groq_json(system, prompt, schema, max_tokens)
    return _claude_json(system, prompt, schema, max_tokens)


_QA_SYSTEM = (
    "You are DevVault, a developer's knowledge assistant. Answer the user's question "
    "using ONLY the provided sources, which are excerpts from the user's personal "
    "knowledge base. If the sources do not contain the answer, say so plainly and do "
    "not speculate. Be concise and technical; use Markdown, and include short code "
    "snippets when helpful."
)

_ANALYZE_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["summary", "tags"],
    "additionalProperties": False,
}

_FLASHCARDS_SCHEMA = {
    "type": "object",
    "properties": {
        "flashcards": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "answer": {"type": "string"},
                },
                "required": ["question", "answer"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["flashcards"],
    "additionalProperties": False,
}


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def analyze_document(text: str, title: str) -> dict:
    _require()
    system = (
        "You are DevVault's librarian. You write tight, technical summaries and assign "
        "useful topical tags so a developer can find and recall material later."
    )
    prompt = (
        f"Document title: {title}\n\n"
        "Produce:\n"
        "1. `summary`: concise Markdown — a one-sentence TL;DR, then 3–6 bullet points "
        "capturing the key ideas, APIs, or takeaways.\n"
        "2. `tags`: 3–6 short, lowercase topical tags (e.g. \"rag\", \"postgres\").\n\n"
        f"<document>\n{text[: settings.SUMMARY_CHARS]}\n</document>"
    )
    data = _json_chat(system, prompt, _ANALYZE_SCHEMA, max_tokens=1500)
    tags = [str(t).strip().lower() for t in data.get("tags", []) if str(t).strip()]
    return {"summary": str(data.get("summary", "")).strip(), "tags": tags[:8]}


def make_flashcards(text: str, title: str, count: int = 8) -> list[dict]:
    _require()
    system = (
        "You are DevVault's study coach. You turn technical material into precise "
        "question/answer flashcards for active recall. Questions are specific; answers "
        "are correct and self-contained."
    )
    prompt = (
        f"Create {count} flashcards from the document below (titled \"{title}\"). "
        "Cover the most important, testable concepts. Avoid trivia.\n\n"
        f"<document>\n{text[: settings.FLASHCARD_CHARS]}\n</document>"
    )
    data = _json_chat(system, prompt, _FLASHCARDS_SCHEMA, max_tokens=4096)
    cards = []
    for c in data.get("flashcards", []):
        q, a = str(c.get("question", "")).strip(), str(c.get("answer", "")).strip()
        if q and a:
            cards.append({"question": q, "answer": a})
    return cards


def answer_question(question: str, retrieved: list[dict]) -> dict:
    if not retrieved:
        return {
            "answer": "I couldn't find anything relevant in your vault. Try adding "
            "sources, rephrasing, or broadening the question.",
            "citations": [],
            "used_sources": [],
        }
    _require()
    if settings.provider() == "groq":
        return _groq_answer(question, retrieved)
    return _claude_answer(question, retrieved)
