# OAuth Discovery Integration Tests
#
# Live HTTP tests against deployed production servers.
# EXCLUDED from default pytest runs via addopts = -m "not live" in pytest.ini.
#
# To run live tests:
#   pytest -m live tests/integration/oauth_discovery/ -v
#
# See doc/ADR/ADR_005_platform_oauth_discovery_contracts.md for context.
