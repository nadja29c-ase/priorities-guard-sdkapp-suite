"""
Part C — boot guard on MindSort-Claude's audience config.

CLARITY_CLAUDE_AUDIENCE participates directly in cross-app token isolation, yet it was
the only consequential setting in this module that fell back to a silent default while
five less consequential ones failed fast. The asymmetry was the defect.

These tests exercise `_validate_audience_config` directly rather than reloading the
module. Reload would re-run every module-level guard and, worse, this package contains a
shim that rebinds module globals at import time (REBOUND_GLOBALS in mcp_auth_dupl) —
importing it contaminates later tests. A pure function sidesteps both.

Every test states the bug that would still pass it.
"""

import pytest

from mcp_server.mindsort_claude.config import (
    _validate_audience_config,
    _PRODUCTION_ENV_VALUES,
    _DEV_ENV_VALUES,
)


RESOURCE = "https://mindsort-mcp.priority-guard.com/mcp"


def _validate(env, audience, resource=RESOURCE, explicitly_set=True):
    return _validate_audience_config(
        env=env,
        audience_explicitly_set=explicitly_set,
        audience=audience,
        resource_url=resource,
    )


# ============================================================================
# Must raise in production-like ENV
# ============================================================================

@pytest.mark.parametrize("env", sorted(_PRODUCTION_ENV_VALUES))
def test_raises_when_audience_unset_in_every_production_env(env):
    """
    Bug this catches: the guard checking only ENV == "production" and missing "prod" or
    "staging". A staging deployment would then boot with an issuer-shaped audience and
    silently accept tokens minted for another app in the suite.

    Also catches the subtler failure: checking `audience is None` instead of whether the
    variable was SET. The module-level value holds a default, so a None check can never
    fire — the guard would be permanently dead code.
    """
    with pytest.raises(RuntimeError) as exc:
        _validate(env, audience="https://www.priority-guard.com", explicitly_set=False)

    assert "CLARITY_CLAUDE_AUDIENCE" in str(exc.value)
    assert RESOURCE in str(exc.value)


def test_raises_on_trailing_slash_difference():
    """
    Bug this catches: normalization creeping into the guard. This test is the entire
    point of the byte-exact rule — PyJWT 2.10.1 compares `aud` by exact string equality
    (empirically verified: a trailing-slash variant is rejected with
    InvalidAudienceError). A guard that tolerated the slash would pass a config that
    then fails at runtime on every single tool call, while manufacturing confidence
    that the config had been checked.
    """
    with pytest.raises(RuntimeError) as exc:
        _validate("production", audience=RESOURCE + "/")

    assert "byte-exact" in str(exc.value)


def test_raises_on_case_difference():
    """
    Bug this catches: `.lower()` or `casefold()` sneaking into the comparison. PyJWT
    rejects a case variant, so tolerating it here reproduces the trailing-slash failure
    mode in a form that is harder to spot by eye.
    """
    with pytest.raises(RuntimeError):
        _validate("production", audience=RESOURCE.replace("mindsort", "MindSort"))


def test_raises_when_audience_is_the_issuer():
    """
    Bug this catches: THE ORIGINAL DEFECT. The code default is issuer-shaped
    ("https://www.priority-guard.com"). If someone sets the env var to that value —
    or the guard is written to accept the default — MindSort-Claude accepts
    issuer-audience tokens, which is precisely the §11 defect PG-Claude already has.
    """
    with pytest.raises(RuntimeError):
        _validate("production", audience="https://www.priority-guard.com")


def test_raises_when_audience_is_the_bare_origin():
    """
    Bug this catches: accepting MCP_SERVER_URL (origin, no /mcp path) as if it were the
    resource. The origin is a bare-origin alias already present in the accepted-audience
    list (backlog 10); letting the guard bless it too would entrench the alias rather
    than tighten it.
    """
    with pytest.raises(RuntimeError):
        _validate("production", audience="https://mindsort-mcp.priority-guard.com")


def test_raises_on_another_apps_resource_url_on_the_same_origin():
    """
    Bug this catches: SAME-ORIGIN comparison instead of byte-exact — explicitly rejected
    in the design. Origin equality would let https://host/pg satisfy a guard whose
    expected value is https://host/mindsort, which is the exact cross-app confusion the
    guard exists to prevent. Origin checks stop protecting the moment two apps share a
    host with path-based resource identifiers, which is this suite's topology.
    """
    with pytest.raises(RuntimeError):
        _validate(
            "production",
            audience="https://mindsort-mcp.priority-guard.com/pg",
            resource="https://mindsort-mcp.priority-guard.com/mindsort",
        )


# ============================================================================
# Must NOT raise
# ============================================================================

@pytest.mark.parametrize("env", sorted(_PRODUCTION_ENV_VALUES))
def test_does_not_raise_on_byte_exact_match_in_any_production_env(env):
    """
    Bug this catches: an over-strict guard that fails a CORRECT production config — which
    would hard-fail boot on every deploy. Part C is designed to refuse to start, so a
    false positive here is an outage, not an inconvenience.
    """
    _validate(env, audience=RESOURCE)


@pytest.mark.parametrize("env", sorted(_DEV_ENV_VALUES))
def test_does_not_raise_in_dev_or_test_env(env):
    """
    Bug this catches: the guard firing outside production. Local development uses shared
    backend discovery, which may legitimately not match a per-app resource URL — the
    issuer-shaped default exists for exactly that reason. A guard that fired in dev would
    make the module unimportable locally and in CI.
    """
    _validate(env, audience="https://www.priority-guard.com", explicitly_set=False)


def test_dev_env_values_and_production_env_values_are_disjoint():
    """
    Bug this catches: an ENV value appearing in both sets, which would make the guard's
    behaviour depend on set-iteration order. Guards against a careless edit to either
    constant rather than against current code.
    """
    assert _PRODUCTION_ENV_VALUES.isdisjoint(_DEV_ENV_VALUES)


# ============================================================================
# Error message quality — §7.1 requires naming variable, expected and actual
# ============================================================================

def test_error_message_names_variable_expected_and_actual():
    """
    Bug this catches: a bare "config invalid" failure. This guard hard-fails boot, so the
    message is the only diagnostic an operator gets from a service that will not start.
    Omitting the actual value makes a trailing-slash or case mismatch nearly impossible
    to spot from logs.
    """
    wrong = "https://wrong.example.com/mcp"
    with pytest.raises(RuntimeError) as exc:
        _validate("production", audience=wrong)

    message = str(exc.value)
    assert "CLARITY_CLAUDE_AUDIENCE" in message
    assert "CLARITY_CLAUDE_MCP_RESOURCE_URL" in message
    assert repr(RESOURCE) in message, "expected value must be quoted in the message"
    assert repr(wrong) in message, "actual value must be quoted in the message"
