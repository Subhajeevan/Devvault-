"""Source loaders: turn PDFs and web pages into plain text."""
from __future__ import annotations

import io

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
    text = "\n\n".join(p for p in parts if p.strip())

    # Little/no text layer → likely a scanned or image-only PDF: fall back to OCR.
    if len(text.strip()) < 40:
        ocr_text = _ocr_pdf(file_bytes)
        if len(ocr_text.strip()) > len(text.strip()):
            return ocr_text
    return text


_ocr_engine = None


def _get_ocr_engine():
    """Lazily build the RapidOCR engine (loads ONNX models once)."""
    global _ocr_engine
    if _ocr_engine is None:
        from rapidocr_onnxruntime import RapidOCR

        _ocr_engine = RapidOCR()
    return _ocr_engine


def _ocr_pdf(file_bytes: bytes) -> str:
    """OCR a scanned/image PDF: render each page to an image and read the text.
    Returns "" if the OCR dependencies aren't available."""
    try:
        import fitz  # PyMuPDF
        import numpy as np
    except ImportError:
        return ""

    from .config import settings

    try:
        engine = _get_ocr_engine()
    except Exception:
        return ""

    parts: list[str] = []
    with fitz.open(stream=file_bytes, filetype="pdf") as doc:
        for page in doc[: settings.MAX_OCR_PAGES]:
            pix = page.get_pixmap(dpi=settings.OCR_DPI)
            img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
                pix.height, pix.width, pix.n
            )
            if pix.n == 4:  # drop alpha channel
                img = img[:, :, :3]
            try:
                result, _ = engine(img)
            except Exception:
                result = None
            if result:
                parts.append(" ".join(line[1] for line in result))
    return "\n\n".join(p for p in parts if p.strip())


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
