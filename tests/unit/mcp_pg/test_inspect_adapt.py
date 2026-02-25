"""
Unit tests for inspect_adapt MCP tool (Increment 30).

Single-call tool — tests:
- Success cases
- Provenance validation (isError: true)
- Conversational guardrails (isError: false)
- Defensive guards (ToolUsageError)
"""

import pytest

from mcp_server.priority_guardian.tools.inspect_adapt import (
    handle,
    GUIDANCE_COMMIT_SUCCESS,
    GUIDANCE_EMPTY_REFLECTION_VERBATIM,
    GUIDANCE_EMPTY_ACTION_VERBATIM,
    GUIDANCE_INVALID_DERIVED_FROM_ID,
    GUIDANCE_USER_NOT_CONFIRMED,
)
from mcp_server.priority_guardian.tools.base import ToolUsageError


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def valid_reflection_items():
    """Valid reflection items."""
    return [
        {
            "id": "r1",
            "user_reflection_verbatim": "I blocked 2 hours every morning before checking email",
            "lens": "helped",
        },
    ]


@pytest.fixture
def valid_action_steps():
    """Valid action steps."""
    return [
        {
            "user_action_verbatim": "I'll keep the morning block but add a reminder",
            "derived_from_id": "r1",
        },
    ]


@pytest.fixture
def valid_args(valid_reflection_items, valid_action_steps):
    """Valid arguments for inspect_adapt."""
    return {
        "reflection_items": valid_reflection_items,
        "action_steps": valid_action_steps,
        "user_confirmed": True,
    }


# ============================================================================
# Success Tests
# ============================================================================

