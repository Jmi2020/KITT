# syntax=docker/dockerfile:1.6
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY services/common ./services/common
COPY services/safety ./services/safety

RUN pip install --upgrade pip && \
    if [ -f services/common/requirements.txt ]; then pip install -r services/common/requirements.txt; fi && \
    if [ -f services/safety/requirements.txt ]; then pip install -r services/safety/requirements.txt; fi && \
    if [ -f services/common/pyproject.toml ]; then \
        pip install poetry && \
        cd services/common && poetry build -f wheel && pip install dist/*.whl && cd /app; \
    fi && \
    if [ -f services/safety/pyproject.toml ]; then \
        pip install poetry && \
        cd services/safety && poetry build -f wheel && pip install dist/*.whl && cd /app; \
    fi

EXPOSE 8400
CMD ["uvicorn", "services.safety.app:app", "--host", "0.0.0.0", "--port", "8400"]
