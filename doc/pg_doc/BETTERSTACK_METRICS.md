# Priority Guardian — Better Stack Metric Definitions

**Snapshot as of 2026-09-28.** Better Stack is configured in its UI/API, not in this repo — this
file describes that configuration and can drift from it. When in doubt, the Better Stack API
(`metric_expressions`, `dashboard`, `chart`) is the truth; update this file when you change it.

Team: `t499724`. All log events referenced below are structlog events; the event name lives at
`message.event` in the raw JSON (not top-level `event`). Top-level fields are only `level`, `dt`,
`message`, `context`, etc. — a rule that reads `JSONExtractString(raw, 'event')` never matches.

---

## 1. User levels (headline definitions)

| Level | Definition | Why it exists |
|---|---|---|
| **Visitor** | Invoked ≥1 Priority Guardian tool | Reach: people find and open PG |
| **Active** | Invoked a tool **and** has ≥1 priority | Activation: they set PG up. **Headline "active user" metric.** |
| **Engaged** | Has ≥1 priority **and** Google Calendar connected | Core value: PG can actually track time invested |

Decided 2026-09-28. The previous "PG WAU" counted Visitors and was renamed, because every user
active in the week of 2026-09-21 had 0 priorities (verified against `pg_priorities`), so "active"
was overstating real usage.

Common rules for all three:

- **Tool invocation** = a `tool.timing` event (logged by the dispatcher for every authenticated
  call, success or failure — `mcp_server/priority_guardian/handlers/tools.py`).
- **Excluded:** `record_widget_diagnostic` — a private, widget-only telemetry tool
  (`visibility="private"`, `tools/widget_tools/record_widget_diagnostic.py`) that fires on widget
  mount/display-mode changes without any user intent, including when an old chat is reopened.
- **Excluded:** the internal test account `e974b9ad-e82b-4af3-8ab1-8d795af671ec`. To exclude
  another internal account, add its UUID to the `NOT IN (...)` list in **every** metric and chart
  below that has one.
- **Excluded:** events with an empty `user_id` (unauthenticated calls).

---

## 2. Sources

| Source ID | Name | What ships to it |
|---|---|---|
| `2397712` | Priority Guardian MCP | **PG-OpenAI (ChatGPT) MCP server only.** PG-Claude does not ship logs to Better Stack yet (see `doc/OPERATIONS_PREDEPLOY.md` → Better Stack Log Shipping → Deferred Services). All user-level metrics are therefore **ChatGPT-only**. |
| `2397574` | Priority-Guard-Suite-Shared Backend | Shared backend (OAuth, consent, Google OAuth, APIs) — serves both PG-ChatGPT and PG-Claude. |
| `1719219` | Unpack v1.1 live | Unpack (not covered here). |

**Retention:** raw logs are kept ~3 days; extracted metrics are kept much longer. Metric rules
apply to **new logs only** (`build_type: new_data`) — a new or edited rule has no history before
its creation date. `historical_logs` rebuild exists but only reaches the ~3 days still in raw storage.

---

## 3. Metric expressions — Priority Guardian MCP (`2397712`)

### Labels (attached to every metric row from the same log line)

| Label | Expression |
|---|---|
| `user_id` | `JSONExtractString(raw, 'message', 'user_id')` |
| `tool_name` | `JSONExtractString(raw, 'message', 'tool_name')` |
| `Event` | `JSONExtractString(raw, 'message', 'event')` |
| `level` | `JSONExtractCaseInsensitive(raw, 'level', 'Nullable(String)')` |
| `success` | `JSONExtractBool(raw, 'message', 'success')` (unused) |

### Metrics

**`pg_tool_execution_count`** — sum. One per `tool.timing` event. Carries `user_id` and
`tool_name` labels, so it is also the source for **Visitors** (distinct `label('user_id')`) with
full history back to 2026-05.

```sql
if(JSONExtractString(raw, 'message', 'event') = 'tool.timing', 1, NULL)
```

**`pg_funnel_has_priority_users`** — uniq(user_id). **Active** level. Since 2026-09-24.
A user qualifies when, in the window, `get_priorities` reported ≥1 priority, or they successfully
created one.

