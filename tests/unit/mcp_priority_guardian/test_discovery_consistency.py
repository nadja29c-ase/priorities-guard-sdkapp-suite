"""
RETIRED — Migrated to tests/unit/oauth_discovery/test_oauth_discovery_contracts.py

This file previously contained Shape #1 (PG-OpenAI) discovery consistency tests.
Per inc_oauth_discovery_contracts (2026-07-02), all discovery contract tests were
consolidated into a single cross-service module covering all four MCP servers.

See:
- tests/unit/oauth_discovery/test_oauth_discovery_contracts.py (unit tests)
- tests/integration/oauth_discovery/test_live_discovery_chain.py (live tests)
- doc/ADR_005_platform_oauth_discovery_contracts.md (rationale)

DO NOT add new tests here — add them to test_oauth_discovery_contracts.py.
"""

# This file is intentionally empty. The import below verifies the new module exists.
# If this import fails, the migration is incomplete.
from tests.unit.oauth_discovery import test_oauth_discovery_contracts as _migrated  # noqa: F401
