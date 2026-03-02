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
        """create_priority has name, type, and verbatim fields as required."""
        from mcp_server.priority_guardian.tools.create_priority import INPUT_SCHEMA

        required = INPUT_SCHEMA.get("required", [])
        assert "name" in required, "name should be required"
        assert "type" in required, "type should be required"
        assert "user_priority_name_verbatim" in required, "user_priority_name_verbatim should be required"
        assert "user_priority_type_verbatim" in required, "user_priority_type_verbatim should be required"

    def test_create_priority_schema_requires_verbatim_fields(self):
        """create_priority requires verbatim provenance fields."""
        from mcp_server.priority_guardian.tools.create_priority import INPUT_SCHEMA

        required = INPUT_SCHEMA.get("required", [])
        assert "user_priority_name_verbatim" in required
        assert "user_priority_type_verbatim" in required

    def test_create_priority_schema_has_additional_properties_false(self):
        """create_priority schema has additionalProperties: false."""
        from mcp_server.priority_guardian.tools.create_priority import INPUT_SCHEMA

        assert INPUT_SCHEMA.get("additionalProperties") is False

    def test_create_priority_has_all_fields(self):
        """create_priority schema has all expected fields including verbatim."""
        from mcp_server.priority_guardian.tools.create_priority import INPUT_SCHEMA

        properties = INPUT_SCHEMA.get("properties", {})
        expected_fields = {
            "user_priority_name_verbatim",
            "name",
            "user_priority_type_verbatim",
            "type",
            "calendar_keyword",
            "deadline",
            "weekly_hour_target",
            "checkpoint_date",
            "user_goal_verbatim",
            "initial_goal_text",
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

    @pytest.mark.asyncio
    async def test_public_tools_with_widget_uri_have_ui_resource_uri(self):
        """Public tools with widget_uri set have ui.resourceUri in meta."""
        from mcp_server.priority_guardian.tools import TOOL_REGISTRY, list_tools

        tools = await list_tools()
        tool_metas = {t.name: t.meta for t in tools}

        for name, tool_def in TOOL_REGISTRY.items():
            meta = tool_metas[name]
            ui_meta = meta.get("ui", {})
            if tool_def.visibility == "private":
                # Private tools do NOT get resourceUri - they mutate existing widget
                assert "resourceUri" not in ui_meta, \
                    f"Private tool {name} should not have ui.resourceUri"
                assert ui_meta.get("visibility") == ["app"], \
                    f"Private tool {name} should have ui.visibility: ['app']"
            elif tool_def.widget_uri:
                # Public tools with widget_uri must have ui.resourceUri
                assert ui_meta.get("resourceUri") == tool_def.widget_uri, \
                    f"{name} has widget_uri but missing ui.resourceUri in meta"
                # Also check compat alias
                assert meta.get("openai/outputTemplate") == tool_def.widget_uri, \
                    f"{name} meta openai/outputTemplate should match widget_uri (compat alias)"
            else:
                # Tools without widget_uri should not have resourceUri
                assert "resourceUri" not in ui_meta, \
                    f"{name} has no widget_uri but has ui.resourceUri"

    def test_create_priority_has_widget_uri(self):
        """create_priority has widget_uri for rendering dashboard after creation."""
        from mcp_server.priority_guardian.tools.create_priority import CREATE_PRIORITY

        assert CREATE_PRIORITY.widget_uri == "ui://widget/pg-dashboard.html"

    def test_create_priority_not_widget_accessible(self):
        """create_priority is not widget_accessible (requires verbatim provenance)."""
        from mcp_server.priority_guardian.tools.create_priority import CREATE_PRIORITY

        # widget_accessible should be False (default) or explicitly not True
        assert CREATE_PRIORITY.widget_accessible is not True


class TestListToolsMeta:
    """Tests for _meta produced by list_tools()."""

    @pytest.mark.asyncio
    async def test_create_priority_model_only_visibility(self):
        """create_priority has ui.visibility: ['model'] (Inc 16 security)."""
        from mcp_server.priority_guardian.tools import list_tools

        tools = await list_tools()
        create_priority_tool = next(t for t in tools if t.name == "create_priority")

        meta = create_priority_tool.meta
        ui_meta = meta.get("ui", {})
        # Must have ui.resourceUri (produces widget)
        assert ui_meta.get("resourceUri") == "ui://widget/pg-dashboard.html"
        # Must have ui.visibility: ["model"] (widget cannot call this tool)
        assert ui_meta.get("visibility") == ["model"], \
            "create_priority should have ui.visibility: ['model'] - widget cannot call it"
        # Compat alias should exist
        assert meta.get("openai/outputTemplate") == "ui://widget/pg-dashboard.html"

    @pytest.mark.asyncio
    async def test_get_priorities_model_and_app_visibility(self):
        """get_priorities has ui.visibility: ['model', 'app'] (widget can call it)."""
        from mcp_server.priority_guardian.tools import list_tools

        tools = await list_tools()
        get_priorities_tool = next(t for t in tools if t.name == "get_priorities")

        meta = get_priorities_tool.meta
        ui_meta = meta.get("ui", {})
        # Must have ui.resourceUri
        assert ui_meta.get("resourceUri") == "ui://widget/pg-dashboard.html"
        # Must have ui.visibility: ["model", "app"] (both model and widget can call)
        assert ui_meta.get("visibility") == ["model", "app"], \
            "get_priorities should have ui.visibility: ['model', 'app']"
        # Compat alias should exist
        assert meta.get("openai/outputTemplate") == "ui://widget/pg-dashboard.html"

    @pytest.mark.asyncio
    async def test_private_tool_meta_has_correct_flags(self):
        """Private tools have ui.visibility: ['app'], no invocation messages."""
        from mcp_server.priority_guardian.tools import list_tools

        tools = await list_tools()
        add_priority_tool = next(t for t in tools if t.name == "add_priority")

        meta = add_priority_tool.meta
        ui_meta = meta.get("ui", {})
        # Must have ui.visibility: ["app"] (widget-only)
        assert ui_meta.get("visibility") == ["app"], \
            "Private tool should have ui.visibility: ['app']"
        # Must NOT have ui.resourceUri (private tools mutate existing widget)
        assert "resourceUri" not in ui_meta, \
            "Private tool should not have ui.resourceUri"
        # Must NOT have invocation messages (LLM doesn't see private tools)
        assert "openai/toolInvocation/invoking" not in meta, \
            "Private tool should not have invocation messages"
        assert "openai/toolInvocation/invoked" not in meta, \
            "Private tool should not have invocation messages"

    @pytest.mark.asyncio
    async def test_oauth2_tool_has_security_schemes(self):
        """Tool with required_scopes has oauth2 securitySchemes in meta."""
        from mcp_server.priority_guardian.tools import list_tools

        tools = await list_tools()
        create_priority_tool = next(t for t in tools if t.name == "create_priority")

        meta = create_priority_tool.meta
        security_schemes = meta.get("securitySchemes")
        assert security_schemes is not None, "Tool should have securitySchemes"
        assert len(security_schemes) == 1
        assert security_schemes[0]["type"] == "oauth2"
        assert "scopes" in security_schemes[0]
        assert len(security_schemes[0]["scopes"]) > 0, "oauth2 tool should have non-empty scopes"

    @pytest.mark.asyncio
    async def test_noauth_tool_has_noauth_security_scheme(self):
        """Tool without required_scopes has noauth securitySchemes in meta."""
        from mcp_server.priority_guardian.tools import list_tools, TOOL_REGISTRY

        # Find a tool without required_scopes
        tool_without_scopes = None
        for name, tool_def in TOOL_REGISTRY.items():
            if not tool_def.required_scopes:
                tool_without_scopes = name
                break

        if tool_without_scopes is None:
            pytest.skip("No tools without required_scopes found")

        tools = await list_tools()
        tool = next(t for t in tools if t.name == tool_without_scopes)

        meta = tool.meta
        security_schemes = meta.get("securitySchemes")
        assert security_schemes is not None, "Tool should have securitySchemes"
        assert len(security_schemes) == 1
        assert security_schemes[0]["type"] == "noauth"
