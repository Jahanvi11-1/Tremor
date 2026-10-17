FROM python:3.11-slim

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

# Copy deps first for layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all source files
COPY src/ ./src/
COPY .env.example .env.example

# Clone the click repo (data source) — or mount at runtime
RUN mkdir -p data && \
    git clone --depth=50 https://github.com/pallets/click.git data/click || true

# Set Python path
ENV PYTHONPATH=/app/src
ENV FALKORDB_HOST=falkordb
ENV FALKORDB_PORT=6379
ENV FALKORDB_GRAPH=tremor
ENV MCP_BASE_URL=http://localhost:8765

# Expose port
EXPOSE 8765

# Start MCP server
CMD ["python", "src/mcp_server.py"]
