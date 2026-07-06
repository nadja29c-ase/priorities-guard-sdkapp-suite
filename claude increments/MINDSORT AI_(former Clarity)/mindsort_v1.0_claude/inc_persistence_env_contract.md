# Increment Briefing: inc_persistence_env_contract (MindSort-Claude + shared clarity persistence)

**Date:** 2026-07-05
**Trigger incident:** Silent persistence failure on MindSort-Claude since first deploy.
**Scope:** Persistence configuration contract, logging truthfulness, config guard hardening, live-suite coverage gap. **ZERO OAuth/discovery/wire changes** — the OAuth surface is verified and locked (ADR_005 + contract tests); nothing in this increment may alter it.

---

## Canonical guidance (read fresh before starting)

Claude-side: `doc/Claude_Compliance/claude_connectors_compliance_master.md`, `doc/Claude_Compliance/structural_guideline_claude_vs_openai.md` (shared-vs-platform layer boundaries — persistence sits in the SHARED layer and this increment touches it).
Shared: `Shared Backend — Architecture, Data Flow, Storage Strategy` (project KB), `Data Retention Strategy` (data-integrity relevance below), `doc/OPERATIONS_PREDEPLOY.md` (before ANY commit), `doc/testing_baseline_2026-07-04.md` (known-red baseline), `CLAUDE.md` rules (hash-verified rounds; briefing constraints binding).
This incident's evidence record: production logs 2026-07-05 07:37–07:47 (persist + retrieve failures with concurrent successful JWKS fetch to www), Render env screenshots, `doc/OAuth/platform_quirk_mindsort_openai_401.md` Evidence Record section (extend it, see D5).

## Root cause (100% confirmed, source + env + logs — do not re-derive)

`mcp_server/clarity/persistence.py` line ~24: `from .config import BACKEND_URL, INTERNAL_API_SECRET` — binds **clarity's** namespace (env `CLARITY_BACKEND_URL`) at import time. The MindSort-Claude Render service sets only `CLARITY_CLAUDE_BACKEND_URL` (correct value, read by nothing in the persistence path); `CLARITY_BACKEND_URL` is absent there → `BACKEND_URL` silently fell to the dev default (`http://localhost:8000`) **in production** → every persist/retrieve since deploy: `All connection attempts failed`. The rebinding shim (`mindsort_claude/mcp_auth_dupl.py`) covers auth globals only — persistence was never in its contract. Failure was masked because `organize_thoughts` logs `auto_persisted` and returns success AFTER `persist_cluster` returns None. Nadja has applied the env hotfix (`CLARITY_BACKEND_URL=https://www.priority-guard.com` on the Claude service) and manually verified the roundtrip — confirm current env/hotfix status with her before assuming.

## Deliverables

### D1 — Resolve the persistence config namespace contract
Requirement (decide the mechanism, don't inherit the accident): on the MindSort-Claude service, the persistence layer's backend URL and internal secret must be **deterministically sourced and fail-fast when absent** — either (a) persistence config sourced from the Claude app's own namespace on that service, or (b) the clarity-env dependency (`CLARITY_BACKEND_URL`, `INTERNAL_API_SECRET`) made explicit: documented in the shim header's rebinding contract as "NOT rebound — must be set per-service," AND guarded so a missing value fails at boot instead of defaulting to localhost.
Mandatory sub-investigation: **why didn't the existing production guards catch this?** Read clarity's config required-env/localhost guard coverage for `CLARITY_BACKEND_URL` under `ENV=production` and state the exact gap (this also feeds D3). Constraint: MindSort-OpenAI runs the same module with `CLARITY_BACKEND_URL` correctly set — its behavior must be byte-identical after this increment. Copy and Adjust, Never Rewrite.

### D2 — Logging and response truthfulness on persist failure
Requirement: when `persist_cluster` returns None, neither logs nor the tool result may claim success. `organize_thoughts` currently logs `auto_persisted` unconditionally after the failure warning — fix. Decide and state (don't bury) whether/how the failure is surfaced in the tool's `structuredContent`/`assistant_guidance` so the model can inform the user their board was NOT saved — remember the lever separation: `assistant_guidance` controls what the model says after the tool fires. `load_saved_board`'s existing honest handling (`persistence_error`) is the reference. Applies to the shared clarity handler → verify the OpenAI twin's behavior stays correct.

### D3 — Promote the clarity config hardening (Codex finding #2, now materialized)
`CLARITY_BACKEND_URL` (and audit the sibling URL vars) must be production-guarded in `clarity/config.py`: required in production ENV, localhost rejected — per the established inc_05b/parity guard pattern. Behavior-neutral for correctly-configured services; both MindSort services must boot post-change (deployer checklist: verify both services' env BEFORE deploy — the Claude service now has the hotfix var; the OpenAI service has had it since day one). This is the increment where "latent, defense-in-depth" became "silent data loss" — say so in the guard's comment.

### D4 — Close the live-suite coverage gap
Requirement: an on-demand, live-marked check that exercises an **authenticated persist + retrieve roundtrip** against production for MindSort-Claude (and optionally the OpenAI twin). This class of failure survived every audit because nothing live ever called a tool with a valid token. Constraints: excluded from default runs (existing `live` marker discipline); token acquisition mechanism is your design (env-provided token, skip-unless-provided, etc.) but must never store or log a token; reference it from `OPERATIONS_PRESUBMISSION.md` if it fits naturally, flag if not.

### D5 — Evidence record + data-integrity note
Extend the incident's evidence into the record (either the existing Evidence Record section or a sibling `doc/OAuth/`-adjacent incident note — follow the established record pattern): root cause, affected window (first Claude-service deploy → 2026-07-05 hotfix), and the data-integrity statement per the Data Retention Strategy: during the window, MindSort-Claude boards were never persisted (nothing stored → nothing to retain/delete; affected user = Nadja only, pre-submission — no external-user exposure). GDPR-relevant framing required, not optional.

## Tests
**Unit:** guard behavior for D1/D3 (subprocess pattern per the established guard-test discipline: missing/localhost `CLARITY_BACKEND_URL` under production ENV fails at boot with named var; correct env imports clean); logging-truthfulness test for D2 (persist failure → no success log/claim — state what bug each test would still pass).
**Integration (live-marked, on-demand):** D4 roundtrip.
**Baseline:** full suite per `doc/testing_baseline_2026-07-04.md` — known-red set unchanged, zero new failures.

## Definition of done
- All five deliverables; every claim hash-verifiable (`git show <hash>:<path>`); round ends with the commit hash.
- Explicit statement of the D1 guard-gap finding (why production guards missed it).
- Both MindSort services boot post-deploy; live suite green; D4 roundtrip demonstrated once against production.
- Explicit list of what was NOT verified.
- Reminder: briefing constraints are binding (CLAUDE.md Rule 0a). Evidence-only sub-items stay evidence-only.
