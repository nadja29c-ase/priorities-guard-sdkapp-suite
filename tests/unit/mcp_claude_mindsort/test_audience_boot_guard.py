"""
Part C — boot guard on MindSort-Claude's audience config.

CLARITY_CLAUDE_AUDIENCE participates directly in cross-app token isolation, yet it was
the only consequential setting in this module that fell back to a silent default while
five less consequential ones failed fast. The asymmetry was the defect.

These tests exercise `_validate_audience_config` directly rather than reloading the
module. Reload would re-run every module-level guard and, worse, this package contains a
shim that rebinds module globals at import time (REBOUND_GLOBALS in mcp_auth_dupl) —
importing it contaminates later tests. A pure function sidesteps both.

BUT A PURE FUNCTION IS NOT THE THING THAT PROTECTS PRODUCTION. The module-level CALL at
the bottom of the guard section is. Testing only the function leaves that wiring
unverified: a mutation such as `if not _is_production_env(env) or env == ENV: return`
disables the guard on import in production while every direct-call test below still
passes. The subprocess boot tests at the end of this file close that gap — they import
the module under a production environment in a child process, which is the only way to
observe import-time behaviour without contaminating this one.

Every test states the bug that would still pass it.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from mcp_server.mindsort_claude.config import (
    _validate_audience_config,
    _PRODUCTION_ENV_VALUES,
    _DEV_ENV_VALUES,
)


RESOURCE = "https://mindsort-mcp.priority-guard.com/mcp"

_REPO_ROOT = Path(__file__).resolve().parents[3]

# A complete, valid production environment. Every subprocess case below starts from this
# and overrides exactly one thing, so a failure is attributable to that one change and
# not to an unrelated guard firing first. Deliberately NOT inherited from os.environ: a
# developer with CLARITY_CLAUDE_* exported would otherwise silently change what is tested.
_PROD_ENV = {
    "PATH": os.environ.get("PATH", ""),
    "ENV": "production",
    "CLARITY_CLAUDE_MCP_SERVER_URL": "https://mindsort-mcp.priority-guard.com",
    "CLARITY_CLAUDE_MCP_RESOURCE_URL": RESOURCE,
    "CLARITY_CLAUDE_AUDIENCE": RESOURCE,
    "CLARITY_CLAUDE_JWKS_URL": "https://www.priority-guard.com/oauth/pg/jwks",
    "CLARITY_CLAUDE_ISSUER": "https://www.priority-guard.com",
    "CLARITY_CLAUDE_BACKEND_URL": "https://www.priority-guard.com",
    "CLARITY_CLAUDE_OAUTH_ISSUER_URL": "https://www.priority-guard.com/oauth/pg",
    "CLARITY_CLAUDE_OAUTH_ISSUER_BASE": "https://www.priority-guard.com",
    "CLARITY_CLAUDE_CORS_ALLOWED_ORIGINS": "https://claude.ai",
    "CLARITY_CLAUDE_INTERNAL_API_SECRET": "test-secret",
}


def _import_config(**overrides):
    """Import the config module in a child process. Returns (returncode, stderr)."""
    env = {**_PROD_ENV, **overrides}
    # A None override means "unset this variable entirely" — distinct from setting "".
    env = {k: v for k, v in env.items() if v is not None}
    proc = subprocess.run(
        [sys.executable, "-c", "import mcp_server.mindsort_claude.config"],
        cwd=str(_REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
    )
    return proc.returncode, proc.stderr


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


def test_production_env_values_has_exactly_the_mandated_members():
    """
    Bug this catches: shrinking _PRODUCTION_ENV_VALUES. Every other test in this file
    parametrizes OVER that constant, so dropping "staging" from it would not fail any of
    them — the staging case would simply stop being generated and the suite would stay
    green while staging silently lost the guard.

    This assertion pins the requirement (§13: cover prod and staging) instead of tracking
    the implementation. It is the only test here that would fail on such an edit.
    """
    assert _PRODUCTION_ENV_VALUES == {"production", "prod", "staging"}


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


# ============================================================================
# Boot wiring — the guards must actually RUN at module import, not merely exist
#
# Everything above calls the validator directly. That verifies the function and nothing
# else. These tests import the module in a child process under a production environment,
# which is what Render does, and is the only assertion here that a mutation to the
# module-level call site would break.
# ============================================================================

def test_module_import_succeeds_under_a_valid_production_environment():
    """
    Bug this catches: an over-strict guard that refuses a CORRECT production config.
    This is the control for every other subprocess test — without it, a module that
    failed to import for ANY reason (a typo, a missing dependency) would make the
    negative cases below pass vacuously while proving nothing.
    """
    returncode, stderr = _import_config()

    assert returncode == 0, f"Valid production config must import cleanly. stderr:\n{stderr}"


@pytest.mark.parametrize("env", sorted(_PRODUCTION_ENV_VALUES))
def test_module_import_fails_on_audience_mismatch_in_every_production_env(env):
    """
    Bug this catches: THE MODULE-LEVEL CALL BEING REMOVED OR NEUTERED. The pure-function
    tests above cannot see this. Codex's mutation — `if not _is_production_env(env) or
    env == ENV: return` — passes all of them while disabling the guard on import in
    production, because in the test process ENV is "test" and the injected env is
    "production", so the two never match and the function still raises when called
    directly. Here they DO match, because the child process actually runs as production.
    """
    returncode, stderr = _import_config(
        ENV=env,
        CLARITY_CLAUDE_AUDIENCE="https://www.priority-guard.com",  # issuer, not resource
    )

    assert returncode != 0, "Import must fail when audience != resource in production"
    assert "CLARITY_CLAUDE_AUDIENCE" in stderr, (
        f"Failure must come from the audience guard, not an unrelated error:\n{stderr}"
    )


def test_module_import_fails_when_audience_unset_in_production():
    """
    Bug this catches: the explicitly-set check being dropped from the module-level call
    site — e.g. passing a literal True for audience_explicitly_set. The module default is
    issuer-shaped, so an unset variable must be rejected on its own terms rather than
    merely failing the equality check by luck.
    """
    returncode, stderr = _import_config(CLARITY_CLAUDE_AUDIENCE=None)  # None = unset

    assert returncode != 0, "Import must fail when CLARITY_CLAUDE_AUDIENCE is unset in production"
    assert "not set" in stderr, (
        f"Failure must name the unset variable specifically:\n{stderr}"
    )


@pytest.mark.parametrize("agreed_value", ["", "/mcp"])
def test_module_import_fails_when_resource_and_audience_agree_on_an_invalid_value(agreed_value):
    """
    Bug this catches: the audience guard being trusted to do a job it cannot do. It only
    asserts the two values are EQUAL, so setting both to "" satisfies it completely — and
    discovery then advertises "" as the RFC 9728 resource. Found by adversarial review,
    closed by the production URL invariants block rather than by the audience guard.

    AGREEMENT IS THE POINT. When the two values DISAGREE the audience guard fires first,
    which is why MCP_RESOURCE_URL is absent from the single-variable parametrization
    below — overriding it alone can never reach the invariants block. Only a config that
    is self-consistent and still invalid gets that far.

    If someone were to "simplify" the predicate back to the PG-OpenAI form
    (`"localhost" in value or startswith("http://")`), both values here would sail
    through both guards and this test would fail.
    """
    returncode, stderr = _import_config(
        CLARITY_CLAUDE_MCP_RESOURCE_URL=agreed_value,
        CLARITY_CLAUDE_AUDIENCE=agreed_value,
    )

    assert returncode != 0, (
        f"Import must fail when resource and audience both equal {agreed_value!r}"
    )
    assert "Production URL validation failed" in stderr, (
        f"Failure must come from the URL invariants block:\n{stderr}"
    )


@pytest.mark.parametrize(
    "var,bad_value",
    [
        ("CLARITY_CLAUDE_JWKS_URL", "http://localhost:8000/oauth/pg/jwks"),
        ("CLARITY_CLAUDE_BACKEND_URL", "http://localhost:8000"),
        ("CLARITY_CLAUDE_ISSUER", "http://www.priority-guard.com"),
    ],
)
def test_module_import_fails_on_any_non_https_url_setting_in_production(var, bad_value):
    """
    Bug this catches: the invariants block covering only some settings. Before it existed,
    MindSort-Claude validated exactly one URL (OAUTH_ISSUER_BASE, localhost only) — so a
    JWKS_URL left at its localhost default would boot happily and then fail every token
    validation, and a BACKEND_URL left at its default would lose every board write.

    Each case overrides one variable, so a pass proves that variable specifically is
    covered rather than that some other guard happened to fire.
    """
    returncode, stderr = _import_config(**{var: bad_value})

    assert returncode != 0, f"Import must fail when {var}={bad_value!r} in production"
    assert "Production URL validation failed" in stderr, (
        f"Failure must come from the URL invariants block:\n{stderr}"
    )
    assert var in stderr, f"Error must name the offending variable {var}:\n{stderr}"


def test_module_import_succeeds_in_dev_with_localhost_everywhere():
    """
    Bug this catches: the invariants block firing outside production, which would make
    the module unimportable locally and in CI — every developer machine and the whole
    test suite, broken by a guard meant for Render.
    """
    returncode, stderr = _import_config(
        ENV="dev",
        CLARITY_CLAUDE_MCP_SERVER_URL="http://localhost:8003",
        CLARITY_CLAUDE_MCP_RESOURCE_URL="http://localhost:8003/mcp",
        CLARITY_CLAUDE_AUDIENCE="http://localhost:8000",
        CLARITY_CLAUDE_JWKS_URL="http://localhost:8000/oauth/pg/jwks",
        CLARITY_CLAUDE_BACKEND_URL="http://localhost:8000",
        CLARITY_CLAUDE_OAUTH_ISSUER_URL="http://localhost:8000/oauth/pg",
        CLARITY_CLAUDE_OAUTH_ISSUER_BASE="http://localhost:8000",
        CLARITY_CLAUDE_CORS_ALLOWED_ORIGINS=None,
    )

    assert returncode == 0, f"Dev config must import cleanly. stderr:\n{stderr}"
