Claude Code Briefing: Pin Python Runtime Version
Context
The repo has no Python runtime pin. Render build logs confirm the service is currently running Python 3.13 (wheels installing with cp313 ABI tag — e.g. sqlalchemy-2.0.44-cp313-cp313-manylinux..., uvloop-0.22.1-cp313-cp313-manylinux...). This matches Render's documented default of 3.13.4 for services created between 2025-06-12 and 2026-02-11.
No PYTHON_VERSION env var is set on the service, and no .python-version file exists in the repo. Production is running on Render's default, which Render can change unilaterally on newly-created services (current default for new services since 2026-02-11 is 3.14.3).
pyproject.toml declares python = "^3.11" (i.e. >=3.11, <4.0) — this is a Poetry floor constraint only, satisfied by 3.13. It does not pin the interpreter Render chooses.
Local .venv is Python 3.13.7.
Goal
Single-line change: add a Python runtime pin at the repo root so Render locks to the interpreter the app is already successfully running on, eliminating drift risk and aligning local + prod on the same version.
Implementation Approach — Copy and Adjust, Never Rewrite
Create exactly one new file. Do not modify pyproject.toml, requirements_fullbackend.txt, alembic.ini, CI config, or any other file. Do not rewrite, restructure, or "improve" anything not explicitly listed below.
Pre-Check (Human Executes Before Commit)
Before this file is committed, the human must verify the Render service does not have a PYTHON_VERSION env var set. Render precedence is: PYTHON_VERSION env var → .python-version file. If the env var exists, the new file will be silently ignored.
Steps:

Render Dashboard → priority-guardian service → Environment tab.
Confirm no key named PYTHON_VERSION exists.
If it exists: delete it (preferred — keeps source of truth in the repo). Do not proceed with this increment until confirmed.

File to Create
Path: /Users/nadja/Desktop/Priority Guard Suite/priority-guardian/.python-version
Contents (exact, single line, trailing newline):
3.13.7
That is the entire file. No comments, no extra whitespace, no BOM.
Why 3.13.7 specifically

Render is already running Python 3.13 (build log evidence: cp313 wheel ABI tags). Pinning to 3.13.x means locking current state, not changing versions — zero risk of dependency reinstall surprises.
3.13.7 matches the local .venv, eliminating local/prod drift in the same change.
Inside the pyproject.toml ^3.11 constraint — no pyproject edit needed.
Alternative 3.13.4 (Render's documented default for this service's creation window) is also valid but leaves a minor local/prod mismatch. 3.13.7 is strictly better.

Render reads .python-version and uses it as the interpreter version for Python services. See: https://render.com/docs/python-version
Verification Steps (local, before commit)

Confirm the file exists at the repo root (same level as pyproject.toml, poetry.lock, README.md):

bash   ls -la .python-version
   cat .python-version
Expected output: 3.13.7 followed by a newline. File size should be 7 bytes.

Confirm the file is not accidentally gitignored:

bash   git check-ignore .python-version
Expected: no output (file is tracked).

Confirm no other runtime pin files exist that could conflict:

bash   ls runtime.txt render.yaml 2>/dev/null
Expected: both return "No such file or directory".
Unit Tests
None required. This is a build-configuration file with no runtime behavior.
Integration Tests
None required in this increment. Verification happens at next Render deploy (see Deployment Verification below).
Deployment Verification (post-deploy, human executes)
Before deploying: read OPERATIONS_PREDEPLOY.md for the standard pre-deploy checklist (Alembic head check, OAuth discovery sanity check, env var verification).
After the first deploy with this change:

In Render dashboard → priority-guardian service → latest deploy → Logs → Build phase. Look for a line similar to:

   ==> Using Python version 3.13.7 (default)
or:
   ==> Requesting Python version 3.13.7
Confirm the version shown matches 3.13.7 exactly.

Cross-check: wheel filenames should still show cp313 ABI tags (e.g. sqlalchemy-2.0.44-cp313-cp313-...). If the tag changes (e.g. to cp311 or cp314), the pin is not being honored — flag to human.
If Render reports a different version or warns the version is unavailable: do not proceed. Flag to human. Likely causes: a PYTHON_VERSION env var is still set and overriding the file, or Render's supported version list has changed.
Smoke-check: hit /health on the deployed service and confirm 200 response. No behavior change is expected — the interpreter version is unchanged (3.13.x → 3.13.7), only the precision of the pin is new.

Out of Scope — Do Not Touch

pyproject.toml (the python = "^3.11" declaration stays as-is; it's a Poetry floor and 3.13.7 satisfies it)
poetry.lock
requirements_fullbackend.txt
.venv/ (already on 3.13.7 — no change needed)
CI configuration
Any code under backend/, mcp_server/, or tests/
The Celery asyncio.get_event_loop() pattern (confirmed working on 3.13 — no action needed)

Commit Message
chore: pin Python runtime to 3.13.7

Adds .python-version at repo root to lock Render to the Python 3.13
version the service is already running (confirmed via cp313 wheel ABI
tags in build logs). Aligns with local .venv (3.13.7). Prevents silent
drift when Render updates default Python versions for new services.

No runtime behavior change — pinning current state.

What's different from the previous briefing

Version: 3.11.9 → 3.13.7. Evidence showed prod is already on 3.13. Pinning to 3.11 would have been a downgrade, not a lock.
"Flag to Human" section removed. The local/prod mismatch resolves itself — 3.13.7 matches both.
Pre-Check section added. Render env var precedence means a lingering PYTHON_VERSION would silently void the whole increment. Worth 30 seconds of dashboard verification before commit.
Verification upgraded. Added the cp313 ABI tag cross-check — direct evidence the pin is honored, not just what Render's log string claims.

Ship it.