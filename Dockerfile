# Build Stage
ARG BASE_IMAGE=python:3.13.5-alpine
FROM ${BASE_IMAGE} AS builder

# Install dependencies
RUN apk add --no-cache build-base gcc

WORKDIR /app

# Install Python packages
COPY requirements.txt .
RUN pip install --upgrade pip && pip install --no-cache-dir --prefix=/install -r requirements.txt

# Runtime Stage
ARG BASE_IMAGE=python:3.13.5-alpine
FROM ${BASE_IMAGE} AS runtime

WORKDIR /app

# Install curl
RUN apk add --no-cache curl

# Set Python path
ENV PYTHONPATH=/usr/local/lib/python3.13/site-packages

# Copy dependencies and app code
COPY --from=builder /install /usr/local
COPY . .

# Create user and switch
RUN adduser -D appuser
USER appuser

# Expose port and healthcheck
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s \
    CMD curl -f http://localhost:8000/ || exit 1

# Run app
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
