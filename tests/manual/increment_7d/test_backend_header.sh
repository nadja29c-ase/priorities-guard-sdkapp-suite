#!/bin/bash
# Increment 7D Backend Tests - X-User-ID header extraction

echo "=== Increment 7D: Backend Header Extraction Tests ==="
echo ""

# Test 1: Backend receives X-User-ID header (primary path)
echo "Test 1: Call backend WITH X-User-ID header"
echo "Expected: Request succeeds, no fallback warning"
echo ""
curl -s -X POST http://localhost:8000/api/focused/tools/check_calendar \
  -H "Content-Type: application/json" \
  -H "X-User-ID: 00000000-0000-0000-0000-000000000001" \
  -H "X-Correlation-ID: test-header-extraction-001" \
  -d '{"time_start":null,"time_end":null,"max_results":10}' | python3 -m json.tool
echo ""
echo "✅ PASS if:"
echo "  - Response is success=true"
echo "  - Backend logs show: correlation_id=test-header-extraction-001"
echo "  - Backend logs DO NOT show: check_calendar.user_id_fallback"
echo ""
echo "---"
echo ""

# Test 2: Backend falls back when header missing (backward compatibility)
echo "Test 2: Call backend WITHOUT X-User-ID header"
echo "Expected: Request succeeds with fallback warning"
echo ""
curl -s -X POST http://localhost:8000/api/focused/tools/check_calendar \
  -H "Content-Type: application/json" \
  -H "X-Correlation-ID: test-fallback-002" \
  -d '{"time_start":null,"time_end":null,"max_results":10}' | python3 -m json.tool
echo ""
echo "⚠️ PASS if:"
echo "  - Response is success=true (backward compatible)"
echo "  - Backend logs show: WARNING check_calendar.user_id_fallback"
echo "  - Backend logs show: source=hardcoded"
echo ""
echo "---"
echo ""

# Test 3: Correlation ID propagation
echo "Test 3: Correlation ID propagates through request"
echo "Expected: Custom correlation ID appears in logs"
echo ""
curl -s -X POST http://localhost:8000/api/focused/tools/check_calendar \
  -H "Content-Type: application/json" \
  -H "X-User-ID: 00000000-0000-0000-0000-000000000001" \
  -H "X-Correlation-ID: manual-test-correlation-12345" \
  -d '{"time_start":null,"time_end":null,"max_results":10}' | python3 -m json.tool
echo ""
echo "✅ PASS if:"
echo "  - Backend logs show: correlation_id=manual-test-correlation-12345"
echo ""

echo "=== All Tests Complete ==="
echo ""
echo "Summary:"
echo "  Test 1: X-User-ID header extraction (primary path)"
echo "  Test 2: Fallback to hardcoded user (backward compatibility)"
echo "  Test 3: Correlation ID propagation"
echo ""
echo "Check your uvicorn terminal for log verification!"
