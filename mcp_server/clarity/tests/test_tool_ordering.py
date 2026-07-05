import pytest
from mcp import types as mcp_types

from mcp_server.clarity.tools import list_tools


@pytest.mark.asyncio
async def test_tools_returned_in_alphabetical_order():
    """Tools are returned sorted by name for deterministic output."""
    tools = await list_tools()
    names = [t.name for t in tools]
    assert names == sorted(names)


@pytest.mark.asyncio
async def test_annotations_typed_not_in_meta():
    """All tools have typed ToolAnnotations, not raw dict in _meta.

    inc_92: Annotations must be typed mcp_types.ToolAnnotations objects
    on tool.annotations, NOT raw dicts embedded in _meta["annotations"].
    The raw dict pattern caused Pydantic serialization warnings.
    """
    tools = await list_tools()
    for tool in tools:
        # tool.annotations must be a typed ToolAnnotations instance
        assert tool.annotations is not None, f"{tool.name}: missing annotations"
        assert isinstance(tool.annotations, mcp_types.ToolAnnotations), (
            f"{tool.name}: annotations is {type(tool.annotations).__name__}, "
            f"expected ToolAnnotations"
        )

        # Verify annotation values are set (not None)
        assert tool.annotations.readOnlyHint is not None, (
            f"{tool.name}: readOnlyHint is None"
        )
        assert tool.annotations.destructiveHint is not None, (
            f"{tool.name}: destructiveHint is None"
        )
        assert tool.annotations.openWorldHint is not None, (
            f"{tool.name}: openWorldHint is None"
        )

        # _meta must NOT contain annotations key
        # (annotations live on tool.annotations, not in _meta)
        assert tool.meta is not None, f"{tool.name}: missing meta"
        assert "annotations" not in tool.meta, (
            f"{tool.name}: _meta should not contain 'annotations' key - "
            f"annotations belong on tool.annotations (typed field)"
        )
