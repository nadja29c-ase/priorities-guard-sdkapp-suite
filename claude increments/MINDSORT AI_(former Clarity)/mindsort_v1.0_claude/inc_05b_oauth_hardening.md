# Increment MindSort-Claude-OAuth-Hardening (inc_05b): structural parity with PG

**Status:** DEFERRED — do NOT start until inc_05 is deployed AND the MindSort connector has SUCCESSFULLY connected in a real Claude session. This hardens a *confirmed* fix; it is pointless (and adds risk) before the root-issuer fix is proven.

**Purpose:** Bring MindSort-Claude's OAuth config to structural parity with the proven PG-Claude reference: a dedicated root-issuer config value plus PG's same-origin fail-fast guard. This is not a bug fix — inc_05 already fixed the bug. This removes the *latent* fragility that the bug came from: a single config value (`CLARITY_ISSUER`) now serving two semantic roles (JWT `iss` validation AND discovery `authorization_servers`), with no guard preventing future issuer/endpoint origin drift.

**Why this is worth doing (not optional polish):** the original defect existed because `OAUTH_ISSUER_URL` was overloaded for both endpoint construction and `authorization_servers`. inc_05 fixes the symptom by reusing `CLARITY_ISSUER`, but that re-creates a milder version of the same overloading. PG avoided this with TWO explicit values (`OAUTH_ISSUER_BASE` for issuer/authorization_servers, `OAUTH_ISSUER_URL` for endpoints) AND a startup guard asserting they share an origin. That guard is the safety net that would have caught the original bug class at deploy time. Without it, MindSort stays one careless edit away from a silent OAuth break, and the two Claude connectors (PG, MindSort) stay structurally divergent — extra cognitive load when maintaining both.

**Scope:** ONLY `mcp_server/mindsort_claude/config.py` + `discovery_dupl.py` + that service's tests. NO backend, NO clarity/, NO OpenAI code. Roll independently.

---

## Canonical guidance + reference
- Read fresh: `claude_connectors_compliance_master.md`, `structural_guideline_claude_vs_openai_MindSortAI.md`, `OPERATIONS_PREDEPLOY.md`.
- **Mirror exactly:** `mcp_server/priority_guardian_claude/config.py` — the `OAUTH_ISSUER_BASE` block, the same-origin fail-fast guard (the `urlparse` origin-tuple comparison with the explicit "startswith is insufficient" comment), and the localhost-in-production guard.

### Source-verified specifics (confirmed against PG config.py this session — copy this exact shape)
- `from urllib.parse import urlparse` is imported at the top of PG's config (MindSort's config does NOT currently import it — add the import).
- `OAUTH_ISSUER_BASE` uses `get_env("...OAUTH_ISSUER_BASE", default="http://localhost:8000")` — NOT `required=True`. The localhost-in-prod guard is what enforces it in production; the localhost default keeps dev working. Do not set `required=True` (it would break the local dev default).
- The same-origin guard is placed at **module load, immediately after both `OAUTH_ISSUER_URL` and `OAUTH_ISSUER_BASE` are defined** — not inside a function. It uses module-level temporaries (`_base_parsed`, `_url_parsed`) and compares `(scheme, netloc)` tuples.
- The localhost-in-prod guard comes immediately after the same-origin guard.
- PG checks `ENV in ("production", "prod", "staging")`. MindSort's existing guards (e.g. CORS) check `ENV in ("production", "staging")` — note the discrepancy and match MindSort's EXISTING convention for consistency within the file, OR align both; flag which you chose. Do not silently introduce a third variant.
- Only adaptation from PG: env-var prefix `PG_CLAUDE_*` → `CLARITY_CLAUDE_*` in the var name and the RuntimeError messages.

---

## Required change (Copy and Adjust, Never Rewrite)

