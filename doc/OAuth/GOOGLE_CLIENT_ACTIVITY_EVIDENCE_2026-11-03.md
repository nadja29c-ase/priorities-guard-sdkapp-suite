# Google OAuth client activity — evidence record (2026-11-03)

**Why this file exists.** On 2026-11-03 Google sent "[Action Advised] Manage your unused OAuth clients":
project `priority-guardian` has OAuth clients inactive for at least 5 months, to be deleted in 30 days
(≈ 2026-12-03) unless used in a Sign-in with Google flow or a refresh-token exchange. The project has one
client, `907396021268-…` ("Priority Guardian Backend"), which is the production client of the shared
backend. Our own records show refresh-token exchanges on that client inside the 5-month window. This file
preserves that evidence, because Better Stack keeps raw logs for only ~3 days (they expire ≈ 2026-11-06).

**Framing for any support ticket:** *"Our records show the exchanges below on this client; this seems
inconsistent with the notice."* We cannot tell from our side why the client was flagged (error, delay, or
a definition of activity we don't know). Do not assert that Google made a mistake.

---

## 1. Facts and how each was established

| # | Fact | Source |
|---|---|---|
| F1 | Project `priority-guardian` contains exactly one OAuth client, `907396021268-…` | Google Cloud Console (Nadja, 2026-11-03) |
| F2 | Production `GOOGLE_CLIENT_ID` on the shared backend is that client | Render env vs. console, compared by Nadja (2026-11-03) |
| F3 | The backend has exactly one Google client setting, used for authorize, code exchange and refresh | `backend/core/google_oauth.py:240,292`, `backend/core/google_calendar.py:43` (at `4822aef`) |
| F4 | Only one backend web service exists (no staging); local `.env` has no Better Stack token and a different Google client | Render service list; local `.env` check (2026-11-03) |
| F5 | The only writer of `core_connections.encrypted_refresh_token` is the reconnect upsert, and it always sets `updated_at`. The refresh path writes access token, `token_expires_at`, `updated_at` only. No migration, script or ops file writes the column; no re-encryption/key-rotation code exists | Code audit at `195b680`: `backend/core/repositories/google_connection_repo.py:41-63`, `backend/core/google_token_management.py:203-205` |
| F6 | No manual SQL edits to `core_connections` | Nadja (2026-11-03) |
| F7 | A Google refresh token is only usable with the client that issued it | OAuth 2.0 / Google token endpoint behaviour |

## 2. Production database snapshot (before today's test)

Run by Nadja on 2026-11-03 before 12:53 UTC, read-only (`default_transaction_read_only=on`):

```sql
SELECT left(user_id::text, 8) AS user_prefix, connection_type, created_at, updated_at,
       token_expires_at, last_used_at, revoked_at
FROM core_connections WHERE provider = 'google'
ORDER BY updated_at DESC NULLS LAST LIMIT 20;
```

```
 user_prefix | connection_type |          created_at           |          updated_at           |       token_expires_at        |         last_used_at          | revoked_at
-------------+-----------------+-------------------------------+-------------------------------+-------------------------------+-------------------------------+------------
 954318c4    | google          | 2026-10-19 05:14:45.901584+00 | 2026-10-19 22:48:44.130071+00 | 2026-10-19 23:48:42.606333+00 | 2026-10-19 22:48:44.127191+00 |
 33146c89    | google          | 2026-10-16 15:20:24.782358+00 | 2026-10-16 15:20:24.782358+00 | 2026-10-16 16:20:23.768414+00 |                               |
 64b8f998    | google          | 2026-10-08 07:48:25.167055+00 | 2026-10-14 19:17:34.654505+00 | 2026-10-14 20:17:33.109092+00 | 2026-10-14 19:17:34.64438+00  |
 e974b9ad    | google          | 2026-08-06 12:11:41.410143+00 | 2026-09-24 14:50:39.983496+00 | 2026-09-24 15:50:38.475029+00 | 2026-09-24 14:50:39.977113+00 |
 9c4bffda    | google          | 2026-07-30 10:05:30.813516+00 | 2026-09-17 11:12:21.662818+00 | 2026-09-17 12:12:20.20967+00  | 2026-09-17 11:12:21.658304+00 |
 4e2a0663    | google          | 2026-09-08 07:37:14.771021+00 | 2026-09-08 07:39:05.177541+00 | 2026-09-08 08:37:13.764131+00 | 2026-09-08 07:39:05.475728+00 |
```

Reading (only rows that still exist; disconnects/offboarding delete rows, so this is not a complete history):

- **Refresh-token exchanges** (`token_expires_at` = `updated_at` + 1 h): 2026-09-17 11:12, 2026-09-24 14:50,
  2026-10-14 19:17, 2026-10-19 22:48. (`4e2a0663`'s 07:39 `updated_at` is NOT a refresh: its
  `token_expires_at` is creation + 1 h.)
