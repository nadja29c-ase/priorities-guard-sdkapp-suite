"""
Unit tests for Increment Claude-01: priority_guardian_claude folder scaffold.

Tests verify:
1. Server creates without backend connectivity
2. Health endpoint returns correct service name
3. OAuth discovery endpoints are present
4. HEAD /mcp returns 200
5. POST /mcp without token returns 401 with WWW-Authenticate
6. Config isolation between priority_guardian and priority_guardian_claude
"""

import pytest
import httpx


@pytest.fixture
def set_dev_env(monkeypatch):
    """Set ENV=dev to allow server creation without production configs."""
    monkeypatch.setenv("ENV", "dev")


@pytest.mark.asyncio
async def test_server_creates_without_backend(set_dev_env):
    """ENV=dev, create_app() completes without error and without making network calls."""
    # Import inside test to ensure ENV is set first
    from mcp_server.priority_guardian_claude.server_dupl import create_app

    # Should not raise, should not require backend connectivity
    app = create_app()
    assert app is not None


@pytest.mark.asyncio
async def test_health_returns_ok(set_dev_env):
    """GET /health returns 200, body contains 'priority-guardian-claude-mcp'."""
    from mcp_server.priority_guardian_claude.server_dupl import create_app

    app = create_app()
    async with httpx.AsyncClient(app=app, base_url="http://test") as client:
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.text == "ok"

        # Also test root endpoint
        resp = await client.get("/")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["service"] == "priority-guardian-claude-mcp"


@pytest.mark.asyncio
async def test_oauth_protected_resource(set_dev_env):
    """GET /.well-known/oauth-protected-resource returns JSON with required keys."""
    from mcp_server.priority_guardian_claude.server_dupl import create_app

    app = create_app()
    async with httpx.AsyncClient(app=app, base_url="http://test") as client:
        resp = await client.get("/.well-known/oauth-protected-resource")
        assert resp.status_code == 200
        body = resp.json()
        assert "resource" in body
        assert "authorization_servers" in body
        assert "scopes_supported" in body


@pytest.mark.asyncio
async def test_head_mcp_returns_200(set_dev_env):
    """HEAD /mcp returns 200 (reachability probe)."""
    from mcp_server.priority_guardian_claude.server_dupl import create_app

    app = create_app()
    async with httpx.AsyncClient(app=app, base_url="http://test") as client:
        resp = await client.head("/mcp")
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_post_mcp_without_token_returns_401(set_dev_env):
    """POST /mcp without Authorization header returns 401 with WWW-Authenticate."""
    from mcp_server.priority_guardian_claude.server_dupl import create_app

    app = create_app()
    async with httpx.AsyncClient(app=app, base_url="http://test") as client:
        resp = await client.post("/mcp", json={})
        assert resp.status_code == 401
        assert "www-authenticate" in resp.headers


