"""
Tests for export_checklist tool.

Tests both pure logic (tool_logic.py) and handler (tools/export_checklist.py).
"""

import pytest
from pydantic import ValidationError

from mcp_server.sharpen.tool_logic import generate_checklist_markdown, export_checklist
from mcp_server.sharpen.tools.export_checklist import handle, ExportChecklistRequest


# ============================================================================
# Pure Logic Tests (tool_logic.py)
# ============================================================================


class TestGenerateChecklistMarkdown:
    """Tests for generate_checklist_markdown function."""

    def test_single_deliverable_generates_correct_markdown(self):
        """Input: 3 items under 1 deliverable. Assert: one ## section, 3 checkboxes."""
        items = [
            {"task_name": "Task 1", "deliverable": "Deliverable A", "estimate_hours": 2},
            {"task_name": "Task 2", "deliverable": "Deliverable A", "estimate_hours": 1},
            {"task_name": "Task 3", "deliverable": "Deliverable A", "estimate_hours": 3},
        ]

        result = generate_checklist_markdown("Test Project", items)

        # Check header
        assert "# Test Project — Work Plan" in result

        # Check single deliverable section
        assert "## Deliverable A" in result
        assert result.count("##") == 1  # Only one deliverable section

        # Check all 3 checkboxes
        assert "- [ ] Task 1 (2h)" in result
        assert "- [ ] Task 2 (1h)" in result
        assert "- [ ] Task 3 (3h)" in result

    def test_multiple_deliverables_grouped_correctly(self):
        """Input: 5 items across 2 deliverables. Assert: two ## sections, items grouped."""
        items = [
            {"task_name": "Task A1", "deliverable": "Deliverable A", "estimate_hours": 2},
            {"task_name": "Task B1", "deliverable": "Deliverable B", "estimate_hours": 1},
            {"task_name": "Task A2", "deliverable": "Deliverable A", "estimate_hours": 3},
            {"task_name": "Task B2", "deliverable": "Deliverable B", "estimate_hours": 2},
            {"task_name": "Task B3", "deliverable": "Deliverable B"},  # No estimate
        ]

        result = generate_checklist_markdown("Multi-Deliverable", items)

        # Check two deliverable sections
        assert "## Deliverable A" in result
        assert "## Deliverable B" in result
        assert result.count("##") == 2

        # Tasks should be grouped (A tasks together, B tasks together)
        a_section_start = result.index("## Deliverable A")
        b_section_start = result.index("## Deliverable B")

        # Task A1 and A2 should appear after Deliverable A header
        assert result.index("Task A1") > a_section_start
        assert result.index("Task A2") > a_section_start

        # Task B1, B2, B3 should appear after Deliverable B header
        assert result.index("Task B1") > b_section_start
        assert result.index("Task B2") > b_section_start
        assert result.index("Task B3") > b_section_start

    def test_estimate_hours_formatted_correctly(self):
        """Items with estimates show (Xh), items without don't."""
        items = [
            {"task_name": "With estimate", "deliverable": "Test", "estimate_hours": 2.5},
            {"task_name": "Without estimate", "deliverable": "Test"},
            {"task_name": "Zero estimate", "deliverable": "Test", "estimate_hours": 0},
        ]

        result = generate_checklist_markdown("Estimate Test", items)

        assert "- [ ] With estimate (2.5h)" in result
        assert "- [ ] Without estimate" in result
        # Verify "Without estimate" line has no hours suffix
        for line in result.split("\n"):
            if "Without estimate" in line:
                assert "(h)" not in line
        assert "- [ ] Zero estimate (0h)" in result  # Zero is still shown

    def test_markdown_footer_includes_branding(self):
        """Footer contains 'Generated with Sharpen'."""
        items = [{"task_name": "Task", "deliverable": "Deliverable"}]

        result = generate_checklist_markdown("Branding Test", items)

        assert "Generated with Sharpen" in result
        assert "priority-guard.com" in result


