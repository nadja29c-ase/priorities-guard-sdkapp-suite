import pytest
from mcp_server.clarity.tools import list_tools


@pytest.mark.asyncio
async def test_tools_returned_in_alphabetical_order():
    """Tools are returned sorted by name for deterministic output."""
    tools = await list_tools()
    names = [t.name for t in tools]
    assert names == sorted(names)