def test_config_isolation(set_dev_env):
    """
    Test config module isolation — both config and _dupl modules are independent.

    Part 1: Config module isolation
    - priority_guardian.config.BACKEND_URL and priority_guardian_claude.config.BACKEND_URL
      are independent module-level variables.

    Part 2: Self-contained _dupl module verification
    - The _dupl files (mcp_auth_dupl, http_client_dupl) are complete copies that
      import from priority_guardian_claude.config instead of priority_guardian.config.
    - This ensures complete isolation — no cross-module patching or contamination.
    - In production, each platform runs as a separate Render service anyway.
    """
    # Part 1: Config isolation
    import mcp_server.priority_guardian.config as pg_config
    import mcp_server.priority_guardian_claude.config as claude_config

    # Store original values
    original_pg_backend = pg_config.BACKEND_URL
    original_claude_backend = claude_config.BACKEND_URL

    # Modify Claude config
    claude_config.BACKEND_URL = "http://test-claude-backend:9999"

    # PG config should be unaffected
    assert pg_config.BACKEND_URL == original_pg_backend
    assert claude_config.BACKEND_URL == "http://test-claude-backend:9999"

    # Restore
    claude_config.BACKEND_URL = original_claude_backend

    # Part 2: Self-contained module verification
    # mcp_auth_dupl.py is now fully self-contained — it imports from
    # priority_guardian_claude.config instead of monkeypatching priority_guardian.
    # This means both modules have their own independent config values.
    import mcp_server.priority_guardian.mcp_auth as pg_mcp_auth
    import mcp_server.priority_guardian_claude.mcp_auth_dupl as claude_mcp_auth

    # Verify each module uses its own config values (no cross-contamination)
    pg_expected_origin = pg_mcp_auth._extract_origin(pg_config.MCP_SERVER_URL)
    claude_expected_origin = claude_mcp_auth._extract_origin(claude_config.MCP_SERVER_URL)

    assert pg_mcp_auth._MCP_ORIGIN == pg_expected_origin, (
        f"PG mcp_auth should use PG config. Expected {pg_expected_origin}, "
        f"got {pg_mcp_auth._MCP_ORIGIN}."
    )
    assert claude_mcp_auth._MCP_ORIGIN == claude_expected_origin, (
        f"Claude mcp_auth_dupl should use Claude config. Expected {claude_expected_origin}, "
        f"got {claude_mcp_auth._MCP_ORIGIN}."
    )

    # Verify complete isolation — no shared module globals
    # (This is the clean architecture post-refactor benefit)
    assert pg_mcp_auth.PG_JWKS_URL == pg_config.PG_JWKS_URL
    assert claude_mcp_auth.PG_JWKS_URL == claude_config.PG_JWKS_URL


# =============================================================================
# Increment Claude-02: Tool Wiring + Response Adapter Tests
# =============================================================================


@pytest.mark.asyncio
async def test_list_tools_returns_public_tools_only(set_dev_env):
    """list_tools_for_claude returns only public tools from TOOL_REGISTRY."""
    from mcp_server.priority_guardian.tools import TOOL_REGISTRY
    from mcp_server.priority_guardian_claude.tools_list_dupl import list_tools_for_claude

    expected_public_names = {
        name for name, td in TOOL_REGISTRY.items() if td.visibility == "public"
    }
    tools = await list_tools_for_claude()
    assert {t.name for t in tools} == expected_public_names


@pytest.mark.asyncio
async def test_list_tools_annotations_match_registry(set_dev_env):
    """Tool annotations match ToolDefinition fields."""
    from mcp_server.priority_guardian.tools import TOOL_REGISTRY
    from mcp_server.priority_guardian_claude.tools_list_dupl import list_tools_for_claude

    tools = await list_tools_for_claude()
    for tool in tools:
        assert tool.annotations is not None
        assert tool.annotations.title is not None
        assert len(tool.annotations.title) > 0
        assert tool.annotations.readOnlyHint == TOOL_REGISTRY[tool.name].read_only_hint
        assert tool.annotations.destructiveHint == TOOL_REGISTRY[tool.name].destructive_hint
        assert tool.annotations.openWorldHint == TOOL_REGISTRY[tool.name].open_world_hint
        # get_priorities has _meta for widget prefetch; others have None
        if tool.name == "get_priorities":
            assert tool.meta is not None
        else:
            assert tool.meta is None


@pytest.mark.asyncio
async def test_list_tools_title_derived_correctly(set_dev_env):
    """Tool titles are derived from snake_case names."""
    from mcp_server.priority_guardian_claude.tools_list_dupl import list_tools_for_claude

    tools = await list_tools_for_claude()
    titles = {t.name: t.annotations.title for t in tools}
    assert titles["get_priorities"] == "Get Priorities"
    assert titles["render_weekly_report"] == "Render Weekly Report"
    assert titles["onboarding_calendar_setup"] == "Onboarding Calendar Setup"


@pytest.mark.asyncio
async def test_adapter_moves_string_guidance_to_content(set_dev_env):
    """Adapter moves string assistant_guidance to content."""
    from mcp import types as mcp_types
    from mcp_server.priority_guardian_claude.response_adapter_dupl import adapt_tool_result

    result = mcp_types.CallToolResult(
        content=[mcp_types.TextContent(type="text", text="Short summary.")],
        structuredContent={"success": True, "data": {"foo": "bar"}, "assistant_guidance": "Do not repeat priorities."},
    )
    adapted = adapt_tool_result(result)
    assert "Do not repeat priorities." in adapted.content[0].text
    assert "Short summary." in adapted.content[0].text
    assert "assistant_guidance" not in adapted.structuredContent
    assert adapted.structuredContent["data"] == {"foo": "bar"}
    assert "_meta" not in adapted.structuredContent


