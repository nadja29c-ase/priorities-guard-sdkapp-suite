import pytest
from mcp_server.clarity.tools import list_tools, TOOL_REGISTRY, register_tool
from mcp_server.clarity.tools.base import ToolDefinition


@pytest.mark.asyncio
async def test_all_tools_have_security_schemes():
    """Every tool must declare securitySchemes in meta."""
    tools = await list_tools()
    for tool in tools:
        assert tool.meta is not None, f"{tool.name}: missing meta"
        assert "securitySchemes" in tool.meta, f"{tool.name}: missing securitySchemes"
        schemes = tool.meta["securitySchemes"]
        assert isinstance(schemes, list), f"{tool.name}: securitySchemes must be list"
        assert len(schemes) > 0, f"{tool.name}: securitySchemes cannot be empty"


@pytest.mark.asyncio
async def test_security_schemes_match_required_scopes():
    """securitySchemes must reflect tool_def.required_scopes.

    inc_91 behavior:
    - required_scopes is a list (including empty []) → oauth2 with those scopes
    - required_scopes is None → noauth (no auth required)

    Empty scopes [] means "auth required, any authenticated user" (runtime
    always requires valid JWT via authenticate_request()). This differs from
    noauth which means "no auth required at all".
    """
    tools = await list_tools()
    for tool in tools:
        tool_def = TOOL_REGISTRY.get(tool.name)
        schemes = tool.meta["securitySchemes"]

        if tool_def.required_scopes is None:
            # Explicitly None = noauth (not used by any current tool)
            assert schemes[0]["type"] == "noauth", f"{tool.name}: expected noauth"
        else:
            # List (including empty []) = oauth2 with those scopes
            assert schemes[0]["type"] == "oauth2", f"{tool.name}: expected oauth2"
            assert schemes[0]["scopes"] == tool_def.required_scopes, (
                f"{tool.name}: scopes mismatch"
            )


@pytest.mark.asyncio
async def test_security_schemes_format():
    """Validate securitySchemes structure per SDK spec."""
    tools = await list_tools()
    for tool in tools:
        for scheme in tool.meta["securitySchemes"]:
            assert "type" in scheme
            assert scheme["type"] in ("oauth2", "noauth")
            if scheme["type"] == "oauth2":
                assert "scopes" in scheme
                assert isinstance(scheme["scopes"], list)


@pytest.mark.asyncio
async def test_empty_scopes_maps_to_oauth2_not_noauth():
    """Tools with empty required_scopes get oauth2 with empty scopes array.

    inc_91 fix: Empty scopes means "auth required, any authenticated user",
    NOT "no auth required". Runtime always requires valid JWT via
    authenticate_request(), so the descriptor must reflect this.

    Bug this test guards against: mapping [] to noauth would tell ChatGPT
    "no auth needed" when the runtime actually requires a valid JWT,
    causing auth failures when users try to call the tool.
    """

    # Dummy handler for test tool
    async def dummy_handler(user_id, correlation_id, arguments):
        pass

    # Create temporary tool with empty scopes (not None)
    mock_tool = ToolDefinition(
        name="_test_empty_scopes_tool",
        description="Test tool with empty scopes",
        input_schema={"type": "object", "properties": {}},
        required_scopes=[],  # Empty list = oauth2 with empty scopes
        widget_uri=None,
        handle=dummy_handler,
    )

    try:
        register_tool(mock_tool)
        tools = await list_tools()
        test_tool = next(t for t in tools if t.name == "_test_empty_scopes_tool")

        schemes = test_tool.meta["securitySchemes"]
        # Must be oauth2 with empty scopes, NOT noauth
        assert schemes == [{"type": "oauth2", "scopes": []}], (
            f"Empty scopes should map to oauth2 with empty scopes, got {schemes}"
        )
    finally:
        # Cleanup
        TOOL_REGISTRY.pop("_test_empty_scopes_tool", None)


@pytest.mark.asyncio
async def test_diagnostic_tool_descriptor_is_oauth2():
    """_diagnostic_tiny_widget must show oauth2 with empty scopes in descriptor.

    inc_91 requirement: The diagnostic tool has [] scopes (any authenticated user)
    and must emit oauth2 with empty scopes, not noauth.
    """
    tools = await list_tools()
    diag_tool = next((t for t in tools if t.name == "_diagnostic_tiny_widget"), None)

    assert diag_tool is not None, "_diagnostic_tiny_widget not found in list_tools"

    schemes = diag_tool.meta["securitySchemes"]
    assert schemes == [{"type": "oauth2", "scopes": []}], (
        f"Diagnostic tool should be oauth2 with empty scopes, got {schemes}"
    )
