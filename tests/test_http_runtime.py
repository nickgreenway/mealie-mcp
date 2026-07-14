"""Tests for the opt-in HTTP transport runtime (src/http_runtime.py).

These verify env parsing and the transport dispatch without launching a real
server, plus that stdio remains the default (regression guard for existing
stdio users).
"""

import sys
from pathlib import Path

import pytest

# Ensure src is importable the same way server.py does.
SRC = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(SRC))

import http_runtime  # noqa: E402


class TestGetTransport:
    def test_default_is_stdio(self):
        assert http_runtime.get_transport({}) == "stdio"

    def test_explicit_stdio(self):
        assert http_runtime.get_transport({"MCP_TRANSPORT": "stdio"}) == "stdio"

    def test_http(self):
        assert http_runtime.get_transport({"MCP_TRANSPORT": "http"}) == "http"

    @pytest.mark.parametrize(
        "value", ["HTTP", " http ", "streamable-http", "streamable_http"]
    )
    def test_http_aliases_and_case(self, value):
        assert http_runtime.get_transport({"MCP_TRANSPORT": value}) == "http"

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            http_runtime.get_transport({"MCP_TRANSPORT": "grpc"})


class TestGetHttpSettings:
    def test_defaults(self):
        s = http_runtime.get_http_settings({})
        assert s == {"host": "0.0.0.0", "port": 8000, "path": "/mcp"}

    def test_overrides(self):
        s = http_runtime.get_http_settings(
            {"MCP_HOST": "127.0.0.1", "MCP_PORT": "9001", "MCP_PATH": "/custom"}
        )
        assert s == {"host": "127.0.0.1", "port": 9001, "path": "/custom"}

    def test_path_gets_leading_slash(self):
        s = http_runtime.get_http_settings({"MCP_PATH": "mcp"})
        assert s["path"] == "/mcp"

    def test_invalid_port_raises(self):
        with pytest.raises(ValueError):
            http_runtime.get_http_settings({"MCP_PORT": "not-a-number"})


class _FakeMCP:
    """Records how run() was invoked as (args, kwargs) tuples."""

    def __init__(self):
        self.calls = []

    def run(self, *args, **kwargs):
        self.calls.append((args, kwargs))


class TestRunDispatch:
    def test_stdio_calls_bare_run(self):
        mcp = _FakeMCP()
        http_runtime.run(mcp, env={})
        assert mcp.calls == [((), {})]

    def test_http_passes_transport_and_settings(self):
        mcp = _FakeMCP()
        http_runtime.run(
            mcp,
            env={
                "MCP_TRANSPORT": "http",
                "MCP_HOST": "127.0.0.1",
                "MCP_PORT": "8123",
                "MCP_PATH": "/mcp",
            },
        )
        assert mcp.calls == [
            (
                (),
                {
                    "transport": "http",
                    "host": "127.0.0.1",
                    "port": 8123,
                    "path": "/mcp",
                },
            )
        ]
