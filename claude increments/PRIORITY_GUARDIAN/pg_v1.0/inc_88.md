Claude Code Briefing — Increment: Delete Dead Backend Public Surface + Harmonize Clarity Consent Legal Links
Context
Backend pg.priority-guard.com is an MCP/OAuth host. It currently exposes four public HTML routes (/, /privacy, /terms, /clarity) that serve no functional purpose:

/privacy and /terms reference static files that don't exist → cause unhandled RuntimeError 500s (9 in last 46h of logs).
/ and /clarity serve landing pages that are not referenced by any external surface (verified — no marketing links, no LinkedIn posts, no shared URLs reference them).
Bots (Bingbot, Barkrowler, Dataprovider, OAI-SearchBot, etc.) discovered /privacy and /terms via the publicly-indexed / landing page and keep crawling them.

Verification audit (Increment 87) confirmed:

No tests, ADRs, OPERATIONS docs, scripts, or CI workflows depend on these routes.
No widget code, MCP server code, or OAuth consent template links to them.
OAuth provider metadata (DCR, discovery) does not expose them.
The only references are the route definitions themselves and broken links in index.html and clarity.html.

Canonical legal surface is Framer-hosted on fulfilling-productivity.com. All current OAuth consent templates for live/active apps (PG EN/DE, MindSort EN) already point there. Clarity's consent template is the exception — it points to https://www.priority-guard.com/privacy (status unverified, likely broken) and has no Terms of Service link at all. Clarity is a published app (v1.0), so this is a compliance gap.
This increment closes the public-surface dead code and brings Clarity's consent screen in line with PG and MindSort.
Scope
Part A — Delete dead public routes and static files
In backend/main.py, delete the following route handlers:

@app.get("/") — root() function and its body
@app.get("/privacy") — privacy_policy() function and its body
@app.get("/terms") — terms_of_service() function and its body
@app.get("/clarity") — clarity_landing() function and its body

After deletion, check whether FileResponse is still imported and used elsewhere in main.py. If unused, remove from the from fastapi.responses import FileResponse, JSONResponse import (keep JSONResponse). If still used elsewhere in the file, leave the import.
Do not touch:

The app.mount("/static", StaticFiles(...)) line — it serves logos referenced by OAuth consent templates (/static/pg_logo_icon_128.png, /static/logo-mindsort-64.svg, etc.).
Any other route, middleware, exception handler, or lifespan code.

In backend/static/, delete the following files:

index.html
clarity.html

Do not delete any other files in backend/static/ — the logos and SVGs are referenced by OAuth consent templates and must stay.
After deletion, expected behavior:

pg.priority-guard.com/ → 404
pg.priority-guard.com/privacy → 404 (no longer 500)
pg.priority-guard.com/terms → 404 (no longer 500)
pg.priority-guard.com/clarity → 404
pg.priority-guard.com/static/<logo> → still works
All OAuth, MCP, and .well-known endpoints → unchanged

