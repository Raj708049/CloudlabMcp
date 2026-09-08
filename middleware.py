"""Starlette middleware to read Smithery's per-request config.

Smithery deploys HTTP MCP servers and passes the user's configuration on every
request as a base64-encoded JSON string in the `config` query parameter, e.g.
    POST /mcp?config=<base64_json>

This middleware decodes it and applies it to the shared Config object so the
tools use the caller's CloudLab settings. When credentials change, the cached
auth token is cleared so the next call logs in again.
"""

import base64
import json

from starlette.middleware.base import BaseHTTPMiddleware

from config import config


class SmitheryConfigMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        raw = request.query_params.get("config")
        if raw:
            try:
                # urlsafe + tolerate missing padding.
                padded = raw + "=" * (-len(raw) % 4)
                decoded = base64.urlsafe_b64decode(padded).decode("utf-8")
                data = json.loads(decoded)
                if isinstance(data, dict):
                    prev = (config.base_url, config.username, config.password)
                    config.apply(data)
                    # If credentials changed, force a fresh login next call.
                    if (config.base_url, config.username, config.password) != prev:
                        from client import client

                        client.reset_auth()
            except Exception:
                # A bad config param shouldn't crash the request; the tools
                # will surface a clear "missing config" error instead.
                pass
        return await call_next(request)
