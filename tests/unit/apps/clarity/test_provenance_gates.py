"""
Unit tests for Clarity verbatim provenance gates.

Tests the behavioral gates on organize_thoughts and prioritize_clusters
that require explicit user confirmation before tool execution.
"""

import pytest
from mcp import types as mcp_types


class TestOrganizeThoughtsProvenanceGate:
    """Tests for organize_thoughts user_thoughts_exhausted_verbatim gate."""

    @pytest.mark.asyncio
    async def test_empty_string_returns_provenance_error(self):
        """Empty user_thoughts_exhausted_verbatim returns provenance error."""
        from mcp_server.clarity.tools.organize_thoughts import handle

        result = await handle(
            user_id="test",
            correlation_id="test",
            arguments={
                "user_thoughts_exhausted_verbatim": "",
                "clusters": [{"cluster_name": "Test", "thought_items": ["item1"]}],
            },
        )

        assert result.isError is True
        assert result.structuredContent is not None
        assert result.structuredContent["error"] == "empty_thoughts_exhausted_verbatim"
        assert result.structuredContent["assistant_guidance"]["action"] == "ASK_CLARIFYING"

    @pytest.mark.asyncio
    async def test_missing_field_returns_provenance_error(self):
        """Missing user_thoughts_exhausted_verbatim returns provenance error."""
        from mcp_server.clarity.tools.organize_thoughts import handle

        result = await handle(
            user_id="test",
            correlation_id="test",
            arguments={
                "clusters": [{"cluster_name": "Test", "thought_items": ["item1"]}],
            },
        )

        assert result.isError is True
        assert result.structuredContent is not None
        assert result.structuredContent["error"] == "empty_thoughts_exhausted_verbatim"

    @pytest.mark.asyncio
    async def test_whitespace_only_returns_provenance_error(self):
        """Whitespace-only user_thoughts_exhausted_verbatim returns provenance error."""
        from mcp_server.clarity.tools.organize_thoughts import handle

        result = await handle(
            user_id="test",
            correlation_id="test",
            arguments={
                "user_thoughts_exhausted_verbatim": "   ",
                "clusters": [{"cluster_name": "Test", "thought_items": ["item1"]}],
            },
        )

        assert result.isError is True
        assert result.structuredContent["error"] == "empty_thoughts_exhausted_verbatim"

    @pytest.mark.asyncio
    async def test_non_empty_verbatim_proceeds_past_gate(self):
        """Non-empty user_thoughts_exhausted_verbatim proceeds past provenance gate."""
        from mcp_server.clarity.tools.organize_thoughts import handle

        result = await handle(
            user_id="test",
            correlation_id="test",
            arguments={
                "user_thoughts_exhausted_verbatim": "that's it",
                "clusters": [{"cluster_name": "Test", "thought_items": ["item1"]}],
            },
        )

        # Should NOT return provenance error - may return success or validation error
        if result.structuredContent:
            assert result.structuredContent.get("error") != "empty_thoughts_exhausted_verbatim"


class TestPrioritizeClustersProvenanceGate:
    """Tests for prioritize_clusters user_priorities_verbatim gate."""

    @pytest.mark.asyncio
    async def test_empty_string_returns_provenance_error(self):
        """Empty user_priorities_verbatim returns provenance error."""
        from mcp_server.clarity.tools.prioritize_clusters import handle

        result = await handle(
            user_id="test",
            correlation_id="test",
            arguments={
                "user_priorities_verbatim": "",
                "clusters": [{"cluster_name": "Test", "thought_items": ["item1"]}],
                "priorities": [{"name": "Test", "rank": "P1"}],
            },
        )

        assert result.isError is True
        assert result.structuredContent is not None
        assert result.structuredContent["error"] == "empty_priorities_verbatim"
        assert result.structuredContent["assistant_guidance"]["action"] == "ASK_CLARIFYING"

    @pytest.mark.asyncio
    async def test_missing_field_returns_provenance_error(self):
        """Missing user_priorities_verbatim returns provenance error."""
        from mcp_server.clarity.tools.prioritize_clusters import handle

        result = await handle(
            user_id="test",
            correlation_id="test",
            arguments={
                "clusters": [{"cluster_name": "Test", "thought_items": ["item1"]}],
                "priorities": [{"name": "Test", "rank": "P1"}],
            },
        )

        assert result.isError is True
        assert result.structuredContent is not None
        assert result.structuredContent["error"] == "empty_priorities_verbatim"

    @pytest.mark.asyncio
    async def test_whitespace_only_returns_provenance_error(self):
        """Whitespace-only user_priorities_verbatim returns provenance error."""
        from mcp_server.clarity.tools.prioritize_clusters import handle

        result = await handle(
            user_id="test",
            correlation_id="test",
            arguments={
                "user_priorities_verbatim": "   ",
                "clusters": [{"cluster_name": "Test", "thought_items": ["item1"]}],
                "priorities": [{"name": "Test", "rank": "P1"}],
            },
        )

        assert result.isError is True
        assert result.structuredContent["error"] == "empty_priorities_verbatim"

    @pytest.mark.asyncio
    async def test_non_empty_verbatim_proceeds_past_gate(self):
        """Non-empty user_priorities_verbatim proceeds past provenance gate."""
        from mcp_server.clarity.tools.prioritize_clusters import handle

        result = await handle(
            user_id="test",
            correlation_id="test",
            arguments={
                "user_priorities_verbatim": "my P1 is the work cluster",
                "clusters": [{"cluster_name": "Test", "thought_items": ["item1"]}],
                "priorities": [{"name": "Test", "rank": "P1"}],
            },
        )

        # Should NOT return provenance error - may return success or validation error
        if result.structuredContent:
            assert result.structuredContent.get("error") != "empty_priorities_verbatim"
