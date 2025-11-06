# syntax=docker/dockerfile:1.6
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    UVICORN_WORKERS=2

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY services/common ./services/common
COPY services/gateway ./services/gateway

RUN pip install --upgrade pip && \
    if [ -f services/common/requirements.txt ]; then pip install -r services/common/requirements.txt; fi && \
    if [ -f services/gateway/requirements.txt ]; then pip install -r services/gateway/requirements.txt; fi && \
    if [ -f services/common/pyproject.toml ]; then \
        cd services/common && pip install -e . && cd /app; \
    fi && \
    if [ -f services/gateway/pyproject.toml ]; then \
        cd services/gateway && pip install -e . && cd /app; \
    fi

EXPOSE 8080
CMD ["python", "-m", "uvicorn", "gateway.app:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "2"]
