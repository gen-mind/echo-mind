# ===============================================
# EchoMind Sandbox Agent -- Ephemeral Container
# ===============================================
# Runs a single-session agent with NATS communication
# and MCP tool access. Designed for security isolation.

# ===============================================
# Stage 1: Builder -- install Python dependencies
# ===============================================
FROM python:3.12.12-slim-bookworm AS builder

WORKDIR /build

COPY sandbox/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Install echomind_lib from local copy
COPY echomind_lib /build/echomind_lib
RUN pip install --no-cache-dir --prefix=/install /build/echomind_lib

# ===============================================
# Stage 2: Runtime -- minimal production image
# ===============================================
FROM python:3.12.12-slim-bookworm

WORKDIR /app

# Minimal runtime deps: curl for healthcheck, jq for debugging, git for skills
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    jq \
    git \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY sandbox /app/sandbox
COPY echomind_lib /app/echomind_lib

ENV PYTHONPATH="/app"
ENV PYTHONUNBUFFERED="1"

# Non-root user (CRITICAL for security)
RUN useradd -m -u 1000 -s /bin/false sandboxuser && \
    chown -R sandboxuser:sandboxuser /app

USER sandboxuser

# Health check endpoint
HEALTHCHECK --interval=10s --timeout=5s --start-period=3s --retries=2 \
    CMD curl -f http://localhost:8080/healthz || exit 1

EXPOSE 8080

CMD ["python", "-m", "sandbox.main"]
