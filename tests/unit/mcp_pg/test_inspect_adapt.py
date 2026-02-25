"""
Unit tests for inspect_adapt MCP tool (Increment 29).

Tests:
- Phase start validation
- Phase commit provenance validation (isError: true)
- Phase commit conversational guardrails (isError: false)
- Phase commit defensive guards (ToolUsageError)
"""

import pytest

from mcp_server.priority_guardian.tools.inspect_adapt import (
    handle,
    GUIDANCE_START,
    GUIDANCE_COMMIT_SUCCESS,
    GUIDANCE_EMPTY_REFLECTION_VERBATIM,
    GUIDANCE_EMPTY_REFLECTION_DESCRIPTION,
    GUIDANCE_EMPTY_ACTION_VERBATIM,
    GUIDANCE_EMPTY_ACTION,
    GUIDANCE_INVALID_DERIVED_FROM_ID,
    GUIDANCE_USER_NOT_CONFIRMED,
)
from mcp_server.priority_guardian.tools.base import ToolUsageError


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def valid_reflection_items():
    """Valid reflection items for commit phase."""
    return [
        {
            "id": "r1",
            "user_reflection_verbatim": "I blocked 2 hours every morning before checking email",
            "description": "Morning time block before email",
            "lens": "helped",
        },
    ]


@pytest.fixture
def valid_action_steps():
    """Valid action steps for commit phase."""
    return [
        {
            "user_action_verbatim": "I'll keep the morning block but add a reminder",
            "action": "Continue morning block with calendar reminder at 8am",
            "derived_from_id": "r1",
        },
    ]


@pytest.fixture
def valid_commit_args(valid_reflection_items, valid_action_steps):
    """Valid arguments for commit phase."""
    return {
        "phase": "commit",
        "reflection_items": valid_reflection_items,
        "action_steps": valid_action_steps,
        "user_confirmed": True,
    }


# ============================================================================
# Phase Start Tests
# ============================================================================

class TestPhaseStart:
    """Tests for phase='start' validation."""

    @pytest.mark.asyncio
    async def test_start_returns_guidance(self):
        """Valid start call returns success with GUIDANCE_START."""
        args = {
            "phase": "start",
            "weekly_context_summary": "P1 got 8h this week, on track. P2 got 2h, below target.",
        }

        result = await handle("user-123", "corr-456", args)

        assert result.isError is not True
        assert result.structuredContent["success"] is True
        assert result.structuredContent["phase"] == "start"
        assert result.structuredContent["weekly_context_summary"] == args["weekly_context_summary"]
        assert result.structuredContent["assistant_guidance"] == GUIDANCE_START

    @pytest.mark.asyncio
    async def test_start_missing_context(self):
        """Missing weekly_context_summary raises ToolUsageError."""
        args = {
            "phase": "start",
        }

        with pytest.raises(ToolUsageError) as exc_info:
            await handle("user-123", "corr-456", args)

        assert "weekly_context_summary is required" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_start_empty_context(self):
        """Empty string weekly_context_summary raises ToolUsageError."""
        args = {
            "phase": "start",
            "weekly_context_summary": "",
        }

        with pytest.raises(ToolUsageError) as exc_info:
            await handle("user-123", "corr-456", args)

        assert "weekly_context_summary is required" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_start_whitespace_only_context(self):
        """Whitespace-only weekly_context_summary raises ToolUsageError."""
        args = {
            "phase": "start",
            "weekly_context_summary": "   ",
        }

        with pytest.raises(ToolUsageError) as exc_info:
            await handle("user-123", "corr-456", args)

        assert "weekly_context_summary is required" in str(exc_info.value)


# ============================================================================
# Phase Commit - Success Tests
# ============================================================================

