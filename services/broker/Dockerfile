FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ ./src/

# Create directories for config and logs
RUN mkdir -p /etc/kitty /var/log/kitty

# Copy default allow-list
COPY config/commands.yaml /etc/kitty/commands.yaml

# Set environment variables
ENV PYTHONPATH=/app/src
ENV BROKER_HOST=0.0.0.0
ENV BROKER_PORT=8777
ENV BROKER_ALLOW_LIST=/etc/kitty/commands.yaml
ENV BROKER_AUDIT_LOG=/var/log/kitty/broker-audit.jsonl
ENV BROKER_ENABLE_PRIVILEGE_DROP=false

# Expose port
EXPOSE 8777

# Run broker
CMD ["python", "-m", "uvicorn", "broker.app:app", "--host", "0.0.0.0", "--port", "8777"]
