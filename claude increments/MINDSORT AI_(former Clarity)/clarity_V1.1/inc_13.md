Increment Briefing: MindSort — Fix Unclustered Min-2 Validator Contradiction (rev. 3 — FINAL)
App: MindSort AI (ChatGPT SDK app; fix propagates to MindSort-Claude via shared tool registry)
Scope: Bug fix, single file + tests. Independently rollable.
Severity: Production bug — organize_thoughts fails with a generic "Invalid input format" error whenever exactly one item total lands in the Unclustered cluster (single orphaned item, no pre-existing Unclustered with other items). This is a common payload shape.

1. Context & Root Cause
Production incident 2026-07-20 (~16:49 UTC, mindsort-mcp on Render). Root cause strongly evidenced from production logs + working-tree source (the Pydantic error input in the incident log is byte-identical to the dict literal the repair code constructs):

Model sent a cluster ("Operations") with exactly 1 thought_item.
The pre-validation single-item repair in mcp_server/clarity/tools/organize_thoughts.py correctly removed it and placed the orphaned item into a new Unclustered cluster — as documented in the tool's own input schema: "If only 1 item exists, the server will place it in Unclustered automatically."
ClusterInput.validate_cluster then rejected the repair's own output, because the min-2-items rule has no exemption for Unclustered.
The post-validation fallback repair block handles only invalid tags, raw-string cluster lists, and a content field. It cannot repair min-cardinality violations → clusters_data is None → generic build_invalid_params_error("Invalid input format", "Expected 'clusters' array with cluster objects").

Pre-implementation verification step (required, before writing any code):
Identify the currently deployed revision of mindsort-mcp (Render deploy → commit SHA; ask Nadja if you cannot access Render). Run git show <deployed-sha>:mcp_server/clarity/tools/organize_thoughts.py and diff against the working tree. Record the result in your report. If it matches: root cause is confirmed at deployment level. If the deployed revision cannot be identified: record root cause as "strongly evidenced, deployment provenance unverified" and proceed — the contradiction exists in the source that ships next regardless.
Design verdict: Three artifacts agree that a one-item Unclustered is intended (schema description, repair implementation, repair code comment). The validator is the outlier. Align the validator with the documented Unclustered semantics. Do NOT patch the fallback repair block, and do NOT change the repair logic.

2. Required Changes
Change A (the fix): In ClusterInput.validate_cluster, the min-2 thought_items rule must not apply to the cluster named Unclustered. All other cluster invariants (non-empty, tag limits, tag whitelist) still apply to Unclustered. The min-2 rule remains fully enforced for every other cluster name. The subcluster min-2 rule is untouched.
Change B (observability): For the failure path where validation failed and no repair strategy applied (clusters_data is None), the log emission must be exactly:

event: organize_thoughts.repair_failed (unchanged — preserves the existing event taxonomy)
reason: no_applicable_repair (replaces the inaccurate unrecognized_format; accurate for both the validation-failed case and the genuinely-unrecognizable-payload case — do NOT add shape-classification logic to distinguish them; the preceding validation_failed_attempt_repair line already carries the full Pydantic error details for disambiguation)
additional field: validation_error_type = the unique Pydantic error type values from e.errors() as a list (e.g. ["value_error"]). The ValidationError e is in scope at this log site — extraction is a read of existing metadata, no restructuring.
The reason=revalidation_failed emission on the second repair path is untouched.

No other log emissions change. No behavior change beyond the log fields.
Explicitly out of scope: the fallback repair block's capabilities, the repair logic itself, edit_board, _dupl files, the stale organize_thoughts_v2.cpython-313.pyc (separate repo-hygiene task), widget code, the pre-existing verbatim thought-content logging in repair_single_item_cluster (separate GDPR/retention backlog item — do not touch it here).

3. Cross-Platform Note (critical)
mindsort_claude/handlers/tools_dupl.py dispatches via from mcp_server.clarity.tools import get_tool — the Claude variant executes the same handler. This fix therefore covers both platforms' code paths with zero _dupl changes. Your report must confirm no _dupl file was touched and state this reasoning.
Code propagation ≠ platform verification: ChatGPT and Claude have separate hosts, auth paths, and request envelopes. Platform runtime verification is handled in the operator checklist (§8), not by you. MindSort-Claude runtime verification is pending until that surface is live (currently blocked pre-submission).

4. Implementation Approach — Copy and Adjust, Never Rewrite

Modify only the validator condition (Change A) and the specified log fields (Change B) in mcp_server/clarity/tools/organize_thoughts.py.
Do not rewrite, restructure, reorder, or "improve" anything not explicitly listed — including docstrings, the schema description, error messages, the repair block, or the DESCRIPTION constant.
If while implementing you believe something adjacent is also wrong, flag it in your report; do not fix it.
After editing, verify the changes stuck (re-read the file).