Part B — Harmonize Clarity consent screen legal links
In backend/templates/oauth_consent_clarity_en.html, locate the .privacy-notice div (currently around the line containing the link to https://www.priority-guard.com/privacy).
Replace the entire .privacy-notice block with the same two-link structure already used in oauth_consent_pg_en.html and oauth_consent_mindsort_en.html, pointing to:

Privacy Policy: https://www.fulfilling-productivity.com/pg-privacy-policy
Terms of Service: https://www.fulfilling-productivity.com/pg-terms-of-service

The visible text should follow the same pattern as the existing PG/MindSort consent screens ("By authorizing this application, you agree to our Privacy Policy and Terms of Service.").
Do not touch any other consent template:

oauth_consent_pg_en.html, oauth_consent_pg_de.html — already correct.
oauth_consent_mindsort_en.html — already correct.
oauth_consent_mindsort_de.html — out of scope (MindSort not yet live; submission flow handles its own audit).
oauth_consent_en.html, oauth_consent_de.html (Focused) — Focused is deprecated; do not touch.
oauth_consent_clarity_de.html — only modify if the file currently has the same broken link pattern as the EN version. Read it first; if it already points to Framer URLs, leave it. If it has the same broken priority-guard.com/privacy pattern, apply the same harmonization.

Implementation approach — Copy and Adjust, Never Rewrite
This is not a copy-from-source-file increment, but the principle still applies for the consent template change: do not rewrite the styling, structure, or any unrelated text in oauth_consent_clarity_en.html. Make only the .privacy-notice block change. Leave all CSS, all other text, all form structure, all script blocks exactly as they are.
For main.py: delete only the four route handler blocks specified. Do not refactor adjacent code, do not "clean up" comments, do not reorder imports beyond removing FileResponse if it becomes unused.
Pre-deploy checklist
Before committing, read doc/OPERATIONS_PREDEPLOY.md and follow the checklist for any deployment-impacting changes. This increment touches public HTTP behavior (routes returning 404 instead of 200/500), so the operational surface is changed.
Verify locally:

App boots without errors after route deletion (no orphaned references to deleted handlers).
Hitting /, /privacy, /terms, /clarity returns FastAPI's default 404 JSON.
Hitting /static/pg_logo_icon_128.png still serves the logo.
Hitting /.well-known/oauth-authorization-server and /.well-known/openid-configuration still returns the expected JSON.
Rendering the Clarity consent screen (manually or via the existing test path) shows the new Framer links and a Terms link present.

Tests
Unit tests
No new unit tests required.
The deleted routes had no business logic — they were direct FileResponse returns. There is nothing to unit-test about their absence.
For the Clarity consent template change, no unit test is required: this is a static template content change, and existing template-rendering tests (if any cover Clarity) will continue to pass since structure is unchanged.
Integration tests
No new integration tests required.
If any existing integration test happens to assert on the absence or 404 behavior of these routes, it should now pass. The verification audit (Inc 87) confirmed no test currently asserts on these routes returning content.
Manual verification
After deploy:

Curl each deleted route — expect HTTP 404, no exception logged in Better Stack:

   curl -i https://pg.priority-guard.com/
   curl -i https://pg.priority-guard.com/privacy
   curl -i https://pg.priority-guard.com/terms
   curl -i https://pg.priority-guard.com/clarity

Curl a static asset to confirm the mount still works:

   curl -i https://pg.priority-guard.com/static/pg_logo_icon_128.png

Trigger a Clarity OAuth authorize flow (or render the consent template via local dev) and visually confirm:

Both Privacy Policy and Terms of Service links are present
Both point to fulfilling-productivity.com URLs
Both open in a new tab (target="_blank")


Monitor Better Stack for 24 hours after deploy. Expected: zero http.unhandled_exception events with path=/privacy or path=/terms. Bots will still hit these paths until their crawl indexes refresh — that's expected and harmless (clean 404s, no exceptions).

Compliance and production-readiness

GDPR / data retention: No impact. No user data flows touched. No new processing.
Scalability: Negative impact on resource usage (fewer routes, fewer file reads). No concern.
Latency: Negligible improvement on 404 paths (skip a filesystem stat).
OAuth/OpenID compliance: Unchanged. Discovery endpoints, DCR, consent flows, token endpoints all untouched.
OpenAI App Store / Google OAuth verification: Confirmed externally — both reference Framer URLs, not backend URLs. No re-verification needed.

Out of scope for this increment

Sharpen MCP /privacy-policy and /terms routes in mcp_server/sharpen/server.py:151-211. Sharpen is paused. When Sharpen resumes, audit and harmonize those routes the same way.
MindSort DE consent template — handled in MindSort submission flow.
Focused consent templates (EN/DE) — Focused is deprecated.
Adding client_uri / policy_uri / tos_uri to OAuth provider metadata. The MCP clients (ChatGPT, Claude) currently work without these fields. Adding them is a separate compliance enhancement, not a 500-fix.

Rollback
If anything breaks: git revert the commit. No DB migrations, no infra changes, no schema changes. Pure code-deletion + one HTML template edit.1