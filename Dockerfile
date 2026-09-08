# cloudlabMcp — container image for Smithery / any Docker host.
FROM python:3.11-slim

WORKDIR /app

# Install dependencies first (better layer caching).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the server code.
COPY server.py client.py config.py middleware.py ./

# Run as an HTTP MCP server. Smithery injects PORT at runtime.
ENV MCP_TRANSPORT=streamable-http \
    MCP_HOST=0.0.0.0 \
    MCP_PORT=8000

EXPOSE 8000

CMD ["python", "server.py"]