class TestPhaseCommitSuccess:
    """Tests for successful commit phase."""

    @pytest.mark.asyncio
    async def test_commit_success(self, valid_commit_args):
        """Valid commit with all fields returns success with GUIDANCE_COMMIT_SUCCESS."""
        result = await handle("user-123", "corr-456", valid_commit_args)

        assert result.isError is not True
        assert result.structuredContent["success"] is True
        assert result.structuredContent["phase"] == "commit"
        assert result.structuredContent["completed"] is True
        assert result.structuredContent["assistant_guidance"] == GUIDANCE_COMMIT_SUCCESS
        assert len(result.structuredContent["reflection_items"]) == 1
        assert len(result.structuredContent["action_steps"]) == 1
        assert "1 action step(s) confirmed" in result.content[0].text

    @pytest.mark.asyncio
    async def test_commit_multiple_items(self):
        """Commit with multiple reflection items and action steps succeeds."""
        args = {
            "phase": "commit",
            "reflection_items": [
                {
                    "id": "r1",
                    "user_reflection_verbatim": "Morning routine helped",
                    "description": "Consistent morning routine",
                    "lens": "helped",
                },
                {
                    "id": "r2",
                    "user_reflection_verbatim": "Too many meetings in the afternoon",
                    "description": "Afternoon meeting overload",
                    "lens": "hindered",
                },
            ],
            "action_steps": [
                {
                    "user_action_verbatim": "Keep morning routine",
                    "action": "Continue morning routine",
                    "derived_from_id": "r1",
                },
                {
                    "user_action_verbatim": "Block one meeting-free afternoon",
                    "action": "Block Wednesday afternoon as meeting-free",
                    "derived_from_id": "r2",
                },
            ],
            "user_confirmed": True,
        }

        result = await handle("user-123", "corr-456", args)

        assert result.isError is not True
        assert result.structuredContent["success"] is True
        assert "2 action step(s) confirmed" in result.content[0].text

    @pytest.mark.asyncio
    async def test_commit_valid_derived_from_id_linkage(self):
        """derived_from_id correctly matches reflection item ids, succeeds."""
        args = {
            "phase": "commit",
            "reflection_items": [
                {
                    "id": "r1",
                    "user_reflection_verbatim": "First reflection",
                    "description": "First item",
                    "lens": "helped",
                },
                {
                    "id": "r2",
                    "user_reflection_verbatim": "Second reflection",
                    "description": "Second item",
                    "lens": "hindered",
                },
            ],
            "action_steps": [
                {
                    "user_action_verbatim": "Action for second",
                    "action": "Do something about second",
                    "derived_from_id": "r2",  # Links to r2
                },
            ],
            "user_confirmed": True,
        }

        result = await handle("user-123", "corr-456", args)

        assert result.isError is not True
        assert result.structuredContent["success"] is True


# ============================================================================
# Phase Commit - Provenance Validation Tests (isError: true)
# ============================================================================

