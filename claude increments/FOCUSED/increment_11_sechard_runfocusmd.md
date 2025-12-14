# Increment 11: OAuth Hardening + run_focus_mode()

## Context

Focused is a ChatGPT SDK app that connects Google Calendar with Apple Focus Mode. The backend infrastructure is complete (OAuth provider, sync engine, webhooks, conflict detection). This increment adds the missing security hardening and the core user-facing action.

**Reference docs:**
- Architecture: `/mnt/project/mvp1_description__focused__production_ready_4.pdf` (page 3 for tool specs)
- Data retention: `/mnt/project/Data_Retention_Strategy__Focused__7.pdf`
- Existing code: `backend/core/google_oauth.py`, `backend/apps/focused/mcp_server.py`

**All timestamps stored as UTC.**

---

## Part A: Google OAuth Security Hardening

### Problem
Current outbound Google OAuth flow (`/auth/focused/google/start` → `/auth/focused/google/callback`) lacks CSRF protection. This will fail Google OAuth verification and security review.

### Requirements

**State parameter (REQUIRED):**
- Generate cryptographically secure random state in `/start`
- Store in Redis with 10-minute TTL, keyed by state value
- Redis value must contain: `user_id`, `code_verifier` (if PKCE), `created_at`
- Validate state in `/callback` before token exchange
- Reject if: no entry found, TTL expired, or user context mismatch

**PKCE S256 (RECOMMENDED):**
- Generate `code_verifier` (43-128 char random string)
- Derive `code_challenge` = base64url(sha256(code_verifier)) — no padding
- Store verifier in Redis alongside state
- Send `code_challenge` + `code_challenge_method=S256` to Google authorize URL
- Include `code_verifier` in token exchange request

**Error responses:**
- Never log tokens or secrets
- Log structured JSON errors server-side with correlation IDs (via structlog)
- Return HTML error page to browser (user-facing redirect flow)
- Use existing `structlog` patterns from Increment 7C

### Google OAuth endpoints
- Authorize: `https://accounts.google.com/o/oauth2/v2/auth`
- Token: `https://oauth2.googleapis.com/token`
- Scope: `https://www.googleapis.com/auth/calendar.readonly`

### Files to modify
- `backend/core/google_oauth.py`
- `backend/apps/focused/routers/auth_router.py`

---

## Part B: run_focus_mode() Tool

### Problem
Focused cannot activate Focus Mode. The app reads calendars but takes no action.

### Tool Contract
```
Tool: run_focus_mode
Scope: focused.write
Purpose: Activate/deactivate Apple Focus Mode via iOS Shortcuts

Inputs:
  action: "on" | "off" (required)
  focus_name: string (optional, default "Work")
  duration_minutes: integer (optional, triggers auto-deactivate)
  trigger_source: "calendar" | "user" (required)
  session_id: UUID (required if trigger_source="calendar", ignored if trigger_source="user")
  user_confirmation: boolean (required for action="on")

Outputs:
  shortcut_status: "success" | "failed" | "not_installed" | "already_active" | "already_inactive"
  shortcut_url: string | null (URL for ChatGPT client to open on device)
  focus_name: string
  start_time: ISO 8601 string
  end_time: ISO 8601 string | null
  message: string
  error_details: string | null
```

### Apple Shortcuts Integration

**Invocation method:** URL scheme
- Activate: `shortcuts://run-shortcut?name=Activate%20Focus%20Mode&input=text&text={focus_name}`
- Deactivate: `shortcuts://run-shortcut?name=Deactivate%20Focus%20Mode`

**Assumption:** User has pre-installed two Shortcuts named exactly:
- "Activate Focus Mode" 
- "Deactivate Focus Mode"

**Important:** Backend generates the URL and returns it in `shortcut_url`. ChatGPT client opens it on user's device. Backend never calls shortcuts:// directly.

### Session Management

**One active session per user rule:**
- Before activating (`action="on"`), check for existing open session (`actual_end IS NULL`)
- If open session exists: return `shortcut_status: "already_active"` with message prompting user to deactivate first
- Do NOT auto-close previous sessions (explicit user control)

