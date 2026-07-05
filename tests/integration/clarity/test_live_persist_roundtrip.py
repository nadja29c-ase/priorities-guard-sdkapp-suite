"""
Live Persist Roundtrip Test — Production Verification.

This test exercises an authenticated persist + retrieve roundtrip through the
DEPLOYED MindSort-Claude MCP server. It calls /mcp with JSON-RPC tools/call,
which exercises the full MCP → backend path internally (X-User-ID + X-Internal-Secret).

EXCLUDED FROM DEFAULT CI — requires:
  1. External network access to production
  2. A valid access token (provided via env var)

To run manually:
    MINDSORT_CLAUDE_TEST_TOKEN=<token> pytest -m live tests/integration/clarity/test_live_persist_roundtrip.py -v

WARNING — DESTRUCTIVE TEST:
This test OVERWRITES the user's MindSort board with test data. The test saves
the existing board first and restores it after. If the test fails mid-run,
manual restoration may be needed.

INCIDENT CONTEXT (2026-07-05):
This test was added after a silent persistence failure on MindSort-Claude that
went undetected for days. The failure occurred because CLARITY_BACKEND_URL was
unset in the MCP server, falling back to localhost:8000, while organize_thoughts
logged "auto_persisted" anyway. This test exercises the actual MCP→backend path
that failed — calling the backend directly would not detect this class of failure.

TOKEN HANDLING:
- Token is read from env var MINDSORT_CLAUDE_TEST_TOKEN
- Test is skipped if token is not provided
- Token is NEVER logged (security requirement)
- To obtain a token: use MCP Inspector to connect to the MCP server, copy the
  access_token from the successful auth flow. Do NOT extract from logs (tokens
  are correctly not logged).

See doc/OAuth/platform_quirk_mindsort_openai_401.md for the full incident record.
"""

import os
import json

import httpx
import pytest

# Mark all tests as live (excluded from default runs via addopts = -m "not live")
pytestmark = pytest.mark.live

# Production MCP server URL (the service that had the localhost BACKEND_URL bug)
MCP_SERVER_URL = "https://mindsort-mcp.priority-guard.com"

# Token env var name
TOKEN_ENV_VAR = "MINDSORT_CLAUDE_TEST_TOKEN"

# JSON-RPC request counter
_request_id = 0


def _next_request_id() -> int:
    global _request_id
    _request_id += 1
    return _request_id


@pytest.fixture
def access_token():
    """Get access token from environment, skip if not provided."""
    token = os.getenv(TOKEN_ENV_VAR)
    if not token:
        pytest.skip(f"{TOKEN_ENV_VAR} not set — skipping live persist roundtrip test")
    return token


@pytest.fixture
def http_client():
    """Provide an httpx client with reasonable timeout."""
    return httpx.Client(timeout=30.0)


def _mcp_call(client: httpx.Client, token: str, method: str, params: dict) -> dict:
    """Make a JSON-RPC call to the MCP server."""
    request = {
        "jsonrpc": "2.0",
        "method": method,
        "params": params,
        "id": _next_request_id(),
    }
    response = client.post(
        f"{MCP_SERVER_URL}/mcp",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json=request,
    )
    response.raise_for_status()
    return response.json()


class TestLivePersistRoundtrip:
    """
    Live verification of persist + retrieve roundtrip through MCP server.

    This test goes through /mcp → MCP server → backend, exercising the full
    path that failed in the 2026-07-05 incident.
    """

    def test_organize_and_load_roundtrip(self, http_client, access_token):
        """
        Exercise the full persist + retrieve path through the MCP server.

        Steps:
        1. Save existing board (if any) for restoration
        2. Call organize_thoughts with test data
        3. Verify no isError in response (persist succeeded)
        4. Call load_saved_board to verify data persisted
        5. Restore original board
        """
        # Step 1: Save existing board for restoration
        load_result = _mcp_call(
            http_client, access_token,
            "tools/call",
            {"name": "load_saved_board", "arguments": {}},
        )

        original_board = None
        if "result" in load_result:
            result = load_result["result"]
            # Check if board exists (not persistence_error, not no_board)
            if not result.get("isError"):
                sc = result.get("structuredContent", {})
                if sc.get("success") and sc.get("clusters"):
                    original_board = sc["clusters"]

        # Step 2: Call organize_thoughts with test data
        test_clusters = [
            {
                "cluster_name": "Live Roundtrip Test",
                "thought_items": [
                    {"text": "Test item 1 (live roundtrip)", "tag": "work"},
                    {"text": "Test item 2 (live roundtrip)", "tag": "personal"},
                ],
            }
        ]

        organize_result = _mcp_call(
            http_client, access_token,
            "tools/call",
            {
                "name": "organize_thoughts",
                "arguments": {
                    "clusters": test_clusters,
                    "thoughts_exhausted": False,
                },
            },
        )

        # Step 3: Verify no isError (persist succeeded)
        assert "result" in organize_result, (
            f"MCP call failed: {organize_result}. "
            f"If error contains 'connection' or 'timeout', CLARITY_BACKEND_URL "
            f"may still be localhost in the MCP server."
        )

        result = organize_result["result"]
        assert not result.get("isError"), (
            f"organize_thoughts returned isError=True: {result}. "
            f"structuredContent: {result.get('structuredContent', {})}. "
            f"If error='persist_failed', this test caught a real persistence failure."
        )

        # Step 4: Call load_saved_board to verify data persisted
        load_result = _mcp_call(
            http_client, access_token,
            "tools/call",
            {"name": "load_saved_board", "arguments": {}},
        )

        assert "result" in load_result, f"load_saved_board call failed: {load_result}"
        result = load_result["result"]
        assert not result.get("isError"), (
            f"load_saved_board returned isError=True: {result}. "
            f"If error='persistence_error', the backend is unreachable."
        )

        sc = result.get("structuredContent", {})
        assert sc.get("success"), f"load_saved_board success=false: {sc}"
        assert sc.get("clusters"), f"load_saved_board returned no clusters: {sc}"

        # Verify test data is present
        loaded_clusters = sc["clusters"]
        assert any(
            c.get("name") == "Live Roundtrip Test" or c.get("cluster_name") == "Live Roundtrip Test"
            for c in loaded_clusters
        ), f"Test cluster not found in loaded data: {loaded_clusters}"

        # Step 5: Restore original board (best effort)
        if original_board is not None:
            try:
                _mcp_call(
                    http_client, access_token,
                    "tools/call",
                    {
                        "name": "organize_thoughts",
                        "arguments": {
                            "clusters": original_board,
                            "thoughts_exhausted": False,
                        },
                    },
                )
            except Exception:
                # Don't fail the test if restoration fails
                pass
