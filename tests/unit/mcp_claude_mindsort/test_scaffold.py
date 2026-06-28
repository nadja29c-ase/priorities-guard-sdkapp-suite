"""
MindSort Claude MCP Server scaffold tests (MindSort-Claude-01).

Tests the server scaffold without any backend connectivity.
"""

import pytest
from httpx import AsyncClient, ASGITransport


@pytest.fixture
def set_dev_env(monkeypatch):
    """Set ENV=dev for all tests."""
    monkeypatch.setenv("ENV", "dev")


@pytest.fixture(autouse=True)
def restore_mcp_auth_globals():
    """
    Restore clarity.mcp_auth globals after each test.

    Importing mcp_auth_dupl rebinds clarity.mcp_auth.MCP_SERVER_URL (and other globals)
    to Claude config values. This is intentional for runtime but leaks state across tests.
    This fixture saves and restores the original values to prevent cross-test pollution.
    """
    import mcp_server.clarity.mcp_auth as clarity_mcp_auth
    import mcp_server.clarity.config as clarity_config

    # Save original values
    original_values = {
        "mcp_auth.MCP_SERVER_URL": clarity_mcp_auth.MCP_SERVER_URL,
        "mcp_auth.CLARITY_JWKS_URL": clarity_mcp_auth.CLARITY_JWKS_URL,
        "mcp_auth.CLARITY_ISSUER": clarity_mcp_auth.CLARITY_ISSUER,
        "mcp_auth.CLARITY_AUDIENCE": clarity_mcp_auth.CLARITY_AUDIENCE,
        "mcp_auth.TOOL_SCOPES": clarity_mcp_auth.TOOL_SCOPES.copy(),
        "config.MCP_SERVER_URL": clarity_config.MCP_SERVER_URL,
    }

    yield

    # Restore original values
    clarity_mcp_auth.MCP_SERVER_URL = original_values["mcp_auth.MCP_SERVER_URL"]
    clarity_mcp_auth.CLARITY_JWKS_URL = original_values["mcp_auth.CLARITY_JWKS_URL"]
    clarity_mcp_auth.CLARITY_ISSUER = original_values["mcp_auth.CLARITY_ISSUER"]
    clarity_mcp_auth.CLARITY_AUDIENCE = original_values["mcp_auth.CLARITY_AUDIENCE"]
    clarity_mcp_auth.TOOL_SCOPES = original_values["mcp_auth.TOOL_SCOPES"]
    clarity_config.MCP_SERVER_URL = original_values["config.MCP_SERVER_URL"]


@pytest.fixture
async def client(set_dev_env):
    """Create test client for the MindSort Claude server."""
    from mcp_server.mindsort_claude.server_dupl import create_app

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
async def test_server_creates_without_backend(set_dev_env):
    """ENV=dev, create_app() completes with no network calls."""
    from mcp_server.mindsort_claude.server_dupl import create_app

    # Should not raise, even with no backend running
    app = create_app()
    assert app is not None


@pytest.mark.asyncio
async def test_health_returns_ok(client):
    """GET /health returns 200, body contains 'mindsort-claude-mcp'."""
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.text == "ok"

    # Also test root endpoint which returns JSON
    response = await client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "mindsort-claude-mcp"


@pytest.mark.asyncio
async def test_oauth_protected_resource(client):
    """GET /.well-known/oauth-protected-resource returns required fields."""
    response = await client.get("/.well-known/oauth-protected-resource")
    assert response.status_code == 200

    data = response.json()
    assert "resource" in data
    assert "authorization_servers" in data
    assert "scopes_supported" in data

    # resource must end with /mcp
    assert data["resource"].endswith("/mcp")


@pytest.mark.asyncio
async def test_oauth_advertises_pkce_s256(client):
    """GET /.well-known/oauth-authorization-server returns code_challenge_methods_supported == ['S256']."""
    response = await client.get("/.well-known/oauth-authorization-server")
    assert response.status_code == 200

    data = response.json()
    assert "code_challenge_methods_supported" in data
    assert data["code_challenge_methods_supported"] == ["S256"]


@pytest.mark.asyncio
async def test_post_mcp_without_token_returns_401(client):
    """POST /mcp with no Authorization header returns 401 with WWW-Authenticate header."""
    response = await client.post("/mcp", content=b"{}")
    assert response.status_code == 401
    assert "www-authenticate" in response.headers


@pytest.mark.asyncio
async def test_origin_validation_rejects_unknown(client):
    """POST /mcp with unknown Origin returns 401 or 403 (not 200)."""
    # With unknown origin and no token: should be rejected
    # Could be 403 from OriginValidation or 401 from BearerAuth (either proves rejection)
    response = await client.post(
        "/mcp",
        content=b"{}",
        headers={"Origin": "https://evil.example"}
    )
    assert response.status_code in {401, 403}

    # Request with no Origin header must NOT be rejected by origin validation
    # (it will still get 401 from BearerAuth, but that's expected)
    response_no_origin = await client.post("/mcp", content=b"{}")
    # Should be 401 (no token), not 403 (origin rejected)
    assert response_no_origin.status_code == 401


