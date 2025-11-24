#!/bin/bash
# Test 1: Valid Token + Correct Scope

echo "=== Test 1: Valid Token + Correct Scope ==="
echo ""

# Generate fresh token
cd "/Users/nadja/Desktop/Priority Guard Suite/priority-guardian"
TOKEN=$(poetry run python tests/manual/increment_7d/generate_test_token.py)

echo "Token generated (first 50 chars): ${TOKEN:0:50}..."
echo ""

echo "Calling check_calendar with valid token..."
curl -s -X POST http://localhost:8001/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"check_calendar","arguments":{"max_results":10}},"id":1}' | python3 -m json.tool

echo ""
echo "✅ PASS if:"
echo "  - Response is 200 OK"
echo "  - No authentication errors"
echo "  - Check MCP logs for: auth.success"
echo "  - Check backend logs for: X-User-ID header received"