### 1. `config.py`
- Add `OAUTH_ISSUER_BASE`, read from env `CLARITY_CLAUDE_OAUTH_ISSUER_BASE`, dev default `http://localhost:8000`, production value `https://www.priority-guard.com`. Copy PG's variable + comment semantics ("root domain; used for issuer + authorization_servers; do NOT derive from OAUTH_ISSUER_URL — define explicitly to avoid path-change fragility").
- Copy PG's **same-origin fail-fast guard** verbatim: `urlparse` both `OAUTH_ISSUER_URL` and `OAUTH_ISSUER_BASE`, compare `(scheme, netloc)` tuples, raise `RuntimeError` on mismatch. Do NOT use `startswith` (PG's comment explains why: `https://www.example.com.evil.com` startswith `https://www.example.com`). Adjust only the env-var names in the message to `CLARITY_CLAUDE_*`.
- Copy PG's localhost-in-production guard for `OAUTH_ISSUER_BASE` (raise if `localhost` in value and `ENV` in production/staging).
- Keep `CLARITY_ISSUER` and `OAUTH_ISSUER_URL` as-is. Add a comment noting `CLARITY_ISSUER` (JWT `iss` validation) and `OAUTH_ISSUER_BASE` (discovery advertisement) hold the same production value but serve different roles — keep both, do not merge.

