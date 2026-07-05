"""
Unit tests for persist truthfulness fixes (D2).

Verifies that when persist_cluster returns None (failure), the tool handlers:
1. Do NOT log "auto_persisted" (false success)
2. Return error response with isError=True
3. Include assistant_guidance telling the model to inform the user

These tests were added after the 2026-07-05 incident where organize_thoughts
logged "auto_persisted" even when persistence failed silently.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from mcp import types as mcp_types


class TestOrganizeThoughtsTruthfulness:
    """Tests for organize_thoughts persist failure handling."""

    @pytest.mark.asyncio
    async def test_persist_none_returns_error(self):
        """When persist_cluster returns None, organize_thoughts returns isError=True."""
        from mcp_server.clarity.tools.organize_thoughts import handle

        # Valid input that will pass provenance checks
        # Note: thought_items are strings, not dicts
        valid_arguments = {
            "clusters": [
                {
                    "cluster_name": "Test",
                    "thought_items": ["item one", "item two"],
                }
            ],
            "thoughts_exhausted": False,
            "user_thoughts_exhausted_verbatim": "that's everything",
            "user_confirmed_no_more_thoughts": True,
        }

        with patch("mcp_server.clarity.tools.organize_thoughts.persist_cluster",
                   new_callable=AsyncMock, return_value=None):  # Returns None!

            result = await handle(
                user_id="test-user",
                correlation_id="test-corr-id",
                arguments=valid_arguments,
            )

        # Verify error response
        assert result.isError is True
        assert result.structuredContent["success"] is False
        assert result.structuredContent["error"] == "persist_failed"
        assert "assistant_guidance" in result.structuredContent
        assert "NOT" in result.structuredContent["assistant_guidance"]["instruction"]

    @pytest.mark.asyncio
    async def test_persist_none_does_not_log_success(self):
        """When persist_cluster returns None, no success log is emitted."""
        from mcp_server.clarity.tools.organize_thoughts import handle

        valid_arguments = {
            "clusters": [
                {
                    "cluster_name": "Test",
                    "thought_items": ["item one", "item two"],
                }
            ],
            "thoughts_exhausted": False,
            "user_thoughts_exhausted_verbatim": "that's everything",
            "user_confirmed_no_more_thoughts": True,
        }

        with patch("mcp_server.clarity.tools.organize_thoughts.persist_cluster",
                   new_callable=AsyncMock, return_value=None), \
             patch("mcp_server.clarity.tools.organize_thoughts.logger") as mock_logger:

            await handle(
                user_id="test-user",
                correlation_id="test-corr-id",
                arguments=valid_arguments,
            )

        # Verify no "auto_persisted" log (that would be a false success claim)
        info_calls = [c for c in mock_logger.info.call_args_list
                      if "auto_persisted" in str(c)]
        assert len(info_calls) == 0, "Should not log auto_persisted on failure"

        # Verify error log was emitted
        error_calls = [c for c in mock_logger.error.call_args_list
                       if "persist_returned_none" in str(c)]
        assert len(error_calls) == 1, "Should log persist_returned_none"

    @pytest.mark.asyncio
    async def test_persist_success_logs_auto_persisted(self):
        """When persist_cluster returns cluster_id, auto_persisted IS logged."""
        from mcp_server.clarity.tools.organize_thoughts import handle

        valid_arguments = {
            "clusters": [
                {
                    "cluster_name": "Test",
                    "thought_items": ["item one", "item two"],
                }
            ],
            "thoughts_exhausted": False,
            "user_thoughts_exhausted_verbatim": "that's everything",
            "user_confirmed_no_more_thoughts": True,
        }

        with patch("mcp_server.clarity.tools.organize_thoughts.persist_cluster",
                   new_callable=AsyncMock, return_value="cluster-123"), \
             patch("mcp_server.clarity.tools.organize_thoughts.logger") as mock_logger:

            result = await handle(
                user_id="test-user",
                correlation_id="test-corr-id",
                arguments=valid_arguments,
            )

        # Verify success response
        assert result.isError is not True

        # Verify auto_persisted log WAS emitted with cluster_id
        info_calls = [str(c) for c in mock_logger.info.call_args_list]
        auto_persisted_calls = [c for c in info_calls if "auto_persisted" in c]
        assert len(auto_persisted_calls) == 1, "Should log auto_persisted on success"


class TestEditBoardTruthfulness:
    """Tests for edit_board persist failure handling."""

    @pytest.mark.asyncio
    async def test_persist_none_returns_error(self):
        """When persist_cluster returns None, edit_board returns isError=True."""
        from mcp_server.clarity.tools.edit_board import handle

        # Valid edit operation
        valid_arguments = {
            "operation": "rename_cluster",
            "target_name": "Old",
            "new_name": "New",
        }

        # Mock get_cluster to return existing board
        existing_board = {
            "cluster_id": "existing-123",
            "cluster_data": {
                "clusters": [
                    {
                        "cluster_name": "Old",
                        "thought_items": ["item one", "item two"],
                        "subclusters": [],
                        "tags": [],
                    }
                ]
            }
        }

        with patch("mcp_server.clarity.tools.edit_board.get_cluster",
                   new_callable=AsyncMock, return_value=existing_board), \
             patch("mcp_server.clarity.tools.edit_board.persist_cluster",
                   new_callable=AsyncMock, return_value=None):  # Returns None!

            result = await handle(
                user_id="test-user",
                correlation_id="test-corr-id",
                arguments=valid_arguments,
            )

        # Verify error response
        assert result.isError is True
        assert result.structuredContent["success"] is False
        assert result.structuredContent["error"] == "persist_failed"


class TestStartPrioritizationFlowTruthfulness:
    """Tests for start_prioritization_flow persist failure handling."""

    @pytest.mark.asyncio
    async def test_persist_none_returns_error(self):
        """When persist_cluster returns None, start_prioritization_flow returns isError=True."""
        from mcp_server.clarity.tools.start_prioritization_flow import handle

        # Valid prioritization (set P1) with required verbatim fields
        valid_arguments = {
            "user_prioritization_criterion_verbatim": "I want to focus on relief",
            "user_priorities_verbatim": "I'll focus on Cluster1 first",
            "priorities": [
                {"name": "Cluster1", "rank": "P1"}
            ],
        }

        # Mock get_cluster to return existing board
        existing_board = {
            "cluster_id": "existing-123",
            "cluster_data": {
                "clusters": [
                    {
                        "cluster_name": "Cluster1",
                        "thought_items": ["item one", "item two"],
                        "subclusters": [],
                        "tags": [],
                    }
                ]
            }
        }

        with patch("mcp_server.clarity.tools.start_prioritization_flow.get_cluster",
                   new_callable=AsyncMock, return_value=existing_board), \
             patch("mcp_server.clarity.tools.start_prioritization_flow.persist_cluster",
                   new_callable=AsyncMock, return_value=None):  # Returns None!

            result = await handle(
                user_id="test-user",
                correlation_id="test-corr-id",
                arguments=valid_arguments,
            )

        # Verify error response
        assert result.isError is True
        assert result.structuredContent["success"] is False
        assert result.structuredContent["error"] == "persist_failed"
