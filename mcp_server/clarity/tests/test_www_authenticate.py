import pytest
from mcp_server.clarity.mcp_auth import (
    build_unauthorized_error,
    build_forbidden_error,
    MCP_SERVER_URL,
)


def test_unauthorized_error_format():
    """401 response has RFC 6750 header string format."""
    result = build_unauthorized_error()

    assert "mcp/www_authenticate" in result
    www_auth = result["mcp/www_authenticate"]
    assert isinstance(www_auth, list)
    assert len(www_auth) == 1

    # Must be string, not dict
    header = www_auth[0]
    assert isinstance(header, str)

    # Must contain required parts
    assert header.startswith("Bearer ")
    assert f'resource_metadata="{MCP_SERVER_URL}/.well-known/oauth-protected-resource"' in header
    assert 'error="invalid_token"' in header
    assert 'error_description=' in header


def test_forbidden_error_format():
    """403 response has RFC 6750 header string with scope."""
    result = build_forbidden_error(required_scopes=["clarity.write"])

    assert "mcp/www_authenticate" in result
    www_auth = result["mcp/www_authenticate"]
    header = www_auth[0]

    assert isinstance(header, str)
    assert 'error="insufficient_scope"' in header
    assert 'scope="clarity.write"' in header


def test_forbidden_error_multiple_scopes():
    """403 with multiple scopes joins them with space."""
    result = build_forbidden_error(required_scopes=["clarity.read", "clarity.write"])

    header = result["mcp/www_authenticate"][0]
    assert 'scope="clarity.read clarity.write"' in header
