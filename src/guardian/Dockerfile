# EchoMind Guardian Service Dockerfile
#
# Multi-stage build for DLQ monitoring and alerting service.
# Lightweight service - only needs NATS and HTTP client.

# ===============================================
# Stage 1: Builder - Install dependencies
# ===============================================
FROM python:3.12.12-slim-bookworm AS builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (cache layer optimization)
COPY guardian/requirements.txt .

# Install Python dependencies in a separate location
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ===============================================
# Stage 2: Runtime - Minimal final image
# ===============================================
FROM python:3.12.12-slim-bookworm

WORKDIR /app

# Install only runtime dependencies (curl for health checks)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY guardian /app/guardian
COPY echomind_lib /app/echomind_lib

# Set Python path
ENV PYTHONPATH="/app"

# Create non-root user for security
RUN useradd -m -u 1000 guardianuser && \
    chown -R guardianuser:guardianuser /app
USER guardianuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8080/healthz || exit 1

# Expose port
EXPOSE 8080

# Run guardian
CMD ["python", "-m", "guardian.main"]
