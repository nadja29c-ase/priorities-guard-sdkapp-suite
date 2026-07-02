# Increment inc_07: MindSort consent-screen routing (/oauth/pg → /oauth/mindsort)

**STATUS: CLOSED — NOT NEEDED. Premise disproven by source verification (the inc_07 gate). Do NOT implement.**

## Why this increment is cancelled

The source-verification gate (required before implementation) disproved the increment's core premise. Verified against backend source this session:

1. **The consent screen is selected by SCOPE, not by route.** `backend/core/oauth_provider/authorize.py::authorize_endpoint` is a single handler for all three routes (`/oauth/{focused,pg,mindsort}/authorize`). It chooses the consent template purely from the requested scope prefix:
   - `clarity.*` → `oauth_consent_mindsort_{lang}.html`, `client_name = "MindSort AI"`
   - `pg.*` → `oauth_consent_pg_{lang}.html`, `client_name = "Priority Guardian"`
   The URL route is irrelevant to branding.
2. **MindSort-Claude requests `clarity.write`** (verified: `mcp_server/mindsort_claude/config.py` `SCOPES_SUPPORTED = ["clarity.write"]`; DCR via `/oauth/pg/register` assigns `clarity.write` per `ROUTE_SCOPE_REGISTRY`).
3. **Therefore MindSort-Claude ALREADY shows the MindSort-branded consent screen**, even though it authenticates via `/oauth/pg`. The original premise ("users authorizing MindSort see the Priority Guardian consent screen") is FALSE — it was an unverified assumption, now disproven.

## Why switching routes would be pure churn (net negative)

All auth-relevant endpoints are route-independent — the same handlers serve all three families (verified):
- **`iss`**: both `discovery.py` and `mindsort_discovery.py` use `settings.OAUTH_ISSUER` (root). Identical. `mindsort_discovery.py` carries an explicit "DO NOT change per app" comment.
- **token / `aud`**: `token_endpoint.py` — one handler stacked on `/oauth/{focused,pg,mindsort}/token`. Route does not change token issuance.
- **JWKS keys**: `jwks.py` — one handler stacked on all three `/jwks` paths, same `get_jwks()`. `/oauth/mindsort/jwks` and `/oauth/pg/jwks` serve identical keys.
- **consent processing / GDPR app-name**: `consent_ui.py` derives app name from scope (`clarity.*` → `mindsort`), route-independent.

Switching MindSort-Claude to `/oauth/mindsort` would change only the advertised `.well-known` paths and `jwks_uri` string — **no user-visible change** (consent already correct), **no token/key change** (same handlers) — while adding the risk surface of an OAuth-route change to a working, connected production connector. Net negative on a stabilization track.

## The only remaining (weak) reason to ever do it

Architectural tidiness: MindSort-OpenAI already advertises `/oauth/mindsort` (confirmed via inc_06 curl). One could argue all MindSort surfaces "should" use the MindSort route for consistency. This is cosmetic-of-cosmetic — it fixes nothing a user or reviewer sees. If ever pursued, treat as a low-priority "consistency" task (NOT a fix), requiring: the same `aud`/JWKS/`iss` verification (now done, all route-independent), a live-connection re-test, and the §0 decision about the in-review ChatGPT server. Not worth an increment during stabilization.

## Disposition
No code change. No tests. inc_07 closed as not-needed. The stabilization track (inc_05 → inc_06 → inc_05b) is complete; consent branding was already correct and required no work.

---

## KNOWN LATENT RISK (surfaced while closing inc_07 — NOT inc_07's job to fix; tracked here so it isn't lost)

**Risk:** silent wrong-consent-screen fallthrough in `backend/core/oauth_provider/authorize.py::authorize_endpoint`.

**Mechanism (verified at source):** the consent template is chosen by a scope-prefix `if/elif/else` chain:
```python
if   any(s.startswith("clarity.") for s in requested_scopes):  # → MindSort AI screen
elif any(s.startswith("pg.")      for s in requested_scopes):  # → Priority Guardian screen
else:                                                          # → Focused screen (catch-all)
```
The `else` is a **fail-open catch-all**: any registered client whose scopes match neither `clarity.` nor `pg.` silently renders the **Focused** consent screen — no error, no log.

**Why it is NOT exposed today:** an upstream guard (`requested_scopes.issubset(allowed_scopes)`) rejects any scope a client wasn't registered with *before* template selection. So the `else` is reached only by a legitimately-registered client whose scopes are non-`clarity`/non-`pg` — which today means exactly Focused (`focused.*`), and Focused→Focused is correct. **There is no active bug now.**

**The actual trigger (when this becomes a real bug):** introducing a NEW app/scope, or **renaming `clarity.*`** (likely someday, since "clarity" is the legacy pre-MindSort name), WITHOUT adding a matching `elif` branch here. That client would be registered with the new scope, pass `issubset`, match neither existing prefix, and silently show the **Focused** branding for a non-Focused app — a consent-integrity defect (the user authorizes "MindSort 2" but sees "Focused"). Consent integrity is exactly what directory reviewers and GDPR care about. The unguarded coupling is: *"every registered non-Focused scope prefix has a matching template branch"* — nothing enforces it.

**Prevention — two levels (both deferred; do NOT inline-edit `authorize.py`, it is shared backend OAuth serving all three live apps on both platforms — any change goes through its own small increment + predeploy discipline):**

