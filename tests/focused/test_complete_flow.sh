#!/bin/bash

echo "============================================"
echo "Complete Testing Flow for Updated System"
echo "============================================"
echo

# Step 1: Get OAuth URL
echo "STEP 1: Getting Google OAuth URL..."
echo "Visit this URL in your browser to authenticate:"
echo
curl -s "http://localhost:8000/auth/focused/google/start?user_id=test_user" | jq -r '.data.auth_url'
echo
echo "After you authenticate, Google will redirect to localhost:3000/callback"
echo "Copy the full callback URL and we'll test again."
echo
echo "============================================"
echo

# Wait for user
read -p "Press Enter after you've completed authentication..."

# Step 2: Test Backend API
echo
echo "STEP 2: Testing Backend API..."
echo "Request: POST /api/focused/check_calendar"
curl -s -X POST http://localhost:8000/api/focused/check_calendar \
  -H "Content-Type: application/json" \
  -d '{"max_results": 5}' | jq .
echo
echo "============================================"
echo

# Step 3: Create MCP test
echo "STEP 3: Testing would require MCP Inspector"
echo "You can open MCP Inspector at: http://localhost:8001/mcp"
echo "Or run: npx @modelcontextprotocol/inspector http://localhost:8001/mcp"
echo
