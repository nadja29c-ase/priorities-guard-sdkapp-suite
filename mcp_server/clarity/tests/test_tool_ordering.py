import pytest
from mcp_server.clarity.tools import list_tools


@pytest.mark.asyncio
async def test_tools_returned_in_alphabetical_order():
    """Tools are returned sorted by name for deterministic output."""
    tools = await list_tools()
    names = [t.name for t in tools]
    assert names == sorted(names)


@pytest.mark.asyncio
async def test_annotations_in_meta():
    """All tools have annotations in _meta."""
    tools = await list_tools()
    for tool in tools:
        assert tool.meta is not None, f"{tool.name}: missing meta"
        assert "annotations" in tool.meta, f"{tool.name}: missing annotations in meta"
        annotations = tool.meta["annotations"]
        # Verify annotation structure
        assert "readOnlyHint" in annotations
        assert "destructiveHint" in annotations
        assert "openWorldHint" in annotations


@pytest.mark.asyncio
async def test_annotations_mirrored_at_top_level_if_supported():
    """Annotations mirrored at top level if SDK supports it."""
    tools = await list_tools()
    for tool in tools:
        # Check if SDK supports top-level annotations
        if hasattr(tool, "annotations") and tool.annotations is not None:
            # If supported and set, verify it matches _meta.annotations
            meta_annotations = tool.meta.get("annotations", {})
            assert tool.annotations == meta_annotations, f"{tool.name}: annotations mismatch"
