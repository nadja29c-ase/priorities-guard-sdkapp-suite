Increment Briefing — Fix: Disconnect Should Not Revoke PG OAuth Tokens (revised)
Goal: Fix two related bugs caused by the disconnect endpoint revoking PG OAuth session tokens.

Background
POST /api/priority-guardian/disconnect currently does three things:

Revokes the Google OAuth token at Google
Marks core_connections.revoked_at
Bulk-revokes all OAuthAccessToken rows for the user (any row with pg.access scope)

Step 3 is wrong for a Google Calendar disconnect. It kills the active ChatGPT ↔ PG session, causing all subsequent MCP tool calls in the same conversation to fail with invalid_grant. It also prevents onRefresh() in the widget from succeeding after disconnect, so the UI never updates to show connected: false — leaving the disconnect button visible and triggering a second failed disconnect attempt.

Fix
File: backend/apps/priority_guardian/routers/offboarding_router.py
Remove PG OAuth token revocation from the disconnect handler only — the entire try block under # 2. Mark PG OAuth tokens as revoked. Also remove pg_tokens_revoked from the details dict initialisation, the logger.info call at the end, and the return payload.
Critical constraint: offboarding_router.py will eventually contain a delete-data endpoint. PG token revocation must remain present in any full offboarding / delete-account / explicit revoke flows. Do not remove or generalise revocation logic beyond the disconnect handler.
The rule is: disconnect = revoke Google Calendar access only. PG token revocation belongs in delete-account and explicit revoke flows, not in disconnect.

What does NOT change

Google token revocation at Google (step 1) — keep
core_connections.revoked_at update (step 2) — keep
ConnectionStatus.tsx — no changes; onRefresh() already calls get_priorities correctly, it just needs the session alive to succeed
No migration — no schema changes


Tests
No new test files needed. All test coverage lives in existing files.

Unit tests — tests/unit/priority_guardian/
No existing unit test file covers the offboarding router. Create test_offboarding_router.py with:

- test_disconnect_does_not_revoke_pg_tokens — mock DB, assert oauth_access_tokens UPDATE is never called
- test_disconnect_keeps_session_valid — mock DB, assert active token remains unrevoked
- test_disconnect_revokes_google_connection — regression guard: assert core_connections.revoked_at is still set
- test_disconnect_already_disconnected_idempotent — assert 200 with already_disconnected: True on second call

Integration tests — tests/integration/priority_guardian/test_pg_offboarding.py
This file exists and has comprehensive coverage. Update it for the fix:

- Remove pg_tokens_revoked assertions from TestDisconnectIntegration — the response no longer includes this field
- The two DB state tests already exist in TestDisconnectDBStateVerification:
  - test_disconnect_does_not_revoke_pg_tokens (5b) — already written, verify it passes after the fix
  - test_disconnect_keeps_session_valid (5b2) — already written, verify it passes after the fix
- Verify the pg_user_with_tokens fixture is intact — it creates 2 unrevoked pg.access tokens, which is the correct setup for both DB tests

The integration test file was written anticipating this fix (comments already say # pg_tokens_revoked no longer returned). After the code change, the existing DB state tests should pass without modification — run them to confirm.


Pre-deploy
Read doc/OPERATIONS_PREDEPLOY.md. No migration involved. After deploy, run the OAuth discovery sanity check.

Verification

- Connect Google Calendar in the widget
- Click Disconnect → confirm → widget re-renders showing disconnected state
- Subsequent tool calls in the same conversation succeed
- DB check: core_connections.revoked_at is set; oauth_access_tokens rows are NOT revoked