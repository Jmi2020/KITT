# Multi-stage build for KITTY Coder Agent
FROM python:3.11-slim as builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY services/coder-agent/requirements.txt .

# Install Python dependencies to /install
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# Production image
FROM python:3.11-slim

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy Python packages from builder
COPY --from=builder /install /usr/local

# Copy source code
COPY services/coder-agent/src/coder_agent /app/coder_agent

# Set PYTHONPATH for the app
ENV PYTHONPATH=/app

# Create non-root user for sandbox security
RUN useradd -m -u 1000 coder && \
    chown -R coder:coder /app

# Switch to non-root user
USER coder

# Expose service port
EXPOSE 8092

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8092/healthz || exit 1

# Run service
CMD ["python", "-m", "coder_agent.app"]
