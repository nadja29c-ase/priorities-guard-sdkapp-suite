#!/bin/bash

echo "=== Test 3: Security Headers on All Endpoints ==="
echo ""

echo "Step 3.1 - Test root endpoint:"
echo "Expected: All 6 security headers present"
echo ""
curl -sI http://localhost:8000/ | grep -iE "X-Content-Type-Options|X-Frame-Options|X-XSS-Protection|Strict-Transport-Security|Cache-Control|Pragma"
echo ""

echo "Step 3.2 - Test health endpoint:"
echo "Expected: Same security headers"
echo ""
curl -sI http://localhost:8000/api/focused/health | grep -iE "X-Content-Type-Options|X-Frame-Options|X-XSS-Protection|Strict-Transport-Security|Cache-Control|Pragma"
echo ""

echo "✅ Pass if all 6 headers present on both endpoints:"
echo "   - X-Content-Type-Options: nosniff"
echo "   - X-Frame-Options: DENY"
echo "   - X-XSS-Protection: 1; mode=block"
echo "   - Strict-Transport-Security: max-age=31536000; includeSubDomains"
echo "   - Cache-Control: no-store"
echo "   - Pragma: no-cache"
