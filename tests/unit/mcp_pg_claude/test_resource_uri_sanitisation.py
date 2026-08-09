"""F1 — every client-controlled URI site in the Claude resources handler is sanitised.

WHY THIS EXISTS RATHER THAN A PRODUCTION PROBE. A22 was closed with a before/after
wire probe against production. That standard is NOT achievable for F1, and the
reason is worth stating: the sanitiser is a NO-OP on the only URI that normally
occurs (`ui://pg-claude/dashboard-v10.html` passes through unchanged), so a
production log line is byte-identical before and after the fix. Distinguishing
them would require a resources/read carrying a hostile URI, which requires a valid
bearer token. Observation of normal traffic proves nothing here.

WHAT THIS COVERS THAT THE EARLIER CHECK DID NOT. The port was verified two ways:
the function is byte-identical to its source (inspect.getsource), and it behaves
identically on nine inputs. Neither proves the CALL SITES route through it — that
was confirmed only by reading greps, which is exactly the method that missed a
site in the first place. These tests exercise handle_read_resource end to end.

Site 170 is the one that matters most and is the easiest to assert: it does not
log, it REFLECTS raw caller input into a response _meta that travels back into
Claude's context — a prompt-injection surface rather than a logging concern.
"""

import pytest
import structlog

from mcp_server.priority_guardian_claude.handlers import resources_dupl as R


class _Params:
    def __init__(self, uri):
        self.uri = uri


class _Req:
    def __init__(self, uri):
        self.params = _Params(uri)


# Hostile inputs a caller could actually send. Each pairs a raw URI with a
# substring that MUST NOT survive into any log or response.
HOSTILE = [
    ("mailto:victim@example.com?body=secret", "victim@example.com"),
    ("https://user:hunter2@evil.test/p?token=SECRET#f", "hunter2"),
    ("https://user:hunter2@evil.test/p?token=SECRET#f", "SECRET"),
    ("javascript:alert(1)", "alert(1)"),
    ("data:text/html;base64,PHNjcmlwdD4=", "PHNjcmlwdD4"),
    ("ui://x/y?token=LEAKED", "LEAKED"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("raw,secret", HOSTILE)
async def test_unknown_resource_error_does_not_reflect_raw_uri(raw, secret):
    """Site 170 — the REFLECTION site.

    An unknown resource returns _meta['error'] containing the URI. Raw caller
    input echoed back to the client is a wider exposure than a log line: this
    response travels into Claude's context.
    """
    result = await R.handle_read_resource(_Req(raw))
    error = result.meta["error"] if hasattr(result, "meta") else result._meta["error"]

    assert secret not in error, f"reflected response leaked {secret!r}: {error!r}"
    assert raw not in error, "reflected response contains the raw URI verbatim"


@pytest.mark.asyncio
@pytest.mark.parametrize("raw,secret", HOSTILE)
async def test_log_sites_do_not_emit_raw_uri(raw, secret):
    """Sites 133, 135 and 140 — the LOG sites.

    Captures structlog output rather than trusting that the call sites were
    edited. 140 is the multi-line logger.debug that a same-line grep missed.
    """
    structlog.configure(
        processors=[structlog.testing.LogCapture()],
        wrapper_class=structlog.BoundLogger,
        cache_logger_on_first_use=False,
    )
    cap = structlog.testing.LogCapture()
    structlog.configure(processors=[cap], cache_logger_on_first_use=False)

    try:
        await R.handle_read_resource(_Req(raw))
        emitted = repr(cap.entries)
        assert secret not in emitted, f"a log site leaked {secret!r}"
        assert raw not in emitted, "a log site emitted the raw URI verbatim"
        assert cap.entries, "no log entries captured — the assertion proves nothing"
    finally:
        structlog.reset_defaults()


@pytest.mark.asyncio
async def test_legitimate_widget_uri_is_unchanged():
    """The no-op case, and the reason a production probe cannot close F1.

    The real widget URI passes through the sanitiser unchanged — which is why
    today's production log lines look identical before and after the fix, and why
    this test file exists instead of a wire probe.

    NEGATIVE CONTROL, run 2026-08-09: with _sanitize_uri_for_logging replaced by
    the identity function, 13 of the 14 tests in this file fail — and the one that
    still passes is THIS ONE. That is not a weakness in the test; it is the
    limitation itself, made executable. The only URI production normally sees is
    the one the sanitiser does not change, so no amount of watching production can
    tell the fixed build from the broken one.
    """
    assert R._sanitize_uri_for_logging(R.WIDGET_URI) == R.WIDGET_URI

    result = await R.handle_read_resource(_Req(R.WIDGET_URI))
    contents = result.contents
    assert len(contents) == 1, "the happy path must still serve the widget"
    assert str(contents[0].uri) == R.WIDGET_URI


def test_sanitiser_matches_its_source_exactly():
    """Ported, not reimplemented — guards against future drift in either tree.

    This is the check that would have caught F1 itself, had it existed.
    """
    import inspect
    from mcp_server.priority_guardian.handlers import resources as SRC

    assert inspect.getsource(R._sanitize_uri_for_logging) == \
        inspect.getsource(SRC._sanitize_uri_for_logging), \
        "Claude copy has drifted from the OpenAI source"
    assert R._SAFE_SCHEMES == SRC._SAFE_SCHEMES
    assert R._MAX_URI_LOG_LENGTH == SRC._MAX_URI_LOG_LENGTH
