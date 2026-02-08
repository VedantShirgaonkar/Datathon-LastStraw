# ──────────────────────────────────────────────────────────
# Dockerfile — Engineering Intelligence API
# Optimised for HuggingFace Spaces (port 7860)
# ──────────────────────────────────────────────────────────
# Build:   docker build -t eng-intel-api .
# Run:     docker run -p 7860:7860 --env-file .env eng-intel-api
# ──────────────────────────────────────────────────────────

FROM python:3.12-slim AS base

# ── System deps (libpq for psycopg2) ──
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libpq-dev gcc && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── Install Python dependencies first (Docker cache layer) ──
COPY server/requirements.txt /app/server/requirements.txt
RUN pip install --no-cache-dir -r /app/server/requirements.txt

# ── Copy application code ──
COPY agents/ /app/agents/
COPY server/ /app/server/

# ── HuggingFace Spaces requires port 7860 ──
ENV PORT=7860
EXPOSE 7860

# ── Health check (HF Spaces expects /api/health or / to respond) ──
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:7860/api/health')" || exit 1

# ── Run ──
CMD ["python", "-m", "uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "7860"]
