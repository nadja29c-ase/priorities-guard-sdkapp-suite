#!/usr/bin/env python3
"""Test MCP server validation error handling."""

import asyncio
import httpx


async def test_validation_error():
    """Test that MCP server returns unified error format for validation errors."""

    # MCP protocol: initialize, list tools, call tool
    async with httpx.AsyncClient(timeout=30.0) as client:
        base_url = "http://localhost:8001/mcp"

        # Initialize session
        init_resp = await client.post(base_url, json={
            "jsonrpc": "2.0",
            "method": "initialize",
            "params": {},
            "id": 1
        })
        print(f"Initialize: {init_resp.status_code}")

        # Test with max_results=0 (should trigger validation error)
        print("\n=== Testing max_results=0 (should fail) ===")
        call_resp = await client.post(base_url, json={
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "check_calendar",
                "arguments": {
                    "focus_keywords": ["Deep Work"],
                    "max_results": 0
                }
            },
            "id": 2
        })

        result = call_resp.json()
        print(f"Status: {call_resp.status_code}")
        print(f"Response: {result}")

        # Check if result contains unified error format
        if "result" in result:
            import json
            content = json.loads(result["result"]["content"][0]["text"])
            print(f"\nParsed content: {json.dumps(content, indent=2)}")

            if content.get("success") is False:
                error = content.get("error", {})
                print(f"\n✅ Unified error format confirmed!")
                print(f"   Code: {error.get('code')}")
                print(f"   Message: {error.get('message')}")
            else:
                print(f"\n❌ Expected error but got success")

        # Test with max_results=100 (should trigger validation error)
        print("\n=== Testing max_results=100 (should fail) ===")
        call_resp = await client.post(base_url, json={
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "check_calendar",
                "arguments": {
                    "focus_keywords": ["Deep Work"],
                    "max_results": 100
                }
            },
            "id": 3
        })

        result = call_resp.json()
        print(f"Status: {call_resp.status_code}")

        if "result" in result:
            import json
            content = json.loads(result["result"]["content"][0]["text"])
            print(f"Parsed content: {json.dumps(content, indent=2)}")

            if content.get("success") is False:
                error = content.get("error", {})
                print(f"\n✅ Unified error format confirmed!")
                print(f"   Code: {error.get('code')}")
                print(f"   Message: {error.get('message')}")
            else:
                print(f"\n❌ Expected error but got success")


if __name__ == "__main__":
    asyncio.run(test_validation_error())
