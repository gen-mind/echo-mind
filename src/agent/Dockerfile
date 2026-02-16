# Agent Sandbox Docker Image
# Runs the sandbox runner inside an ephemeral container
# managed by SandboxManager.

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
COPY agent/requirements.txt .

# Install Python dependencies in a separate location
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ===============================================
# Stage 2: Runtime - Minimal final image
# ===============================================
FROM python:3.12.12-slim-bookworm

WORKDIR /app

# Install only runtime dependencies (no build tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY agent /app/agent
COPY echomind_lib /app/echomind_lib

# Set Python path
ENV PYTHONPATH="/app"

# Create non-root user for security
RUN useradd -m -u 1000 sandboxuser && \
    chown -R sandboxuser:sandboxuser /app
USER sandboxuser

# Health check
HEALTHCHECK --interval=10s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8080/healthz || exit 1

# Expose health check port
EXPOSE 8080

# Run sandbox runner
CMD ["python", "-m", "agent.sandbox_runner"]
