#!/usr/bin/env python3
"""
Test error scenarios for MCP check_calendar tool.
"""

import asyncio
import httpx
import json

MCP_URL = "http://localhost:8001/mcp"


async def init_session(client):
    """Initialize MCP session and return session_id."""
    init_response = await client.post(
        MCP_URL,
        json={
            "jsonrpc": "2.0",
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test-client", "version": "1.0"}
            },
            "id": 1
        },
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream"
        }
    )

    session_id = init_response.headers.get("mcp-session-id")

    # Send initialized notification
    await client.post(
        MCP_URL,
        json={
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {}
        },
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "mcp-session-id": session_id
        }
    )

    return session_id


async def call_check_calendar(client, session_id, arguments):
    """Call check_calendar tool with given arguments."""
    response = await client.post(
        MCP_URL,
        json={
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "check_calendar",
                "arguments": arguments
            },
            "id": 3
        },
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "mcp-session-id": session_id
        }
    )

    # Parse SSE response
    for line in response.text.split('\n'):
        if line.startswith('data: '):
            return json.loads(line[6:])


async def test_error_scenarios():
    """Test various error scenarios."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        session_id = await init_session(client)

        # Test 1: Empty focus_keywords
        print("=== Test 1: Empty focus_keywords ===")
        result = await call_check_calendar(client, session_id, {
            "focus_keywords": [],
            "max_results": 10
        })
        print(json.dumps(result, indent=2))
        print()

        # Test 2: Invalid max_results (too low)
        print("=== Test 2: max_results < 1 ===")
        result = await call_check_calendar(client, session_id, {
            "focus_keywords": ["Deep Work"],
            "max_results": 0
        })
        print(json.dumps(result, indent=2))
        print()

        # Test 3: Invalid max_results (too high)
        print("=== Test 3: max_results > 50 ===")
        result = await call_check_calendar(client, session_id, {
            "focus_keywords": ["Deep Work"],
            "max_results": 100
        })
        print(json.dumps(result, indent=2))
        print()

        print("=== All Error Tests Complete ===")


if __name__ == "__main__":
    asyncio.run(test_error_scenarios())
