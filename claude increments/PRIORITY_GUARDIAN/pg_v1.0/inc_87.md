Claude Code Briefing — Verification Audit: /, /privacy, /terms, /clarity Route Dependencies
Purpose
Independent verification of an analysis that concluded these four routes and their static files have no meaningful dependencies in the codebase and can be safely deleted.
This is an audit task. Do NOT make any code changes, do NOT propose fixes, do NOT create any briefings. Read-only investigation only. Report findings.
Background — what was already verified
A previous analysis by another Claude instance read the following files and found references to /, /privacy, /terms, /clarity, index.html, clarity.html, terms.html, or PrivacyPolicy_PGS.html:
FileResultbackend/main.pyDefines the four routes themselves — the only route definitions foundbackend/static/index.htmlLinks to /privacy, /terms, /claritybackend/static/clarity.htmlLinks to /privacy, /termsbackend/static/ directory listingterms.html and PrivacyPolicy_PGS.html do not existbackend/templates/oauth_consent_pg_en.htmlNo reference (uses Framer URLs)backend/templates/oauth_consent_pg_de.htmlNo reference (uses Framer URLs)backend/templates/oauth_consent_mindsort_en.htmlNo reference (uses Framer URLs)backend/templates/oauth_consent_clarity_en.htmlNo reference (uses priority-guard.com/privacy, not local route)backend/templates/oauth_consent_en.html (Focused)No reference (uses priority-guard.com/privacy)backend/templates/oauth_consent_de.html (Focused)No reference (uses priority-guard.com/privacy)backend/core/oauth_provider/discovery.pyNo reference; no policy_uri/tos_uri/client_uri in metadatabackend/core/oauth_provider/mindsort_discovery.pyNo referencebackend/core/oauth_provider/register_client.pyNo reference; DCR response excludes legal URLsmcp_server/priority_guardian/server.pyNo referencemcp_server/priority_guardian/discovery.pyNo referencemcp_server/priority_guardian/widget-react/src/App.tsxNo referencemcp_server/priority_guardian/widget-react/src/constants.tsNo referencepg-inspect.htmlNo referencetests/conftest.pyNo referencetests/integration/conftest.pyNo referenceREADME.mdNo reference
Conclusion of prior analysis: nothing meaningful depends on these routes. The bots hitting /privacy and /terms (causing 9 unhandled 500 exceptions in logs from May 4–6) are following the broken links in static/index.html, which itself is publicly indexed.
What you need to verify
The prior analysis had three explicit gaps that need closing:
Gap 1 — Other Python files in backend/
The prior analysis read backend/main.py and the OAuth provider directory but did not systematically check every Python file in backend/ for references to these routes or static files.
Task: Use grep-style content search across all .py files in backend/ (excluding __pycache__, .venv) for any of:

String literals: "/privacy", "/terms", "/clarity", "index.html", "clarity.html", "terms.html", "PrivacyPolicy_PGS.html"
Path references: static/index.html, static/clarity.html, static/terms.html, static/PrivacyPolicy_PGS.html
Function references: anywhere privacy_policy, terms_of_service, clarity_landing, or root (the function names from main.py) are imported or called

Report every match with file path, line number, and surrounding context. Pay particular attention to:

Health check files
Smoke test files
Any router that might do internal redirects
Celery jobs or background workers that might emit URLs in emails/notifications
Logging or analytics middleware that might log path strings

Gap 2 — Test files
The prior analysis read the two conftest.py files and confirmed no test directory exists named landing/, static/, or legal/, but did not content-grep test files.
Task: Content-search all files under tests/ (recursive) for:

String literals: "/privacy", "/terms", "/clarity", '/' used as a path (be careful — '/' will have many false positives like dict keys; prioritize matches in client.get(...) or httpx.get(...) contexts)
References to the route handler function names: privacy_policy, terms_of_service, clarity_landing
References to the static HTML filenames

Report every match. If any test exercises these routes, that's a real dependency.
Gap 3 — Documentation and ADRs
The prior analysis listed doc/ directory contents but only read README.md. The 4 ADRs, 3 OPERATIONS files, compliance_master_1.3.26.md, openai_uiux_1.3.26.md, openai_widget_impl_guidelines.md, and contents of Claude_Compliance/, OAuth/, clarity_doc/, internal_changelog/, legal/, pg_doc/ were not read.
Task: Content-search all files under doc/ (recursive) for:

The four route paths (/privacy, /terms, /clarity, and root / in URL contexts)
The four static HTML filenames
URL patterns: pg.priority-guard.com/privacy, pg.priority-guard.com/terms, pg.priority-guard.com/clarity, or any documented contract that mentions these endpoints as part of the system's external surface

Report every match. If a compliance doc or ADR documents these as required endpoints, deletion changes the contract.
Bonus — Anything else
Also content-grep:

scripts/ — any deploy/smoke/health scripts that hit these URLs
ops/ — any operational tooling that depends on them
.github/workflows/ if it exists (CI smoke tests)
claude increments/ — any prior briefing that documents these routes as expected

Constraints

Filesystem with spaces: the project root is /Users/nadja/Desktop/Priority Guard Suite/priority-guardian/. Bash cd to this path will fail. Use the filesystem MCP tool's read/search capabilities, or use find from a parent directory with proper quoting.
Read-only: do not modify any file. Do not create any file. Do not propose fixes.
No assumptions: if a file might contain a reference and you cannot read it (binary, too large, permission), report that explicitly. Do not skip and assume "probably no reference".
Distinguish signal from noise: a string '/' in a Python dict literal is not a route reference. A string '/' in a client.get(...) call is. Use context.

Deliverables
A single report with:

Confirmed matches — every file/line that references these routes or static files, with context.
Unread files flagged — anything you couldn't fully scan, with reason.
Verdict — one of:

"Confirmed: no meaningful dependencies. Safe to delete." (if all matches are either the route handlers themselves in main.py, the broken links in the two HTML files, or trivially-replaceable references)
"Found dependencies — DO NOT DELETE without addressing: [list]." (if anything actually depends on these routes)
"Inconclusive: [files that couldn't be checked] need manual review before proceeding."



Do not propose code changes. Do not draft a fix briefing. Just verify and report.
