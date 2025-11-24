#!/usr/bin/env python3
"""
Test USER_NOT_CONNECTED error scenario.

This requires temporarily modifying the user_id in mcp_server.py
"""

import asyncio
import httpx
import json

MCP_URL = "http://localhost:8001/mcp"


async def test_user_not_connected():
    """Test USER_NOT_CONNECTED error."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Initialize session
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

        # Call check_calendar (user_id will be "nonexistent_user" in mcp_server.py)
        print("=== Test: USER_NOT_CONNECTED ===")
        response = await client.post(
            MCP_URL,
            json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": "check_calendar",
                    "arguments": {
                        "focus_keywords": ["Deep Work"],
                        "max_results": 10
                    }
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
                result = json.loads(line[6:])
                print(json.dumps(result, indent=2))

        print("\n=== Test Complete ===")


if __name__ == "__main__":
    asyncio.run(test_user_not_connected())
