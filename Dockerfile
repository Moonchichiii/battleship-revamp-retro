# ---------- Build stage ----------
ARG BASE_IMAGE=python:3.12-alpine
FROM ${BASE_IMAGE} AS builder

# Faster pip; build deps for wheels
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1
RUN apk add --no-cache build-base gcc musl-dev libffi-dev openssl-dev

WORKDIR /app

# Install runtime deps (use your existing requirements.txt)
COPY requirements.txt ./
RUN python -m pip install --upgrade pip \
    && pip install --prefix=/install --no-cache-dir -r requirements.txt

# ---------- Runtime stage ----------
FROM ${BASE_IMAGE} AS runtime

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
# runtime libs only
RUN apk add --no-cache curl libffi openssl tzdata libstdc++

WORKDIR /app

# bring in site-packages and console scripts
COPY --from=builder /install /usr/local

# app code
COPY . .

# non-root
RUN adduser -D appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s \
    CMD curl -fsS http://localhost:8000/health || exit 1

# prod default
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
