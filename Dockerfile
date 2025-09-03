# ---------- Build stage ----------
ARG BASE_IMAGE=python:3.12-alpine
FROM ${BASE_IMAGE} AS builder

# Faster, quieter pip/poetry; no local venvs; stable export
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    POETRY_VERSION=1.8.3

# Build deps only for compiling wheels (bcrypt/argon2/asyncpg, etc.)
RUN apk add --no-cache build-base gcc musl-dev libffi-dev openssl-dev

WORKDIR /app

# Install Poetry (export is built-in on 1.8.x; no plugin needed)
RUN pip install "poetry==${POETRY_VERSION}" && poetry config warnings.export false

# Cache deps: copy only metadata first
COPY pyproject.toml poetry.lock* ./

# Export locked runtime deps and install them to /install (no dev deps)
RUN mkdir -p /install && set -eux; \
    poetry export -f requirements.txt --without-hashes --without dev -o /tmp/requirements.txt; \
    pip install --prefix=/install --no-cache-dir -r /tmp/requirements.txt


# ---------- Runtime stage ----------
FROM ${BASE_IMAGE} AS runtime

# Useful envs for containers
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Runtime libs only (no compilers); curl for healthcheck
# libffi/openssl cover common crypto/hash wheels; tzdata for logs/timestamps; libstdc++ for some wheels
RUN apk add --no-cache curl libffi openssl tzdata libstdc++

WORKDIR /app

# Bring in installed site-packages and console scripts
COPY --from=builder /install /usr/local

# App code
COPY . .

# Non-root user
RUN adduser -D appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s \
    CMD curl -fsS http://localhost:8000/health || exit 1

# Light concurrency without reload in prod
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