@pytest.mark.asyncio
async def test_adapter_moves_dict_guidance_to_content(set_dev_env):
    """Adapter moves dict assistant_guidance to content as JSON."""
    from mcp import types as mcp_types
    from mcp_server.priority_guardian_claude.response_adapter_dupl import adapt_tool_result

    result = mcp_types.CallToolResult(
        content=[mcp_types.TextContent(type="text", text="Summary.")],
        structuredContent={
            "success": True,
            "data": {},
            "assistant_guidance": {"action": "PRIORITY_CREATED", "instruction": "Do not list priorities."},
        },
    )
    adapted = adapt_tool_result(result)
    assert "PRIORITY_CREATED" in adapted.content[0].text
    assert "Do not list priorities." in adapted.content[0].text
    assert "assistant_guidance" not in adapted.structuredContent


@pytest.mark.asyncio
async def test_adapter_handles_no_meta_in_structured_content(set_dev_env):
    """Adapter works when structuredContent has no _meta key."""
    from mcp import types as mcp_types
    from mcp_server.priority_guardian_claude.response_adapter_dupl import adapt_tool_result

    result = mcp_types.CallToolResult(
        content=[mcp_types.TextContent(type="text", text="Summary.")],
        structuredContent={"success": True, "data": {}, "assistant_guidance": "Some guidance."},
    )
    adapted = adapt_tool_result(result)
    assert "Some guidance." in adapted.content[0].text
    assert "assistant_guidance" not in adapted.structuredContent


@pytest.mark.asyncio
async def test_adapter_handles_no_structured_content(set_dev_env):
    """Adapter returns new object when structuredContent is None."""
    from mcp import types as mcp_types
    from mcp_server.priority_guardian_claude.response_adapter_dupl import adapt_tool_result

    result = mcp_types.CallToolResult(
        content=[mcp_types.TextContent(type="text", text="Summary.")],
        structuredContent=None,
    )
    adapted = adapt_tool_result(result)
    assert adapted is not result
    assert adapted.content[0].text == "Summary."
    assert adapted.structuredContent is None


@pytest.mark.asyncio
async def test_adapter_does_not_modify_data(set_dev_env):
    """Adapter preserves data and strips _meta from structuredContent."""
    from mcp import types as mcp_types
    from mcp_server.priority_guardian_claude.response_adapter_dupl import adapt_tool_result

    result = mcp_types.CallToolResult(
        content=[mcp_types.TextContent(type="text", text="Summary.")],
        structuredContent={
            "success": True,
            "data": {"priorities": [{"id": "1", "name": "Test"}], "otherEvents": [{"title": "Meeting"}]},
            "assistant_guidance": "guidance",
            "_meta": {"openai/outputTemplate": "ui://widget/test.html"},
        },
    )
    adapted = adapt_tool_result(result)
    assert adapted.structuredContent["data"]["priorities"] == [{"id": "1", "name": "Test"}]
    assert adapted.structuredContent["data"]["otherEvents"] == [{"title": "Meeting"}]
    assert len(adapted.structuredContent["data"]["otherEvents"]) == 1
    assert "_meta" not in adapted.structuredContent
    assert "assistant_guidance" not in adapted.structuredContent


@pytest.mark.asyncio
async def test_adapter_does_not_mutate_original(set_dev_env):
    """Adapter returns new object, original is unchanged."""
    from mcp import types as mcp_types
    from mcp_server.priority_guardian_claude.response_adapter_dupl import adapt_tool_result

    original_structured = {
        "success": True,
        "data": {"foo": "bar"},
        "assistant_guidance": "guidance",
        "_meta": {"openai/outputTemplate": "ui://widget/test.html"},
    }
    result = mcp_types.CallToolResult(
        content=[mcp_types.TextContent(type="text", text="Summary.")],
        structuredContent=original_structured,
    )
    adapted = adapt_tool_result(result)
    assert adapted is not result
    assert "assistant_guidance" in result.structuredContent
    assert "_meta" in result.structuredContent