**Calendar-triggered flows (`trigger_source="calendar"`):**
- Row in `focused_focus_sessions` already exists (created by sync engine when Focus Block detected)
- `session_id` input references this existing row
- Backend must verify `focused_focus_sessions.user_id == X-User-ID`; if not, return 404 (do not leak existence of other users' sessions)
- `run_focus_mode("on")`: sets `actual_start`, updates status
- `run_focus_mode("off")`: sets `actual_end`

**Manual flows (`trigger_source="user"`):**
- `session_id` input is ignored (even if provided)
- Create new row in `focused_focus_sessions` with `google_event_id=NULL`, `trigger_source='user'`
- This ensures all focus activity is tracked for analytics

**Deactivation idempotency:**
- If `actual_end` is already set when `action="off"` is called, do not change it
- Return `shortcut_status: "already_inactive"` with success message
- This applies to both manual deactivation and scheduled auto-deactivate

### Auto-Deactivation

When `duration_minutes` is provided and `action="on"`:
1. Calculate `end_time = now + duration_minutes` (UTC)
2. Schedule Celery task `auto_deactivate_focus` to run at `end_time`
3. Store scheduled job in `focused_scheduled_jobs` with `payload = {"session_id": <UUID>}`
4. Task signature: `auto_deactivate_focus(user_id: UUID, session_id: UUID)`

**Task execution (Option A - direct backend logic):**
- Load `focused_focus_sessions` row by `(user_id, session_id)`
- If `actual_end IS NULL`: set `actual_end = now`, generate deactivate shortcut_url
- If `actual_end` already set: no-op (idempotent)
- Mark job row as `status = "completed"` in either case

### Database

**New table: `focused_scheduled_jobs`**
- `id`: UUID primary key
- `user_id`: FK to core_users
- `job_type`: enum ('focus_deactivate', 'webhook_renewal', etc.)
- `scheduled_at`: timestamp (UTC)
- `status`: enum ('pending', 'completed', 'failed', 'cancelled')
  - On creation: `pending`
  - On success: `completed`
  - On failure: `failed` (increment retry_count)
  - On cancel: `cancelled`
- `celery_task_id`: string
- `retry_count`: integer, default 0
- `payload`: JSONB (stores session_id and other job-specific params)
- `created_at`, `updated_at`: timestamps (UTC)

**Retention enforcement:** Celery periodic task deletes rows with `status IN ('completed', 'failed', 'cancelled')` where `updated_at < NOW() - INTERVAL '7 days'`.

**Update `focused_focus_sessions`:**
- Set `actual_start` when Focus activated
- Set `actual_end` when Focus deactivated
- For manual sessions: new row with `google_event_id=NULL`, `trigger_source='user'`

### Scope Enforcement

- MCP server validates `focused.write` scope (already wired in 7D)
- Backend endpoint expects valid `X-User-ID` header
- Backend trusts that MCP has already enforced scope

### Error Handling

| Scenario | Response |
|----------|----------|
| Shortcut not installed | `shortcut_status: "not_installed"`, suggest installation |
| Shortcut execution fails | `shortcut_status: "failed"`, include error_details |
| User declined confirmation | Do not execute, return informative message |
| Invalid focus_name | Fall back to "Work", note in message |
| Already active session | `shortcut_status: "already_active"`, prompt to deactivate first |
| Already inactive session | `shortcut_status: "already_inactive"`, success message |
| Invalid session_id | Return 404 (session not found) |
| session_id belongs to different user | Return 404 (do not leak existence) |

### Files to create/modify
- `backend/apps/focused/tools.py` - add run_focus_mode logic
- `backend/apps/focused/mcp_server.py` - register tool with scope
- `backend/apps/focused/models.py` - add FocusedScheduledJob model
- `backend/core/celery_tasks.py` - add auto_deactivate_focus task + scheduled_jobs cleanup task
- New migration for focused_scheduled_jobs table

---

## Acceptance Criteria

### Part A
- [ ] `/auth/focused/google/start` generates and stores state parameter
- [ ] State Redis entry contains `user_id` and `code_verifier`
- [ ] `/auth/focused/google/callback` validates state before token exchange
- [ ] PKCE code_challenge sent to Google, code_verifier used in exchange
- [ ] Invalid/missing state: logged with correlation ID, returns HTML error page to browser
- [ ] Expired state: rejected, logged, returns HTML error page
- [ ] Mismatched user context: rejected, logged, returns HTML error page
- [ ] No tokens logged anywhere

### Part B
- [ ] MCP tool `run_focus_mode` registered with scope `focused.write`
- [ ] Tool input accepts `session_id` for calendar-triggered flows
- [ ] `session_id` ownership verified against `X-User-ID`; mismatch returns 404
- [ ] Manual sessions (`trigger_source="user"`) ignore input `session_id` and create new row
- [ ] Only one active focus session per user; duplicate activation returns `already_active`
- [ ] Deactivation is idempotent; already-closed session returns `already_inactive`
- [ ] Tool output includes `shortcut_url` for client invocation
- [ ] Auto-deactivate job scheduled with `session_id` in payload when duration provided
- [ ] Celery task closes correct session using `user_id` + `session_id`
- [ ] Scheduled job no-ops if session already closed (idempotent)
- [ ] Focus session recorded/updated in `focused_focus_sessions`
- [ ] `focused_scheduled_jobs` rows cleaned up per retention policy (7 days after completion)
- [ ] All error scenarios return structured responses

---

## Test Plan

### Part A: OAuth Security Hardening

#### Unit Tests (`tests/unit/test_google_oauth.py`)

**State generation:**
- [ ] `test_state_generation_is_cryptographically_random` - verify sufficient entropy (32+ bytes)
- [ ] `test_state_stored_in_redis_with_correct_ttl` - verify 10-minute TTL
- [ ] `test_state_redis_value_contains_user_id` - verify user_id present
- [ ] `test_state_redis_value_contains_code_verifier` - verify PKCE verifier stored

**PKCE:**
- [ ] `test_code_verifier_length_valid` - 43-128 characters
- [ ] `test_code_challenge_is_base64url_sha256` - correct derivation
- [ ] `test_code_challenge_no_padding` - no `=` characters

**State validation:**
- [ ] `test_valid_state_accepted` - happy path
- [ ] `test_missing_state_rejected` - no state param returns error
- [ ] `test_invalid_state_rejected` - unknown state returns error
- [ ] `test_expired_state_rejected` - state past TTL returns error
- [ ] `test_state_user_mismatch_rejected` - different user_id returns error
- [ ] `test_state_deleted_after_use` - single-use enforcement

**Error logging:**
- [ ] `test_invalid_state_logged_with_correlation_id` - structlog output verified
- [ ] `test_tokens_never_logged` - scan log output for token patterns

#### Integration Tests (`tests/integration/test_google_oauth_flow.py`)

- [ ] `test_full_oauth_flow_success` - /start → redirect → /callback → tokens stored
- [ ] `test_oauth_flow_state_validation` - manipulated state rejected
- [ ] `test_oauth_flow_pkce_exchange` - code_verifier correctly sent to Google
- [ ] `test_oauth_callback_returns_html_error_on_invalid_state` - verify HTML response (not JSON)
- [ ] `test_oauth_callback_returns_html_error_on_expired_state`
- [ ] `test_concurrent_oauth_flows_isolated` - two users don't interfere

### Part B: run_focus_mode() Tool

#### Unit Tests (`tests/unit/test_run_focus_mode.py`)

**Input validation:**
- [ ] `test_action_on_requires_user_confirmation` - confirmation=false rejected
- [ ] `test_action_on_valid_inputs` - all required fields present
- [ ] `test_action_off_valid_inputs`
- [ ] `test_invalid_action_rejected` - action not "on" or "off"
- [ ] `test_missing_trigger_source_rejected`
- [ ] `test_calendar_trigger_requires_session_id`
- [ ] `test_user_trigger_ignores_session_id` - session_id in input ignored, new session created

**Session ownership:**
- [ ] `test_session_id_belongs_to_user_accepted`
- [ ] `test_session_id_belongs_to_other_user_returns_404`
- [ ] `test_nonexistent_session_id_returns_404`

**One active session rule:**
- [ ] `test_activate_with_no_existing_session_succeeds`
- [ ] `test_activate_with_existing_active_session_returns_already_active`
- [ ] `test_activate_after_previous_session_closed_succeeds`

**Deactivation idempotency:**
- [ ] `test_deactivate_open_session_sets_actual_end`
- [ ] `test_deactivate_already_closed_session_returns_already_inactive`
- [ ] `test_deactivate_already_closed_session_does_not_modify_actual_end`

**Shortcut URL generation:**
- [ ] `test_activate_generates_correct_shortcut_url` - verify URL encoding
- [ ] `test_deactivate_generates_correct_shortcut_url`
- [ ] `test_focus_name_url_encoded` - special characters handled
- [ ] `test_default_focus_name_is_work`

**Session creation:**
- [ ] `test_manual_activation_creates_session_row`
- [ ] `test_manual_session_has_null_google_event_id`
- [ ] `test_manual_session_has_user_trigger_source`
- [ ] `test_calendar_activation_updates_existing_session`
- [ ] `test_activation_sets_actual_start`
- [ ] `test_deactivation_sets_actual_end`

**Auto-deactivation scheduling:**
- [ ] `test_duration_provided_schedules_celery_task`
- [ ] `test_no_duration_does_not_schedule_task`
- [ ] `test_scheduled_job_has_correct_payload` - session_id in payload
- [ ] `test_scheduled_job_status_is_pending`
- [ ] `test_scheduled_at_is_start_plus_duration`

#### Unit Tests (`tests/unit/test_auto_deactivate_task.py`)

**Task execution:**
- [ ] `test_task_closes_open_session` - actual_end set
- [ ] `test_task_idempotent_on_closed_session` - no change, no error
- [ ] `test_task_marks_job_completed_on_success`
- [ ] `test_task_marks_job_completed_even_if_session_already_closed`
- [ ] `test_task_marks_job_failed_on_error`
- [ ] `test_task_increments_retry_count_on_failure`
- [ ] `test_task_with_invalid_session_id_marks_failed`
- [ ] `test_task_with_invalid_user_id_marks_failed`

**Retention cleanup:**
- [ ] `test_cleanup_deletes_completed_jobs_older_than_7_days`
- [ ] `test_cleanup_deletes_failed_jobs_older_than_7_days`
- [ ] `test_cleanup_deletes_cancelled_jobs_older_than_7_days`
- [ ] `test_cleanup_keeps_pending_jobs`
- [ ] `test_cleanup_keeps_recent_completed_jobs`

#### Integration Tests (`tests/integration/test_run_focus_mode_flow.py`)

**Full activation flow:**
- [ ] `test_mcp_tool_call_activates_focus` - MCP → backend → session created
- [ ] `test_mcp_tool_requires_focused_write_scope` - wrong scope rejected
- [ ] `test_activation_with_duration_schedules_deactivation`

**Full deactivation flow:**
- [ ] `test_mcp_tool_call_deactivates_focus`
- [ ] `test_scheduled_deactivation_executes_at_correct_time`
- [ ] `test_manual_deactivation_before_scheduled_time`
- [ ] `test_scheduled_job_after_manual_deactivation_noops`

**Calendar-triggered flow:**
- [ ] `test_calendar_trigger_with_valid_session_id`
- [ ] `test_calendar_trigger_session_ownership_enforced`

**Manual flow:**
- [ ] `test_manual_trigger_creates_new_session`
- [ ] `test_manual_trigger_ignores_provided_session_id`

**Error scenarios:**
- [ ] `test_tool_returns_already_active_correctly`
- [ ] `test_tool_returns_already_inactive_correctly`
- [ ] `test_tool_returns_not_found_for_invalid_session`

#### End-to-End Tests (`tests/e2e/test_focus_mode_e2e.py`)

- [ ] `test_user_activates_focus_for_2_hours` - full flow with auto-deactivate
- [ ] `test_user_manually_deactivates_before_timer` - scheduled job handles gracefully
- [ ] `test_calendar_event_triggers_focus_activation` - webhook → session created → tool called
- [ ] `test_concurrent_activation_attempts_rejected` - race condition handled
- [ ] `test_retention_cleanup_removes_old_jobs` - 7-day retention enforced

---

## Out of Scope (Increment 12+)

- Calendar-triggered automation (webhook → detect Focus Block → prompt user)
- notify_user() tool
- Widgets/UI components
- Focus pattern analytics

**Parallel non-code task (not deferred to future increment):**
- Google OAuth verification submission (scope justification doc, consent screen screenshots)