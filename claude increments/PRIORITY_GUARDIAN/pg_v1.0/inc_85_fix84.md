Here's the patch instruction for Claude Code:

Patch: Service field, scrubber gaps, logtail import safety
Four small changes to close real gaps. All in shared/logging.py plus tests + docs.

1. Add add_service_name processor
In shared/logging.py, add a new processor function after add_correlation_id:
pythondef add_service_name(logger: Any, method_name: str, event_dict: dict) -> dict:
    """
    Add service name to log events for filtering in Better Stack.

    Reads SERVICE_NAME env var. Used to distinguish backend logs from MCP
    server logs when both ship to the same Better Stack source. Falls back
    to "priority-guard-suite" if unset (e.g., local dev or scripts).

    Args:
        logger: Logger instance (unused, required by structlog)
        method_name: Method name (unused, required by structlog)
        event_dict: Log event dictionary

    Returns:
        Event dictionary with `service` field
    """
    if "service" not in event_dict:
        event_dict["service"] = os.getenv("SERVICE_NAME", "priority-guard-suite")
    return event_dict
The if "service" not in event_dict guard preserves any explicit service value already set by callers (e.g., RequestLoggingMiddleware's service_name kwarg in the MCP server).
In the structlog.configure() processor list, add add_service_name after add_correlation_id:
pythonprocessors=[
    structlog.stdlib.add_log_level,
    structlog.processors.TimeStamper(fmt="iso"),
    add_correlation_id,
    add_service_name,        # <-- NEW, after correlation_id
    scrub_sensitive_data,
    structlog.processors.StackInfoRenderer(),
    structlog.processors.format_exc_info,
    structlog.processors.JSONRenderer(),
],
Order matters: add_service_name must run before scrub_sensitive_data and JSONRenderer. Placing after add_correlation_id is consistent with where context-injection processors live.

2. Expand scrubber REDACT_KEYS
In shared/logging.py, add two entries to REDACT_KEYS:
pythonREDACT_KEYS = [
    # OAuth tokens
    "access_token",
    "refresh_token",
    "authorization_code",
    "authorization",
    "token",
    "id_token",                    # <-- NEW: defensive (not in current use, but free protection)

    # PKCE
    "code_verifier",
    "code_challenge",

    # Secrets
    "client_secret",
    "client_secret_enc",           # <-- NEW: actual DB column on CoreConnection
    "password",
    "secret",

    # Google tokens
    "encrypted_access_token",
    "encrypted_refresh_token",
]
Why these specifically:

client_secret_enc is a real database column on CoreConnection (verified in backend/core/models.py). If a CoreConnection row is ever logged as a dict — even for debugging — the encrypted client secret would leak to Better Stack.
id_token is not currently in the codebase, but is preventive: if OIDC is ever added, the scrubber catches it automatically.

Do NOT add access_token_enc or refresh_token_enc. These names do not exist in this codebase — the actual field names are encrypted_access_token and encrypted_refresh_token, both already in the list.

3. Move logtail import inside try/except
In the configure_logging() Better Stack block, the current code has the import outside the try:
pythonif token:
    from logtail import LogtailHandler   # <-- outside try (current)
    already_attached = any(...)
    if already_attached:
        ...
    else:
        try:
            logtail_handler = LogtailHandler(source_token=token)
            ...
Restructure so the import is also protected:
pythonif token:
    try:
        from logtail import LogtailHandler
        # Idempotency: skip if a LogtailHandler is already attached
        # Use type name check for robustness (works with mocks in tests)
        already_attached = any(
            type(h).__name__ == "LogtailHandler" for h in logging.root.handlers
        )
        if already_attached:
            logger.info("logging.betterstack.already_configured")
        else:
            logtail_handler = LogtailHandler(source_token=token)
            logging.root.addHandler(logtail_handler)
            logger.info("logging.betterstack.enabled")
    except Exception as e:
        # DO NOT raise — service must start even if Better Stack is unreachable
        # or the logtail package has an import-time issue.
        logger.warning(
            "logging.betterstack.init_failed",
            error=str(e),
            error_type=type(e).__name__,
        )
else:
    logger.info("logging.betterstack.disabled")
Why: logtail-python is in pyproject.toml, so an ImportError is unlikely in production — but the briefing's safety contract was "any LogtailHandler initialization failure MUST NOT prevent service startup." Import-time failure counts. This change costs nothing and tightens the contract.
The idempotency check is moved inside the try block too — that's intentional, harmless, and keeps the structure flat.

4. Add tests for the new behavior
In tests/unit/shared/test_logging_with_logtail.py, add a new test class and one new test for the scrubber:
Add to TestScrubberIntegration:
pythondef test_scrubber_redacts_client_secret_enc(self, captured_records):
    """client_secret_enc (DB column on CoreConnection) must be redacted."""
    HandlerClass = make_capturing_handler_class("TestLogtailHandler_secret_enc")

    with patch.dict(os.environ, {"BETTER_STACK_SOURCE_TOKEN": "test-token", "ENV": "dev"}):
        with patch.dict("sys.modules", {"logtail": MagicMock()}):
            sys.modules["logtail"].LogtailHandler = HandlerClass

            import shared.logging as shared_logging
            reload(shared_logging)

            shared_logging.configure_logging()

            logger = structlog.get_logger("test")
            logger.info(
                "oauth.client_loaded",
                client_secret_enc="encrypted-secret-payload",
                id_token="should-also-be-redacted",
            )

    matching = [r for r in captured_records if "oauth.client_loaded" in str(r.msg)]
    assert len(matching) >= 1

    payload = json.loads(matching[0].msg)
    assert payload.get("client_secret_enc") == "[REDACTED]"
    assert payload.get("id_token") == "[REDACTED]"
    assert "encrypted-secret-payload" not in matching[0].msg
    assert "should-also-be-redacted" not in matching[0].msg
Add a new test class for service field:
pythonclass TestServiceField:
    """Tests for service field injection (filtering across single Better Stack source)."""

    def test_service_field_uses_env_var_when_set(self, captured_records):
        """SERVICE_NAME env var should appear as 'service' field in payload."""
        HandlerClass = make_capturing_handler_class("TestLogtailHandler_service_env")

        with patch.dict(
            os.environ,
            {
                "BETTER_STACK_SOURCE_TOKEN": "test-token",
                "ENV": "dev",
                "SERVICE_NAME": "priority-guardian-backend",
            },
        ):
            with patch.dict("sys.modules", {"logtail": MagicMock()}):
                sys.modules["logtail"].LogtailHandler = HandlerClass

                import shared.logging as shared_logging
                reload(shared_logging)

                shared_logging.configure_logging()

                logger = structlog.get_logger("test")
                logger.info("test.service_field")

        matching = [r for r in captured_records if "test.service_field" in str(r.msg)]
        assert len(matching) >= 1

        payload = json.loads(matching[0].msg)
        assert payload.get("service") == "priority-guardian-backend"

    def test_service_field_default_when_env_unset(self, captured_records):
        """When SERVICE_NAME is unset, fall back to 'priority-guard-suite'."""
        HandlerClass = make_capturing_handler_class("TestLogtailHandler_service_default")

        env = {"BETTER_STACK_SOURCE_TOKEN": "test-token", "ENV": "dev"}  # no SERVICE_NAME

        with patch.dict(os.environ, env, clear=True):
            with patch.dict("sys.modules", {"logtail": MagicMock()}):
                sys.modules["logtail"].LogtailHandler = HandlerClass

                import shared.logging as shared_logging
                reload(shared_logging)

                shared_logging.configure_logging()

                logger = structlog.get_logger("test")
                logger.info("test.service_default")

        matching = [r for r in captured_records if "test.service_default" in str(r.msg)]
        assert len(matching) >= 1

        payload = json.loads(matching[0].msg)
        assert payload.get("service") == "priority-guard-suite"

    def test_explicit_service_kwarg_not_overwritten(self, captured_records):
        """If caller passes service= kwarg explicitly, processor must not overwrite it."""
        HandlerClass = make_capturing_handler_class("TestLogtailHandler_service_explicit")

        with patch.dict(
            os.environ,
            {
                "BETTER_STACK_SOURCE_TOKEN": "test-token",
                "ENV": "dev",
                "SERVICE_NAME": "priority-guardian-backend",
            },
        ):
            with patch.dict("sys.modules", {"logtail": MagicMock()}):
                sys.modules["logtail"].LogtailHandler = HandlerClass

                import shared.logging as shared_logging
                reload(shared_logging)

                shared_logging.configure_logging()

                logger = structlog.get_logger("test")
                # RequestLoggingMiddleware passes service=service_name as kwarg
                logger.info("http.request", service="priority-guardian-mcp")

        matching = [r for r in captured_records if "http.request" in str(r.msg)]
        assert len(matching) >= 1

        payload = json.loads(matching[0].msg)
        # Explicit kwarg wins over env var
        assert payload.get("service") == "priority-guardian-mcp"
The third test is important — RequestLoggingMiddleware already passes service=service_name as a kwarg, and the new processor must respect that.

5. Update .env.example
Add a SERVICE_NAME entry near the BETTER_STACK_SOURCE_TOKEN block:
# Service identifier injected into every structured log entry.
# Used to filter logs from different Render services within a single
# Better Stack source. Set per-service in Render env vars:
#   - Backend:        SERVICE_NAME=priority-guardian-backend
#   - PG OpenAI MCP:  SERVICE_NAME=priority-guardian-mcp
# If unset, falls back to "priority-guard-suite" (safe local dev default).
SERVICE_NAME=

6. Update OPERATIONS_PREDEPLOY.md
In the existing "Better Stack Log Shipping" section, update the env var table to include SERVICE_NAME:
VariableRequired OnValueBETTER_STACK_SOURCE_TOKENBackend, PG OpenAI MCPToken from Better Stack source settingsSERVICE_NAMEBackend, PG OpenAI MCPpriority-guardian-backend (backend) / priority-guardian-mcp (MCP)
Add a note under the table:

Why SERVICE_NAME matters: All suite logs flow into a single Better Stack source. The service field (injected automatically by shared/logging.py) is how you filter backend vs MCP logs in saved views. If SERVICE_NAME is unset on a service, its logs are tagged priority-guard-suite and become indistinguishable from other services — degrading the value of saved views and alerts.

In the "Deferred Services" subsection, add SERVICE_NAME to the reactivation checklist for PG Claude MCP:


Add BETTER_STACK_SOURCE_TOKEN to its Render env vars
Add SERVICE_NAME=priority-guardian-claude-mcp to its Render env vars (NEW)
Add configure_logging() call inside server_dupl.py's create_app()
Follow the "Resuming a suspended Render service" checklist



Out of scope — explicitly do not change

Do not make the scrubber case-insensitive. The current codebase logs lowercase keys consistently (Python convention for structlog kwargs). Case-insensitivity is defensive engineering for a problem that doesn't exist in this code; adds complexity without measurable benefit. If you ever start logging raw HTTP headers as dict keys (e.g., Authorization with capital A), revisit.
Do not add access_token_enc or refresh_token_enc to scrubber. These names do not exist in the codebase. The actual fields (encrypted_access_token, encrypted_refresh_token) are already in REDACT_KEYS.
Do not rename existing tests or test classes.
Do not change the order of processors except where this patch specifies.
Do not modify the MCP server (server.py) or backend/core/logging.py shim — both are correct as-is.


Pre-deploy verification
After applying:

Run cd /Users/nadja/Desktop/Priority\ Guard\ Suite/priority-guardian && pytest tests/unit/shared/ — all existing tests plus 4 new tests should pass.
Verify the processor order in shared/logging.py by reading the structlog.configure() block. Expected order: add_log_level → TimeStamper → add_correlation_id → add_service_name → scrub_sensitive_data → StackInfoRenderer → format_exc_info → JSONRenderer.
Confirm from logtail import LogtailHandler is INSIDE the try block in configure_logging().

Post-deploy verification (after Render env vars are set)
When you set env vars on Render, set BOTH BETTER_STACK_SOURCE_TOKEN and SERVICE_NAME on each service in the same deploy:

Backend service: SERVICE_NAME=priority-guardian-backend
PG OpenAI MCP service: SERVICE_NAME=priority-guardian-mcp

After restart, in Better Stack live tail, verify:

Backend's logging.betterstack.enabled event has service: "priority-guardian-backend"
MCP server's logging.betterstack.enabled event has service: "priority-guardian-mcp"
A saved view with filter service = "priority-guardian-backend" returns only backend logs (no MCP)
A saved view with filter service = "priority-guardian-mcp" returns only MCP logs (no backend)

If both services appear under both filters, the env var wasn't picked up — restart the service or check env var spelling.

That's the entire patch. Hand it over.