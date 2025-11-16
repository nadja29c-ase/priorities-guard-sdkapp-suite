#!/bin/bash
# List available MCP tools

set -e

MCP_URL="http://localhost:8001/mcp"

echo "=== Initialize MCP Session ==="
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

SESSION_ID=$(echo "$INIT_RESPONSE" | grep -i "mcp-session-id:" | cut -d' ' -f2 | tr -d '\r')
echo "Session ID: $SESSION_ID"
echo ""

echo "=== List Available Tools ==="
curl -X POST "$MCP_URL" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "mcp-session-id: $SESSION_ID" \
  -d '{
    "jsonrpc":"2.0",
    "method":"tools/list",
    "params":{},
    "id":2
  }'

echo ""