@pytest.mark.asyncio
async def test_list_tools_for_claude_directly(set_dev_env):
    """list_tools_for_claude returns sorted list of Tool objects."""
    from mcp import types as mcp_types
    from mcp_server.priority_guardian_claude.tools_list_dupl import list_tools_for_claude

    tools = await list_tools_for_claude()
    assert len(tools) > 0
    assert all(isinstance(t, mcp_types.Tool) for t in tools)
    names = [t.name for t in tools]
    assert names == sorted(names)


# =============================================================================
# Increment Claude-04: Data Serialization Tests
# =============================================================================


@pytest.mark.asyncio
async def test_adapter_includes_data_in_content(set_dev_env):
    """Adapter serializes structuredContent.data into content for Claude."""
    from mcp import types as mcp_types
    from mcp_server.priority_guardian_claude.response_adapter_dupl import adapt_tool_result

    result = mcp_types.CallToolResult(
        content=[mcp_types.TextContent(type="text", text="Summary.")],
        structuredContent={
            "success": True,
            "data": {
                "priorities": [{"name": "Ship PG", "calendarKeyword": "P1", "actualHours": 7.0}],
                "timeAllocation": {"totalTrackedHours": 40.25},
            },
            "assistant_guidance": "Do not repeat priority names.",
        },
    )
    adapted = adapt_tool_result(result)
    # Guidance present
    assert "Do not repeat priority names." in adapted.content[0].text
    # Data present — Claude can read priority name and hours
    assert "Ship PG" in adapted.content[0].text
    assert "7.0" in adapted.content[0].text
    assert "40.25" in adapted.content[0].text
    # Summary present
    assert "Summary." in adapted.content[0].text
    # Order: guidance before data
    guidance_pos = adapted.content[0].text.index("Do not repeat priority names.")
    summary_pos = adapted.content[0].text.index("Summary.")
    data_pos = adapted.content[0].text.index("Ship PG")
    assert guidance_pos < summary_pos < data_pos


@pytest.mark.asyncio
async def test_adapter_handles_empty_data(set_dev_env):
    """Adapter handles empty data dict without crash."""
    from mcp import types as mcp_types
    from mcp_server.priority_guardian_claude.response_adapter_dupl import adapt_tool_result

    result = mcp_types.CallToolResult(
        content=[mcp_types.TextContent(type="text", text="Summary.")],
        structuredContent={
            "success": True,
            "data": {},
            "assistant_guidance": "Some guidance.",
        },
    )
    adapted = adapt_tool_result(result)
    assert "Some guidance." in adapted.content[0].text
    # No crash on empty data


@pytest.mark.asyncio
async def test_adapter_handles_missing_data_key(set_dev_env):
    """Adapter handles missing data key without crash."""
    from mcp import types as mcp_types
    from mcp_server.priority_guardian_claude.response_adapter_dupl import adapt_tool_result

    result = mcp_types.CallToolResult(
        content=[mcp_types.TextContent(type="text", text="Summary.")],
        structuredContent={
            "success": True,
            "assistant_guidance": "Some guidance.",
            # no "data" key at all
        },
    )
    adapted = adapt_tool_result(result)
    assert "Some guidance." in adapted.content[0].text
    # No crash


@pytest.mark.asyncio
async def test_adapter_data_preserved_in_structured_content(set_dev_env):
    """Adapter preserves data in structuredContent while also serializing to content."""
    from mcp import types as mcp_types
    from mcp_server.priority_guardian_claude.response_adapter_dupl import adapt_tool_result

    result = mcp_types.CallToolResult(
        content=[mcp_types.TextContent(type="text", text="Summary.")],
        structuredContent={
            "success": True,
            "data": {"priorities": [{"name": "Test"}]},
            "assistant_guidance": "guidance",
        },
    )
    adapted = adapt_tool_result(result)
    # Data still in structuredContent (unchanged)
    assert adapted.structuredContent["data"] == {"priorities": [{"name": "Test"}]}
    # Data also in content (serialized)
    assert "Test" in adapted.content[0].text


