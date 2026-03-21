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
    Test config module isolation and document monkeypatch behavior.

    Part 1: Config module isolation
    - priority_guardian.config.BACKEND_URL and priority_guardian_claude.config.BACKEND_URL
      are independent module-level variables.

    Part 2: Monkeypatch documentation
    - Importing mcp_auth_dupl patches priority_guardian.mcp_auth's globals.
    - This is INTENTIONAL and SAFE — in production, each platform runs as a
      separate Render service (separate process), so there is no conflict.
    - This documents the known limitation and why the post-OpenAI refactor
      into mcp_server/shared/ with proper config injection is needed.
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

    # Part 2: Monkeypatch behavior documentation
    # After importing mcp_auth_dupl, priority_guardian.mcp_auth's globals
    # reflect the Claude config values. This is expected and intentional.
    import mcp_server.priority_guardian.mcp_auth as pg_mcp_auth

    # Save original values before the import triggers monkeypatching
    original_mcp_origin = pg_mcp_auth._MCP_ORIGIN
    original_pg_jwks_url = pg_mcp_auth.PG_JWKS_URL
    original_pg_issuer = pg_mcp_auth.PG_ISSUER
    original_pg_audience = pg_mcp_auth.PG_AUDIENCE
    original_mcp_server_url = pg_mcp_auth.MCP_SERVER_URL
    original_mcp_resource_url = pg_mcp_auth.MCP_RESOURCE_URL
    original_jwks_cache_ttl = pg_mcp_auth.JWKS_CACHE_TTL_SECONDS
    original_jwks_max_stale = pg_mcp_auth.JWKS_MAX_STALE_SECONDS
    original_jwks_fetch_timeout = pg_mcp_auth.JWKS_FETCH_TIMEOUT_SECONDS
    original_token_expiry_grace = pg_mcp_auth.TOKEN_EXPIRY_GRACE_SECONDS

    import mcp_server.priority_guardian_claude.mcp_auth_dupl  # noqa: F401 - import for side effect

    # The monkeypatch in mcp_auth_dupl.py sets _MCP_ORIGIN to Claude's URL.
    # This is the expected behavior — verify it happened.
    # NOTE: This is intentional and safe in production (separate processes).
    # The post-OpenAI refactor will move shared logic to mcp_server/shared/
    # with proper config injection to eliminate this coupling.
    expected_origin = pg_mcp_auth._extract_origin(claude_config.MCP_SERVER_URL)
    assert pg_mcp_auth._MCP_ORIGIN == expected_origin, (
        f"Expected _MCP_ORIGIN to be patched to Claude config value {expected_origin}, "
        f"got {pg_mcp_auth._MCP_ORIGIN}. This is the expected monkeypatch behavior."
    )

    # Restore all patched globals to prevent test session pollution
    pg_mcp_auth._MCP_ORIGIN = original_mcp_origin
    pg_mcp_auth.PG_JWKS_URL = original_pg_jwks_url
    pg_mcp_auth.PG_ISSUER = original_pg_issuer
    pg_mcp_auth.PG_AUDIENCE = original_pg_audience
    pg_mcp_auth.MCP_SERVER_URL = original_mcp_server_url
    pg_mcp_auth.MCP_RESOURCE_URL = original_mcp_resource_url
    pg_mcp_auth.JWKS_CACHE_TTL_SECONDS = original_jwks_cache_ttl
    pg_mcp_auth.JWKS_MAX_STALE_SECONDS = original_jwks_max_stale
    pg_mcp_auth.JWKS_FETCH_TIMEOUT_SECONDS = original_jwks_fetch_timeout
    pg_mcp_auth.TOKEN_EXPIRY_GRACE_SECONDS = original_token_expiry_grace


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
    """Tool annotations match ToolDefinition fields, _meta is None."""
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