### 2. `discovery_dupl.py`
- Change `oauth_protected_resource()` `authorization_servers` from `[CLARITY_ISSUER]` (inc_05's value) to `[OAUTH_ISSUER_BASE]`. Functionally identical in production (both root), but semantically correct: `authorization_servers` is a discovery concern, not a JWT-validation concern.
- Update the fix-record comment to note the hardening landed and the value now comes from the dedicated discovery var.

### 3. Render env (deployer; state in DoD)
- Add `CLARITY_CLAUDE_OAUTH_ISSUER_BASE=https://www.priority-guard.com` to the MindSort Claude MCP service BEFORE redeploy. Without it, the localhost-in-prod guard correctly fails startup (intended fail-fast — the var is now required in production).

---

## Tests (in addition to inc_05's, which must still pass)
1. **Same-origin guard RAISES on differing origins** — `OAUTH_ISSUER_BASE` and `OAUTH_ISSUER_URL` set to different origins → `RuntimeError`. *Catches:* a no-op guard (e.g. `startswith`).
2. **Same-origin guard PASSES the legitimate pairing** — `base=https://www.priority-guard.com`, `url=https://www.priority-guard.com/oauth/pg` → does NOT raise. *Catches:* an over-strict guard that rejects same-origin-different-path, which would break the real config — this is the critical asymmetry the guard must get right.
3. **localhost-in-prod guard** — `OAUTH_ISSUER_BASE` containing localhost + `ENV=production` → raises. *Catches:* guard not wired to ENV.
4. **`authorization_servers` now sourced from `OAUTH_ISSUER_BASE`** and still root (no path). *Catches:* leaving inc_05's `CLARITY_ISSUER` reference (functionally fine, but defeats the semantic separation this increment exists for).

State for each what bug would still pass it.

## Definition of Done
- [ ] `config.py`: `OAUTH_ISSUER_BASE` added; same-origin guard + localhost-prod guard copied from PG; `CLARITY_ISSUER`/`OAUTH_ISSUER_URL` untouched; dual-role comment added.
- [ ] `discovery_dupl.py`: `authorization_servers` sourced from `OAUTH_ISSUER_BASE`; comment updated.
- [ ] inc_05 tests still pass; new guard tests 1–4 pass.
- [ ] Full `pytest tests/unit/ --ignore=tests/unit/mcp_focused -q`: baseline unchanged.
- [ ] Deployer sets `CLARITY_CLAUDE_OAUTH_ISSUER_BASE` BEFORE redeploy.
- [ ] Post-deploy: re-run the inc_05 discovery curls — `authorization_servers[0]` still root; connection still works (delete+re-add connector, retry). The hardening must be a no-op on observable behavior — if the connection breaks, the guard or env var is misconfigured.
- [ ] Read OPERATIONS_PREDEPLOY before commit; update the MindSort runbook env-var table to add `CLARITY_CLAUDE_OAUTH_ISSUER_BASE` as required.

## Note
This increment must be observably behavior-neutral (same discovery output as inc_05). Its entire value is the fail-fast guard + semantic separation. If a reviewer can't articulate what future bug the guard prevents, re-read the original AS-mismatch defect — that is the bug it prevents.

---

# ADDENDUM (inc_05b-fix): close two adversarial-review findings

The initial inc_05b implementation passed review but a follow-up Codex review + a second Claude review found two real gaps. Both are confirmed against the implemented `config.py`. Address both before inc_05b is considered closed. Scope unchanged: ONLY `mcp_server/mindsort_claude/config.py` + tests.

## Context: deployed ENV is `production` (confirmed)
The live MindSort Claude MCP service runs `ENV=production`, so Finding 1 is a **latent trap**, not an active production bypass — but one typo (`ENV=prod`) or one new deployment using the `prod` alias springs it. Fix anyway: this increment exists to make misconfiguration fail fast, and a guard that silently no-ops under a common ENV alias is worse than no guard (false confidence).

## Finding 1 (high): file-wide `ENV` convention lets `ENV=prod` bypass every production guard
**Confirmed in code:** all three prod-gated checks — the localhost guard, the CORS-required guard, and `get_env(required=True)` — use `ENV in ("production", "staging")`. None includes the common alias `"prod"`. With `ENV=prod`: localhost guard skipped; CORS-required skipped; if OAuth env vars are also unset, both `OAUTH_ISSUER_BASE` and `OAUTH_ISSUER_URL` default to `localhost:8000` → same origin → same-origin guard passes → **service boots in production advertising localhost discovery values.**

### Required fix — one canonical ENV predicate, used everywhere
- Define a module-level helper `_is_production_env(env: str) -> bool` returning `env in {"production", "prod", "staging"}`.
- **Placement (critical — file executes top-to-bottom at import):** define `_is_production_env` **immediately after** `ENV = os.getenv("ENV", "dev")` and **before** `get_env` is defined, because `get_env` will call it. Getting placement wrong → `NameError` at import.
- Replace the prod check inside `get_env` (`if ENV in ("production", "staging")`) with `if _is_production_env(ENV)`.
- Replace the localhost-in-prod guard's `ENV in ("production", "staging")` with `_is_production_env(ENV)`.
- Replace the CORS-required guard's `ENV in ("production", "staging")` with `_is_production_env(ENV)`.
- **Raise-on-unknown-ENV (defense in depth):** after computing `ENV`, if `ENV` is neither a known production value nor a known dev/test value, raise `RuntimeError`. Known dev/test set MUST cover everything the dev + CI + test harness uses. MindSort's existing `IS_DEV` uses `{"dev", "development", "local"}` — **extend the known set to also include `"test"` and `"ci"`** to avoid breaking any test/CI run that sets those. Before finalizing, GREP the repo + CI config for `ENV=` / `setenv("ENV"` / `monkeypatch.setenv("ENV"` and confirm no value outside `{production,prod,staging,dev,development,local,test,ci}` is used. If one is, add it to the known set — do NOT let raise-on-unknown break the suite. **Flag what you found in the grep.**
- Keep `IS_DEV` consistent: redefine it as `not _is_production_env(ENV)` OR as membership in the dev set — pick one and ensure it doesn't contradict the prod predicate (no ENV value should be both).

**Why file-wide, not just the OAuth guard:** fixing only the localhost guard leaves CORS + `required=` still bypassable by `ENV=prod` — inconsistent and still latent. The canonical predicate documents the convention in one place and closes the whole class. (Nadja approved this wider scope explicitly.)

## Finding 2 (medium): same-origin guard doesn't enforce that `OAUTH_ISSUER_BASE` is an exact root issuer
**Confirmed in code:** the guard compares only `(scheme, netloc)`. So `OAUTH_ISSUER_BASE = https://www.priority-guard.com/` (trailing slash) or `https://www.priority-guard.com/oauth/pg` (path) shares origin with `OAUTH_ISSUER_URL` and PASSES the guard — but makes `authorization_servers[0]` non-root, reintroducing the exact Claude DCR discovery mismatch inc_05 fixed. The guard protects origin but not issuer *shape*.

### Required fix — normalize + reject non-root shape on `OAUTH_ISSUER_BASE`
- `.rstrip("/")` on `OAUTH_ISSUER_BASE` at definition (mirror the existing `MCP_SERVER_URL` / `BACKEND_URL` pattern). This handles the trailing-slash case.
- After `urlparse(OAUTH_ISSUER_BASE)`, **reject any non-empty `path` (beyond `""`/`"/"`), `query`, or `fragment`** with a `RuntimeError`. This handles the `/oauth/pg` and `?x=`/`#x` cases. The rstrip alone is insufficient — it removes a trailing slash but not a real path segment.
- Message must name the var and show the offending value, consistent with the other guards.
- Place this validation with the other `OAUTH_ISSUER_BASE` guards (after definition, near the same-origin guard). Order: rstrip at definition → shape-rejection guard → same-origin guard → localhost guard. (Shape-reject before same-origin is fine either way, but keep it adjacent and deterministic.)

## Tests to add (each with "what bug would still pass it?")
All guard tests use the established subprocess technique (fresh interpreter + controlled `env`), and MUST assert on stderr substring (not just returncode) so a `ModuleNotFoundError` can't pass them for the wrong reason — same discipline as the existing guard tests.

5. **`ENV=prod` + default/unset OAuth env → MUST raise** (the exact Finding-1 bypass). Assert returncode≠0 AND stderr names the localhost guard (or whichever fires first under `prod` now that the predicate includes it). *Catches:* the `prod` alias still being treated as non-prod.
6. **`ENV=produciton` (typo) → MUST raise** with an "unknown ENV" message. *Catches:* raise-on-unknown-ENV being absent or not wired. Without this test the defense-in-depth is unverified.
7. **`OAUTH_ISSUER_BASE=https://www.priority-guard.com/oauth/pg` (path) → MUST raise** with a path-rejection message, `ENV=dev` so only the shape guard can fire. *Catches:* Finding 2's path case — guard that checks origin but not shape.
8. **`OAUTH_ISSUER_BASE=https://www.priority-guard.com/` (trailing slash) → MUST NOT raise, and `authorization_servers[0] == https://www.priority-guard.com` exactly** (rstrip normalized it). *Catches:* rstrip missing → trailing slash leaks into the advertised value.
9. **Full production env (all vars set correctly, `ENV=production`) → imports clean AND `authorization_servers[0]` equals exactly `https://www.priority-guard.com`** (root, no slash, no path). *Catches:* any guard false-positive on the real deployed combination; proves Finding 2's positive case end-to-end. (This extends the existing prod-happy-path test to assert the exact root value, not just clean import.)
- Confirm `ENV=test`/`ci` (if used by the harness) still import clean — see the Finding 1 grep. If the harness uses neither, state that.

## Addendum Definition of Done
- [ ] `_is_production_env` helper defined before `get_env`; used in `get_env`, localhost guard, CORS guard.
- [ ] Raise-on-unknown-ENV added; known dev/test set covers everything the grep found; grep result stated.
- [ ] `OAUTH_ISSUER_BASE` rstrip'd + non-empty path/query/fragment rejected.
- [ ] Tests 5–9 added and passing; existing inc_05/inc_05b tests still pass; all guard tests assert on stderr substring.
- [ ] Full `pytest tests/unit/ --ignore=tests/unit/mcp_focused -q`: known-5 baseline unchanged.
- [ ] Behavior-neutral on the deployed config: `ENV=production` + correct vars still boots and still advertises exactly the root `authorization_servers`. (The fix only ADDS failure modes for MISconfiguration; the correct config is unaffected.)
- [ ] No change outside `config.py` + tests. (`discovery_dupl.py` already correct from inc_05b; do not touch.)