@pytest.mark.asyncio
async def test_config_isolation(set_dev_env, monkeypatch):
    """Config isolation: mindsort_claude config does not affect clarity config.

    NOTE: The autouse restore_mcp_auth_globals fixture handles cleanup of
    globals modified by mcp_auth_dupl import.
    """
    import importlib
    import mcp_server.clarity.config as clarity_config
    import mcp_server.clarity.mcp_auth as clarity_mcp_auth

    # Set a distinct MCP_SERVER_URL for mindsort_claude
    monkeypatch.setenv("CLARITY_CLAUDE_MCP_SERVER_URL", "http://test-claude:9999")

    import mcp_server.mindsort_claude.config as claude_config

    # Reload to pick up env changes
    importlib.reload(clarity_config)
    importlib.reload(claude_config)

    # Verify isolation: claude config should have our test value
    assert claude_config.MCP_SERVER_URL == "http://test-claude:9999"
    # clarity config should have its default (localhost:8002)
    assert clarity_config.MCP_SERVER_URL == "http://localhost:8002"

    # Now test mcp_auth rebinding
    # After importing mcp_auth_dupl, clarity.mcp_auth.MCP_SERVER_URL should reflect Claude's value
    # NOTE: This rebinding is INTENTIONAL and SAFE — the two servers never run
    # in the same process in production. Documents the known limitation.
    import mcp_server.mindsort_claude.mcp_auth_dupl as mcp_auth_dupl

    # Reload mcp_auth_dupl to pick up the new config values and re-apply rebinding
    importlib.reload(mcp_auth_dupl)

    # After reloading mcp_auth_dupl, the shared module's MCP_SERVER_URL is rebound
    assert clarity_mcp_auth.MCP_SERVER_URL == "http://test-claude:9999"


# ============================================================================
# MindSort-Claude-02: Tool Listing Tests
# ============================================================================


@pytest.mark.asyncio
async def test_list_tools_returns_all_registered(set_dev_env):
    """list_tools_for_claude returns all tools in TOOL_REGISTRY (no visibility filter)."""
    from mcp_server.clarity.tools import TOOL_REGISTRY
    from mcp_server.mindsort_claude.tools_list_dupl import list_tools_for_claude

    tools = await list_tools_for_claude()
    tool_names = {t.name for t in tools}

    assert tool_names == set(TOOL_REGISTRY.keys())


@pytest.mark.asyncio
async def test_list_tools_annotations(set_dev_env):
    """All tools have annotations with required fields, _meta is None."""
    from mcp_server.clarity.tools import TOOL_REGISTRY
    from mcp_server.mindsort_claude.tools_list_dupl import list_tools_for_claude

    tools = await list_tools_for_claude()

    for tool in tools:
        # annotations must exist and have title
        assert tool.annotations is not None
        assert isinstance(tool.annotations.title, str)
        assert len(tool.annotations.title) > 0

        # readOnlyHint and openWorldHint match source
        source = TOOL_REGISTRY[tool.name]
        assert tool.annotations.readOnlyHint == source.read_only_hint
        assert tool.annotations.openWorldHint == source.open_world_hint

        # Widget-producing tools have _meta.ui.resourceUri; others have _meta=None
        widget_tools = {"organize_thoughts", "load_saved_board", "start_prioritization_flow", "edit_board"}
        if tool.name in widget_tools:
            assert tool.meta is not None
            assert "ui" in tool.meta
            assert "resourceUri" in tool.meta["ui"]
        else:
            assert tool.meta is None


@pytest.mark.asyncio
async def test_destructive_hint_override(set_dev_env):
    """destructiveHint overrides work correctly for Claude."""
    from mcp_server.clarity.tools import TOOL_REGISTRY
    from mcp_server.mindsort_claude.tools_list_dupl import list_tools_for_claude

    tools = await list_tools_for_claude()
    tools_by_name = {t.name: t for t in tools}

    # start_prioritization_flow: source is False, override is True
    assert TOOL_REGISTRY["start_prioritization_flow"].destructive_hint is False
    assert tools_by_name["start_prioritization_flow"].annotations.destructiveHint is True

    # organize_thoughts: known-destructive, should be True
    assert tools_by_name["organize_thoughts"].annotations.destructiveHint is True

    # read_board_before_editing: read-only, should be False
    assert tools_by_name["read_board_before_editing"].annotations.destructiveHint is False


@pytest.mark.asyncio
async def test_title_derivation(set_dev_env):
    """Title derivation works correctly with overrides."""
    from mcp_server.mindsort_claude.tools_list_dupl import list_tools_for_claude

    tools = await list_tools_for_claude()
    titles = {t.name: t.annotations.title for t in tools}

    # Derived from name
    assert titles["organize_thoughts"] == "Organize Thoughts"
    assert titles["edit_board"] == "Edit Board"

    # Explicit override
    assert titles["start_prioritization_flow"] == "Set Priorities"


@pytest.mark.asyncio
async def test_list_tools_sorted(set_dev_env):
    """Tools are returned in sorted order by name."""
    from mcp_server.mindsort_claude.tools_list_dupl import list_tools_for_claude

    tools = await list_tools_for_claude()
    names = [t.name for t in tools]

    assert names == sorted(names)


# ============================================================================
# MindSort-Claude-02: Response Adapter Tests
# ============================================================================


def test_adapter_moves_string_guidance():
    """String assistant_guidance moves to content, stripped from structuredContent, data preserved."""
    from mcp import types as mcp_types
    from mcp_server.mindsort_claude.response_adapter_dupl import adapt_tool_result

    original = mcp_types.CallToolResult(
        content=[],
        structuredContent={
            "clusters": [{"cluster_name": "Test"}],
            "assistant_guidance": "This is the guidance.",
        },
        isError=False,
    )

    adapted = adapt_tool_result(original)

    # Guidance moved to content
    assert len(adapted.content) == 1
    assert adapted.content[0].text == "This is the guidance."

    # Stripped from structuredContent
    assert "assistant_guidance" not in adapted.structuredContent

    # Data preserved
    assert adapted.structuredContent["clusters"] == [{"cluster_name": "Test"}]


def test_adapter_dict_guidance_renders_instruction_only():
    """Dict guidance renders instruction only, drops action."""
    from mcp import types as mcp_types
    from mcp_server.mindsort_claude.response_adapter_dupl import adapt_tool_result

    original = mcp_types.CallToolResult(
        content=[],
        structuredContent={
            "success": False,
            "assistant_guidance": {
                "action": "ASK_CLARIFYING",
                "instruction": "Ask the user X.",
            },
        },
        isError=True,
    )

    adapted = adapt_tool_result(original)

    # instruction rendered, action dropped
    assert "Ask the user X." in adapted.content[0].text
    assert "ASK_CLARIFYING" not in adapted.content[0].text


