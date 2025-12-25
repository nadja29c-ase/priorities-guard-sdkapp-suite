import pytest
from mcp_server.clarity.tools import list_tools, TOOL_REGISTRY


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