class TestPhaseCommitProvenance:
    """Tests for commit phase provenance validation (isError: true)."""

    @pytest.mark.asyncio
    async def test_commit_missing_reflection_items(self):
        """Missing reflection_items returns provenance error."""
        args = {
            "phase": "commit",
            "action_steps": [
                {
                    "user_action_verbatim": "Do something",
                    "action": "Something",
                    "derived_from_id": "r1",
                },
            ],
            "user_confirmed": True,
        }

        result = await handle("user-123", "corr-456", args)

        assert result.isError is True
        assert result.structuredContent["success"] is False
        assert result.structuredContent["error"] == "empty_reflection_verbatim"
        assert GUIDANCE_EMPTY_REFLECTION_VERBATIM in result.structuredContent["assistant_guidance"]["instruction"]

    @pytest.mark.asyncio
    async def test_commit_empty_reflection_items(self):
        """Empty reflection_items array returns provenance error."""
        args = {
            "phase": "commit",
            "reflection_items": [],
            "action_steps": [
                {
                    "user_action_verbatim": "Do something",
                    "action": "Something",
                    "derived_from_id": "r1",
                },
            ],
            "user_confirmed": True,
        }

        result = await handle("user-123", "corr-456", args)

        assert result.isError is True
        assert result.structuredContent["error"] == "empty_reflection_verbatim"

    @pytest.mark.asyncio
    async def test_commit_reflection_verbatim_empty(self):
        """Empty user_reflection_verbatim returns provenance error."""
        args = {
            "phase": "commit",
            "reflection_items": [
                {
                    "id": "r1",
                    "user_reflection_verbatim": "",
                    "description": "Some description",
                    "lens": "helped",
                },
            ],
            "action_steps": [
                {
                    "user_action_verbatim": "Do something",
                    "action": "Something",
                    "derived_from_id": "r1",
                },
            ],
            "user_confirmed": True,
        }

        result = await handle("user-123", "corr-456", args)

        assert result.isError is True
        assert result.structuredContent["error"] == "empty_reflection_verbatim"

    @pytest.mark.asyncio
    async def test_commit_reflection_description_empty(self):
        """Empty description returns provenance error."""
        args = {
            "phase": "commit",
            "reflection_items": [
                {
                    "id": "r1",
                    "user_reflection_verbatim": "User said something",
                    "description": "",
                    "lens": "helped",
                },
            ],
            "action_steps": [
                {
                    "user_action_verbatim": "Do something",
                    "action": "Something",
                    "derived_from_id": "r1",
                },
            ],
            "user_confirmed": True,
        }

        result = await handle("user-123", "corr-456", args)

        assert result.isError is True
        assert result.structuredContent["error"] == "empty_reflection_description"
        assert GUIDANCE_EMPTY_REFLECTION_DESCRIPTION in result.structuredContent["assistant_guidance"]["instruction"]

    @pytest.mark.asyncio
    async def test_commit_missing_action_steps(self):
        """Missing action_steps returns provenance error."""
        args = {
            "phase": "commit",
            "reflection_items": [
                {
                    "id": "r1",
                    "user_reflection_verbatim": "User said something",
                    "description": "Description",
                    "lens": "helped",
                },
            ],
            "user_confirmed": True,
        }

        result = await handle("user-123", "corr-456", args)

        assert result.isError is True
        assert result.structuredContent["error"] == "empty_action_verbatim"
        assert GUIDANCE_EMPTY_ACTION_VERBATIM in result.structuredContent["assistant_guidance"]["instruction"]

    @pytest.mark.asyncio
    async def test_commit_empty_action_steps(self):
        """Empty action_steps array returns provenance error."""
        args = {
            "phase": "commit",
            "reflection_items": [
                {
                    "id": "r1",
                    "user_reflection_verbatim": "User said something",
                    "description": "Description",
                    "lens": "helped",
                },
            ],
            "action_steps": [],
            "user_confirmed": True,
        }

        result = await handle("user-123", "corr-456", args)

        assert result.isError is True
        assert result.structuredContent["error"] == "empty_action_verbatim"

    @pytest.mark.asyncio
    async def test_commit_action_verbatim_empty(self):
        """Empty user_action_verbatim returns provenance error."""
        args = {
            "phase": "commit",
            "reflection_items": [
                {
                    "id": "r1",
                    "user_reflection_verbatim": "User said something",
                    "description": "Description",
                    "lens": "helped",
                },
            ],
            "action_steps": [
                {
                    "user_action_verbatim": "",
                    "action": "Something",
                    "derived_from_id": "r1",
                },
            ],
            "user_confirmed": True,
        }

        result = await handle("user-123", "corr-456", args)

        assert result.isError is True
        assert result.structuredContent["error"] == "empty_action_verbatim"

    @pytest.mark.asyncio
    async def test_commit_action_empty(self):
        """Empty action returns provenance error."""
        args = {
            "phase": "commit",
            "reflection_items": [
                {
                    "id": "r1",
                    "user_reflection_verbatim": "User said something",
                    "description": "Description",
                    "lens": "helped",
                },
            ],
            "action_steps": [
                {
                    "user_action_verbatim": "User said they will do something",
                    "action": "",
                    "derived_from_id": "r1",
                },
            ],
            "user_confirmed": True,
        }

        result = await handle("user-123", "corr-456", args)

        assert result.isError is True
        assert result.structuredContent["error"] == "empty_action"
        assert GUIDANCE_EMPTY_ACTION in result.structuredContent["assistant_guidance"]["instruction"]

    @pytest.mark.asyncio
    async def test_commit_invalid_derived_from_id(self):
        """derived_from_id doesn't match any reflection item id, returns provenance error."""
        args = {
            "phase": "commit",
            "reflection_items": [
                {
                    "id": "r1",
                    "user_reflection_verbatim": "User said something",
                    "description": "Description",
                    "lens": "helped",
                },
            ],
            "action_steps": [
                {
                    "user_action_verbatim": "User said they will do something",
                    "action": "Do something",
                    "derived_from_id": "r99",  # Invalid - r99 doesn't exist
                },
            ],
            "user_confirmed": True,
        }

        result = await handle("user-123", "corr-456", args)

        assert result.isError is True
        assert result.structuredContent["error"] == "invalid_derived_from_id"
        assert GUIDANCE_INVALID_DERIVED_FROM_ID in result.structuredContent["assistant_guidance"]["instruction"]


