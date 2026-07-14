# Mealie MCP Server
# FastMCP-based Model Context Protocol server for Mealie integration

FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY src/ ./src/

# Environment variables MEALIE_URL and MEALIE_API_TOKEN must be provided at runtime.
#
# Transport is selected at runtime via MCP_TRANSPORT:
#   - stdio (default): communicates over stdin/stdout, no port needed.
#   - http: serves the Streamable HTTP transport on MCP_PORT (default 8000).
# The port below is only used when MCP_TRANSPORT=http.
EXPOSE 8000

ENTRYPOINT ["python", "-m", "src.server"]