def test_adapter_discriminates_top_meta():
    """Top-level _meta: keeps non-openai/* keys, strips openai/* keys."""
    from mcp import types as mcp_types
    from mcp_server.mindsort_claude.response_adapter_dupl import adapt_tool_result

    original = mcp_types.CallToolResult(
        content=[],
        structuredContent={"clusters": []},
        isError=False,
        _meta={
            "saved_board_hash": "abc123",
            "openai/toolInvocation/invoking": "Processing...",
            "openai/toolInvocation/invoked": "Done.",
        },
    )

    adapted = adapt_tool_result(original)

    # saved_board_hash kept, openai/* stripped
    assert adapted.meta == {"saved_board_hash": "abc123"}


def test_adapter_empty_meta_becomes_none():
    """When only openai/* keys present, _meta becomes None."""
    from mcp import types as mcp_types
    from mcp_server.mindsort_claude.response_adapter_dupl import adapt_tool_result

    original = mcp_types.CallToolResult(
        content=[],
        structuredContent={"clusters": []},
        isError=False,
        _meta={
            "openai/toolInvocation/invoked": "Done.",
        },
    )

    adapted = adapt_tool_result(original)

    assert adapted.meta is None


def test_adapter_empty_content_with_guidance():
    """Empty content + guidance → content becomes guidance only."""
    from mcp import types as mcp_types
    from mcp_server.mindsort_claude.response_adapter_dupl import adapt_tool_result

    original = mcp_types.CallToolResult(
        content=[],
        structuredContent={
            "clusters": [],
            "assistant_guidance": "No board found.",
        },
        isError=False,
    )

    adapted = adapt_tool_result(original)

    # Content is guidance alone
    assert len(adapted.content) == 1
    assert adapted.content[0].text == "No board found."

    # structuredContent has clusters, no assistant_guidance
    assert "clusters" in adapted.structuredContent
    assert "assistant_guidance" not in adapted.structuredContent


def test_adapter_none_structured_content():
    """structuredContent=None returns new object with discriminated _meta."""
    from mcp import types as mcp_types
    from mcp_server.mindsort_claude.response_adapter_dupl import adapt_tool_result

    original = mcp_types.CallToolResult(
        content=[mcp_types.TextContent(type="text", text="Hello")],
        structuredContent=None,
        isError=False,
        _meta={
            "saved_board_hash": "h",
            "openai/x": 1,
        },
    )

    adapted = adapt_tool_result(original)

    # New object
    assert adapted is not original

    # structuredContent stays None
    assert adapted.structuredContent is None

    # _meta discriminated
    assert adapted.meta == {"saved_board_hash": "h"}


def test_adapter_does_not_mutate_original():
    """Original CallToolResult is not mutated."""
    from mcp import types as mcp_types
    from mcp_server.mindsort_claude.response_adapter_dupl import adapt_tool_result

    original = mcp_types.CallToolResult(
        content=[],
        structuredContent={
            "clusters": [],
            "assistant_guidance": "Guidance text.",
        },
        isError=False,
    )

    adapted = adapt_tool_result(original)

    # Different object
    assert adapted is not original

    # Original still has assistant_guidance
    assert "assistant_guidance" in original.structuredContent


def test_adapter_preserves_data():
    """Data keys (clusters, cluster_names, has_history) preserved unchanged."""
    from mcp import types as mcp_types
    from mcp_server.mindsort_claude.response_adapter_dupl import adapt_tool_result

    clusters = [
        {"cluster_name": "Work", "thought_items": ["Item 1", "Item 2"]},
        {"cluster_name": "Personal", "thought_items": ["Item 3"]},
    ]
    cluster_names = ["Work", "Personal"]

    original = mcp_types.CallToolResult(
        content=[],
        structuredContent={
            "clusters": clusters,
            "cluster_names": cluster_names,
            "has_history": True,
            "is_empty_snapshot": False,
            "assistant_guidance": "Board loaded.",
        },
        isError=False,
    )

    adapted = adapt_tool_result(original)

    # All data preserved exactly
    assert adapted.structuredContent["clusters"] == clusters
    assert adapted.structuredContent["cluster_names"] == cluster_names
    assert adapted.structuredContent["has_history"] is True
    assert adapted.structuredContent["is_empty_snapshot"] is False

    # No truncation (same length)
    assert len(adapted.structuredContent["clusters"]) == 2


# ============================================================================
# MindSort-Claude-Widget-0b: Adapter Tests (ui.resourceUri stripping)
# ============================================================================


def test_adapter_strips_ui_resource_uri():
    """
    Adapter strips ui.resourceUri, preserves other _meta keys.

    Bug this catches: OpenAI widget URI leaking through to Claude results.
    """
    from mcp import types as mcp_types
    from mcp_server.mindsort_claude.response_adapter_dupl import adapt_tool_result

    original = mcp_types.CallToolResult(
        content=[],
        structuredContent={"clusters": []},
        isError=False,
        _meta={
            "ui": {"resourceUri": "ui://widget/clarity-clusters.html?v=1.1.4"},
            "saved_board_hash": "abc123",
        },
    )

    adapted = adapt_tool_result(original)

    # ui.resourceUri stripped
    assert adapted.meta is not None
    assert "ui" not in adapted.meta or "resourceUri" not in adapted.meta.get("ui", {})
    # Non-platform keys preserved
    assert adapted.meta.get("saved_board_hash") == "abc123"


