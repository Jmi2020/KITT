# syntax=docker/dockerfile:1.6
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install system dependencies and CuraEngine from Debian repositories
# CuraEngine is available pre-built for both ARM64 and x86_64
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    wget \
    ffmpeg \
    libsm6 \
    libxext6 \
    libgl1 \
    cura-engine \
    && rm -rf /var/lib/apt/lists/*

ENV CURAENGINE_BIN_PATH=/usr/bin/CuraEngine

COPY services/common ./services/common
COPY services/fabrication ./services/fabrication

RUN pip install --upgrade pip && \
    if [ -f services/common/requirements.txt ]; then pip install -r services/common/requirements.txt; fi && \
    if [ -f services/fabrication/requirements.txt ]; then pip install -r services/fabrication/requirements.txt; fi && \
    if [ -f services/common/pyproject.toml ]; then \
        cd services/common && pip install -e . && cd /app; \
    fi && \
    if [ -f services/fabrication/pyproject.toml ]; then \
        cd services/fabrication && pip install -e . && cd /app; \
    fi

EXPOSE 8300
CMD ["python", "-m", "uvicorn", "fabrication.app:app", "--host", "0.0.0.0", "--port", "8300"]
