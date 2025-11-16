#!/usr/bin/env python3
"""
Test client for MCP check_calendar tool.

Properly handles MCP session management and streamable HTTP protocol.
"""

import asyncio
import httpx
import json

MCP_URL = "http://localhost:8001/mcp"


async def test_check_calendar():
    """Test the check_calendar MCP tool."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Step 1: Initialize session
        print("=== Step 1: Initialize MCP Session ===")
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
        print(f"Session ID: {session_id}")
        print(f"Status: {init_response.status_code}")
        print(f"Response: {init_response.text[:200]}...")
        print()

        # Step 1.5: Send initialized notification
        print("=== Step 1.5: Send Initialized Notification ===")
        initialized_response = await client.post(
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
        print(f"Status: {initialized_response.status_code}")
        print()

        # Step 2: List available tools
        print("=== Step 2: List Available Tools ===")
        list_response = await client.post(
            MCP_URL,
            json={
                "jsonrpc": "2.0",
                "method": "tools/list",
                "params": {},
                "id": 2
            },
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
                "mcp-session-id": session_id
            }
        )

        print(f"Status: {list_response.status_code}")
        print(f"Response: {list_response.text}")
        print()

        # Step 3: Call check_calendar tool
        print("=== Step 3: Call check_calendar Tool ===")
        call_response = await client.post(
            MCP_URL,
            json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": "check_calendar",
                    "arguments": {
                        "focus_keywords": ["Deep Work", "Focus Time", "Focus"],
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

        print(f"Status: {call_response.status_code}")
        print(f"Response:")

        # Parse the SSE response
        for line in call_response.text.split('\n'):
            if line.startswith('data: '):
                data = json.loads(line[6:])
                print(json.dumps(data, indent=2))

        print("\n=== Test Complete ===")


if __name__ == "__main__":
    asyncio.run(test_check_calendar())
