"""
Schema compliance tests for Priority Guardian MCP tools.

Tests:
- All INPUT_SCHEMA objects have additionalProperties: False (recursive)
- All tool module files are registered in TOOL_REGISTRY (filesystem coverage)
"""

from pathlib import Path

import pytest

from mcp_server.priority_guardian.tools import TOOL_REGISTRY


# =============================================================================
# Schema Compliance Tests
# =============================================================================


def _check_additional_properties_false(schema: dict, path: str = "root") -> list[str]:
    """
    Recursively check that all 'type: object' schemas have additionalProperties: False.

    Args:
        schema: JSON schema dict to check
        path: Current path for error messages

    Returns:
        List of paths where additionalProperties is missing or not False
    """
    errors = []

    if not isinstance(schema, dict):
        return errors

    # Check if this is an object type
    if schema.get("type") == "object":
        if schema.get("additionalProperties") is not False:
            errors.append(path)

    # Recursively check nested schemas
    # Check 'properties' values
    if "properties" in schema and isinstance(schema["properties"], dict):
        for prop_name, prop_schema in schema["properties"].items():
            errors.extend(
                _check_additional_properties_false(
                    prop_schema, f"{path}.properties.{prop_name}"
                )
            )

    # Check 'items' (for array types)
    if "items" in schema:
        items = schema["items"]
        if isinstance(items, dict):
            errors.extend(_check_additional_properties_false(items, f"{path}.items"))
        elif isinstance(items, list):
            for i, item_schema in enumerate(items):
                errors.extend(
                    _check_additional_properties_false(item_schema, f"{path}.items[{i}]")
                )

    # Check 'additionalProperties' if it's a schema (not just False)
    if "additionalProperties" in schema and isinstance(schema["additionalProperties"], dict):
        errors.extend(
            _check_additional_properties_false(
                schema["additionalProperties"], f"{path}.additionalProperties"
            )
        )

    # Check 'patternProperties' values
    if "patternProperties" in schema and isinstance(schema["patternProperties"], dict):
        for pattern, pattern_schema in schema["patternProperties"].items():
            errors.extend(
                _check_additional_properties_false(
                    pattern_schema, f"{path}.patternProperties.{pattern}"
                )
            )

    # Check allOf, anyOf, oneOf
    for keyword in ("allOf", "anyOf", "oneOf"):
        if keyword in schema and isinstance(schema[keyword], list):
            for i, sub_schema in enumerate(schema[keyword]):
                errors.extend(
                    _check_additional_properties_false(sub_schema, f"{path}.{keyword}[{i}]")
                )

    # Check 'if', 'then', 'else'
    for keyword in ("if", "then", "else"):
        if keyword in schema and isinstance(schema[keyword], dict):
            errors.extend(
                _check_additional_properties_false(schema[keyword], f"{path}.{keyword}")
            )

    return errors


class TestSchemaCompliance:
    """Tests for INPUT_SCHEMA compliance."""

    def test_all_input_schemas_have_additional_properties_false(self):
        """Every object schema must have additionalProperties: False."""
        all_errors = {}

        for tool_name, tool_def in TOOL_REGISTRY.items():
            errors = _check_additional_properties_false(
                tool_def.input_schema, f"{tool_name}.INPUT_SCHEMA"
            )
            if errors:
                all_errors[tool_name] = errors

        if all_errors:
            error_msg = "\n".join(
                f"  {tool}: {', '.join(paths)}"
                for tool, paths in all_errors.items()
            )
            pytest.fail(
                f"The following schemas are missing additionalProperties: False:\n{error_msg}"
            )


# =============================================================================
# Filesystem Coverage Tests
# =============================================================================


