"""Runtime configuration, read from environment variables (.env supported)."""
import os

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # dotenv is optional
    pass


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


class Settings:
    # ---- LLM providers -----------------------------------------------------
    # DevVault can use Groq (free hosted) or Claude. Leave DEVVAULT_PROVIDER
    # empty to auto-pick whichever key is present (Groq preferred if both).
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    PROVIDER: str = os.getenv("DEVVAULT_PROVIDER", "").strip().lower()

    # Per-provider model IDs.
    MODEL: str = os.getenv("DEVVAULT_MODEL", "claude-opus-4-8")
    GROQ_MODEL: str = os.getenv("DEVVAULT_GROQ_MODEL", "llama-3.3-70b-versatile")

    # ---- Storage -----------------------------------------------------------
    DATA_DIR: str = os.getenv("DEVVAULT_DATA_DIR", "./data")
    COLLECTION: str = "devvault"

    # ---- Retrieval / chunking ---------------------------------------------
    TOP_K: int = _int("DEVVAULT_TOP_K", 6)
    CHUNK_SIZE: int = _int("DEVVAULT_CHUNK_SIZE", 1200)
    CHUNK_OVERLAP: int = _int("DEVVAULT_CHUNK_OVERLAP", 150)
    MAX_DOC_CHARS: int = _int("DEVVAULT_MAX_DOC_CHARS", 120_000)
    # Smaller caps for LLM-generated summaries/flashcards keep token use well under
    # free-tier per-minute limits (a doc's head is plenty for a good summary).
    SUMMARY_CHARS: int = _int("DEVVAULT_SUMMARY_CHARS", 8_000)
    FLASHCARD_CHARS: int = _int("DEVVAULT_FLASHCARD_CHARS", 12_000)

    # OCR fallback for scanned/image PDFs (bounded to keep memory/time in check).
    MAX_OCR_PAGES: int = _int("DEVVAULT_MAX_OCR_PAGES", 15)
    OCR_DPI: int = _int("DEVVAULT_OCR_DPI", 200)

    @property
    def CHROMA_DIR(self) -> str:
        return os.path.join(self.DATA_DIR, "chroma")

    @property
    def DB_PATH(self) -> str:
        return os.path.join(self.DATA_DIR, "devvault.db")

    # ---- Provider resolution ----------------------------------------------
    def provider(self) -> str:
        """Which LLM backend is active: 'groq', 'claude', or 'none'."""
        if self.PROVIDER in ("claude", "groq"):
            return self.PROVIDER
        if self.GROQ_API_KEY:
            return "groq"
        if self.ANTHROPIC_API_KEY:
            return "claude"
        return "none"

    def active_model(self) -> str:
        p = self.provider()
        if p == "groq":
            return self.GROQ_MODEL
        if p == "claude":
            return self.MODEL
        return ""

    def has_llm(self) -> bool:
        """True when the active provider has the key it needs."""
        p = self.provider()
        if p == "groq":
            return bool(self.GROQ_API_KEY)
        if p == "claude":
            return bool(self.ANTHROPIC_API_KEY)
        return False


settings = Settings()