1. **Cheap, behavior-neutral, do-first (recommended):** add a WARNING log in the `else` branch when `requested_scopes` contains anything not starting with `focused.` — e.g. `oauth.authorize.consent_template_fallthrough` with the offending scopes. Does NOT change behavior (still renders Focused); converts the silent wrong-screen into a Better Stack signal the first time it ever happens. Few lines, cannot break anything (log-only). This is the inc_05b fail-loud principle applied to consent selection.
2. **Correct end-state, small risk, deliberate:** replace the bare `else → Focused` with explicit known-prefix handling — render Focused only for `focused.*`; for scopes matching NO known app prefix, raise/error rather than silently defaulting. Makes a forgotten-branch misconfiguration impossible to ship unnoticed (fail-closed). Needs a test pass (confirm nothing legitimate relies on the current catch-all) — not a blind edit.

**Recommended disposition:** do (1) as a tiny standalone backend increment whenever convenient; treat (2) as a required step in whatever future increment introduces a new app scope or renames `clarity.*` — that is precisely when the guard earns its keep. Until then, this is a documented latent risk, not an active defect.

---

## [SUPERSEDED — original briefing below, premise disproven above]

# Increment inc_07: MindSort consent-screen routing (/oauth/pg → /oauth/mindsort)

**Status:** DEFERRED — pre-submission, NOT pre-test. Do NOT start until inc_05 has produced a SUCCESSFUL Claude connection. This is branding/consent correctness, not connection unblocking. Bundling it with the AS fix destroys diagnosability.

**Problem:** MindSort-Claude authenticates via `/oauth/pg/*`, so a user authorizing MindSort sees the **Priority Guardian** consent screen. The backend already has a purpose-built MindSort AS — `backend/core/oauth_provider/mindsort_discovery.py` (`/oauth/mindsort/*`), MindSort-branded consent templates (`backend/templates/oauth_consent_mindsort_{de,en}.html`), and `/oauth/mindsort/register` granting `clarity.write` — currently unused by the Claude connector.

**This is the SHARED concern, unlike inc_05.** inc_05 was safe to fix Claude-only because it lived in the platform-coupled `_dupl` discovery file. Switching the OAuth *route* is different: it changes which AS the connector uses, and to keep Canonical Product Rule §0 (Claude and ChatGPT MindSort behave consistently), the ChatGPT MindSort server's route must be considered in the same decision. This needs a PRODUCT DECISION before implementation:

- **Option A:** switch BOTH platforms (Claude + ChatGPT MindSort) to `/oauth/mindsort` together — consistent, correct branding everywhere, but touches the in-review ChatGPT `clarity/` server (do not do this while OpenAI review is open).
- **Option B:** switch Claude to `/oauth/mindsort`, leave ChatGPT on `/oauth/pg`, document the divergence as deliberate (platform-coupled, like other `_dupl` divergences). Lower blast radius; accepts temporary inconsistency.

Nadja decides A vs B. Do not let an implementer choose.

## Pre-work before this is briefable for implementation (verify at source, do not assume)
1. Confirm switching MindSort-Claude's `OAUTH_ISSUER_URL` to `…/oauth/mindsort` needs NO backend change (the routes already exist — `mindsort_discovery.py`, `/oauth/mindsort/register` in `register_client.py`'s decorators, `mindsort` in `ROUTE_SCOPE_REGISTRY`). Verify.
2. Confirm JWT `iss`/`aud` and scope (`clarity.write`) are IDENTICAL across `/oauth/pg` and `/oauth/mindsort` (same signer, same issuer claim). If they differ, MindSort's `CLARITY_ISSUER`/`CLARITY_AUDIENCE` validation could break — verify before switching.
3. Confirm the `/oauth/mindsort/register` redirect-URI allowlist is the same shared `settings.OAUTH_ALLOWED_REDIRECT_URIS` (it is — `register_client.py` uses one allowlist for all routes — so the Claude URIs already apply to the mindsort route). Re-confirm.
4. Confirm the MindSort consent templates render correctly and are wired to the `/oauth/mindsort/authorize` consent flow.

## Likely change surface (once decided, Option B)
- MindSort-Claude `config.py`: `OAUTH_ISSUER_URL` default/env → `…/oauth/mindsort`; `CLARITY_JWKS_URL` → `…/oauth/mindsort/jwks` (if the mindsort AS serves its own jwks — verify it isn't shared).
- `discovery_dupl.py`: endpoints rebuild from the new `OAUTH_ISSUER_URL` automatically; `authorization_servers` stays root (`CLARITY_ISSUER`/`OAUTH_ISSUER_BASE`) — unchanged by the route switch.
- Render env: update `CLARITY_CLAUDE_OAUTH_ISSUER_URL` (and JWKS if applicable).
- Tests: discovery endpoints now `/oauth/mindsort/*`; issuer still root; an integration check that the MindSort consent screen (not PG's) renders.

## Sequencing
Run order: inc_05 (connect) → inc_06 (verify no OpenAI collateral) → inc_05b (harden) → inc_07 (this, consent branding). Each independently deployable and rollback-able. Never bundle inc_07 with inc_05 — one variable at a time, especially on the OAuth surface.

## Do NOT
- Do not start until inc_05 connection is confirmed.
- Do not pick Option A vs B as the implementer.
- Do not touch `clarity/` while OpenAI review is open (rules out Option A for now regardless).