class TestExportChecklist:
    """Tests for export_checklist function (pure domain data only)."""

    def test_returns_domain_data_only(self):
        """Result contains only domain data fields."""
        items = [
            {"task_name": "Task 1", "deliverable": "Deliverable", "estimate_hours": 2},
        ]

        result = export_checklist("Test Project", items)

        # Domain data should be present
        assert result["project_name"] == "Test Project"
        assert result["item_count"] == 1
        assert "checklist_markdown" in result

        # MCP transport concerns should NOT be in pure logic
        assert "status" not in result
        assert "format" not in result
        assert "assistant_guidance" not in result

    def test_item_count_matches_input(self):
        """item_count reflects actual number of items."""
        items = [
            {"task_name": "Task 1", "deliverable": "A"},
            {"task_name": "Task 2", "deliverable": "B"},
            {"task_name": "Task 3", "deliverable": "A"},
        ]

        result = export_checklist("Test", items)

        assert result["item_count"] == 3

    def test_checklist_markdown_contains_project(self):
        """checklist_markdown contains the formatted markdown."""
        items = [{"task_name": "Task", "deliverable": "Deliverable", "estimate_hours": 1}]

        result = export_checklist("Content Test", items)

        assert "# Content Test — Work Plan" in result["checklist_markdown"]


# ============================================================================
# Handler Tests (tools/export_checklist.py)
# ============================================================================


class TestExportChecklistHandler:
    """Tests for the MCP tool handler."""

    @pytest.mark.asyncio
    async def test_valid_input_returns_structured_content(self):
        """Valid input returns structuredContent with required fields."""
        arguments = {
            "project_name": "Handler Test",
            "items": [
                {"task_name": "Task 1", "deliverable": "Deliverable A", "estimate_hours": 2},
                {"task_name": "Task 2", "deliverable": "Deliverable A", "estimate_hours": 1},
            ],
        }

        result = await handle(arguments)

        assert result.isError is not True
        assert result.structuredContent is not None
        assert result.structuredContent["status"] == "exported"
        assert result.structuredContent["item_count"] == 2
        assert result.structuredContent["assistant_guidance"]["action"] == "CONFIRM_EXPORT"

    @pytest.mark.asyncio
    async def test_missing_project_name_returns_error(self):
        """Missing project_name returns isError=True."""
        arguments = {
            "items": [
                {"task_name": "Task", "deliverable": "Deliverable"},
            ],
        }

        result = await handle(arguments)

        assert result.isError is True

    @pytest.mark.asyncio
    async def test_missing_items_returns_error(self):
        """Missing items returns isError=True."""
        arguments = {
            "project_name": "No Items",
        }

        result = await handle(arguments)

        assert result.isError is True

    @pytest.mark.asyncio
    async def test_empty_items_returns_error(self):
        """Empty items array returns isError=True."""
        arguments = {
            "project_name": "Empty Items",
            "items": [],
        }

        result = await handle(arguments)

        assert result.isError is True

    @pytest.mark.asyncio
    async def test_item_missing_task_name_returns_error(self):
        """Item missing task_name returns isError=True."""
        arguments = {
            "project_name": "Missing Task Name",
            "items": [
                {"deliverable": "Deliverable"},  # Missing task_name
            ],
        }

        result = await handle(arguments)

        assert result.isError is True

    @pytest.mark.asyncio
    async def test_item_missing_deliverable_returns_error(self):
        """Item missing deliverable returns isError=True."""
        arguments = {
            "project_name": "Missing Deliverable",
            "items": [
                {"task_name": "Task"},  # Missing deliverable
            ],
        }

        result = await handle(arguments)

        assert result.isError is True


# ============================================================================
# Pydantic Model Tests
# ============================================================================


class TestExportChecklistRequest:
    """Tests for Pydantic validation model."""

    def test_valid_request(self):
        """Valid request parses correctly."""
        data = {
            "project_name": "Test",
            "items": [
                {"task_name": "Task", "deliverable": "Deliverable", "estimate_hours": 2},
            ],
        }

        request = ExportChecklistRequest.model_validate(data)

        assert request.project_name == "Test"
        assert len(request.items) == 1
        assert request.items[0].task_name == "Task"
        assert request.items[0].estimate_hours == 2

    def test_optional_estimate_hours(self):
        """estimate_hours is optional."""
        data = {
            "project_name": "Test",
            "items": [
                {"task_name": "Task", "deliverable": "Deliverable"},
            ],
        }

        request = ExportChecklistRequest.model_validate(data)

        assert request.items[0].estimate_hours is None

    def test_empty_items_raises(self):
        """Empty items array raises validation error."""
        data = {
            "project_name": "Test",
            "items": [],
        }

        with pytest.raises(ValidationError):
            ExportChecklistRequest.model_validate(data)