class TestSuccess:
    """Tests for successful inspect_adapt calls."""

    @pytest.mark.asyncio
    async def test_commit_success(self, valid_args):
        """Valid call with all fields returns success with GUIDANCE_COMMIT_SUCCESS."""
        result = await handle("user-123", "corr-456", valid_args)

        assert result.isError is not True
        assert result.structuredContent["success"] is True
        assert result.structuredContent["completed"] is True
        assert result.structuredContent["assistant_guidance"] == GUIDANCE_COMMIT_SUCCESS
        assert len(result.structuredContent["reflection_items"]) == 1
        assert len(result.structuredContent["action_steps"]) == 1
        assert "1 action step(s) confirmed" in result.content[0].text

    @pytest.mark.asyncio
    async def test_commit_multiple_items(self):
        """Multiple reflection items and action steps succeed."""
        args = {
            "reflection_items": [
                {
                    "id": "r1",
                    "user_reflection_verbatim": "Morning routine helped",
                    "lens": "helped",
                },
                {
                    "id": "r2",
                    "user_reflection_verbatim": "Too many meetings in the afternoon",
                    "lens": "hindered",
                },
            ],
            "action_steps": [
                {
                    "user_action_verbatim": "Keep morning routine",
                    "derived_from_id": "r1",
                },
                {
                    "user_action_verbatim": "Block one meeting-free afternoon",
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
            "reflection_items": [
                {
                    "id": "r1",
                    "user_reflection_verbatim": "First reflection",
                    "lens": "helped",
                },
                {
                    "id": "r2",
                    "user_reflection_verbatim": "Second reflection",
                    "lens": "hindered",
                },
            ],
            "action_steps": [
                {
                    "user_action_verbatim": "Action for second",
                    "derived_from_id": "r2",  # Links to r2
                },
            ],
            "user_confirmed": True,
        }

        result = await handle("user-123", "corr-456", args)

        assert result.isError is not True
        assert result.structuredContent["success"] is True


# ============================================================================
# Provenance Validation Tests (isError: true)
# ============================================================================

class TestProvenanceValidation:
    """Tests for provenance validation (isError: true)."""

    @pytest.mark.asyncio
    async def test_missing_reflection_items(self):
        """Missing reflection_items returns provenance error."""
        args = {
            "action_steps": [
                {
                    "user_action_verbatim": "Do something",
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
    async def test_empty_reflection_items(self):
        """Empty reflection_items array returns provenance error."""
        args = {
            "reflection_items": [],
            "action_steps": [
                {
                    "user_action_verbatim": "Do something",
                    "derived_from_id": "r1",
                },
            ],
            "user_confirmed": True,
        }

        result = await handle("user-123", "corr-456", args)

        assert result.isError is True
        assert result.structuredContent["error"] == "empty_reflection_verbatim"

    @pytest.mark.asyncio
    async def test_reflection_verbatim_empty(self):
        """Empty user_reflection_verbatim returns provenance error."""
        args = {
            "reflection_items": [
                {
                    "id": "r1",
                    "user_reflection_verbatim": "",
                    "lens": "helped",
                },
            ],
            "action_steps": [
                {
                    "user_action_verbatim": "Do something",
                    "derived_from_id": "r1",
                },
            ],
            "user_confirmed": True,
        }

        result = await handle("user-123", "corr-456", args)

        assert result.isError is True
        assert result.structuredContent["error"] == "empty_reflection_verbatim"

    @pytest.mark.asyncio
    async def test_missing_action_steps(self):
        """Missing action_steps returns provenance error."""
        args = {
            "reflection_items": [
                {
                    "id": "r1",
                    "user_reflection_verbatim": "User said something",
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
    async def test_empty_action_steps(self):
        """Empty action_steps array returns provenance error."""
        args = {
            "reflection_items": [
                {
                    "id": "r1",
                    "user_reflection_verbatim": "User said something",
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
    async def test_action_verbatim_empty(self):
        """Empty user_action_verbatim returns provenance error."""
        args = {
            "reflection_items": [
                {
                    "id": "r1",
                    "user_reflection_verbatim": "User said something",
                    "lens": "helped",
                },
            ],
            "action_steps": [
                {
                    "user_action_verbatim": "",
                    "derived_from_id": "r1",
                },
            ],
            "user_confirmed": True,
        }

        result = await handle("user-123", "corr-456", args)

        assert result.isError is True
        assert result.structuredContent["error"] == "empty_action_verbatim"

    @pytest.mark.asyncio
    async def test_invalid_derived_from_id(self):
        """derived_from_id doesn't match any reflection item id, returns provenance error."""
        args = {
            "reflection_items": [
                {
                    "id": "r1",
                    "user_reflection_verbatim": "User said something",
                    "lens": "helped",
                },
            ],
            "action_steps": [
                {
                    "user_action_verbatim": "User said they will do something",
                    "derived_from_id": "r99",  # Invalid - r99 doesn't exist
                },
            ],
            "user_confirmed": True,
        }

        result = await handle("user-123", "corr-456", args)

        assert result.isError is True
        assert result.structuredContent["error"] == "invalid_derived_from_id"
        assert GUIDANCE_INVALID_DERIVED_FROM_ID in result.structuredContent["assistant_guidance"]["instruction"]

    @pytest.mark.asyncio
    async def test_whitespace_only_reflection_verbatim(self):
        """user_reflection_verbatim containing only whitespace returns provenance error."""
        args = {
            "reflection_items": [
                {
                    "id": "r1",
                    "user_reflection_verbatim": "   \t\n  ",
                    "lens": "helped",
                },
            ],
            "action_steps": [
                {"user_action_verbatim": "x", "derived_from_id": "r1"},
            ],
            "user_confirmed": True,
        }

        result = await handle("user-123", "corr-456", args)

        assert result.isError is True
        assert result.structuredContent["error"] == "empty_reflection_verbatim"

    @pytest.mark.asyncio
    async def test_whitespace_only_action_verbatim(self):
        """user_action_verbatim containing only whitespace returns provenance error."""
        args = {
            "reflection_items": [
                {
                    "id": "r1",
                    "user_reflection_verbatim": "Something",
                    "lens": "helped",
                },
            ],
            "action_steps": [
                {"user_action_verbatim": "   ", "derived_from_id": "r1"},
            ],
            "user_confirmed": True,
        }

        result = await handle("user-123", "corr-456", args)

        assert result.isError is True
        assert result.structuredContent["error"] == "empty_action_verbatim"


# ============================================================================
# Conversational Guardrail Tests (isError: false)
# ============================================================================

class TestConversationalGuardrails:
    """Tests for conversational guardrails (isError: false)."""

    @pytest.mark.asyncio
    async def test_user_not_confirmed(self, valid_reflection_items, valid_action_steps):
        """user_confirmed=false returns soft block with GUIDANCE_USER_NOT_CONFIRMED, isError=false."""
        args = {
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
    async def test_user_confirmed_missing(self, valid_reflection_items, valid_action_steps):
        """user_confirmed not provided returns soft block, isError=false."""
        args = {
            "reflection_items": valid_reflection_items,
            "action_steps": valid_action_steps,
            # user_confirmed omitted
        }

        result = await handle("user-123", "corr-456", args)

        assert result.isError is False
        assert result.structuredContent["success"] is False
        assert result.structuredContent["needs_confirmation"] is True


# ============================================================================
# Defensive Guard Tests (ToolUsageError)
# ============================================================================

class TestDefensiveGuards:
    """Tests for defensive guards (ToolUsageError)."""

    @pytest.mark.asyncio
    async def test_too_many_reflection_items(self):
        """4+ reflection items raises ToolUsageError."""
        args = {
            "reflection_items": [
                {"id": "r1", "user_reflection_verbatim": "a", "lens": "helped"},
                {"id": "r2", "user_reflection_verbatim": "b", "lens": "helped"},
                {"id": "r3", "user_reflection_verbatim": "c", "lens": "helped"},
                {"id": "r4", "user_reflection_verbatim": "d", "lens": "helped"},
            ],
            "action_steps": [
                {"user_action_verbatim": "x", "derived_from_id": "r1"},
            ],
            "user_confirmed": True,
        }

        with pytest.raises(ToolUsageError) as exc_info:
            await handle("user-123", "corr-456", args)

        assert "1-3 items" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_too_many_action_steps(self, valid_reflection_items):
        """4+ action steps raises ToolUsageError."""
        args = {
            "reflection_items": valid_reflection_items,
            "action_steps": [
                {"user_action_verbatim": "a", "derived_from_id": "r1"},
                {"user_action_verbatim": "b", "derived_from_id": "r1"},
                {"user_action_verbatim": "c", "derived_from_id": "r1"},
                {"user_action_verbatim": "d", "derived_from_id": "r1"},
            ],
            "user_confirmed": True,
        }

        with pytest.raises(ToolUsageError) as exc_info:
            await handle("user-123", "corr-456", args)

        assert "1-3 items" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_reflection_item_invalid_lens(self):
        """lens not in ["helped", "hindered"] raises ToolUsageError."""
        args = {
            "reflection_items": [
                {
                    "id": "r1",
                    "user_reflection_verbatim": "Something",
                    "lens": "neutral",  # Invalid
                },
            ],
            "action_steps": [
                {"user_action_verbatim": "x", "derived_from_id": "r1"},
            ],
            "user_confirmed": True,
        }

        with pytest.raises(ToolUsageError) as exc_info:
            await handle("user-123", "corr-456", args)

        assert "helped" in str(exc_info.value) or "hindered" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_reflection_item_missing_id(self):
        """Missing id on reflection item raises ToolUsageError."""
        args = {
            "reflection_items": [
                {
                    # id missing
                    "user_reflection_verbatim": "Something",
                    "lens": "helped",
                },
            ],
            "action_steps": [
                {"user_action_verbatim": "x", "derived_from_id": "r1"},
            ],
            "user_confirmed": True,
        }

        with pytest.raises(ToolUsageError) as exc_info:
            await handle("user-123", "corr-456", args)

        assert "id" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_reflection_item_empty_id(self):
        """Empty id on reflection item raises ToolUsageError."""
        args = {
            "reflection_items": [
                {
                    "id": "",
                    "user_reflection_verbatim": "Something",
                    "lens": "helped",
                },
            ],
            "action_steps": [
                {"user_action_verbatim": "x", "derived_from_id": "r1"},
            ],
            "user_confirmed": True,
        }

        with pytest.raises(ToolUsageError) as exc_info:
            await handle("user-123", "corr-456", args)

        assert "id" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_reflection_item_duplicate_id(self):
        """Two items with same id raises ToolUsageError."""
        args = {
            "reflection_items": [
                {
                    "id": "r1",
                    "user_reflection_verbatim": "First",
                    "lens": "helped",
                },
                {
                    "id": "r1",  # Duplicate
                    "user_reflection_verbatim": "Second",
                    "lens": "hindered",
                },
            ],
            "action_steps": [
                {"user_action_verbatim": "x", "derived_from_id": "r1"},
            ],
            "user_confirmed": True,
        }

        with pytest.raises(ToolUsageError) as exc_info:
            await handle("user-123", "corr-456", args)

        assert "Duplicate" in str(exc_info.value)
        assert "r1" in str(exc_info.value)
