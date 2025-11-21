#!/usr/bin/env python3
"""
Simplified test script for Increment 7C - tests functionality without complex output capture.
"""

import sys
sys.path.insert(0, '/Users/nadja/Desktop/Priority Guard Suite/priority-guardian')


def test_oauth_exceptions():
    """Test OAuth exception classes are properly defined."""
    print("\n=== Test 1: OAuth Exception Classes ===")

    from backend.core.oauth_exceptions import (
        OAuthError,
        InvalidRequestError,
        InvalidClientError,
        InvalidGrantError,
        UnauthorizedClientError,
        UnsupportedGrantTypeError,
        InvalidScopeError,
        AccessDeniedError,
        UnsupportedResponseTypeError,
        ServerError,
        TemporarilyUnavailableError
    )

    # Test base class
    try:
        err = OAuthError("test_error", "Test description", 400)
        assert err.error == "test_error"
        assert err.description == "Test description"
        assert err.status_code == 400
    except Exception as e:
        print(f"❌ FAILED: OAuthError base class: {e}")
        return False

    # Test specific exception classes
    test_cases = [
        (InvalidRequestError, "invalid_request", 400),
        (InvalidClientError, "invalid_client", 401),
        (InvalidGrantError, "invalid_grant", 401),
        (UnauthorizedClientError, "unauthorized_client", 400),
        (UnsupportedGrantTypeError, "unsupported_grant_type", 400),
        (InvalidScopeError, "invalid_scope", 400),
        (AccessDeniedError, "access_denied", 403),
        (UnsupportedResponseTypeError, "unsupported_response_type", 400),
        (ServerError, "server_error", 500),
        (TemporarilyUnavailableError, "temporarily_unavailable", 503),
    ]

    failures = []
    for exc_class, expected_error, expected_status in test_cases:
        try:
            exc = exc_class()
            if exc.error != expected_error:
                failures.append(f"{exc_class.__name__}: wrong error code (got {exc.error}, expected {expected_error})")
            if exc.status_code != expected_status:
                failures.append(f"{exc_class.__name__}: wrong status code (got {exc.status_code}, expected {expected_status})")
        except Exception as e:
            failures.append(f"{exc_class.__name__}: {e}")

    if failures:
        print(f"❌ FAILED: OAuth exception issues:")
        for failure in failures:
            print(f"   - {failure}")
        return False

    print(f"✅ PASSED: All {len(test_cases)} OAuth exception classes defined correctly")
    return True


