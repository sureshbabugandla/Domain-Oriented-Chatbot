# ─── Stage 1: builder ────────────────────────────────────────
# Compiles Python deps (incl. heavy ML libs) in a fat image, then
# we copy only the venv into the lean runtime stages.
FROM python:3.11-slim-bookworm AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential curl git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY pyproject.toml ./
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install runtime deps only (dev extras layered in dev stage).
RUN pip install --upgrade pip setuptools wheel && \
    pip install -e ".[dev]" && \
    python -m spacy download en_core_web_sm

# ─── Stage 2: dev (with hot reload + test deps) ──────────────
FROM python:3.11-slim-bookworm AS dev

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl procps \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -u 1000 cinebot

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY --chown=cinebot:cinebot . .

USER cinebot

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# ─── Stage 3: production runtime ─────────────────────────────
# Smaller, non-root, read-only app. Prod builds use gunicorn with
# uvicorn workers for proper signal handling + graceful shutdown.
FROM python:3.11-slim-bookworm AS prod

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    WEB_CONCURRENCY=4

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -u 1000 -s /usr/sbin/nologin cinebot

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY --chown=cinebot:cinebot ./app ./app
COPY --chown=cinebot:cinebot ./pyproject.toml ./pyproject.toml

USER cinebot

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["gunicorn", "app.main:app", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "4", \
     "--timeout", "60", \
     "--graceful-timeout", "30", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]
