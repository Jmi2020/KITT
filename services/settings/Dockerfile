# syntax=docker/dockerfile:1.6
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY services/common ./services/common
COPY services/settings ./services/settings

RUN pip install --upgrade pip && \
    if [ -f services/common/requirements.txt ]; then pip install -r services/common/requirements.txt; fi && \
    if [ -f services/settings/requirements.txt ]; then pip install -r services/settings/requirements.txt; fi && \
    if [ -f services/common/pyproject.toml ]; then \
        cd services/common && pip install -e . && cd /app; \
    fi && \
    if [ -f services/settings/pyproject.toml ]; then \
        cd services/settings && pip install -e . && cd /app; \
    fi

EXPOSE 8450
CMD ["python", "-m", "uvicorn", "settings.app:app", "--host", "0.0.0.0", "--port", "8450"]