# =============================================================================
# Increment Claude-05: Size-Based Data Trimming Tests
# =============================================================================


@pytest.mark.asyncio
async def test_adapter_strips_large_lists_from_content(set_dev_env):
    """Adapter strips lists with >10 items from content serialization."""
    from mcp import types as mcp_types
    from mcp_server.priority_guardian_claude.response_adapter_dupl import adapt_tool_result

    result = mcp_types.CallToolResult(
        content=[mcp_types.TextContent(type="text", text="Summary.")],
        structuredContent={
            "success": True,
            "data": {
                "priorities": [{"name": "Ship PG"}],
                "otherEvents": [{"title": f"Event {i}"} for i in range(23)],
            },
            "assistant_guidance": "guidance",
        },
    )
    adapted = adapt_tool_result(result)
    # Priority data present — small list passes through
    assert "Ship PG" in adapted.content[0].text
    # Large event list stripped from content
    assert "Event 0" not in adapted.content[0].text
    assert "Event 22" not in adapted.content[0].text
    # structuredContent.data unchanged — large list still there for any downstream consumer
    assert len(adapted.structuredContent["data"]["otherEvents"]) == 23


@pytest.mark.asyncio
async def test_adapter_keeps_small_lists_in_content(set_dev_env):
    """Adapter keeps lists with <=10 items in content serialization."""
    from mcp import types as mcp_types
    from mcp_server.priority_guardian_claude.response_adapter_dupl import adapt_tool_result

    # Simulates get_priority_events returning 4 priorityEvents — must pass through
    result = mcp_types.CallToolResult(
        content=[mcp_types.TextContent(type="text", text="Summary.")],
        structuredContent={
            "success": True,
            "data": {
                "priorityEvents": [
                    {"title": "P1: Deep work", "matchedKeywords": ["P1"]},
                    {"title": "P1: Planning", "matchedKeywords": ["P1"]},
                    {"title": "P1: Review", "matchedKeywords": ["P1"]},
                    {"title": "P1: Build", "matchedKeywords": ["P1"]},
                ],
            },
            "assistant_guidance": "Group events and call render_weekly_report.",
        },
    )
    adapted = adapt_tool_result(result)
    # Small list (4 items) passes through — Claude needs these to group
    assert "P1: Deep work" in adapted.content[0].text
    assert "P1: Build" in adapted.content[0].text


@pytest.mark.asyncio
async def test_adapter_threshold_boundary(set_dev_env):
    """Adapter threshold is >10, not >=10."""
    from mcp import types as mcp_types
    from mcp_server.priority_guardian_claude.response_adapter_dupl import adapt_tool_result

    # Exactly 10 items — should pass through (threshold is > 10, not >= 10)
    result = mcp_types.CallToolResult(
        content=[mcp_types.TextContent(type="text", text="Summary.")],
        structuredContent={
            "success": True,
            "data": {"items": [{"id": i} for i in range(10)]},
            "assistant_guidance": "guidance",
        },
    )
    adapted = adapt_tool_result(result)
    assert '"id": 0' in adapted.content[0].text  # 10 items passes through

    # 11 items — should be stripped
    result2 = mcp_types.CallToolResult(
        content=[mcp_types.TextContent(type="text", text="Summary.")],
        structuredContent={
            "success": True,
            "data": {"items": [{"id": i} for i in range(11)]},
            "assistant_guidance": "guidance",
        },
    )
    adapted2 = adapt_tool_result(result2)
    assert '"id": 0' not in adapted2.content[0].text  # 11 items stripped


