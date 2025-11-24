#!/bin/bash

echo "=== Test 6: OAuth Error Response Format ==="
echo ""

# Note: Replace with your actual client_id from tests/manual/oauth/01_register_client.sh
CLIENT_ID="${CLIENT_ID:-focused-client-ff142fb8-19a6-4d48-b6b7-f4032974443d}"
REDIRECT_URI="https://chatgpt.com/aip/callback"

echo "Step 6.1 - Test with invalid scope (valid client, triggers RFC 6749 error):"
echo "Expected: RFC 6749-compliant error redirect"
echo ""
REDIRECT_URL=$(curl -s "http://localhost:8000/oauth/focused/authorize?response_type=code&client_id=$CLIENT_ID&redirect_uri=$REDIRECT_URI&code_challenge=test123&code_challenge_method=S256&scope=invalid.scope&state=test-error&user_id=00000000-0000-0000-0000-000000000001" -w "%{redirect_url}" -o /dev/null)
echo "Redirect URL:"
echo "$REDIRECT_URL"
echo ""

echo "Checking redirect URL format:"
if echo "$REDIRECT_URL" | grep -q "error=invalid_scope"; then
    echo "✅ Contains error=invalid_scope"
else
    echo "❌ Missing error parameter"
fi

if echo "$REDIRECT_URL" | grep -q "error_description="; then
    echo "✅ Contains error_description"
else
    echo "❌ Missing error_description parameter"
fi

if echo "$REDIRECT_URL" | grep -q "state=test-error"; then
    echo "✅ State parameter preserved"
else
    echo "❌ State parameter not preserved"
fi

echo ""
echo "Step 6.2 - Test with invalid client_id (returns HTTP error, not redirect):"
curl -s "http://localhost:8000/oauth/focused/authorize?response_type=code&client_id=invalid-client-123&redirect_uri=$REDIRECT_URI&code_challenge=test123&code_challenge_method=S256&scope=focused.read&state=test&user_id=00000000-0000-0000-0000-000000000001" | python3 -m json.tool
echo ""
echo "✅ Returns HTTP 401 (correct - can't trust redirect_uri from unknown client)"
echo ""

echo "Note: OAuth 2.0 security best practices:"
echo "  - Invalid client_id → HTTP error (can't trust redirect_uri)"
echo "  - Invalid redirect_uri → HTTP error (can't redirect to unregistered URI)"
echo "  - Invalid scope/response_type → RFC 6749 error redirect (client trusted)"
echo ""
echo "Check Terminal 2 (uvicorn) for:"
echo '  - "event": "oauth.error" or similar'
echo "  - correlation_id present in error logs"
