"""
Unit tests for Clarity schema compliance and timeout guarantees.

Tests:
1. Schema validation: Every "type": "object" node in INPUT_SCHEMA must have
   "additionalProperties": False at ALL depths.
2. Timeout guarantee: persistence.py must wrap all backend calls with
   asyncio.wait_for (static source check).
"""

from pathlib import Path


class TestSchemaAdditionalProperties:
    """Verify all tool schemas have additionalProperties: False on all object nodes."""

    def _walk_schema(self, schema: dict, path: str = "root") -> list[str]:
        """
        Recursively walk a JSON Schema and return paths of any "type": "object"
        nodes missing "additionalProperties": False.

        Returns list of violation paths (empty = compliant).
        """
        violations = []

        if not isinstance(schema, dict):
            return violations

        # Check if this node is a type object
        schema_type = schema.get("type")
        is_object_type = False

        if schema_type == "object":
            is_object_type = True
        elif isinstance(schema_type, list) and "object" in schema_type:
            # Handle "type": ["object", "null"]
            is_object_type = True

        if is_object_type:
            if schema.get("additionalProperties") is not False:
                violations.append(path)

        # Recurse into nested structures
        # Check "properties"
        if "properties" in schema:
            for prop_name, prop_schema in schema["properties"].items():
                violations.extend(
                    self._walk_schema(prop_schema, f"{path}.properties.{prop_name}")
                )

        # Check "items" (for arrays)
        if "items" in schema:
            items = schema["items"]
            if isinstance(items, dict):
                violations.extend(self._walk_schema(items, f"{path}.items"))
            elif isinstance(items, list):
                for i, item_schema in enumerate(items):
                    violations.extend(self._walk_schema(item_schema, f"{path}.items[{i}]"))

        # Check "oneOf", "anyOf", "allOf"
        for keyword in ("oneOf", "anyOf", "allOf"):
            if keyword in schema:
                for i, sub_schema in enumerate(schema[keyword]):
                    violations.extend(
                        self._walk_schema(sub_schema, f"{path}.{keyword}[{i}]")
                    )

        # Check "additionalProperties" if it's a schema (not just False/True)
        if isinstance(schema.get("additionalProperties"), dict):
            violations.extend(
                self._walk_schema(
                    schema["additionalProperties"],
                    f"{path}.additionalProperties"
                )
            )

        return violations

    def test_all_tools_have_additional_properties_false(self):
        """Every 'type: object' node in every tool's INPUT_SCHEMA must have additionalProperties: False."""
        from mcp_server.clarity.tools import TOOL_REGISTRY

        all_violations = []

        for tool_name, tool_def in TOOL_REGISTRY.items():
            schema = tool_def.input_schema
            violations = self._walk_schema(schema, "root")
            for v in violations:
                all_violations.append(f"{tool_name}: {v}")

        if all_violations:
            violation_list = "\n  - ".join(all_violations)
            raise AssertionError(
                f"Schema compliance violation: {len(all_violations)} object node(s) "
                f"missing additionalProperties: False:\n  - {violation_list}"
            )


class TestTimeoutGuarantee:
    """Verify persistence.py wraps all backend calls with asyncio.wait_for."""

    def test_persistence_uses_asyncio_wait_for(self):
        """persistence.py must have asyncio.wait_for wrapping all 3 backend calls."""
        # Read the source file directly
        persistence_path = Path(__file__).parent.parent.parent.parent.parent / \
            "mcp_server" / "clarity" / "persistence.py"

        source = persistence_path.read_text()

        # Count occurrences of asyncio.wait_for
        count = source.count("asyncio.wait_for")

        assert count >= 3, (
            f"persistence.py should have at least 3 asyncio.wait_for calls "
            f"(one per backend call: persist_cluster, get_cluster, delete_cluster). "
            f"Found {count}."
        )

    def test_timeout_constant_exists(self):
        """persistence.py must define TIMEOUT_S constant."""
        persistence_path = Path(__file__).parent.parent.parent.parent.parent / \
            "mcp_server" / "clarity" / "persistence.py"

        source = persistence_path.read_text()

        assert "TIMEOUT_S" in source, (
            "persistence.py should define TIMEOUT_S constant for asyncio.wait_for timeout."
        )

        # Verify it's set to a reasonable value (≤ 8.0 per ADR)
        assert "TIMEOUT_S = 8.0" in source or "TIMEOUT_S=8.0" in source, (
            "TIMEOUT_S should be set to 8.0 (per ADR: must be ≤ 8.0 to leave margin "
            "within ~10s MCP execution window)."
        )
