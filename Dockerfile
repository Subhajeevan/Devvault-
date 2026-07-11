# DevVault — portable container (works on Hugging Face Spaces, Render, Fly, Railway, Koyeb, Cloud Run)
FROM python:3.12-slim

# System libs: libgomp1 is required by onnxruntime; ca-certificates for TLS.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgomp1 ca-certificates && \
    rm -rf /var/lib/apt/lists/*

ENV HOME=/app \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DEVVAULT_DATA_DIR=/app/data \
    DEVVAULT_PROVIDER=groq \
    ANONYMIZED_TELEMETRY=False \
    PORT=7860

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend ./backend
COPY frontend ./frontend

# Pre-bake Chroma's local MiniLM embedding model so first boot is instant & needs no network.
RUN python -c "import urllib.request,tarfile,io,os; \
p='/app/.cache/chroma/onnx_models/all-MiniLM-L6-v2'; os.makedirs(p, exist_ok=True); \
d=urllib.request.urlopen('https://chroma-onnx-models.s3.amazonaws.com/all-MiniLM-L6-v2/onnx.tar.gz', timeout=180).read(); \
tarfile.open(fileobj=io.BytesIO(d)).extractall(p)"

# Make runtime-writable dirs world-writable (Spaces runs as a non-root user).
RUN mkdir -p /app/data && chmod -R 777 /app/data /app/.cache

EXPOSE 7860
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-7860}"]