# ============================================================================
# Phase Commit - Conversational Guardrail Tests (isError: false)
# ============================================================================

class TestPhaseCommitConversationalGuardrails:
    """Tests for commit phase conversational guardrails (isError: false)."""

    @pytest.mark.asyncio
    async def test_commit_user_not_confirmed(self, valid_reflection_items, valid_action_steps):
        """user_confirmed=false returns soft block with GUIDANCE_USER_NOT_CONFIRMED, isError=false."""
        args = {
            "phase": "commit",
            "reflection_items": valid_reflection_items,
            "action_steps": valid_action_steps,
            "user_confirmed": False,
        }

        result = await handle("user-123", "corr-456", args)

        assert result.isError is False  # Soft block, not error
        assert result.structuredContent["success"] is False
        assert result.structuredContent["needs_confirmation"] is True
        assert result.structuredContent["assistant_guidance"] == GUIDANCE_USER_NOT_CONFIRMED

    @pytest.mark.asyncio
    async def test_commit_user_confirmed_missing(self, valid_reflection_items, valid_action_steps):
        """user_confirmed not provided returns soft block, isError=false."""
        args = {
            "phase": "commit",
            "reflection_items": valid_reflection_items,
            "action_steps": valid_action_steps,
            # user_confirmed omitted
        }

        result = await handle("user-123", "corr-456", args)

        assert result.isError is False
        assert result.structuredContent["success"] is False
        assert result.structuredContent["needs_confirmation"] is True


# ============================================================================
# Phase Commit - Defensive Guard Tests (ToolUsageError)
# ============================================================================

