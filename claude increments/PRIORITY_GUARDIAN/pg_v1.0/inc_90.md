# Shared Architecture — Backend `/robots.txt` Route

## Context & Motivation

`priority-guard.com` (and its `www.` redirect) hosts the FastAPI OAuth/API backend. It is **not** a marketing or public-content surface. The marketing site for the brand lives at `fulfilling-productivity.com` (Framer-hosted).

Currently the backend has **no** route at `/robots.txt`. Search engines (Google, Bing, GPTBot, ClaudeBot, etc.) crawl the OAuth backend domain and get `{"detail":"Not Found"}` at `/` and `/robots.txt`. This:

- Creates noise in Google Search Console (homepage 404s, missing sitemap warnings)
- Wastes search engine crawl budget on a domain that should never be indexed
- Leaks the existence of API/OAuth surfaces to opportunistic scanners

The fix: serve a single `robots.txt` that tells all well-behaved crawlers to stay out of the entire backend domain.

## Scope

**In scope:**
- One new FastAPI route: `GET /robots.txt` returning `User-agent: *\nDisallow: /\n` as `text/plain`.
- `include_in_schema=False` so it does not appear in `/docs` (Swagger).
- Unit test verifying status code, content-type, and body.

**Out of scope (do NOT add):**
- No `@app.get("/")` route. No homepage redirect. No `sitemap.xml`. No HTML.
- No middleware changes, no security header changes, no CORS changes.
- No Alembic migration (no DB changes).
- No changes to any other router file.

## Implementation Approach — Copy and Adjust, Never Rewrite

Add the new route to `backend/main.py` **immediately after** the existing `/health` route (lines around the `health_check` function). Do not refactor surrounding code. Do not change the `/health` route. Do not move imports unless strictly required for the new route.

The route handler must:
- Be decorated with `@app.get("/robots.txt", include_in_schema=False)`.
- Return a `PlainTextResponse` (already imported indirectly via FastAPI — verify and import explicitly from `fastapi.responses` at the top of the file if needed).
- Body: literally `User-agent: *\nDisallow: /\n` (two lines, trailing newline).
- No auth, no DB access, no Redis access, no logging on success path.

Add a brief comment block above the route explaining intent:

```python
# -------------------------------------------------------------
# robots.txt — Tell crawlers to stay out of the backend domain.
# This is the OAuth/API backend (priority-guard.com). The public
# marketing surface is fulfilling-productivity.com.
# -------------------------------------------------------------
```

## Files to Touch

1. `backend/main.py` — add the route + import if needed.
2. `tests/backend/test_robots_txt.py` — new test file (see Unit Tests below).

**Do not touch any other file.** No router files. No middleware. No config.

## Unit Tests (separate from integration tests)

Create `tests/backend/test_robots_txt.py` with the following coverage:

- Test 1: `GET /robots.txt` returns HTTP 200.
- Test 2: Response `content-type` starts with `text/plain`.
- Test 3: Response body equals exactly `"User-agent: *\nDisallow: /\n"`.
- Test 4: The route is **not** present in the OpenAPI schema (assert `/robots.txt` not in `app.openapi()["paths"]`).

Use `httpx.AsyncClient` against the FastAPI app following the same pattern as existing tests under `tests/backend/`. If there is no `tests/backend/` directory, place the file under `tests/` following the project's existing test layout — check first, do not invent a new structure.

## Integration Tests

None required. This route has no DB, no Redis, no external dependencies, no auth interactions. A unit test on the FastAPI app is sufficient.

## Production-Readiness Considerations (Increment Scope)

- **Scalability (TAM):** Static one-line response, no I/O. Negligible load impact. No scalability concerns.
- **GDPR / data retention:** No personal data, no logging beyond standard request middleware. No retention concerns.
- **Production load + latency:** Static string response. P99 latency impact: zero.

## Pre-Deploy Checklist

**MANDATORY: Read `doc/OPERATIONS_PREDEPLOY.md` in full before deploying.**

Specific pre-deploy steps for this increment:

1. Confirm `alembic heads | wc -l` returns `1` (no migration forks). This increment adds no migration but the check is part of standard deploy hygiene.
2. After Render deploy completes, verify:
   ```bash
   curl -I https://www.priority-guard.com/robots.txt
   # Expect: HTTP/2 200, content-type: text/plain
   
   curl https://www.priority-guard.com/robots.txt
   # Expect body:
   # User-agent: *
   # Disallow: /
   ```
3. Verify Swagger is unaffected:
   ```bash
   curl https://www.priority-guard.com/openapi.json | grep -c '"/robots.txt"'
   # Expect: 0
   ```
4. Verify `/health` still works (regression check):
   ```bash
   curl https://www.priority-guard.com/health
   # Expect: {"status":"ok"}
   ```

## Submission-Window Consideration

The Anthropic Connectors Directory submission for Priority Guardian is active. This change touches the shared backend that hosts the OAuth provider. The change is low-risk (additive, no auth/DB/middleware touched), but should still be deployed in a window where:

- No other backend changes are batched in the same deploy.
- The OAuth discovery sanity check from `OPERATIONS_PREDEPLOY.md` passes post-deploy.
- The submission reviewer is not actively in the middle of a flow you can observe.

If unsure about timing, defer until the submission decision lands.

## Out-of-Scope Follow-Ups (Document, Do Not Implement)

After this increment is live, the following can be considered separately (each is its own decision):

- Removing `priority-guard.com` as a property from Google Search Console (no code change; UI action only).
- Adding similar `robots.txt` to any other MCP server domains in the suite (`pg.priority-guard.com`, etc.) — these are separate services and need their own briefings.

Do not bundle these into this increment.

## Definition of Done

- [ ] `GET /robots.txt` returns 200 with the exact two-line body in production.
- [ ] Route does not appear in `/docs` or `openapi.json`.
- [ ] Unit tests pass locally and in CI.
- [ ] `/health` and all other existing routes still behave identically.
- [ ] OAuth discovery sanity check from `OPERATIONS_PREDEPLOY.md` still passes after deploy.
- [ ] Briefing notes archived under `claude increments/SHARED ARCHITECTURE/`.