def test_adapter_collapses_empty_ui():
    """
    When ui only contains resourceUri, stripping it collapses ui entirely.

    Bug this catches: {"ui": {}} left behind after stripping resourceUri.
    """
    from mcp import types as mcp_types
    from mcp_server.mindsort_claude.response_adapter_dupl import adapt_tool_result

    original = mcp_types.CallToolResult(
        content=[],
        structuredContent={"clusters": []},
        isError=False,
        _meta={"ui": {"resourceUri": "ui://widget/clarity-clusters.html?v=1.1.4"}},
    )

    adapted = adapt_tool_result(original)

    # ui collapsed entirely, _meta becomes None
    assert adapted.meta is None


def test_adapter_preserves_other_ui_keys():
    """
    Adapter strips ui.resourceUri but preserves other ui.* keys.

    Bug this catches: over-stripping that removes domain, csp, etc.
    """
    from mcp import types as mcp_types
    from mcp_server.mindsort_claude.response_adapter_dupl import adapt_tool_result

    original = mcp_types.CallToolResult(
        content=[],
        structuredContent={"clusters": []},
        isError=False,
        _meta={
            "ui": {
                "resourceUri": "ui://widget/clarity-clusters.html?v=1.1.4",
                "domain": "abc.claudemcpcontent.com",
                "prefersBorder": False,
            },
        },
    )

    adapted = adapt_tool_result(original)

    # resourceUri stripped, domain and prefersBorder preserved
    assert adapted.meta is not None
    assert "ui" in adapted.meta
    assert "resourceUri" not in adapted.meta["ui"]
    assert adapted.meta["ui"]["domain"] == "abc.claudemcpcontent.com"
    assert adapted.meta["ui"]["prefersBorder"] is False


def test_adapter_is_tool_agnostic_no_injection():
    """
    Adapter never injects Claude URI — it only strips.

    Bug this catches: adapter becoming tool-aware and injecting on its own.
    """
    from mcp import types as mcp_types
    from mcp_server.mindsort_claude.response_adapter_dupl import adapt_tool_result

    # Result with no ui on entry
    original = mcp_types.CallToolResult(
        content=[],
        structuredContent={"clusters": []},
        isError=False,
        _meta={"saved_board_hash": "x"},
    )

    adapted = adapt_tool_result(original)

    # No ui injected (adapter doesn't know which tool this is)
    assert adapted.meta is not None
    assert "ui" not in adapted.meta


# ============================================================================
# MindSort-Claude-Widget-0b: Dispatcher Tests (inject-by-intent)
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_name", [
    "organize_thoughts",
    "load_saved_board",
    "start_prioritization_flow",
    "edit_board",
])
async def test_widget_tool_result_carries_claude_uri(set_dev_env, tool_name):
    """
    Widget-producing tools with widget URI on entry exit with Claude URI.

    Bug this catches: OpenAI URI leaking because injection was skipped.
    """
    from unittest.mock import AsyncMock, MagicMock, patch
    from mcp import types as mcp_types
    from mcp_server.mindsort_claude.handlers.tools_dupl import call_tool_request
    from mcp_server.mindsort_claude.handlers.resources_dupl import WIDGET_URI

    # Mock tool handler that returns result with OpenAI widget URI
    mock_result = mcp_types.CallToolResult(
        content=[],
        structuredContent={"clusters": [{"cluster_name": "Test"}]},
        isError=False,
        _meta={
            "ui": {"resourceUri": "ui://widget/clarity-clusters.html?v=1.1.4"},
            "openai/toolInvocation/invoked": "Done",
        },
    )
    mock_tool = MagicMock()
    mock_tool.handle = AsyncMock(return_value=mock_result)

    mock_auth_context = {"user_id": "test-user", "correlation_id": "test-corr"}

    with patch("mcp_server.mindsort_claude.handlers.tools_dupl.get_tool", return_value=mock_tool), \
         patch("mcp_server.mindsort_claude.handlers.tools_dupl.authenticate_request", return_value=mock_auth_context):

        req = mcp_types.CallToolRequest(
            method="tools/call",
            params=mcp_types.CallToolRequestParams(name=tool_name, arguments={}),
        )
        result = await call_tool_request(req)

    # Result carries Claude URI, not OpenAI URI
    assert result.meta is not None
    assert "ui" in result.meta
    assert result.meta["ui"]["resourceUri"] == WIDGET_URI
    assert "clarity-clusters" not in result.meta["ui"]["resourceUri"]


@pytest.mark.asyncio
async def test_openai_uri_never_survives(set_dev_env):
    """
    The OpenAI widget URI is never present in dispatched results.

    Bug this catches: injection skipped, OpenAI URI leaks through.
    """
    from unittest.mock import AsyncMock, MagicMock, patch
    from mcp import types as mcp_types
    from mcp_server.mindsort_claude.handlers.tools_dupl import call_tool_request

    mock_result = mcp_types.CallToolResult(
        content=[],
        structuredContent={"clusters": []},
        isError=False,
        _meta={"ui": {"resourceUri": "ui://widget/clarity-clusters.html?v=1.1.4"}},
    )
    mock_tool = MagicMock()
    mock_tool.handle = AsyncMock(return_value=mock_result)

    with patch("mcp_server.mindsort_claude.handlers.tools_dupl.get_tool", return_value=mock_tool), \
         patch("mcp_server.mindsort_claude.handlers.tools_dupl.authenticate_request",
               return_value={"user_id": "u", "correlation_id": "c"}):

        req = mcp_types.CallToolRequest(
            method="tools/call",
            params=mcp_types.CallToolRequestParams(name="organize_thoughts", arguments={}),
        )
        result = await call_tool_request(req)

    # OpenAI URI never survives
    if result.meta and "ui" in result.meta:
        uri = result.meta["ui"].get("resourceUri", "")
        assert "clarity-clusters" not in uri


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_name", ["read_board_before_editing", "delete_my_data"])
async def test_non_widget_tools_get_no_widget_metadata(set_dev_env, tool_name):
    """
    Non-widget tools have no ui.resourceUri in output.

    Bug this catches: injection applied to wrong tools.
    """
    from unittest.mock import AsyncMock, MagicMock, patch
    from mcp import types as mcp_types
    from mcp_server.mindsort_claude.handlers.tools_dupl import call_tool_request

    # These tools return _meta=None or no ui
    mock_result = mcp_types.CallToolResult(
        content=[mcp_types.TextContent(type="text", text="data")],
        structuredContent={"clusters": []},
        isError=False,
        _meta=None,
    )
    mock_tool = MagicMock()
    mock_tool.handle = AsyncMock(return_value=mock_result)

    with patch("mcp_server.mindsort_claude.handlers.tools_dupl.get_tool", return_value=mock_tool), \
         patch("mcp_server.mindsort_claude.handlers.tools_dupl.authenticate_request",
               return_value={"user_id": "u", "correlation_id": "c"}):

        req = mcp_types.CallToolRequest(
            method="tools/call",
            params=mcp_types.CallToolRequestParams(name=tool_name, arguments={}),
        )
        result = await call_tool_request(req)

    # No widget metadata
    if result.meta:
        assert "ui" not in result.meta or "resourceUri" not in result.meta.get("ui", {})