5. Test Instructions
Unit tests (validator + repair path, no server, no DB)

One orphan, no existing Unclustered (the incident): payload with one single-item cluster among valid clusters → repair produces one-item Unclustered → validation passes → handler proceeds past validation.
One orphan, existing Unclustered with items: orphan merges into existing Unclustered; validation passes.
Multiple orphans, no existing Unclustered: all orphans land in Unclustered (≥2 items); passes (regression guard for the currently working path).
Model-supplied Unclustered with exactly 1 item, no repair involved: passes validation (exemption applies regardless of how the cluster arose).
Ordinary named cluster with 1 item that bypasses repair (constructed ClusterInput directly): still fails validation — the min-2 rule is not weakened globally.
Change B log assertion: a validation failure with no applicable repair emits organize_thoughts.repair_failed with reason=no_applicable_repair and a populated validation_error_type list.

For every test, state in your report what bug would still pass it.
Integration tests (full handle() round-trip)

Full organize_thoughts.handle() with the incident payload shape (valid provenance fields + one single-item cluster): assert non-error result, structuredContent.clusters contains Unclustered with the orphaned item, persistence invoked. Mock persist_cluster. No DB schema change in this increment → no new DB integrity tests required; state this explicitly.
Negative round-trip: payload with genuinely no recognizable clusters still returns the invalid-params error, now logging reason=no_applicable_repair (fallback behavior otherwise unchanged).


6. Canonical Guidance & Operations

Consult ADR_MCP Server implementation standard.md for structured-logging and error-response conventions before implementing Change B; if it conflicts with the spec above, flag before proceeding.
Shared Backend Architecture doc: no data-flow or storage changes; confirm in report.
Before committing: read OPERATIONS_PREDEPLOY.md (and any other relevant OPERATIONS…md); list in your report which tasks apply and which you performed.
If any referenced doc is unreachable or contradicts the code, flag it — do not silently proceed.
If you cannot access Render, git remotes, or anything else needed for §1's deployed-revision check, say so explicitly and tell Nadja what to run — do not skip silently.


7. Production-Readiness (increment scope)

Performance: confirm the diff introduces no new I/O and no new dependencies. Runtime timing is already emitted per-call (tool.timing / tool_ms); post-deploy comparison happens via the operator checklist, not new instrumentation.
GDPR / Data Retention — confirm all four in your report:

no additional payload contents are logged by this diff;
no retention period changes;
no cross-app data access changes;
no new processor or data transfer.


Submission-window safety: MindSort-OpenAI is live; MindSort-Claude is pre-submission. Confirm nothing in the diff touches discovery shapes protected by ADR_005 contract tests.

Successful completion of the operator checklist (§8) establishes deployment readiness for this bug-fix increment — not product-level production readiness under load.

8. Operator Post-Deploy Checklist (Nadja — not Claude Code)
Run after manual deploy to Render:

Record deployed commit SHA and the rollback revision (previous deploy SHA).
⚠️ Use your own test account only — organize_thoughts auto-persists and destructively overwrites the saved board, no undo. Do not run the incident payload against any account whose board matters.
Replay the incident payload shape (one single-item cluster among valid clusters) via ChatGPT Developer Mode → expect a successful board render.
Check Better Stack logs for the expected sequence: repair_single_item_cluster → validation_success — and the absence of validation_failed_attempt_repair and repair_failed for that call.
Confirm the persisted board contains the orphaned item under Unclustered (load_saved_board).
Run one normal multi-cluster call (no single-item clusters) → success, unchanged behavior.
Glance at tool_ms in timing logs vs. pre-deploy baseline (~2ms) — no anomaly expected.
Mark Claude runtime verification: pending until MindSort-Claude is live; add this incident payload to the Claude submission test plan.


9. Report Requirements

Commit hash — review runs against git show <hash>:<path>, not the working tree. No hash, no review.
Deployed-revision diff result from §1 (or explicit statement it couldn't be obtained and why).
Diff summary (files touched must be exactly: organize_thoughts.py + test files).
Per-test statement of what bug would still pass it.
Explicit list of what you did NOT verify.
Confirmations: no _dupl changes, no schema/DESCRIPTION changes, no discovery-shape changes, the four GDPR points, OPERATIONS_PREDEPLOY tasks checked.


Backlog items created by this incident (separate, do not action here):

Verbatim user thought content in info-level logs (repair_single_item_cluster) — check against Data Retention Strategy diagnostic-data rules.
Stale organize_thoughts_v2.cpython-313.pyc with no source — repo hygiene.


 Next touchpoint: adversarial review of the implementation against the commit hash.