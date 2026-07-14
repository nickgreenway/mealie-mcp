"""Runtime transport selection for the Mealie MCP server.

This module is fully additive and opt-in via environment variables. The
defaults preserve the original stdio behavior, so existing users running the
server for Claude Desktop / Claude Code over stdio are completely unaffected.

Environment variables
----------------------
MCP_TRANSPORT   ``stdio`` (default) | ``http``
MCP_HOST        Bind address for http transport (default ``0.0.0.0``)
MCP_PORT        Bind port for http transport (default ``8000``)
MCP_PATH        URL path the MCP endpoint is mounted at (default ``/mcp``)

Running the ``http`` transport exposes an HTTP server. If that endpoint is
reachable from an untrusted network it MUST be protected (see the auth gate:
``MCP_SECRET_PATH`` / ``MCP_BEARER_TOKEN``).
"""

from __future__ import annotations

import os
from typing import Mapping

DEFAULT_TRANSPORT = "stdio"
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8000
DEFAULT_PATH = "/mcp"

# Transports this server knows how to launch. FastMCP also understands "sse",
# but we intentionally expose only the two documented, supported modes.
VALID_TRANSPORTS = ("stdio", "http")

# Accept common spellings of the streamable-http transport and normalize them.
_HTTP_ALIASES = ("http", "streamable-http", "streamable_http", "streamablehttp")


def _env(env: Mapping[str, str] | None) -> Mapping[str, str]:
    return os.environ if env is None else env


def get_transport(env: Mapping[str, str] | None = None) -> str:
    """Return the normalized transport name (``stdio`` or ``http``).

    Raises ValueError for an unrecognized MCP_TRANSPORT value so a typo fails
    loudly at startup instead of silently falling back to stdio.
    """
    raw = _env(env).get("MCP_TRANSPORT", DEFAULT_TRANSPORT).strip().lower()
    if raw in _HTTP_ALIASES:
        return "http"
    if raw in VALID_TRANSPORTS:
        return raw
    raise ValueError(
        f"Invalid MCP_TRANSPORT={raw!r}. "
        f"Expected one of: stdio, http (aliases: {', '.join(_HTTP_ALIASES)})."
    )


def get_http_settings(env: Mapping[str, str] | None = None) -> dict:
    """Resolve host/port/path for the http transport from the environment."""
    e = _env(env)
    port_raw = e.get("MCP_PORT", str(DEFAULT_PORT)).strip()
    try:
        port = int(port_raw)
    except ValueError as exc:
        raise ValueError(f"Invalid MCP_PORT={port_raw!r}; must be an integer.") from exc

    path = e.get("MCP_PATH", DEFAULT_PATH).strip() or DEFAULT_PATH
    if not path.startswith("/"):
        path = "/" + path

    return {
        "host": e.get("MCP_HOST", DEFAULT_HOST).strip() or DEFAULT_HOST,
        "port": port,
        "path": path,
    }


def run(mcp, env: Mapping[str, str] | None = None) -> None:
    """Launch ``mcp`` using the transport selected by the environment.

    ``stdio`` (the default) reproduces the original ``mcp.run()`` behavior
    exactly. ``http`` starts FastMCP's Streamable HTTP transport.
    """
    e = _env(env)
    transport = get_transport(e)

    if transport == "stdio":
        mcp.run()
        return

    settings = get_http_settings(e)
    mcp.run(
        transport="http",
        host=settings["host"],
        port=settings["port"],
        path=settings["path"],
    )
