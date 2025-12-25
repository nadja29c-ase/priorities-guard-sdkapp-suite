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
    """securitySchemes must reflect tool_def.required_scopes."""
    tools = await list_tools()
    for tool in tools:
        tool_def = TOOL_REGISTRY.get(tool.name)
        schemes = tool.meta["securitySchemes"]

        if tool_def.required_scopes:
            # Tools with scopes → oauth2
            assert schemes[0]["type"] == "oauth2", f"{tool.name}: expected oauth2"
            assert schemes[0]["scopes"] == tool_def.required_scopes
        else:
            # Tools without scopes → noauth
            assert schemes[0]["type"] == "noauth", f"{tool.name}: expected noauth"


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
async def test_noauth_security_scheme_for_tool_without_scopes():
    """Tools without required_scopes get noauth securitySchemes."""

    # Dummy handler for test tool
    async def dummy_handler(user_id, correlation_id, arguments):
        pass

    # Create temporary tool with no scopes
    mock_tool = ToolDefinition(
        name="_test_noauth_tool",
        description="Test tool",
        input_schema={"type": "object", "properties": {}},
        required_scopes=[],  # Empty = noauth
        widget_uri=None,
        handle=dummy_handler,
    )

    try:
        register_tool(mock_tool)
        tools = await list_tools()
        test_tool = next(t for t in tools if t.name == "_test_noauth_tool")

        schemes = test_tool.meta["securitySchemes"]
        assert schemes == [{"type": "noauth"}]
    finally:
        # Cleanup
        TOOL_REGISTRY.pop("_test_noauth_tool", None)
