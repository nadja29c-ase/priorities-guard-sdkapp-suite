#!/bin/bash

echo "=== Test 4: Structured Log Format Validation ==="
echo ""

echo "Step 4.1 - Make a request to generate logs:"
curl -s http://localhost:8000/api/focused/health > /dev/null
echo "✅ Request sent"
echo ""

echo "Now check Terminal 2 (uvicorn) for JSON logs with:"
echo "  - timestamp (ISO 8601 format)"
echo "  - level (info, warning, error, etc.)"
echo "  - correlation_id (UUID)"
echo "  - event (dot-notation like 'oauth.token.success')"
echo ""

echo "Step 4.2 - Copy a log line from Terminal 2 and validate JSON:"
echo "Example command:"
echo '  echo '"'"'{"timestamp":"2025-11-24T...", "level":"info", ...}'"'"' | python3 -m json.tool'
echo ""
echo "✅ Pass if: No JSON parsing errors"