@pytest.mark.asyncio
async def test_load_saved_board_error_path_gets_claude_uri(set_dev_env):
    """
    load_saved_board's read-error path (had widget on entry) gets Claude URI.

    This path returns clusters: [] with guidance "do not tell them they have no board"
    but still carries a widget URI on OpenAI. For parity, it gets the Claude URI.

    Bug this catches: injection keyed on success/isError instead of had-widget-on-entry.
    """
    from unittest.mock import AsyncMock, MagicMock, patch
    from mcp import types as mcp_types
    from mcp_server.mindsort_claude.handlers.tools_dupl import call_tool_request
    from mcp_server.mindsort_claude.handlers.resources_dupl import WIDGET_URI

    # Simulate the read-error path: clusters: [], but still has widget URI
    mock_result = mcp_types.CallToolResult(
        content=[],
        structuredContent={
            "clusters": [],
            "assistant_guidance": "The user's board is empty.",
        },
        isError=False,  # Note: isError is False even on this "error" path
        _meta={"ui": {"resourceUri": "ui://widget/clarity-clusters.html?v=1.1.4"}},
    )
    mock_tool = MagicMock()
    mock_tool.handle = AsyncMock(return_value=mock_result)

    with patch("mcp_server.mindsort_claude.handlers.tools_dupl.get_tool", return_value=mock_tool), \
         patch("mcp_server.mindsort_claude.handlers.tools_dupl.authenticate_request",
               return_value={"user_id": "u", "correlation_id": "c"}):

        req = mcp_types.CallToolRequest(
            method="tools/call",
            params=mcp_types.CallToolRequestParams(name="load_saved_board", arguments={}),
        )
        result = await call_tool_request(req)

    # Error path with widget-on-entry gets Claude URI
    assert result.meta is not None
    assert "ui" in result.meta
    assert result.meta["ui"]["resourceUri"] == WIDGET_URI
    assert "clarity-clusters" not in result.meta["ui"]["resourceUri"]


@pytest.mark.asyncio
async def test_meta_none_gets_no_injection(set_dev_env):
    """
    A widget tool result that entered with _meta=None gets NO injection.

    Inject-by-intent: no widget on entry → no widget on exit.

    Bug this catches: inject-by-tool-name-alone wrongly adding widget to error paths.
    """
    from unittest.mock import AsyncMock, MagicMock, patch
    from mcp import types as mcp_types
    from mcp_server.mindsort_claude.handlers.tools_dupl import call_tool_request

    # Widget tool, but _meta=None (e.g. persist_failed error path)
    mock_result = mcp_types.CallToolResult(
        content=[mcp_types.TextContent(type="text", text="Error saving")],
        structuredContent={"success": False},
        isError=True,
        _meta=None,
    )
    mock_tool = MagicMock()
    mock_tool.handle = AsyncMock(return_value=mock_result)

    with patch("mcp_server.mindsort_claude.handlers.tools_dupl.get_tool", return_value=mock_tool), \
         patch("mcp_server.mindsort_claude.handlers.tools_dupl.authenticate_request",
               return_value={"user_id": "u", "correlation_id": "c"}):

        req = mcp_types.CallToolRequest(
            method="tools/call",
            params=mcp_types.CallToolRequestParams(name="organize_thoughts", arguments={}),
        )
        result = await call_tool_request(req)

    # No injection: _meta stays None or has no ui.resourceUri
    if result.meta:
        assert "ui" not in result.meta or "resourceUri" not in result.meta.get("ui", {})


@pytest.mark.asyncio
async def test_no_widget_on_entry_gets_no_injection(set_dev_env):
    """
    A widget tool result that had _meta but no ui.resourceUri gets NO injection.

    Bug this catches: inject-by-tool-name-alone ignoring had-widget-on-entry condition.
    """
    from unittest.mock import AsyncMock, MagicMock, patch
    from mcp import types as mcp_types
    from mcp_server.mindsort_claude.handlers.tools_dupl import call_tool_request

    # Widget tool, but no ui.resourceUri on entry (e.g. some error path)
    mock_result = mcp_types.CallToolResult(
        content=[],
        structuredContent={"success": False},
        isError=True,
        _meta={"error_code": "PERSIST_FAILED"},  # has _meta but no ui
    )
    mock_tool = MagicMock()
    mock_tool.handle = AsyncMock(return_value=mock_result)

    with patch("mcp_server.mindsort_claude.handlers.tools_dupl.get_tool", return_value=mock_tool), \
         patch("mcp_server.mindsort_claude.handlers.tools_dupl.authenticate_request",
               return_value={"user_id": "u", "correlation_id": "c"}):

        req = mcp_types.CallToolRequest(
            method="tools/call",
            params=mcp_types.CallToolRequestParams(name="edit_board", arguments={}),
        )
        result = await call_tool_request(req)

    # No injection: no ui.resourceUri because there was none on entry
    assert result.meta is not None
    assert "error_code" in result.meta  # preserved
    assert "ui" not in result.meta or "resourceUri" not in result.meta.get("ui", {})


