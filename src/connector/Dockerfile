# EchoMind Connector Service Dockerfile
# Fetches files from external sources and uploads to MinIO

FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy shared library first (for layer caching)
COPY echomind_lib/ /app/echomind_lib/

# Copy service requirements and install
COPY connector/requirements.txt /app/connector/requirements.txt
RUN pip install --no-cache-dir -r /app/connector/requirements.txt

# Install shared library
RUN pip install --no-cache-dir -e /app/echomind_lib 2>/dev/null || true

# Copy service code
COPY connector/ /app/connector/

# Set Python path
ENV PYTHONPATH=/app

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/healthz')" || exit 1

# Run the service
CMD ["python", "-m", "connector.main"]
