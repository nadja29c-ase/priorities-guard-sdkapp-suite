"""
Unit tests for Priority Guardian tool definitions.

Tests each tool's INPUT_SCHEMA and annotations:
- Schema is valid JSON Schema
- Required fields are correct
- Annotation values match expectations
"""

import pytest
import jsonschema


class TestInputSchemas:
    """Tests for tool INPUT_SCHEMA validity."""

    def test_connect_google_calendar_schema_valid(self):
        """connect_google_calendar has valid JSON Schema."""
        from mcp_server.priority_guardian.tools.widget_tools.connect_google_calendar import INPUT_SCHEMA

        # Validate it's a valid JSON Schema by using it
        jsonschema.Draft7Validator.check_schema(INPUT_SCHEMA)

    def test_connect_google_calendar_no_required_fields(self):
        """connect_google_calendar has no required fields."""
        from mcp_server.priority_guardian.tools.widget_tools.connect_google_calendar import INPUT_SCHEMA

        required = INPUT_SCHEMA.get("required", [])
        assert required == [], "connect_google_calendar should have no required fields"

    def test_disconnect_google_calendar_schema_valid(self):
        """disconnect_google_calendar has valid JSON Schema."""
        from mcp_server.priority_guardian.tools.widget_tools.disconnect_google_calendar import INPUT_SCHEMA

        jsonschema.Draft7Validator.check_schema(INPUT_SCHEMA)

    def test_disconnect_google_calendar_has_confirm_field(self):
        """disconnect_google_calendar has confirm field."""
        from mcp_server.priority_guardian.tools.widget_tools.disconnect_google_calendar import INPUT_SCHEMA

        properties = INPUT_SCHEMA.get("properties", {})
        assert "confirm" in properties, "disconnect_google_calendar should have confirm field"
        assert properties["confirm"]["type"] == "boolean"

    def test_create_priority_schema_valid(self):
        """create_priority has valid JSON Schema."""
        from mcp_server.priority_guardian.tools.create_priority import INPUT_SCHEMA

        jsonschema.Draft7Validator.check_schema(INPUT_SCHEMA)

    def test_create_priority_required_fields(self):
        """create_priority has name and type as required fields."""
        from mcp_server.priority_guardian.tools.create_priority import INPUT_SCHEMA

        required = INPUT_SCHEMA.get("required", [])
        assert "name" in required, "name should be required"
        assert "type" in required, "type should be required"

    def test_create_priority_has_all_fields(self):
        """create_priority schema has all expected fields."""
        from mcp_server.priority_guardian.tools.create_priority import INPUT_SCHEMA

        properties = INPUT_SCHEMA.get("properties", {})
        expected_fields = {
            "name",
            "type",
            "deadline",
            "weekly_hour_target",
            "checkpoint_date",
            "desired_result",
        }
        assert set(properties.keys()) == expected_fields

    def test_create_priority_type_enum(self):
        """create_priority type field has correct enum values."""
        from mcp_server.priority_guardian.tools.create_priority import INPUT_SCHEMA

        type_field = INPUT_SCHEMA["properties"]["type"]
        assert type_field["type"] == "string"
        assert set(type_field["enum"]) == {"deadline", "flexible"}


class TestRequiredScopesMatchConfig:
    """Tests that required_scopes matches TOOL_SCOPES in config.py."""

    def test_connect_google_calendar_scopes_match(self):
        """connect_google_calendar required_scopes matches config."""
        from mcp_server.priority_guardian.tools import get_tool
        from mcp_server.priority_guardian.config import TOOL_SCOPES

        tool = get_tool("connect_google_calendar")
        config_scopes = TOOL_SCOPES.get("connect_google_calendar", [])
        assert tool.required_scopes == config_scopes

    def test_disconnect_google_calendar_scopes_match(self):
        """disconnect_google_calendar required_scopes matches config."""
        from mcp_server.priority_guardian.tools import get_tool
        from mcp_server.priority_guardian.config import TOOL_SCOPES

        tool = get_tool("disconnect_google_calendar")
        config_scopes = TOOL_SCOPES.get("disconnect_google_calendar", [])
        assert tool.required_scopes == config_scopes

    def test_create_priority_scopes_match(self):
        """create_priority required_scopes matches config."""
        from mcp_server.priority_guardian.tools import get_tool
        from mcp_server.priority_guardian.config import TOOL_SCOPES

        tool = get_tool("create_priority")
        config_scopes = TOOL_SCOPES.get("create_priority", [])
        assert tool.required_scopes == config_scopes


class TestAnnotationValues:
    """Tests for specific annotation values."""

    def test_connect_google_calendar_not_destructive(self):
        """connect_google_calendar is not destructive."""
        from mcp_server.priority_guardian.tools import get_tool

        tool = get_tool("connect_google_calendar")
        assert tool.destructive_hint is False

    def test_disconnect_google_calendar_is_destructive(self):
        """disconnect_google_calendar is destructive (revokes tokens)."""
        from mcp_server.priority_guardian.tools import get_tool

        tool = get_tool("disconnect_google_calendar")
        assert tool.destructive_hint is True

    def test_disconnect_google_calendar_is_open_world(self):
        """disconnect_google_calendar is open_world (external Google API)."""
        from mcp_server.priority_guardian.tools import get_tool

        tool = get_tool("disconnect_google_calendar")
        assert tool.open_world_hint is True

    def test_create_priority_not_open_world(self):
        """create_priority is not open_world (internal only)."""
        from mcp_server.priority_guardian.tools import get_tool

        tool = get_tool("create_priority")
        assert tool.open_world_hint is False

    def test_create_priority_not_read_only(self):
        """create_priority is not read_only (creates data)."""
        from mcp_server.priority_guardian.tools import get_tool

        tool = get_tool("create_priority")
        assert tool.read_only_hint is False

    def test_widget_producing_tools_have_widget_uri(self):
        """Tools that produce widgets have correct widget_uri."""
        from mcp_server.priority_guardian.tools import TOOL_REGISTRY

        # Tools that produce the dashboard widget (used for initial render or pie chart)
        widget_producing_tools = {
            "connect_google_calendar",
            "disconnect_google_calendar",
            "get_priorities",
            "save_semantic_grouping",
        }

        for name, tool in TOOL_REGISTRY.items():
            if name in widget_producing_tools:
                assert tool.widget_uri == "ui://widget/pg-dashboard.html", \
                    f"{name} should have pg-dashboard.html widget_uri"
            else:
                # create_priority and private CRUD tools don't produce widgets
                assert tool.widget_uri is None, f"{name} should have no widget_uri"
