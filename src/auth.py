"""Optional auth gate for the HTTP transport.

Two independent, opt-in gates protect the internet-facing HTTP endpoint. Both
are inert unless configured, and both are irrelevant under stdio (stdio is a
local pipe, so there is nothing to gate).

Environment variables
----------------------
MCP_SECRET_PATH   Random URL path segment. When set, the MCP endpoint is
                  mounted under ``/{MCP_SECRET_PATH}{MCP_PATH}`` (e.g.
                  ``/<secret>/mcp``). Requests to any other path get a 404.
                  This is the primary gate: it rides in the URL, so it works
                  with clients (like Claude custom connectors) that only let
                  you configure a URL, not custom headers.

MCP_BEARER_TOKEN  Optional second gate. When set, every request except the
                  health probe must send ``Authorization: Bearer <token>`` or
                  it is rejected with 401.

Generate secrets with ``openssl rand -hex 24``.
"""

from __future__ import annotations

import hmac
from typing import Mapping

from starlette.middleware import Middleware

# Paths that bypass the bearer gate. The health probe must stay reachable by
# monitors that do not know the token. It is mounted at the server root,
# outside the (secret) MCP path.
DEFAULT_EXEMPT_PATHS = ("/health",)


def get_secret_path(env: Mapping[str, str]) -> str | None:
    """Return the normalized secret path segment, or None if unset.

    Surrounding slashes are stripped so both ``secret`` and ``/secret/`` work.
    """
    raw = env.get("MCP_SECRET_PATH", "").strip().strip("/")
    return raw or None


def build_mcp_path(base_path: str, env: Mapping[str, str]) -> str:
    """Compose the full MCP mount path, prefixing the secret segment if set.

    ``base_path`` is the plain MCP path (default ``/mcp``). With a secret set
    this becomes ``/<secret>/mcp``.
    """
    if not base_path.startswith("/"):
        base_path = "/" + base_path
    secret = get_secret_path(env)
    if not secret:
        return base_path
    return f"/{secret}{base_path}"


def get_bearer_token(env: Mapping[str, str]) -> str | None:
    """Return the configured bearer token, or None if unset."""
    raw = env.get("MCP_BEARER_TOKEN", "").strip()
    return raw or None


class BearerAuthMiddleware:
    """ASGI middleware rejecting requests without a valid bearer token.

    Uses a constant-time comparison to avoid leaking the token via timing.
    Non-HTTP scopes and exempt paths (the health probe) pass through
    untouched.
    """

    def __init__(self, app, token: str, exempt_paths=DEFAULT_EXEMPT_PATHS):
        self.app = app
        self._expected = f"Bearer {token}"
        self.exempt_paths = tuple(exempt_paths)

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http" or scope.get("path") in self.exempt_paths:
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers") or [])
        provided = headers.get(b"authorization", b"").decode("latin-1")

        if not hmac.compare_digest(provided, self._expected):
            await self._reject(send)
            return

        await self.app(scope, receive, send)

    @staticmethod
    async def _reject(send) -> None:
        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"www-authenticate", b"Bearer"),
                ],
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": b'{"error":"unauthorized"}',
            }
        )


def build_asgi_middleware(env: Mapping[str, str]) -> list:
    """Return the ASGI middleware stack for the HTTP transport.

    Currently just the optional bearer gate; empty when no token is set.
    """
    token = get_bearer_token(env)
    if not token:
        return []
    return [Middleware(BearerAuthMiddleware, token=token)]