class TestFilesystemCoverage:
    """Tests to ensure all tool modules are registered."""

    def test_no_unregistered_tool_modules(self):
        """Every .py file in tools/ and tools/widget_tools/ must be in TOOL_REGISTRY."""
        # Get the tools directory
        tools_dir = Path(__file__).parent.parent.parent.parent / "mcp_server" / "priority_guardian" / "tools"

        # Files to exclude (infrastructure, not tools)
        excluded_files = {
            "__init__.py",
            "base.py",
        }

        # Get expected tool module names from filesystem
        expected_tools = set()

        # Check main tools directory
        for file_path in tools_dir.glob("*.py"):
            if file_path.name not in excluded_files:
                expected_tools.add(file_path.stem)

        # Check widget_tools directory
        widget_tools_dir = tools_dir / "widget_tools"
        if widget_tools_dir.exists():
            for file_path in widget_tools_dir.glob("*.py"):
                if file_path.name not in excluded_files:
                    expected_tools.add(file_path.stem)

        # Get registered tool names
        registered_tools = set(TOOL_REGISTRY.keys())

        # Map module names to tool names (they may differ)
        # Build a mapping from filesystem stems to expected tool names
        module_to_tool_mapping = {
            # Main tools
            "create_priority": "create_priority",
            "get_priorities": "get_priorities",
            "get_weekly_report": "get_weekly_report",
            "get_patterns": "get_patterns",
            "onboarding_calendar_setup": "onboarding_calendar_setup",
            "inspect_adapt": "inspect_adapt",
            # Widget tools
            "add_priority": "add_priority",
            "update_priority": "update_priority",
            "delete_priority": "delete_priority",
            "add_deliverable": "add_deliverable",
            "update_deliverable": "update_deliverable",
            "delete_deliverable": "delete_deliverable",
            "add_goal": "add_goal",
            "update_goal": "update_goal",
            "delete_goal": "delete_goal",
            "connect_google_calendar": "connect_google_calendar",
            "disconnect_google_calendar": "disconnect_google_calendar",
        }

        # Check that all expected modules are registered
        missing_tools = []
        for module_name in expected_tools:
            expected_tool_name = module_to_tool_mapping.get(module_name, module_name)
            if expected_tool_name not in registered_tools:
                missing_tools.append(f"{module_name} (expected tool: {expected_tool_name})")

        if missing_tools:
            pytest.fail(
                f"The following tool modules are not registered in TOOL_REGISTRY:\n"
                f"  {', '.join(missing_tools)}"
            )

    def test_registry_has_no_orphan_tools(self):
        """Every tool in TOOL_REGISTRY should have a corresponding module file."""
        # Get the tools directory
        tools_dir = Path(__file__).parent.parent.parent.parent / "mcp_server" / "priority_guardian" / "tools"

        # Build set of module stems
        module_stems = set()

        # Main tools directory
        for file_path in tools_dir.glob("*.py"):
            if file_path.name not in {"__init__.py", "base.py"}:
                module_stems.add(file_path.stem)

        # Widget tools directory
        widget_tools_dir = tools_dir / "widget_tools"
        if widget_tools_dir.exists():
            for file_path in widget_tools_dir.glob("*.py"):
                if file_path.name != "__init__.py":
                    module_stems.add(file_path.stem)

        # Map tool names to module stems
        tool_to_module_mapping = {
            "create_priority": "create_priority",
            "get_priorities": "get_priorities",
            "get_weekly_report": "get_weekly_report",
            "get_patterns": "get_patterns",
            "onboarding_calendar_setup": "onboarding_calendar_setup",
            "inspect_adapt": "inspect_adapt",
            "add_priority": "add_priority",
            "update_priority": "update_priority",
            "delete_priority": "delete_priority",
            "add_deliverable": "add_deliverable",
            "update_deliverable": "update_deliverable",
            "delete_deliverable": "delete_deliverable",
            "add_goal": "add_goal",
            "update_goal": "update_goal",
            "delete_goal": "delete_goal",
            "connect_google_calendar": "connect_google_calendar",
            "disconnect_google_calendar": "disconnect_google_calendar",
        }

        # Check for orphan tools
        orphan_tools = []
        for tool_name in TOOL_REGISTRY.keys():
            expected_module = tool_to_module_mapping.get(tool_name, tool_name)
            if expected_module not in module_stems:
                orphan_tools.append(tool_name)

        if orphan_tools:
            pytest.fail(
                f"The following tools in TOOL_REGISTRY have no module file:\n"
                f"  {', '.join(orphan_tools)}"
            )