```sql
if(
  JSONExtractString(raw, 'message', 'user_id') NOT IN ('', 'e974b9ad-e82b-4af3-8ab1-8d795af671ec')
  AND (
    (JSONExtractString(raw, 'message', 'event') = 'tool.get_priorities.success'
      AND JSONExtractInt(raw, 'message', 'priority_count') > 0)
    OR (JSONExtractString(raw, 'message', 'event') = 'tool.timing'
      AND JSONExtractString(raw, 'message', 'tool_name') IN ('create_priority', 'add_priority')
      AND JSONExtractBool(raw, 'message', 'success') = 1)
  ),
  JSONExtract(raw, 'message', 'user_id', 'Nullable(String)'),
  NULL
)
```

**`pg_engaged_users`** — uniq(user_id). **Engaged** level. Since 2026-09-28.

```sql
if(
  JSONExtractString(raw, 'message', 'user_id') NOT IN ('', 'e974b9ad-e82b-4af3-8ab1-8d795af671ec')
  AND JSONExtractString(raw, 'message', 'event') = 'tool.get_priorities.success'
  AND JSONExtractInt(raw, 'message', 'priority_count') > 0
  AND JSONExtractBool(raw, 'message', 'google_connected') = 1,
  JSONExtract(raw, 'message', 'user_id', 'Nullable(String)'),
  NULL
)
```

Source fields: `tool.get_priorities.success` logs `user_id`, `priority_count`, `google_connected`,
`calendar_available` (`mcp_server/priority_guardian/tools/get_priorities.py`).

**`pg_auth_failures`** — sum. Since 2026-09-28. Tool calls rejected at authentication.
Some 401s are expected (a not-yet-connected user gets one before the OAuth prompt).

```sql
if(JSONExtractString(raw, 'message', 'event') IN ('tool.dispatch.unauthorized', 'tool.dispatch.forbidden'), 1, NULL)
```

**`pg_tool_failed_calls`** — sum. Since 2026-09-28. Authenticated calls that ended unsuccessfully:
`tool.dispatch.rejected` (ToolUsageError), unexpected exceptions, and handlers returning
`isError=True` (e.g. backend errors). `success` is a JSON boolean, compared as raw `'false'`.

```sql
if(
  JSONExtractString(raw, 'message', 'event') = 'tool.timing'
  AND JSONExtractRaw(raw, 'message', 'success') = 'false',
  1, NULL
)
```

**`pg_crashes`** — sum. Log lines at top-level `level = 'error'`.

```sql
CASE WHEN JSONExtractString(raw, 'level') = 'error' THEN 1 ELSE NULL END
```

**`total_ms`** — avg/max/min of `message.total_ms` (tool latency). Not charted.

### Deleted 2026-09-24 / 2026-09-28 (do not recreate)

| Metric | Why deleted |
|---|---|
| `pg_product_active_users` | Counted `record_widget_diagnostic` as activity |
| `pg_wau_users` | Superseded by distinct `label('user_id')` on `pg_tool_execution_count` (full history) |
| `pg_funnel_calendar_users` | Superseded by `pg_engaged_users` (calendar without priority is not a level) |
| `pg_auth_mcptool_failures` | Read top-level `event` → could never match; replaced by `pg_auth_failures` |
| `pg_tool_failures` | Read top-level `event`/`success` → could never match; replaced by `pg_tool_failed_calls` |
| `pg_backend_tool_failures` | Malformed expression (CASE pasted inside a JSON path) → could never match |

---

## 4. Metric expressions — Shared Backend (`2397574`)

**`pg_reg_new_users_daily`** — sum. One per completed Priority Guardian OAuth consent ("Allow").

```sql
CASE
  WHEN JSONExtractString(raw, 'message', 'event') = 'oauth.consent.recorded'
   AND JSONExtractString(raw, 'message', 'app_name') = 'priority_guardian'
  THEN 1 ELSE NULL
END
```

Event source: `backend/core/oauth_provider/services/consent_service.py` (`record_consent`), called
from `consent_ui.py` on every "Allow". Verified 2026-09-28 against raw logs day by day.

**What it actually counts: completed PG connections, not unique new people.**

- The consent screen is shown on every authorize — there is no skip for returning users, so a
  reconnect is logged again.
