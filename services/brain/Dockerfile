# syntax=docker/dockerfile:1.6
FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    UVICORN_WORKERS=2

WORKDIR /app

# Install system dependencies required by common scientific/CV stacks; adjust as implementations mature.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    && rm -rf /var/lib/apt/lists/*

# Copy service sources (shared + service-specific) for dependency resolution.
COPY services/common ./services/common
COPY services/brain ./services/brain
COPY services/mcp ./services/mcp

# Install dependencies when lock/requirements files exist (guards keep the scaffold buildable pre-dependency).
RUN pip install --upgrade pip && \
    if [ -f services/common/requirements.txt ]; then pip install -r services/common/requirements.txt; fi && \
    if [ -f services/brain/requirements.txt ]; then pip install -r services/brain/requirements.txt; fi && \
    if [ -f services/common/pyproject.toml ]; then \
        cd services/common && pip install -e . && cd /app; \
    fi && \
    if [ -f services/brain/pyproject.toml ]; then \
        cd services/brain && pip install -e . && cd /app; \
    fi

EXPOSE 8000
CMD ["python", "-m", "uvicorn", "brain.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