@pytest.mark.asyncio
async def test_adapter_handles_non_dict_data(set_dev_env):
    """Adapter handles non-dict data without crash."""
    from mcp import types as mcp_types
    from mcp_server.priority_guardian_claude.response_adapter_dupl import adapt_tool_result

    # data is a list, not a dict — adapter must not crash
    result = mcp_types.CallToolResult(
        content=[mcp_types.TextContent(type="text", text="Summary.")],
        structuredContent={
            "success": True,
            "data": [{"id": 1}, {"id": 2}],
            "assistant_guidance": "guidance",
        },
    )
    adapted = adapt_tool_result(result)
    # No crash — serialized as-is
    assert "guidance" in adapted.content[0].text


# =============================================================================
# Increment Claude-06: Dashboard Widget Tests
# =============================================================================


@pytest.mark.asyncio
async def test_adapt_get_priorities_meta_sets_widget_uri(set_dev_env):
    """adapt_get_priorities_meta sets _meta.ui.resourceUri for widget linking."""
    from mcp import types as mcp_types
    from mcp_server.priority_guardian_claude.response_adapter_dupl import adapt_get_priorities_meta
    from mcp_server.priority_guardian_claude.handlers.resources_dupl import WIDGET_URI

    result = mcp_types.CallToolResult(
        content=[mcp_types.TextContent(type="text", text="3 priorities")],
        structuredContent={"success": True, "data": {"priorities": []}},
    )
    adapted = adapt_get_priorities_meta(result)
    assert adapted.meta is not None
    # Correct nested structure per MCP Apps spec.
    # Compare against the imported constant, never a literal — a literal goes stale
    # on every WIDGET_URI bump and silently red-lines this file (v1 survived v2, v3, v4).
    assert adapted.meta.get("ui", {}).get("resourceUri") == WIDGET_URI
    # Content and structuredContent unchanged
    assert adapted.content == result.content
    assert adapted.structuredContent == result.structuredContent


@pytest.mark.asyncio
async def test_adapt_get_priorities_meta_preserves_existing_meta(set_dev_env):
    """adapt_get_priorities_meta preserves existing _meta fields."""
    from mcp import types as mcp_types
    from mcp_server.priority_guardian_claude.response_adapter_dupl import adapt_get_priorities_meta
    from mcp_server.priority_guardian_claude.handlers.resources_dupl import WIDGET_URI

    result = mcp_types.CallToolResult(
        content=[mcp_types.TextContent(type="text", text="3 priorities")],
        structuredContent={"success": True},
        _meta={"existing_key": "existing_value"},
    )
    adapted = adapt_get_priorities_meta(result)
    # resourceUri added to ui dict
    assert adapted.meta["ui"]["resourceUri"] == WIDGET_URI
    # Non-ui keys preserved
    assert adapted.meta["existing_key"] == "existing_value"


@pytest.mark.asyncio
async def test_adapt_get_priorities_meta_skips_error_results(set_dev_env):
    """adapt_get_priorities_meta does not modify error results."""
    from mcp import types as mcp_types
    from mcp_server.priority_guardian_claude.response_adapter_dupl import adapt_get_priorities_meta

    result = mcp_types.CallToolResult(
        content=[mcp_types.TextContent(type="text", text="Error occurred")],
        isError=True,
    )
    adapted = adapt_get_priorities_meta(result)
    # Error result returns new object with same values (no widget link added)
    assert adapted is not result
    assert adapted.content[0].text == "Error occurred"
    assert adapted.isError is True
    assert adapted.meta is None


# =============================================================================
# Widget Discovery Tests
# =============================================================================


@pytest.mark.asyncio
async def test_get_priorities_has_widget_meta(set_dev_env):
    """get_priorities tool has _meta.ui.resourceUri for host-side prefetch."""
    from mcp_server.priority_guardian_claude.tools_list_dupl import list_tools_for_claude
    from mcp_server.priority_guardian_claude.handlers.resources_dupl import WIDGET_URI

    tools = await list_tools_for_claude()
    tool = next(t for t in tools if t.name == "get_priorities")
    assert tool.meta is not None
    assert tool.meta.get("ui", {}).get("resourceUri") == WIDGET_URI


@pytest.mark.asyncio
async def test_non_widget_tools_have_no_meta(set_dev_env):
    """Non-widget tools have _meta=None."""
    from mcp_server.priority_guardian_claude.tools_list_dupl import list_tools_for_claude

    tools = await list_tools_for_claude()
    for tool in tools:
        if tool.name != "get_priorities":
            assert tool.meta is None, f"{tool.name} should have _meta=None"