@pytest.mark.asyncio
async def test_dispatcher_idempotence(set_dev_env):
    """
    Applying adapt+inject twice (f(f(x))) produces the same Claude URI.

    True idempotence test: feed the output of the first dispatch back through.
    Bug this catches: strip step that special-cases OpenAI value instead of generic key strip.
    """
    from unittest.mock import AsyncMock, MagicMock, patch
    from mcp import types as mcp_types
    from mcp_server.mindsort_claude.handlers.tools_dupl import call_tool_request
    from mcp_server.mindsort_claude.handlers.resources_dupl import WIDGET_URI

    # First call: OpenAI URI → Claude URI
    mock_result_1 = mcp_types.CallToolResult(
        content=[],
        structuredContent={"clusters": []},
        isError=False,
        _meta={"ui": {"resourceUri": "ui://widget/clarity-clusters.html?v=1.1.4"}},
    )

    mock_tool = MagicMock()
    mock_tool.handle = AsyncMock(return_value=mock_result_1)

    with patch("mcp_server.mindsort_claude.handlers.tools_dupl.get_tool", return_value=mock_tool), \
         patch("mcp_server.mindsort_claude.handlers.tools_dupl.authenticate_request",
               return_value={"user_id": "u", "correlation_id": "c"}):

        req = mcp_types.CallToolRequest(
            method="tools/call",
            params=mcp_types.CallToolRequestParams(name="organize_thoughts", arguments={}),
        )
        result_1 = await call_tool_request(req)

    # First result should have Claude URI
    assert result_1.meta is not None
    assert result_1.meta["ui"]["resourceUri"] == WIDGET_URI

    # Second call: feed the ACTUAL output of the first dispatch back through (f(f(x)))
    # This is the real idempotence test — not a hand-built second input
    mock_tool.handle = AsyncMock(return_value=result_1)

    with patch("mcp_server.mindsort_claude.handlers.tools_dupl.get_tool", return_value=mock_tool), \
         patch("mcp_server.mindsort_claude.handlers.tools_dupl.authenticate_request",
               return_value={"user_id": "u", "correlation_id": "c"}):

        result_2 = await call_tool_request(req)

    # f(f(x)) == f(x): second pass produces identical Claude URI
    assert result_2.meta is not None
    assert result_2.meta["ui"]["resourceUri"] == WIDGET_URI
    # Verify it's actually the same value, not doubled or corrupted
    assert result_1.meta["ui"]["resourceUri"] == result_2.meta["ui"]["resourceUri"]


# ============================================================================
# MindSort-Claude-02b: Discovery Fix Tests
# ============================================================================


@pytest.mark.asyncio
async def test_protected_resource_honors_configured_resource_url(set_dev_env, monkeypatch):
    """oauth_protected_resource returns MCP_RESOURCE_URL, not recomputed value."""
    import importlib

    # Set custom resource URL distinct from origin
    monkeypatch.setenv("CLARITY_CLAUDE_MCP_SERVER_URL", "https://origin.example")
    monkeypatch.setenv("CLARITY_CLAUDE_MCP_RESOURCE_URL", "https://resource.example/custom")

    import mcp_server.mindsort_claude.config as claude_config
    import mcp_server.mindsort_claude.discovery_dupl as discovery

    # Reload to pick up env changes
    importlib.reload(claude_config)
    importlib.reload(discovery)

    try:
        result = await discovery.oauth_protected_resource()

        # Must return the configured resource URL, NOT origin + /mcp
        assert result["resource"] == "https://resource.example/custom"
        assert result["resource"] != "https://origin.example/mcp"
    finally:
        # Restore to default state for subsequent tests
        monkeypatch.delenv("CLARITY_CLAUDE_MCP_SERVER_URL", raising=False)
        monkeypatch.delenv("CLARITY_CLAUDE_MCP_RESOURCE_URL", raising=False)
        importlib.reload(claude_config)
        importlib.reload(discovery)


@pytest.mark.asyncio
async def test_protected_resource_default_is_origin_plus_mcp(set_dev_env):
    """Default resource URL equals {MCP_SERVER_URL}/mcp."""
    import mcp_server.mindsort_claude.config as claude_config
    import mcp_server.mindsort_claude.discovery_dupl as discovery

    result = await discovery.oauth_protected_resource()

    # Default: resource ends with /mcp and equals MCP_SERVER_URL + /mcp
    assert result["resource"].endswith("/mcp")
    assert result["resource"] == f"{claude_config.MCP_SERVER_URL}/mcp"


@pytest.mark.asyncio
async def test_protected_resource_unchanged_fields(set_dev_env):
    """authorization_servers and scopes_supported unchanged by the fix."""
    import mcp_server.mindsort_claude.config as claude_config
    import mcp_server.mindsort_claude.discovery_dupl as discovery

    result = await discovery.oauth_protected_resource()

    # These fields must remain unchanged
    assert result["authorization_servers"] == [claude_config.OAUTH_ISSUER_URL]
    assert result["scopes_supported"] == ["clarity.write"]


# ============================================================================
# MindSort-Claude-Widget-0: Resource Registration Tests
# ============================================================================


