"""Tests for the optional HTTP auth gate (src/auth.py)."""

import sys
from pathlib import Path

import pytest

SRC = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(SRC))

import auth  # noqa: E402


class TestSecretPath:
    def test_unset_is_none(self):
        assert auth.get_secret_path({}) is None

    def test_empty_is_none(self):
        assert auth.get_secret_path({"MCP_SECRET_PATH": "  "}) is None

    def test_value(self):
        assert auth.get_secret_path({"MCP_SECRET_PATH": "abc123"}) == "abc123"

    def test_surrounding_slashes_stripped(self):
        assert auth.get_secret_path({"MCP_SECRET_PATH": "/abc123/"}) == "abc123"


class TestBuildMcpPath:
    def test_no_secret_returns_base(self):
        assert auth.build_mcp_path("/mcp", {}) == "/mcp"

    def test_with_secret_prefixes(self):
        assert auth.build_mcp_path("/mcp", {"MCP_SECRET_PATH": "s3cr3t"}) == "/s3cr3t/mcp"

    def test_base_without_leading_slash(self):
        assert auth.build_mcp_path("mcp", {"MCP_SECRET_PATH": "s3cr3t"}) == "/s3cr3t/mcp"


class TestBearerToken:
    def test_unset_is_none(self):
        assert auth.get_bearer_token({}) is None

    def test_value(self):
        assert auth.get_bearer_token({"MCP_BEARER_TOKEN": "tok"}) == "tok"


class TestBuildAsgiMiddleware:
    def test_no_token_empty(self):
        assert auth.build_asgi_middleware({}) == []

    def test_token_adds_one_middleware(self):
        mw = auth.build_asgi_middleware({"MCP_BEARER_TOKEN": "tok"})
        assert len(mw) == 1


class _Recorder:
    """Captures ASGI send() events and whether the inner app was called."""

    def __init__(self):
        self.events = []
        self.app_called = False

    async def app(self, scope, receive, send):
        self.app_called = True

    async def send(self, event):
        self.events.append(event)

    @property
    def status(self):
        for e in self.events:
            if e["type"] == "http.response.start":
                return e["status"]
        return None


def _http_scope(path="/mcp", token=None):
    headers = []
    if token is not None:
        headers.append((b"authorization", f"Bearer {token}".encode()))
    return {"type": "http", "path": path, "headers": headers}


@pytest.mark.asyncio
class TestBearerMiddleware:
    async def test_valid_token_passes_through(self):
        rec = _Recorder()
        mw = auth.BearerAuthMiddleware(rec.app, token="tok")
        await mw(_http_scope(token="tok"), None, rec.send)
        assert rec.app_called is True
        assert rec.status is None  # no rejection response

    async def test_missing_token_rejected_401(self):
        rec = _Recorder()
        mw = auth.BearerAuthMiddleware(rec.app, token="tok")
        await mw(_http_scope(token=None), None, rec.send)
        assert rec.app_called is False
        assert rec.status == 401

    async def test_wrong_token_rejected_401(self):
        rec = _Recorder()
        mw = auth.BearerAuthMiddleware(rec.app, token="tok")
        await mw(_http_scope(token="nope"), None, rec.send)
        assert rec.app_called is False
        assert rec.status == 401

    async def test_health_path_exempt(self):
        rec = _Recorder()
        mw = auth.BearerAuthMiddleware(rec.app, token="tok")
        await mw(_http_scope(path="/health", token=None), None, rec.send)
        assert rec.app_called is True
        assert rec.status is None

    async def test_non_http_scope_passes_through(self):
        rec = _Recorder()
        mw = auth.BearerAuthMiddleware(rec.app, token="tok")
        await mw({"type": "lifespan"}, None, rec.send)
        assert rec.app_called is True
