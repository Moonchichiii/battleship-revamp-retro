# Use slim Python base
FROM python:3.12-slim

# Avoid interactive prompts
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    POETRY_VERSION=1.8.2

# Install basic tools and build deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl git && \
    pip install --no-cache-dir --upgrade pip && \
    apt-get purge -y --auto-remove && \
    rm -rf /var/lib/apt/lists/*

# Set work directory
WORKDIR /app

# Copy only needed files first to leverage layer caching
COPY pyproject.toml poetry.lock* ./

# Install poetry and project dependencies
RUN curl -sSL https://install.python-poetry.org | python3 - && \
    /root/.local/bin/poetry config virtualenvs.create false && \
    /root/.local/bin/poetry install --no-interaction --no-ansi

# Copy project files
COPY . .

# Expose default FastAPI port
EXPOSE 8000

# Start app
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