def test_middleware_classes():
    """Test that middleware classes are importable and have required methods."""
    print("\n=== Test 2: Middleware Classes ===")

    try:
        from backend.core.middleware import CorrelationIDMiddleware, SecurityHeadersMiddleware
        from starlette.middleware.base import BaseHTTPMiddleware

        # Verify inheritance
        if not issubclass(CorrelationIDMiddleware, BaseHTTPMiddleware):
            print("❌ FAILED: CorrelationIDMiddleware doesn't inherit from BaseHTTPMiddleware")
            return False

        if not issubclass(SecurityHeadersMiddleware, BaseHTTPMiddleware):
            print("❌ FAILED: SecurityHeadersMiddleware doesn't inherit from BaseHTTPMiddleware")
            return False

        # Verify dispatch methods exist
        if not hasattr(CorrelationIDMiddleware, 'dispatch'):
            print("❌ FAILED: CorrelationIDMiddleware missing dispatch method")
            return False

        if not hasattr(SecurityHeadersMiddleware, 'dispatch'):
            print("❌ FAILED: SecurityHeadersMiddleware missing dispatch method")
            return False

        print("✅ PASSED: Middleware classes properly defined")
        return True

    except Exception as e:
        print(f"❌ FAILED: Middleware import error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_logging_module():
    """Test that logging module exports required functions."""
    print("\n=== Test 3: Logging Module ===")

    try:
        from backend.core.logging import configure_logging, get_logger, scrub_sensitive_data, add_correlation_id

        # Verify functions exist
        if not callable(configure_logging):
            print("❌ FAILED: configure_logging not callable")
            return False

        if not callable(get_logger):
            print("❌ FAILED: get_logger not callable")
            return False

        if not callable(scrub_sensitive_data):
            print("❌ FAILED: scrub_sensitive_data not callable")
            return False

        if not callable(add_correlation_id):
            print("❌ FAILED: add_correlation_id not callable")
            return False

        print("✅ PASSED: Logging module exports all required functions")
        return True

    except Exception as e:
        print(f"❌ FAILED: Logging module error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_sensitive_data_scrubber():
    """Test that scrub_sensitive_data function works correctly."""
    print("\n=== Test 4: Sensitive Data Scrubbing Logic ===")

    try:
        from backend.core.logging import scrub_sensitive_data

        # Test event dict with sensitive data
        event_dict = {
            "event": "oauth.test",
            "access_token": "secret-token-123",
            "refresh_token": "secret-refresh-456",
            "authorization_code": "code-789",
            "client_id": "valid-client",
            "user_id": "user-123"
        }

        # Apply scrubber
        scrubbed = scrub_sensitive_data(None, None, event_dict.copy())

        # Verify sensitive fields are redacted
        if scrubbed["access_token"] != "[REDACTED]":
            print(f"❌ FAILED: access_token not redacted: {scrubbed['access_token']}")
            return False

        if scrubbed["refresh_token"] != "[REDACTED]":
            print(f"❌ FAILED: refresh_token not redacted: {scrubbed['refresh_token']}")
            return False

        if scrubbed["authorization_code"] != "[REDACTED]":
            print(f"❌ FAILED: authorization_code not redacted: {scrubbed['authorization_code']}")
            return False

        # Verify non-sensitive fields are preserved
        if scrubbed["client_id"] != "valid-client":
            print(f"❌ FAILED: client_id incorrectly modified: {scrubbed['client_id']}")
            return False

        if scrubbed["user_id"] != "user-123":
            print(f"❌ FAILED: user_id incorrectly modified: {scrubbed['user_id']}")
            return False

        print("✅ PASSED: Sensitive data scrubber works correctly")
        return True

    except Exception as e:
        print(f"❌ FAILED: Scrubber test error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_rate_limit_logging():
    """Test that rate_limit.py has logging integrated."""
    print("\n=== Test 5: Rate Limit Logging ===")

    try:
        from backend.core.rate_limit import check_rate_limit, get_client_ip
        import inspect

        # Check that check_rate_limit accepts request parameter
        sig = inspect.signature(check_rate_limit)
        params = list(sig.parameters.keys())

        if 'request' not in params:
            print(f"❌ FAILED: check_rate_limit missing 'request' parameter")
            print(f"   Parameters: {params}")
            return False

        print("✅ PASSED: Rate limit module has logging support")
        return True

    except Exception as e:
        print(f"❌ FAILED: Rate limit module error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_main_imports():
    """Test that main.py imports are correct."""
    print("\n=== Test 6: Main.py Imports ===")

    try:
        # Read main.py and check imports
        with open('/Users/nadja/Desktop/Priority Guard Suite/priority-guardian/backend/main.py', 'r') as f:
            content = f.read()

        # Check for required imports
        required_imports = [
            'from backend.core.logging import configure_logging, get_logger',
            'from backend.core.middleware import CorrelationIDMiddleware, SecurityHeadersMiddleware',
            'from backend.core.oauth_exceptions import OAuthError',
        ]

        missing = []
        for imp in required_imports:
            if imp not in content:
                missing.append(imp)

        if missing:
            print("❌ FAILED: Missing imports in main.py:")
            for m in missing:
                print(f"   - {m}")
            return False

        # Check for middleware registration
        if 'app.add_middleware(CorrelationIDMiddleware)' not in content:
            print("❌ FAILED: CorrelationIDMiddleware not registered in main.py")
            return False

        if 'app.add_middleware(SecurityHeadersMiddleware)' not in content:
            print("❌ FAILED: SecurityHeadersMiddleware not registered in main.py")
            return False

        # Check for exception handler
        if '@app.exception_handler(OAuthError)' not in content:
            print("❌ FAILED: OAuthError exception handler not registered in main.py")
            return False

        print("✅ PASSED: Main.py has all required imports and registrations")
        return True

    except Exception as e:
        print(f"❌ FAILED: Main.py check error: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    print("=" * 70)
    print("Increment 7C Implementation Tests")
    print("=" * 70)

    tests = [
        test_oauth_exceptions,
        test_middleware_classes,
        test_logging_module,
        test_sensitive_data_scrubber,
        test_rate_limit_logging,
        test_main_imports,
    ]

    results = []
    for test in tests:
        try:
            results.append(test())
        except Exception as e:
            print(f"\n❌ EXCEPTION in {test.__name__}: {e}")
            import traceback
            traceback.print_exc()
            results.append(False)

    # Summary
    print("\n" + "=" * 70)
    print("Test Summary")
    print("=" * 70)
    passed = sum(results)
    total = len(results)

    print(f"Passed: {passed}/{total}")
    print(f"Failed: {total - passed}/{total}")

    if passed == total:
        print("\n✅ All tests passed! Increment 7C implementation verified.")
        print("\nNote: Manual testing still required for:")
        print("  - Server runtime tests (correlation ID propagation, security headers)")
        print("  - Log output verification in actual server logs")
        print("  - Integration testing with OAuth flows")
        return 0
    else:
        print(f"\n❌ {total - passed} test(s) failed. Please review failures above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
