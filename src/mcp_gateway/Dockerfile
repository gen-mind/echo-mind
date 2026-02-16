# EchoMind MCP Gateway Service Dockerfile
# MCP server exposing search and skills tools via Streamable HTTP

FROM python:3.12-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install dependencies
COPY mcp_gateway/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY echomind_lib /app/src/echomind_lib
COPY mcp_gateway /app/src/mcp_gateway

# Expose ports (health: 8080, MCP: 8100)
EXPOSE 8080 8100

# Health check defined in docker-compose.yml (overrides Dockerfile HEALTHCHECK)

# Run as non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Entry point
CMD ["python", "-m", "mcp_gateway.main"]
