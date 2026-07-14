"""Safe/read-mostly tool mode.

When ``MEALIE_MCP_MODE=safe`` the server unregisters a denylist of risky tools
*before* it starts, so those tools are never even advertised to the client.
This matters most for mobile/remote use, where a stray tap or a prompt
injection should not be able to delete data or exfiltrate it to an external
service.

The default is ``full`` (every tool registered, original behavior unchanged).

Two denylist groups make the intent obvious and easy to tune:

* ``DESTRUCTIVE_TOOLS`` — deletes, merges, and bulk clears. Non-reversible
  data loss.
* ``EXTERNAL_EFFECT_TOOLS`` — tools that push data to a URL the caller
  supplies (webhooks, recipe actions) or expose a recipe via a public share
  link. These are an exfiltration vector from an untrusted prompt.

Reads, creates, updates, and "add" operations stay available in safe mode, so
the core recipe/meal-plan/shopping assistant workflow is unaffected.

Environment variables
---------------------
MEALIE_MCP_MODE             ``full`` (default) | ``safe``
MEALIE_MCP_SAFE_EXTRA_DENY  Optional comma-separated tool names to also remove
                            in safe mode (extends the defaults; ignored in full
                            mode).
"""

from __future__ import annotations

import asyncio
import os
import sys
from typing import Mapping

# --- Non-reversible data loss -------------------------------------------------
DESTRUCTIVE_TOOLS = frozenset(
    {
        # Recipes
        "mealie_recipes_delete",
        "mealie_recipes_bulk_delete",
        "mealie_recipes_shared_delete",
        # Meal plans
        "mealie_mealplans_delete",
        "mealie_mealplans_delete_range",
        "mealie_mealplan_rules_delete",
        # Shopping
        "mealie_shopping_lists_delete",
        "mealie_shopping_items_delete",
        "mealie_shopping_clear_checked",
        "mealie_shopping_delete_recipe_from_list",
        # Organizers / catalog
        "mealie_foods_delete",
        "mealie_foods_merge",
        "mealie_units_delete",
        "mealie_units_merge",
        "mealie_categories_delete",
        "mealie_tags_delete",
        "mealie_tools_delete",
        "mealie_cookbooks_delete",
        # Misc
        "mealie_comments_delete",
        "mealie_timeline_delete",
        "mealie_webhooks_delete",
        "mealie_recipe_actions_delete",
    }
)

# --- Pushes data to a caller-supplied URL / exposes data publicly ------------
EXTERNAL_EFFECT_TOOLS = frozenset(
    {
        # Webhooks POST meal-plan data to an arbitrary URL.
        "mealie_webhooks_create",
        "mealie_webhooks_update",
        "mealie_webhooks_test",
        # Recipe actions POST recipe data to an arbitrary URL.
        "mealie_recipe_actions_create",
        "mealie_recipe_actions_update",
        "mealie_recipe_actions_trigger",
        # Share links expose a recipe via a public, tokenless-to-guess URL.
        "mealie_recipes_shared_create",
    }
)

# The full default denylist applied in safe mode.
DEFAULT_SAFE_DENY = DESTRUCTIVE_TOOLS | EXTERNAL_EFFECT_TOOLS

VALID_MODES = ("full", "safe")


def _env(env: Mapping[str, str] | None) -> Mapping[str, str]:
    return os.environ if env is None else env


def get_mode(env: Mapping[str, str] | None = None) -> str:
    """Return the normalized mode (``full`` or ``safe``)."""
    raw = _env(env).get("MEALIE_MCP_MODE", "full").strip().lower()
    if raw not in VALID_MODES:
        raise ValueError(
            f"Invalid MEALIE_MCP_MODE={raw!r}. Expected 'full' or 'safe'."
        )
    return raw


def get_extra_deny(env: Mapping[str, str] | None = None) -> frozenset:
    """Parse MEALIE_MCP_SAFE_EXTRA_DENY into a set of extra tool names."""
    raw = _env(env).get("MEALIE_MCP_SAFE_EXTRA_DENY", "")
    return frozenset(name.strip() for name in raw.split(",") if name.strip())


def get_deny_set(env: Mapping[str, str] | None = None) -> frozenset:
    """Return the effective denylist (defaults plus any env extras)."""
    return DEFAULT_SAFE_DENY | get_extra_deny(env)


def _registered_tool_names(mcp) -> set:
    """Synchronously collect the names of every currently registered tool."""
    tools = asyncio.run(mcp.local_provider.list_tools())
    return {t.name for t in tools}


def apply_safe_mode(mcp, env: Mapping[str, str] | None = None) -> list:
    """Remove denylisted tools when running in safe mode.

    No-op in full mode. Returns the sorted list of tool names actually
    removed. Denylisted names that are not registered (e.g. renamed upstream)
    are skipped with a warning, so a stale entry never crashes startup.
    """
    e = _env(env)
    if get_mode(e) != "safe":
        return []

    deny = get_deny_set(e)
    registered = _registered_tool_names(mcp)
    to_remove = sorted(deny & registered)
    missing = sorted(deny - registered)

    for name in to_remove:
        mcp.local_provider.remove_tool(name)

    if missing:
        print(
            f"safe-mode: {len(missing)} denylisted tool(s) not registered, "
            f"skipped: {', '.join(missing)}",
            file=sys.stderr,
        )
    print(
        f"safe-mode: removed {len(to_remove)} tool(s); "
        f"{len(registered) - len(to_remove)} remain",
        file=sys.stderr,
    )
    return to_remove