@pytest.mark.asyncio
async def test_list_resources_returns_widget(set_dev_env):
    """list_resources() returns exactly one resource with correct URI and MIME type."""
    from mcp_server.mindsort_claude.handlers.resources_dupl import (
        list_resources,
        WIDGET_URI,
        WIDGET_MIME_TYPE,
    )

    resources = await list_resources()

    assert len(resources) == 1
    resource = resources[0]
    assert str(resource.uri) == WIDGET_URI  # uri is AnyUrl, convert to string
    assert resource.mimeType == WIDGET_MIME_TYPE


@pytest.mark.asyncio
async def test_list_resource_templates_returns_template(set_dev_env):
    """list_resource_templates() returns one template with matching URI and metadata split."""
    from mcp_server.mindsort_claude.handlers.resources_dupl import (
        list_resource_templates,
        WIDGET_URI,
        WIDGET_MIME_TYPE,
    )

    templates = await list_resource_templates()

    assert len(templates) == 1
    t = templates[0]
    # uriTemplate is a plain str in the SDK (not AnyUrl), no coercion needed
    assert t.uriTemplate == WIDGET_URI
    assert t.mimeType == WIDGET_MIME_TYPE
    # Same metadata-split rule as the resource: domain in _meta, not resourceUri
    assert "domain" in t.meta["ui"]
    assert "resourceUri" not in t.meta["ui"]


@pytest.mark.asyncio
async def test_ui_domain_is_hash_derived(set_dev_env):
    """ui.domain is sha256(MCP_RESOURCE_URL)[:32].claudemcpcontent.com, not hardcoded."""
    import hashlib
    from mcp_server.mindsort_claude.config import MCP_RESOURCE_URL
    from mcp_server.mindsort_claude.handlers.resources_dupl import list_resources

    resources = await list_resources()
    resource = resources[0]

    # Compute expected hash independently from config
    expected_hash = hashlib.sha256(MCP_RESOURCE_URL.encode()).hexdigest()[:32]
    expected_domain = f"{expected_hash}.claudemcpcontent.com"

    # Verify domain matches
    actual_domain = resource.meta["ui"]["domain"]
    assert actual_domain == expected_domain
    assert actual_domain.endswith(".claudemcpcontent.com")

    # Verify it's NOT a server origin/hostname (should be a hash, not a domain)
    assert "localhost" not in actual_domain
    assert "priority-guard" not in actual_domain


@pytest.mark.asyncio
async def test_ui_domain_uses_full_mcp_url(set_dev_env, monkeypatch):
    """ui.domain hash input includes /mcp path, not just origin."""
    import hashlib
    import importlib

    # Set MCP_RESOURCE_URL with /mcp
    monkeypatch.setenv("CLARITY_CLAUDE_MCP_SERVER_URL", "https://test.example")
    monkeypatch.setenv("CLARITY_CLAUDE_MCP_RESOURCE_URL", "https://test.example/mcp")

    import mcp_server.mindsort_claude.config as claude_config
    import mcp_server.mindsort_claude.handlers.resources_dupl as resources

    importlib.reload(claude_config)
    importlib.reload(resources)

    try:
        # Compute hash of the full URL (with /mcp)
        hash_with_mcp = hashlib.sha256("https://test.example/mcp".encode()).hexdigest()[:32]
        # Compute hash of just the origin (without /mcp)
        hash_without_mcp = hashlib.sha256("https://test.example".encode()).hexdigest()[:32]

        # They should be different (proves /mcp is in the hash input)
        assert hash_with_mcp != hash_without_mcp

        # The actual domain should use the /mcp version
        assert resources.WIDGET_APP_DOMAIN == f"{hash_with_mcp}.claudemcpcontent.com"
    finally:
        monkeypatch.delenv("CLARITY_CLAUDE_MCP_SERVER_URL", raising=False)
        monkeypatch.delenv("CLARITY_CLAUDE_MCP_RESOURCE_URL", raising=False)
        importlib.reload(claude_config)
        importlib.reload(resources)


@pytest.mark.asyncio
async def test_csp_present_and_minimal(set_dev_env):
    """Resource has _meta.ui.csp with empty connectDomains and limited resourceDomains."""
    from mcp_server.mindsort_claude.handlers.resources_dupl import list_resources

    resources = await list_resources()
    resource = resources[0]
    csp = resource.meta["ui"]["csp"]

    # connectDomains must be empty (widget uses postMessage, not HTTP)
    assert csp["connectDomains"] == []

    # resourceDomains must be empty or contain only assets.claude.ai
    assert csp["resourceDomains"] in [[], ["https://assets.claude.ai"]]


@pytest.mark.asyncio
async def test_prefers_border_false(set_dev_env):
    """Resource has _meta.ui.prefersBorder: false."""
    from mcp_server.mindsort_claude.handlers.resources_dupl import list_resources

    resources = await list_resources()
    resource = resources[0]

    assert resource.meta["ui"]["prefersBorder"] is False


@pytest.mark.asyncio
async def test_metadata_placement_split(set_dev_env):
    """Resource carries domain/csp/prefersBorder; tools carry resourceUri only."""
    from mcp_server.mindsort_claude.handlers.resources_dupl import list_resources
    from mcp_server.mindsort_claude.tools_list_dupl import list_tools_for_claude

    # Resource should have domain/csp/prefersBorder, NOT resourceUri
    resources = await list_resources()
    resource = resources[0]
    resource_ui = resource.meta["ui"]

    assert "domain" in resource_ui
    assert "csp" in resource_ui
    assert "prefersBorder" in resource_ui
    assert "resourceUri" not in resource_ui

    # Widget-producing tool should have resourceUri, NOT domain/csp/prefersBorder
    tools = await list_tools_for_claude()
    widget_tool = next(t for t in tools if t.name == "organize_thoughts")
    tool_ui = widget_tool.meta["ui"]

    assert "resourceUri" in tool_ui
    assert "domain" not in tool_ui
    assert "csp" not in tool_ui
    assert "prefersBorder" not in tool_ui