- **Authorization-code exchanges** (`created_at`): 2026-07-30, 2026-08-06, 2026-09-08, 2026-10-08,
  2026-10-16, 2026-10-19. All after early June 2026, i.e. inside the 5-month window.
- `e974b9ad` (Nadja's account) — refresh token last written on or before 2026-09-24 (F5).

## 3. Better Stack long-term counts (Shared Backend source `2397574`, metrics, retained from 2026-10-01)

```sql
SELECT toDate(dt) AS day, label('event') AS ev, sum(logs_count) AS n
FROM {{source}}                        -- source_type: metrics
WHERE dt >= '2026-10-01' AND name IS NULL
  AND label('event') IN ('google_oauth.token_exchange_success','google_oauth.token_exchange_failed',
    'oauth_callback_tokens_stored','google.token.refresh_success','Token refresh successful',
    'google_oauth.token_revoked')
GROUP BY day, ev ORDER BY day, ev;
```

| Day | Event | n |
|---|---|---|
| 2026-10-08 | `google_oauth.token_exchange_success`, `oauth_callback_tokens_stored` | 1 each |
| 2026-10-14 | `google.token.refresh_success`, `Token refresh successful` | 1 each |
| 2026-10-16 | `google_oauth.token_exchange_success`, `oauth_callback_tokens_stored` | 1 each |
| 2026-10-19 | `google_oauth.token_exchange_success`, `oauth_callback_tokens_stored`, `google.token.refresh_success`, `Token refresh successful` | 1 each |
| 2026-11-03 | `google.token.refresh_success`, `Token refresh successful`, `google_oauth.token_revoked`, `google_oauth.token_exchange_success`, `oauth_callback_tokens_stored` | 1 each |

These match the database rows in §2 one for one. **No** `token_exchange_failed` and **no** code exchange
of any kind between 2026-10-19 and 2026-11-03 13:24 UTC.

## 4. Raw events on 2026-11-03 (Better Stack raw logs — expire ≈ 2026-11-06)

All from `service = priority-guardian-backend`, process 55 (the production instance running `4822aef`,
deployed 2026-11-03 12:52:45 UTC). Unlabelled rows at .185812 and .748174 are the HTTP client lines
`POST https://oauth2.googleapis.com/token "HTTP/1.1 200 OK"`.

| UTC | Event | User |
|---|---|---|
| 12:53:43.085 | `google.token.refresh_needed` | e974b9ad |
| 12:53:43.186 | `POST oauth2.googleapis.com/token` → 200 | |
| 12:53:43.187 | `Token refresh successful` | |
| 12:53:43.240 | **`google.token.refresh_success`** | e974b9ad |
| 13:23:44.007 | `google_oauth.token_revoked` (Nadja disconnected Calendar) | |
| 13:23:50.150 | `oauth_start_initiated` → `oauth_start_redirecting_to_google` | e974b9ad |
| 13:24:12.660 | `oauth_callback_state_verified` | e974b9ad |
| 13:24:12.748 | `POST oauth2.googleapis.com/token` → 200 | |
| 13:24:12.749 | **`google_oauth.token_exchange_success`** | |
| 13:24:12.760 | **`oauth_callback_tokens_stored`** | e974b9ad |

Absence check: over 2026-10-31 12:54 → 2026-11-03 12:54 UTC, the only Google event of these types was the
12:53:43 refresh — no `oauth_callback_tokens_stored`, `token_exchange_success` or `oauth_start_initiated`.

## 5. Conclusion

1. `e974b9ad`'s stored refresh token was last written on or before 2026-09-24 (§2 + F5 + F6), and was not
   rewritten before 2026-11-03 12:53 (§3, §4 absence check).
2. That token was successfully exchanged at Google's token endpoint on 2026-11-03 12:53:43 UTC by the
   production backend, whose only Google client is `907396021268-…` (F1–F3).
3. By F7, the token belongs to `907396021268-…`; therefore the 2026-09-24 14:50 refresh of the same stored
   token was also a refresh-token exchange on `907396021268-…` — inside the 5-month window.
4. Independently, the production backend completed code exchanges on 2026-10-08, 10-16, 10-19 and
   2026-11-03, and refreshes on 2026-10-14, 10-19 and 2026-11-03 (§3), with no failed exchanges.

**Residual assumptions:** F2 (env var compared visually, not via API) and F6 (no manual SQL) rest on
Nadja's confirmation. §2 is not a complete history.

## 6. Follow-up

- 2026-11-05: Console → client status + Overview with a 30-day range. If the flag has cleared, no ticket.
- If still flagged: ticket with §2–§4, framed as above.
- 2026-11-25: final status check before the ≈ 2026-12-03 deletion date (deleted clients are restorable for
  30 days in the console).
