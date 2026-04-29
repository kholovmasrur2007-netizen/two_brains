# two_brains — production container.
#
# Two-stage build keeps the runtime image lean: the builder stage installs
# pip dependencies into a venv, the runtime stage copies that venv plus
# the source tree and nothing else (no pip, no build toolchain).
#
#   docker build -t two_brains:latest .
#   docker run -p 8000:8000 -e USE_DB=true -e AUTH_ENABLED=true two_brains:latest

# ── builder ─────────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /build

# System libs needed by psycopg2 and bcrypt at install-time only.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install -r requirements.txt \
    && /opt/venv/bin/pip install psycopg2-binary

# ── runtime ─────────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH"

# libpq is needed at runtime when DATABASE_URL points to PostgreSQL.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Run as a non-root user — never let a runaway agent touch the host.
RUN useradd --create-home --shell /usr/sbin/nologin appuser

COPY --from=builder /opt/venv /opt/venv
WORKDIR /app
COPY --chown=appuser:appuser app/ ./app/
COPY --chown=appuser:appuser requirements.txt pytest.ini ./

# Workspace is mutable runtime state — make it writable.
RUN mkdir -p /app/workspace /app/data && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=3)" \
        || exit 1

CMD ["python", "-m", "app.web", "--host", "0.0.0.0", "--port", "8000"]
