FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy and install dependencies
COPY services/mem0-mcp/pyproject.toml /app/services/mem0-mcp/
RUN pip install --upgrade pip && \
    cd services/mem0-mcp && pip install -e .

# Copy source code
COPY services/mem0-mcp /app/services/mem0-mcp

WORKDIR /app/services/mem0-mcp

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

EXPOSE 8765

CMD ["uvicorn", "src.mem0_mcp.app:app", "--host", "0.0.0.0", "--port", "8765"]