@pytest.mark.asyncio
async def test_read_resource_serves_widget(set_dev_env):
    """read_resource for the widget URI returns the real widget, not fallback HTML."""
    from mcp import types as mcp_types
    from mcp_server.mindsort_claude.handlers.resources_dupl import (
        handle_read_resource,
        WIDGET_URI,
        WIDGET_MIME_TYPE,
        WIDGET_HTML,
        WIDGET_FALLBACK_HTML,
    )

    # Guard: widget load succeeded (fallback not served at module level)
    # Catches: placeholder file not found, permission denied, path misconfigured
    assert WIDGET_HTML != WIDGET_FALLBACK_HTML, (
        "Widget failed to load — WIDGET_HTML equals fallback. "
        "Check WIDGET_PATH resolves and file exists."
    )

    # Create a mock request
    req = mcp_types.ReadResourceRequest(
        method="resources/read",
        params=mcp_types.ReadResourceRequestParams(uri=WIDGET_URI),
    )

    result = await handle_read_resource(req)

    assert len(result.contents) == 1
    content = result.contents[0]
    assert str(content.uri) == WIDGET_URI  # uri is AnyUrl, convert to string
    assert content.mimeType == WIDGET_MIME_TYPE
    assert len(content.text) > 0
    assert "<!DOCTYPE html>" in content.text or "<html" in content.text
    # Unique marker: only in real widget, not in fallback HTML
    # Catches: fallback being served when placeholder file fails to load
    assert "MindSort Widget (placeholder)" in content.text, (
        "Widget content is fallback HTML, not the real placeholder. "
        "The real widget contains 'MindSort Widget (placeholder)'."
    )


@pytest.mark.asyncio
async def test_read_resource_unknown_uri_graceful(set_dev_env):
    """read_resource for unknown URI returns empty contents + error _meta, no exception."""
    from mcp import types as mcp_types
    from mcp_server.mindsort_claude.handlers.resources_dupl import handle_read_resource

    req = mcp_types.ReadResourceRequest(
        method="resources/read",
        params=mcp_types.ReadResourceRequestParams(uri="ui://does-not-exist"),
    )

    # Should not raise
    result = await handle_read_resource(req)

    # Empty contents
    assert result.contents == []

    # Error in _meta
    assert result.meta is not None
    assert "error" in result.meta


@pytest.mark.asyncio
async def test_widget_producing_tools_have_resource_uri(set_dev_env):
    """Widget-producing tools have _meta.ui.resourceUri matching WIDGET_URI."""
    from mcp_server.mindsort_claude.tools_list_dupl import list_tools_for_claude
    from mcp_server.mindsort_claude.handlers.resources_dupl import WIDGET_URI

    tools = await list_tools_for_claude()
    tools_by_name = {t.name: t for t in tools}

    widget_tools = ["organize_thoughts", "load_saved_board", "start_prioritization_flow", "edit_board"]

    for tool_name in widget_tools:
        tool = tools_by_name[tool_name]
        assert tool.meta is not None, f"{tool_name} should have _meta"
        assert "ui" in tool.meta, f"{tool_name} should have _meta.ui"
        assert tool.meta["ui"]["resourceUri"] == WIDGET_URI, f"{tool_name} resourceUri should match WIDGET_URI"


@pytest.mark.asyncio
async def test_non_widget_tools_have_no_meta(set_dev_env):
    """Non-widget tools (read_board_before_editing, delete_my_data) have _meta=None."""
    from mcp_server.mindsort_claude.tools_list_dupl import list_tools_for_claude

    tools = await list_tools_for_claude()
    tools_by_name = {t.name: t for t in tools}

    non_widget_tools = ["read_board_before_editing", "delete_my_data"]

    for tool_name in non_widget_tools:
        tool = tools_by_name[tool_name]
        assert tool.meta is None, f"{tool_name} should have _meta=None"


@pytest.mark.asyncio
async def test_widget_uri_consistency(set_dev_env):
    """Widget URI constant is the same in resources and tools (single source of truth)."""
    from mcp_server.mindsort_claude.handlers.resources_dupl import WIDGET_URI as RESOURCES_WIDGET_URI
    from mcp_server.mindsort_claude.tools_list_dupl import WIDGET_URI as TOOLS_WIDGET_URI

    # Both modules should import the same constant
    assert RESOURCES_WIDGET_URI == TOOLS_WIDGET_URI

    # Verify it's actually used in resources
    from mcp_server.mindsort_claude.handlers.resources_dupl import list_resources
    resources = await list_resources()
    assert str(resources[0].uri) == RESOURCES_WIDGET_URI  # uri is AnyUrl, convert to string

    # Verify it's actually used in widget-producing tools
    from mcp_server.mindsort_claude.tools_list_dupl import list_tools_for_claude
    tools = await list_tools_for_claude()
    organize = next(t for t in tools if t.name == "organize_thoughts")
    assert organize.meta["ui"]["resourceUri"] == TOOLS_WIDGET_URI


@pytest.mark.asyncio
async def test_tool_annotations_unchanged_after_widget0(set_dev_env):
    """Claude-02 invariants still hold: title present, destructiveHint override, sorted."""
    from mcp_server.mindsort_claude.tools_list_dupl import list_tools_for_claude

    tools = await list_tools_for_claude()
    tools_by_name = {t.name: t for t in tools}

    # Title still present
    for tool in tools:
        assert tool.annotations is not None
        assert isinstance(tool.annotations.title, str)
        assert len(tool.annotations.title) > 0

    # destructiveHint override still works
    assert tools_by_name["start_prioritization_flow"].annotations.destructiveHint is True

    # Still sorted
    names = [t.name for t in tools]
    assert names == sorted(names)
