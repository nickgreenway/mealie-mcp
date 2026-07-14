"""Tests for safe/read-mostly tool mode (src/safe_mode.py)."""

import sys
from pathlib import Path

import pytest

SRC = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(SRC))

import safe_mode  # noqa: E402


class TestGetMode:
    def test_default_full(self):
        assert safe_mode.get_mode({}) == "full"

    def test_safe(self):
        assert safe_mode.get_mode({"MEALIE_MCP_MODE": "SAFE"}) == "safe"

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            safe_mode.get_mode({"MEALIE_MCP_MODE": "readonly"})


class TestDenyComposition:
    def test_default_is_union_of_groups(self):
        assert safe_mode.DEFAULT_SAFE_DENY == (
            safe_mode.DESTRUCTIVE_TOOLS | safe_mode.EXTERNAL_EFFECT_TOOLS
        )

    def test_groups_do_not_overlap(self):
        assert not (safe_mode.DESTRUCTIVE_TOOLS & safe_mode.EXTERNAL_EFFECT_TOOLS)

    def test_core_workflow_tools_are_not_denied(self):
        keep = {
            "mealie_recipes_search",
            "mealie_recipes_get",
            "mealie_recipes_create",
            "mealie_recipes_create_from_url",
            "mealie_recipes_update",
            "mealie_mealplans_create",
            "mealie_mealplans_update",
            "mealie_shopping_items_add",
            "mealie_shopping_generate_from_mealplan",
        }
        assert not (keep & safe_mode.DEFAULT_SAFE_DENY)

    def test_extra_deny_parsing(self):
        assert safe_mode.get_extra_deny({"MEALIE_MCP_SAFE_EXTRA_DENY": "a, b ,, c"}) == {
            "a",
            "b",
            "c",
        }
        assert safe_mode.get_extra_deny({}) == frozenset()

    def test_get_deny_set_includes_extras(self):
        ds = safe_mode.get_deny_set({"MEALIE_MCP_SAFE_EXTRA_DENY": "mealie_recipes_update"})
        assert "mealie_recipes_update" in ds
        assert safe_mode.DEFAULT_SAFE_DENY <= ds


class _FakeTool:
    def __init__(self, name):
        self.name = name


class _FakeProvider:
    def __init__(self, names):
        self._names = list(names)

    async def list_tools(self):
        return [_FakeTool(n) for n in self._names]

    def remove_tool(self, name, version=None):
        if name not in self._names:
            raise KeyError(name)
        self._names.remove(name)


class _FakeMCP:
    def __init__(self, names):
        self.local_provider = _FakeProvider(names)

    def names(self):
        return set(self.local_provider._names)


# A registry that includes some denied tools plus some safe ones.
_REGISTRY = [
    "mealie_recipes_search",
    "mealie_recipes_create",
    "mealie_recipes_update",
    "mealie_recipes_delete",
    "mealie_webhooks_create",
    "mealie_recipes_shared_create",
    "mealie_shopping_clear_checked",
    "ping",
]


class TestApplySafeMode:
    def test_full_mode_is_noop(self):
        mcp = _FakeMCP(_REGISTRY)
        removed = safe_mode.apply_safe_mode(mcp, env={})
        assert removed == []
        assert mcp.names() == set(_REGISTRY)

    def test_safe_mode_removes_only_denied_registered(self):
        mcp = _FakeMCP(_REGISTRY)
        removed = safe_mode.apply_safe_mode(mcp, env={"MEALIE_MCP_MODE": "safe"})
        assert set(removed) == {
            "mealie_recipes_delete",
            "mealie_webhooks_create",
            "mealie_recipes_shared_create",
            "mealie_shopping_clear_checked",
        }
        # Safe tools remain.
        assert "mealie_recipes_search" in mcp.names()
        assert "mealie_recipes_update" in mcp.names()
        assert "ping" in mcp.names()
        # Nothing denied remains.
        assert not (safe_mode.DEFAULT_SAFE_DENY & mcp.names())

    def test_extra_deny_removes_additional(self):
        mcp = _FakeMCP(_REGISTRY)
        removed = safe_mode.apply_safe_mode(
            mcp,
            env={
                "MEALIE_MCP_MODE": "safe",
                "MEALIE_MCP_SAFE_EXTRA_DENY": "mealie_recipes_update",
            },
        )
        assert "mealie_recipes_update" in removed
        assert "mealie_recipes_update" not in mcp.names()

    def test_missing_denied_name_is_skipped_without_error(self, capsys):
        # Registry with no denied tools present at all.
        mcp = _FakeMCP(["mealie_recipes_search", "ping"])
        removed = safe_mode.apply_safe_mode(mcp, env={"MEALIE_MCP_MODE": "safe"})
        assert removed == []
        assert mcp.names() == {"mealie_recipes_search", "ping"}
        err = capsys.readouterr().err
        assert "not registered" in err