def test_widget_uri_consistency(set_dev_env):
    """WIDGET_URI constants match between response_adapter and resources."""
    from mcp_server.priority_guardian_claude.response_adapter_dupl import WIDGET_URI
    from mcp_server.priority_guardian_claude.handlers.resources_dupl import WIDGET_URI as RESOURCE_URI
    assert WIDGET_URI == RESOURCE_URI


@pytest.mark.asyncio
async def test_list_resources_returns_widget(set_dev_env):
    """list_resources returns the widget resource."""
    from mcp_server.priority_guardian_claude.handlers.resources_dupl import list_resources, WIDGET_URI

    resources = await list_resources()
    assert len(resources) == 1
    assert str(resources[0].uri) == WIDGET_URI
    assert resources[0].mimeType == "text/html+mcp"


@pytest.mark.asyncio
async def test_advertised_widget_uri_is_actually_servable(set_dev_env):
    """The URI list_resources() advertises must be one handle_read_resource() serves.

    THIS IS THE TEST THE OTHERS CANNOT BE. Comparing WIDGET_URI against WIDGET_URI
    proves nothing — both sides read the same constant. So this test deliberately
    does NOT pass WIDGET_URI to the read handler. It takes whatever list_resources()
    actually advertises and feeds that back in, which is the only way to catch the
    advertise/serve paths diverging.

    Concretely: if handle_read_resource() were changed to match a stale literal like
    "ui://pg-claude/dashboard-v3.html" while list_resources() still advertised v4,
    every other test in this file would pass and Claude would get empty contents and
    silently fall back to a cached bundle. That failure mode produces no error in
    logs — see doc/OPERATIONS_PREDEPLOY.md.

    Survives every version bump, because no version literal appears anywhere in it.
    """
    from mcp import types as mcp_types
    from mcp_server.priority_guardian_claude.handlers.resources_dupl import (
        WIDGET_FALLBACK_HTML,
        handle_read_resource,
        list_resources,
    )

    resources = await list_resources()
    advertised_uri = str(resources[0].uri)

    req = mcp_types.ReadResourceRequest(
        method="resources/read",
        params=mcp_types.ReadResourceRequestParams(uri=advertised_uri),
    )
    result = await handle_read_resource(req)

    assert result.contents, (
        f"list_resources() advertises {advertised_uri} but handle_read_resource() "
        f"returned no contents for it — the advertise and serve paths have diverged. "
        f"In production this is silent: Claude serves a cached bundle instead."
    )
    content = result.contents[0]
    assert str(content.uri) == advertised_uri
    assert content.mimeType == "text/html+mcp"

    # Guard the silent-failure trap: _load_widget_html() swallows every error and
    # returns WIDGET_FALLBACK_HTML, so the server starts fine and serves failure text.
    assert content.text != WIDGET_FALLBACK_HTML, (
        "handle_read_resource() served WIDGET_FALLBACK_HTML — the bundle is missing "
        "from disk or unreadable. The server does not crash on this; it just ships "
        "'Widget failed to load' to users."
    )
    assert "<title>Priority Guardian Dashboard</title>" in content.text, (
        "Served content is not the real widget bundle."
    )


@pytest.mark.asyncio
async def test_read_resource_unknown_uri_returns_empty(set_dev_env):
    """An unrecognised URI yields empty contents, without raising.

    Not decoration. Without this, the test above would still pass if
    handle_read_resource() returned the widget for ANY uri — which would make its
    positive assertion meaningless. This pins the handler to actually discriminating.
    """
    from mcp import types as mcp_types
    from mcp_server.priority_guardian_claude.handlers.resources_dupl import handle_read_resource

    req = mcp_types.ReadResourceRequest(
        method="resources/read",
        params=mcp_types.ReadResourceRequestParams(uri="ui://pg-claude/does-not-exist.html"),
    )
    result = await handle_read_resource(req)

    assert result.contents == []
