#!/bin/bash
# Test script for MCP check_calendar tool
# Maintains session across requests

set -e

MCP_URL="http://localhost:8001/mcp"

echo "=== Step 1: Initialize MCP Session ==="
INIT_RESPONSE=$(curl -s -i -X POST "$MCP_URL" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{
    "jsonrpc":"2.0",
    "method":"initialize",
    "params":{
      "protocolVersion":"2024-11-05",
      "capabilities":{},
      "clientInfo":{"name":"test","version":"1.0"}
    },
    "id":1
  }')

# Extract session ID from headers
SESSION_ID=$(echo "$INIT_RESPONSE" | grep -i "mcp-session-id:" | cut -d' ' -f2 | tr -d '\r')

echo "Session ID: $SESSION_ID"
echo ""

echo "=== Step 2: Call check_calendar tool ==="
curl -X POST "$MCP_URL" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "mcp-session-id: $SESSION_ID" \
  -d '{
    "jsonrpc":"2.0",
    "method":"tools/call",
    "params":{
      "name":"check_calendar",
      "arguments":{
        "focus_keywords":["Deep Work","Focus Time","Focus"],
        "max_results":10
      }
    },
    "id":2
  }'

echo ""
echo ""
echo "=== Test Complete ==="
