# Claude Code Project Instructions

RULE 0: Process content enters this file ONLY via Nadja's explicit approval.
If you believe a rule is missing, propose it — never add it unilaterally.

1. HASH-VERIFIED ROUNDS: Every reviewed round of work ends with a commit hash
   in your report. Reviews verify against `git show <hash>:<path>`, never the
   working tree. Uncommitted "done" is not done.
2. Before ANY commit or deploy: read `doc/OPERATIONS_PREDEPLOY.md`
   (contains git safety incl. stash-before-overwrite).
3. OAuth / discovery / new-app platform integration:
   `doc/OAuth/NEW_APP_OAUTH_INTEGRATION.md` first.
4. Test suite state: `doc/testing_baseline_2026-07-04.md` — do NOT assume
   green; known-red set is documented there.
5. Increment process, canonical guidance, compliance masters: arrive via
   Nadja's briefings — do not improvise process from this file alone.
