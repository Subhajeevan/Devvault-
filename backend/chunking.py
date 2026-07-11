"""Text chunking: split documents into overlapping, boundary-aware chunks."""
import re


def _normalize(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def chunk_text(text: str, chunk_size: int = 1200, overlap: int = 150) -> list[str]:
    """Split text into chunks of ~chunk_size chars, breaking on natural
    boundaries (paragraph > line > sentence > space) and overlapping by
    `overlap` characters so context isn't lost across chunk edges."""
    text = _normalize(text)
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]

    chunks: list[str] = []
    start, n = 0, len(text)
    # Look back at most this far from the hard limit to find a clean break.
    lookback = min(400, chunk_size // 2)

    while start < n:
        end = min(start + chunk_size, n)
        if end < n:
            window = text[start:end]
            for sep in ("\n\n", "\n", ". ", " "):
                idx = window.rfind(sep)
                if idx != -1 and idx >= chunk_size - lookback:
                    end = start + idx + len(sep)
                    break
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= n:
            break
        start = max(end - overlap, start + 1)

    return chunks
