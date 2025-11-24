#!/bin/bash

echo "=== Test 2: Correlation ID Propagation ==="
echo ""

echo "Step 2.1 - Test WITH correlation ID header:"
echo "Expected: Response should include X-Correlation-ID: test-manual-123"
echo ""
curl -v -H "X-Correlation-ID: test-manual-123" http://localhost:8000/ 2>&1 | grep -i "x-correlation-id"
echo ""

echo "Step 2.2 - Test WITHOUT correlation ID header:"
echo "Expected: Response should include X-Correlation-ID with a generated UUID"
echo ""
curl -v http://localhost:8000/ 2>&1 | grep -i "x-correlation-id"
echo ""

echo "✅ Check Terminal 2 (uvicorn) for correlation_id in logs"
