"""Source loaders: turn PDFs, YouTube links, and web pages into plain text."""
from __future__ import annotations

import io
import re
from urllib.parse import parse_qs, urlparse

import httpx

_UA = "Mozilla/5.0 (compatible; DevVault/0.1; +https://github.com/)"


# --------------------------------------------------------------------------- #
# PDF
# --------------------------------------------------------------------------- #
def load_pdf(file_bytes: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(file_bytes))
    parts = []
    for page in reader.pages:
        try:
            parts.append(page.extract_text() or "")
        except Exception:
            parts.append("")
    return "\n\n".join(p for p in parts if p.strip())


# --------------------------------------------------------------------------- #
# YouTube
# --------------------------------------------------------------------------- #
def _video_id(url: str) -> str | None:
    u = urlparse(url)
    host = (u.hostname or "").lower()
    if host == "youtu.be":
        return u.path.lstrip("/") or None
    if "youtube" in host:
        qs = parse_qs(u.query)
        if "v" in qs:
            return qs["v"][0]
        m = re.match(r"^/(embed|shorts|live)/([^/?]+)", u.path)
        if m:
            return m.group(2)
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", url):
        return url
    return None


def _youtube_title(url: str, video_id: str) -> str:
    try:
        r = httpx.get(
            "https://www.youtube.com/oembed",
            params={"url": url, "format": "json"},
            timeout=15,
        )
        if r.status_code == 200:
            title = r.json().get("title")
            if title:
                return title
    except Exception:
        pass
    return f"YouTube · {video_id}"


def load_youtube(url: str) -> tuple[str, str]:
    from youtube_transcript_api import YouTubeTranscriptApi

    video_id = _video_id(url)
    if not video_id:
        raise ValueError("Could not parse a YouTube video ID from that URL.")

    try:
        data = YouTubeTranscriptApi.get_transcript(
            video_id, languages=["en", "en-US", "en-GB"]
        )
    except Exception:
        # Fall back to whatever transcript is available (auto-generated / other lang).
        data = YouTubeTranscriptApi.get_transcript(video_id)

    text = " ".join(seg["text"].strip() for seg in data if seg.get("text"))
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        raise ValueError("No transcript text was found for this video.")
    return _youtube_title(url, video_id), text


# --------------------------------------------------------------------------- #
# Website
# --------------------------------------------------------------------------- #
def load_web(url: str) -> tuple[str, str]:
    from bs4 import BeautifulSoup

    r = httpx.get(
        url, headers={"User-Agent": _UA}, timeout=30, follow_redirects=True
    )
    r.raise_for_status()
    # Parse from raw bytes so BeautifulSoup detects the page's real charset
    # (avoids mojibake like em-dashes when httpx guesses the encoding wrong).
    soup = BeautifulSoup(r.content, "html.parser")

    title = None
    og = soup.find("meta", attrs={"property": "og:title"})
    if og and og.get("content"):
        title = og["content"].strip()
    elif soup.title and soup.title.string:
        title = soup.title.string.strip()

    for tag in soup(
        ["script", "style", "noscript", "nav", "footer", "header",
         "aside", "form", "svg", "iframe"]
    ):
        tag.decompose()

    main = soup.find("main") or soup.find("article") or soup.body or soup
    raw = main.get_text(separator="\n")
    lines = [ln.strip() for ln in raw.splitlines()]
    text = "\n".join(ln for ln in lines if ln)

    if not text.strip():
        raise ValueError("Could not extract readable text from that page.")
    return (title or url), text
