# syntax=docker/dockerfile:1.6
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    nmap \
    && rm -rf /var/lib/apt/lists/*

# Copy common and discovery service code
COPY services/common ./services/common
COPY services/discovery ./services/discovery

# Install Python dependencies
RUN pip install --upgrade pip && \
    if [ -f services/common/requirements.txt ]; then pip install -r services/common/requirements.txt; fi && \
    if [ -f services/discovery/requirements.txt ]; then pip install -r services/discovery/requirements.txt; fi && \
    if [ -f services/common/pyproject.toml ]; then \
        cd services/common && pip install -e . && cd /app; \
    fi && \
    if [ -f services/discovery/pyproject.toml ]; then \
        cd services/discovery && pip install -e . && cd /app; \
    fi

EXPOSE 8500
CMD ["python", "-m", "uvicorn", "discovery.app:app", "--host", "0.0.0.0", "--port", "8500"]