- Without a `login_hint` or session cookie, `/oauth/pg/authorize` creates a **new anonymous
  `core_users` row** on each attempt (`backend/core/oauth_provider/authorize.py`, "Priority 3"). A
  returning human who reconnects therefore gets a new `user_id` and counts again. In the logs of
  2026-09-22..24 every authorize took this path (`identity_source=new_anonymous`).
- Covers **PG-ChatGPT and PG-Claude together** (same `/oauth/pg/authorize`, same `app_name`).
- Do **not** count `oauth.authorize.user_created` instead: it fires in bursts (4× in 2 s for one
  person) and includes abandoned flows.

Other labels on this source: `level`, `event`, `error_name`, `error_message`, `user_agent`,
`correlation_id`. There is **no `user_id` label** here yet, so registrations cannot be joined to
users in charts.

---

## 5. Dashboards and charts

### PG MCP-specific Analytics (`1010460`, source `2397712`)

| Chart | Type | Query basis | Window |
|---|---|---|---|
| PG Visitors — weekly trend | bar | distinct `label('user_id')` on `pg_tool_execution_count`, per `toStartOfWeek(dt, 1)` | time picker |
| PG Visitors (7d) | number | distinct `label('user_id')` on `pg_tool_execution_count` | fixed `now() - 7 DAY` |
| PG Active users (7d) | number | `uniqMerge` of `pg_funnel_has_priority_users` | fixed `now() - 7 DAY` |
| PG Engaged users (7d) | number | `uniqMerge` of `pg_engaged_users` | fixed `now() - 7 DAY` |
| Tool calls — by day, user, tool | table | `sumMerge` of `pg_tool_execution_count` grouped by `toDate(dt)`, `user_id`, `tool_name` | time picker |
| MCP auth failures (401/403) | number | `sumMerge` of `pg_auth_failures` | time picker |
| Failed tool calls (auth OK, tool failed) | number | `sumMerge` of `pg_tool_failed_calls` | time picker |
| MCP tool and dispatcher crashes | number | `sumMerge` of `pg_crashes` | time picker |
| PG user levels: Visitors → Active → Engaged | bar (category) | the three level queries, `UNION ALL` | time picker |

All Visitor queries apply the exclusions from §1 as label filters
(`label('tool_name') != 'record_widget_diagnostic'`, `label('user_id') NOT IN (...)`).

### Shared Backend Analytics (`1000340`, source `2397574`)

| Chart | Type | Query basis |
|---|---|---|
| New PG users per day | bar | `sumMerge(value_sum)` of `pg_reg_new_users_daily` per `toStartOfDay(dt)` (UTC) |
| New PG users — cumulative | line | running `sum() OVER (ORDER BY time)` of the daily totals, from the range start |

Fixed 2026-09-24: both charts previously used `minMerge(value_min)`, which capped every bucket at 1.

---

## 6. Known limitations

1. **ChatGPT-only user metrics.** PG-Claude ships no logs to Better Stack; its users are invisible
   to Visitors/Active/Engaged while they do appear in `pg_reg_new_users_daily`.
2. **Identity is per connection, not per person.** Reconnects create new user IDs (§4). This
   inflates new-user counts and can double-count one person across a week.
3. **Active/Engaged are observed only through `get_priorities`** (or priority creation). A user
   with priorities who only calls other tools in a week is not counted as Active/Engaged.
4. **The level chart counts users per level within a time window — it doesn't follow a group of new
   users through the steps.** A cohort funnel (registered in the last 7 days → + calendar → + active)
   is designed but not built: it needs a `user_id` label on the Shared Backend source, a metric on
   `oauth_callback_tokens_stored` (`backend/core/oauth/google_oauth_service.py`, logged with
   `user_id` after Google tokens are stored), and a second source variable on the dashboard.
   Better Stack configuration only, no code. Deferred 2026-09-28.
5. **No uptime monitoring of own services.** The only monitor checks `google.com`.

---

## Change log

| Date | Change |
|---|---|
| 2026-09-24 | Fixed new-user charts (`minMerge` → `sumMerge`). Tool calls table rebuilt (day × user × tool). Widget diagnostics + test account excluded. Deleted `pg_product_active_users`. |
| 2026-09-28 | Redefined user levels (Visitor / Active / Engaged). Visitors moved to label-based distinct users (full history). Rebuilt auth-failure and failed-call metrics. Deleted broken/unused metrics (§3). Dashboard layout de-overlapped. This document created. |
