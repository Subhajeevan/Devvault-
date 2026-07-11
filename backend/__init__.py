"""DevVault — a developer-focused AI second brain (RAG over your own sources)."""

# Use the OS trust store for TLS verification. Without this, outbound HTTPS to the
# Anthropic API can fail with "Connection error" on machines behind a corporate
# proxy or antivirus that intercepts TLS with a custom root CA (present in the
# Windows store but not in Python's bundled certifi CAs). Best-effort import.
try:
    import truststore

    truststore.inject_into_ssl()
except Exception:
    pass

__version__ = "0.1.0"