class TestPhaseCommitDefensiveGuards:
    """Tests for commit phase defensive guards (ToolUsageError)."""

    @pytest.mark.asyncio
    async def test_commit_too_many_reflection_items(self):
        """4+ reflection items raises ToolUsageError."""
        args = {
            "phase": "commit",
            "reflection_items": [
                {"id": "r1", "user_reflection_verbatim": "a", "description": "a", "lens": "helped"},
                {"id": "r2", "user_reflection_verbatim": "b", "description": "b", "lens": "helped"},
                {"id": "r3", "user_reflection_verbatim": "c", "description": "c", "lens": "helped"},
                {"id": "r4", "user_reflection_verbatim": "d", "description": "d", "lens": "helped"},
            ],
            "action_steps": [
                {"user_action_verbatim": "x", "action": "x", "derived_from_id": "r1"},
            ],
            "user_confirmed": True,
        }

        with pytest.raises(ToolUsageError) as exc_info:
            await handle("user-123", "corr-456", args)

        assert "1-3 items" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_commit_too_many_action_steps(self, valid_reflection_items):
        """4+ action steps raises ToolUsageError."""
        args = {
            "phase": "commit",
            "reflection_items": valid_reflection_items,
            "action_steps": [
                {"user_action_verbatim": "a", "action": "a", "derived_from_id": "r1"},
                {"user_action_verbatim": "b", "action": "b", "derived_from_id": "r1"},
                {"user_action_verbatim": "c", "action": "c", "derived_from_id": "r1"},
                {"user_action_verbatim": "d", "action": "d", "derived_from_id": "r1"},
            ],
            "user_confirmed": True,
        }

        with pytest.raises(ToolUsageError) as exc_info:
            await handle("user-123", "corr-456", args)

        assert "1-3 items" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_commit_reflection_item_invalid_lens(self):
        """lens not in ["helped", "hindered"] raises ToolUsageError."""
        args = {
            "phase": "commit",
            "reflection_items": [
                {
                    "id": "r1",
                    "user_reflection_verbatim": "Something",
                    "description": "Description",
                    "lens": "neutral",  # Invalid
                },
            ],
            "action_steps": [
                {"user_action_verbatim": "x", "action": "x", "derived_from_id": "r1"},
            ],
            "user_confirmed": True,
        }

        with pytest.raises(ToolUsageError) as exc_info:
            await handle("user-123", "corr-456", args)

        assert "helped" in str(exc_info.value) or "hindered" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_commit_reflection_item_missing_id(self):
        """Missing id on reflection item raises ToolUsageError."""
        args = {
            "phase": "commit",
            "reflection_items": [
                {
                    # id missing
                    "user_reflection_verbatim": "Something",
                    "description": "Description",
                    "lens": "helped",
                },
            ],
            "action_steps": [
                {"user_action_verbatim": "x", "action": "x", "derived_from_id": "r1"},
            ],
            "user_confirmed": True,
        }

        with pytest.raises(ToolUsageError) as exc_info:
            await handle("user-123", "corr-456", args)

        assert "id" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_commit_reflection_item_empty_id(self):
        """Empty id on reflection item raises ToolUsageError."""
        args = {
            "phase": "commit",
            "reflection_items": [
                {
                    "id": "",
                    "user_reflection_verbatim": "Something",
                    "description": "Description",
                    "lens": "helped",
                },
            ],
            "action_steps": [
                {"user_action_verbatim": "x", "action": "x", "derived_from_id": "r1"},
            ],
            "user_confirmed": True,
        }

        with pytest.raises(ToolUsageError) as exc_info:
            await handle("user-123", "corr-456", args)

        assert "id" in str(exc_info.value).lower()


# ============================================================================
# Whitespace-Only Verbatim Tests
# ============================================================================

class TestWhitespaceOnlyVerbatim:
    """Tests for whitespace-only verbatim fields."""

    @pytest.mark.asyncio
    async def test_commit_whitespace_only_reflection_verbatim(self):
        """user_reflection_verbatim containing only whitespace returns provenance error."""
        args = {
            "phase": "commit",
            "reflection_items": [
                {
                    "id": "r1",
                    "user_reflection_verbatim": "   \t\n  ",
                    "description": "Description",
                    "lens": "helped",
                },
            ],
            "action_steps": [
                {"user_action_verbatim": "x", "action": "x", "derived_from_id": "r1"},
            ],
            "user_confirmed": True,
        }

        result = await handle("user-123", "corr-456", args)

        assert result.isError is True
        assert result.structuredContent["error"] == "empty_reflection_verbatim"

    @pytest.mark.asyncio
    async def test_commit_whitespace_only_action_verbatim(self):
        """user_action_verbatim containing only whitespace returns provenance error."""
        args = {
            "phase": "commit",
            "reflection_items": [
                {
                    "id": "r1",
                    "user_reflection_verbatim": "Something",
                    "description": "Description",
                    "lens": "helped",
                },
            ],
            "action_steps": [
                {"user_action_verbatim": "   ", "action": "x", "derived_from_id": "r1"},
            ],
            "user_confirmed": True,
        }

        result = await handle("user-123", "corr-456", args)

        assert result.isError is True
        assert result.structuredContent["error"] == "empty_action_verbatim"


# ============================================================================
# Invalid Phase Tests
# ============================================================================

class TestInvalidPhase:
    """Tests for invalid phase handling."""

    @pytest.mark.asyncio
    async def test_invalid_phase_raises_error(self):
        """Invalid phase raises ToolUsageError."""
        args = {
            "phase": "invalid",
        }

        with pytest.raises(ToolUsageError) as exc_info:
            await handle("user-123", "corr-456", args)

        assert "Invalid phase" in str(exc_info.value)
