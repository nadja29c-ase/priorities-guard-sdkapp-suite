Anthropic/Claude: COMPLIANCE FOR CONNECTORS
Last updated: 2026-08-04 — **round 1 (re-fetch + extract) complete on 3 of 10 source pages:** `mcp-apps/design-guidelines`, `building/authentication`, `mcp-apps/transparent-theming`. **Partially refreshed:** the remaining seven (review-criteria, submission, software_directory_policy, troubleshooting, external-links, instance-supersession, cross-compatibility) were last verified 2026-06-23 and are NOT yet re-checked. Treat sections sourced from them as two months old.

**No page is "closed."** Round 1 catches omission — did the source get captured. Round 2 runs
*after* the master rewrite and checks the reverse direction: does every claim now in the master
trace to a line in a source dump, and does every PG status claim trace to a file and line?
Round 1 cannot catch invention, and invention is the failure mode this document actually has —
three fabrications survived round 1 on 2026-08-04 alone (the 500px provenance, a "new"
proactive-refresh item the master already documented, and *"nothing in §4C was stale"*).

**Round 2 status (2026-08-04): run on all three round-1 artifacts, source side clean — no
fabricated requirement in any of them.** Defects found were citation-quality and one miscount,
all fixed. The raw upstream markdown for all three pages is now committed verbatim under
`Claude_Compliance/sources_raw/` (append `.md` to any of these doc URLs), so every quotation is
independently checkable and round 2 no longer depends on who fetched what.

⚠️ **Round 2 has NOT been run on this master.** The artifacts are checked; the synthesis in
§4C/§4K/§4N is not, because it has not been rewritten yet. A green artifact tally does not
transfer here.

⚠️ **Round 2 surfaced a requirement round 1 missed, and PG fails it — see §4C, A18** (redirect
URI hostname on the consent screen). Labelled precisely: **unmet spec-inherited MUST,
directory-gating status unknown until `review-criteria` is fetched.**

⚠️ **Round 1 on `authentication` is REOPENED.** Round 2 returned six omissions, not one. The
cause was the extraction *method* — round 1 swept for obligation keywords ("must", "required",
"prohibits") and missed every requirement carried by a `<Note>`, a conditional, a cross-reference,
or prose attached to a number. **The remaining seven pages are read for obligations, not
keywords.** Round-1 ✅ on design-guidelines and transparent-theming was awarded under the same
defective method and is worth no more than the method that produced it.
Anthropic Software Directory Policy last updated: April 15, 2026
Submission guide: https://claude.com/docs/connectors/building/submission
Pre-submission checklist: https://claude.com/docs/connectors/building/review-criteria
Authentication reference: https://claude.com/docs/connectors/building/authentication
Building overview: https://claude.com/docs/connectors/building

⚠️ The old "Anthropic MCP Directory Policy" has been superseded by the Anthropic Software Directory Policy. The old support article now redirects to the new developer docs. All references should use: https://support.claude.com/en/articles/13145358-anthropic-software-directory-policy


1. Supported Claude Platforms
All major Claude platforms support remote MCP connectors:

Claude.ai (web) — Full support with OAuth
Claude Desktop — Full support with OAuth
Claude Code — Direct connection from user's machine (with OAuth support)
Claude API — Integration support
Claude Mobile apps — Connector support
Cowork — Connector support (uses same OAuth callback as Claude.ai)


2. Submission Types
Developers can submit:

Remote MCP servers — internet-hosted servers that provide tools and data to Claude
Desktop extensions — local MCP servers packaged as MCP Bundles (MCPB) for Claude Desktop
MCP Apps — MCP servers that surface interactive UI elements. Additional requirement: screenshots must be included for submission and directory listing.

Submission forms:

Remote MCPs (including MCP Apps): http://clau.de/mcp-directory-submission
Desktop extensions (MCPB): http://clau.de/desktop-extention-submission

Review times vary with queue volume. Anthropic reviews submissions manually and cannot promise to accept or respond to every submission individually. Do not assume a fixed timeline. A self-serve status dashboard is rolling out in Claude.ai — until then you may not receive proactive notification on every status change. Email mcp-review@anthropic.com for escalations.


3. Technical Limits
Constraint
Limit
Claude.ai / Desktop max tool result size
~150,000 characters
Claude Code max tool result size
25,000 tokens (configurable via MAX_MCP_OUTPUT_TOKENS)
Claude.ai / Desktop timeout
300 seconds (5 minutes)
Claude Code timeout
Configurable via MCP_TOOL_TIMEOUT
Tool name max length
64 characters
Transport protocol
Streamable HTTP (legacy HTTP+SSE being deprecated)


⚠️ UPDATE May 2026: Token/size limits differ by surface. Claude.ai and Desktop use a character limit (~150k), not a token limit. The 25,000 token policy limit applies to Claude Code. Previous versions of this document stated 25,000 tokens universally — incorrect.


4. Mandatory Requirements
All requirements in this section are mandatory for directory approval. Missing any of these will result in rejection or revision requests.
4A. Safety Annotations — title plus the applicable hint
Every tool MUST have:

title — human-readable tool name (mandatory on all tools)
The applicable safety hint — readOnlyHint: true for read-only tools OR destructiveHint: true for tools with side effects. Not both — one or the other depending on what the tool does.

Annotation
When to use
readOnlyHint: true
Tool only reads data — search, get, list, fetch, read
destructiveHint: true
Tool modifies data or has side effects — create, update, delete, send
title
Mandatory on every tool — human-readable name for UI display


⚠️ UPDATE May 2026: title is now explicitly mandatory per policy §5E: "MCP servers must provide all applicable annotations for their tools, in particular readOnlyHint, destructiveHint, and title." Previous versions of this document listed title as "additional recommended." Incorrect — it is required. Missing tool annotations account for ~30% of all rejections.

Annotation behavior in Claude:

readOnlyHint: true tools can run without per-call confirmation
destructiveHint: true tools always prompt the user

Decision table:

Tool Behavior
Annotation
Examples
Only reads data
readOnlyHint: true, destructiveHint: false
search, get, list, fetch, read
Writes/modifies data
destructiveHint: true, readOnlyHint: false
create, update, delete, send
Creates temp files
destructiveHint: true
Even temporary writes count
Sends external requests
destructiveHint: true
Emails, notifications, webhooks
Caches internally only
readOnlyHint: true
Internal optimization OK


✅ RESOLVED — verified in code 2026-08-04. `ToolDefinition` declares `title: str` as a REQUIRED field (`mcp_server/priority_guardian/tools/base.py:39`), every tool in TOOL_REGISTRY supplies one, and every tool carries a title in the served `tools/list` payload on BOTH platforms. See §9 Blocker 0.

  *This note previously read "PG's ToolDefinition dataclass has no title field. All 17 tools lack title… required code fix before submission." That was false, and it survived here after §9 was corrected — the same claim lived in two sections and only one was fixed. `structural_guideline_claude_vs_openai.md` had already recorded "title present on all 17 tools", so the repo contradicted itself in three places.*
4B. Tool Design — Read/Write Split Required
NEW explicit rejection criterion:

A single tool that accepts both safe HTTP methods (GET, HEAD, OPTIONS) and unsafe methods (POST, PUT, PATCH, DELETE) is rejected. Catch-all api_request tools with a method parameter fail review.

Requirements:

Split read-only tools and write tools into separate tools
Ideally split write operations further by action type (create, update, delete)
Documenting safe vs. unsafe operations within one tool's description does NOT satisfy this — they must be separate tools

Custom query tools: If a tool accepts freeform endpoint paths, query strings, or request bodies, its description must include a link to or explicit name of the target API (e.g., "Queries the Slack Web API — see https://api.slack.com/methods"). A description like "Makes a request to the API" with no further context fails.
4C. OAuth Authentication
YES — Required if your server requires authentication.

⚠️ UPDATE May 2026: The policy text says "OAuth 2.0." However, Claude's implementation and the MCP authorization spec require PKCE S256, which aligns with OAuth 2.1 behavior. Correct framing: "OAuth 2.0 authorization code flow with PKCE S256 support, as required by Claude's auth implementation and the MCP authorization spec." Advertising "code_challenge_methods_supported": ["S256"] in your authorization server metadata is mandatory — if absent, Claude will refuse to proceed.

Supported authentication types:

Type
Description
oauth_dcr
OAuth 2.0 with Dynamic Client Registration (RFC 7591)
oauth_cimd
OAuth 2.0 with Client ID Metadata Document
oauth_anthropic_creds
OAuth 2.0 with Anthropic-held client credentials — email mcp-review@anthropic.com
custom_connection
Custom URL or credentials — email mcp-review@anthropic.com
none
No authentication (authless server)


~~static_bearer (user-pasted tokens) is not yet supported.~~

⚠️ **KNOWN FALSE — verified 2026-08-04. Do not cite this line.** The live authentication
page lists **no** `static_bearer`. It lists **`static_headers`** — *"fixed credential
(API key or bearer token) entered by an **organization administrator** as a request
header"* — marked **Beta**. So the capability was renamed, its actor changed from
user-pasted to admin-entered, and it moved from unsupported to beta; or `static_bearer`
was removed outright. Either way this sentence is wrong.

Flagged inline rather than left for the §4C rewrite, on the Blocker 0 precedent: a false
claim in this file survived two rounds and three locations because each fix was scoped to
where someone was pointed. Cost of the inline flag is one paragraph. See
`authentication_claude_connectors.md` Part 3. Not PG-affecting — PG uses `oauth_dcr`.
Confirmed again in round 2 against the committed raw source, which states outright that the
credential *"is shared by the organization rather than pasted per user."*

⚠️ **A18 — REDIRECT URI HOSTNAME ON THE CONSENT SCREEN. PG DOES NOT SATISFY THIS.**
**Unmet spec-inherited MUST — directory-gating status UNKNOWN.**
(Found in round 2, 2026-08-04; missed by round 1. Raw source line 106. Code fix NOT applied.)

The **MCP authorization spec** requires the authorization server to display the redirect URI
hostname clearly on the consent screen, and separately **recommends** an additional warning when
the only registered redirect URIs are loopback addresses. Upstream rationale: a Client ID Metadata
Document *"can't prevent loopback impersonation on its own — any local process can bind a port and
claim to be the legitimate client."*

**Provenance matters here.** This is the MCP spec surfaced on Anthropic's page — **not** an
Anthropic-enumerated directory criterion. Whether reviewers gate on it is unknown until
`review-criteria` is fetched. Do not push it against Blocker 1 as though that were settled.

**Scope: the display obligation is unconditional.** Only the extra *warning* is conditioned on
loopback-only registration. An earlier draft of this block said A18 binds PG "because PG accepts
loopback redirects for Claude Code" — that read the paragraph's context as the obligation's scope.
It applies to the hosted `claude.ai` consent screens too, which makes the gap wider and the fix
cheaper: one change covers every flow rather than a Claude-Code-only branch.

**PG's position.** None of the eight `backend/templates/oauth_consent_*.html` templates render the
redirect URI, hostname or host — grep returns nothing in any of them. The render site is
`oauth_provider/authorize.py` (`TemplateResponse`, `:788`), whose context passes only `request`,
`auth_context_id`, `client_name`, `scopes`, `scope_descriptions`.

⚠️ An earlier draft said the value sat *"one line away"* and called this *"display, not plumbing."*
**Both oversold it.** The existing `urlparse(redirect_uri).netloc` lives in `consent_ui.py` on the
**post-consent redirect path**, feeding a log line — a different module and a different request
phase, with nothing reusable. `redirect_uri` *is* in scope at the render site (`authorize.py:770`),
but nothing computes its `netloc` and nothing passes it. The fix is **an add, not a move**: one
computation plus one context entry in `authorize.py`, plus markup in all eight templates.

Bounded, not dismissed: the *impersonation* scenario needs a hostile local process during an active
Claude Code authorization. The *display* gap applies to every flow, including hosted surfaces,
where it is a transparency failure rather than an exploitable one.

For high-traffic directory servers: Prefer CIMD or oauth_anthropic_creds over DCR. DCR causes Claude to register a new client on every fresh connection, potentially creating very large numbers of registered clients. CIMD and Anthropic-held credentials avoid the registration call entirely.

Enterprise limitation: Claude uses a single shared OAuth application per connector. Tenant-level isolation and enterprise-specific OAuth clients are not supported. Users connect to the same OAuth app; access is scoped by the user's own permissions on your service.

PKCE requirements:

S256 challenge method mandatory
Authorization server must advertise "code_challenge_methods_supported": ["S256"] in metadata
If not advertised, Claude will refuse to proceed

Protected Resource Metadata — required for discovery:

Server must return 401 Unauthorized with a WWW-Authenticate header:

WWW-Authenticate: Bearer resource_metadata="https://your-mcp-server/.well-known/oauth-protected-resource"

Metadata document at that URL must include:

{

  "resource": "https://your-mcp-server",

  "authorization_servers": ["https://your-auth-server"],

  "scopes_supported": ["your.scope"],

  "bearer_methods_supported": ["header"]

}

Token refresh behavior:

Claude refreshes reactively on a 401 response
Proactive refresh up to 5 minutes before stored expiry
Must return RFC 6749-compliant error codes: invalid_grant (not custom codes) when refresh token is no longer valid
Honor refresh-token rotation correctly if you rotate tokens

Callback URLs:

Hosted Claude surfaces (Claude.ai web, Desktop, mobile, Cowork):

https://claude.ai/api/mcp/auth_callback

Note: https://claude.com/api/mcp/auth_callback appears in some older documentation. The current official auth reference lists only the .ai URL for hosted surfaces. Register both to be safe during the transition period.

Claude Code (local development and MCP Inspector):

http://localhost:6274/oauth/callback

http://localhost:6274/oauth/callback/debug

Claude Code also uses RFC 8252 loopback redirects on ephemeral ports. Your authorization server must accept http://localhost/callback and http://127.0.0.1/callback with port-agnostic matching.

Common OAuth errors:

Missing callback URLs — most common OAuth rejection reason
Not returning invalid_grant on expired refresh tokens (Claude requires RFC 6749-compliant error codes)
HEAD requests without tokens — handle gracefully after OAuth flow
4D. Test Account
YES — Required if your server requires authentication.

Must be a fully populated account (not empty)
Must NOT require MFA, SMS verification, or additional sign-up steps for the reviewer
Step-by-step setup instructions for a reviewer unfamiliar with your service
Must remain active throughout review period and beyond (for periodic post-admission reviews)
Provide via secure method (e.g., 1Password link)
4E. Firewall and IP Allowlist
For servers behind firewalls, allowlist Anthropic's outbound IP range: 160.79.104.0/21

⚠️ UPDATE May 2026: The actual CIDR range 160.79.104.0/21 is now documented in the official authentication page. Previous versions of this document only said "see docs.claude.com/en/api/ip-addresses" without the actual range.

Required for: Claude.ai and Claude Desktop
Not required for: Claude Code (connects directly from user's machine)
IP allowlisting alone is not recommended as a security measure — use OAuth 2.1

> ⚠️ NEW — Origin-header validation: Your MCP server must also validate the `Origin` header on incoming requests. This is listed as a technical requirement in the submission form policy checklist alongside OAuth, HTTPS, and annotations. Servers that accept requests without validating the `Origin` header fail the security review.
4F. Documentation
Comprehensive documentation required — published at a stable HTTPS URL before your publish date (a blog post or help-center article is sufficient; can share privately with Anthropic during review).

Required sections:

Server Description — what your server does
Features — key capabilities and use cases
Setup Instructions — how users connect and configure
Authentication — OAuth setup and requirements (if applicable)
Usage Examples — minimum 3 working examples (see format below)
Privacy Policy — link to full privacy policy (mandatory for remote MCP servers that collect user data or connect to a remote service)
Support — how users get help or report issues

Note: The submission page also lists README + manifest privacy_policies field requirements — these apply specifically to local connectors (MCPB desktop extensions), not remote MCP servers. For PG as a remote MCP, a privacy policy URL is the requirement.

Minimum 3 usage examples format:

### Example 1: [Action]

**User prompt:** "[realistic user prompt]"

**What happens:**

- [step 1]

- [step 2]

**Expected output:** [description]
4G. Production Readiness
Server must be in General Availability (GA) status.

Not marked as "beta," "alpha," or "development"
All features fully implemented and tested
Proper error handling — every tool must return a successful response with valid parameters; generic errors ("Internal Server Error" with no detail) fail review
Actionable error messages — validate inputs and return actionable messages, not silent failures
Scalable infrastructure and monitoring
4I. First-Party API Requirement
Your MCP server must call your own first-party APIs or APIs you legitimately proxy. The MCP server domain should match your service. Reviewers verify this during the functional review. This applies to all tools — a server that wraps arbitrary third-party APIs without owning or proxying them will fail review.
4K. MCP Apps Design Guidelines (Interactive Connectors)
Source: https://claude.com/docs/connectors/building/mcp-apps/design-guidelines
Required per policy §3H: developers must follow design guidelines Anthropic publishes.

Inline card constraints:
- **Height:** Auto-fits to content, no nested scrolling. Host caps and clips overflow. No published px limit. If a scroll viewport is needed, escalate to fullscreen via `ui/request-display-mode`
  ⚠️ **On the "500px" figure used in our widgets — read this before citing it as a requirement.**
  The host constrains inline widget height, but Anthropic publishes **no px value**. Our widgets
  (PG-Claude, MindSort-Claude) target **~500px (480px threshold)** as a *conservative engineering
  budget* to avoid host clipping while remaining compatible with current Claude host behaviour.
  This is an **implementation target, not a documented platform specification.**
  Consequences: exceeding 500px is **not** automatically a compliance violation — the real
  requirements are (a) auto-fit to content and (b) never nested-scroll. Do not brief increments as
  though 500px were a published Anthropic limit (this has caused incorrect constraints twice).
- **Width:** **No documented width limit and no fixed breakpoints.** Official guidance: *"Apps always
  fill the container width—there are no fixed breakpoints. Design responsively from 320px up to
  fullscreen."* Also: *"Full-width layouts — don't add side margins that waste screen real estate"*
  and *"avoid fixed-width layouts; content must reflow gracefully."*
  ⚠️ **The `max-width: 600px` cap — re-argued 2026-08-04 against M10, not inherited.**
  This section previously called the cap *"a product/design choice, not compliance."* That hedge
  was written **before** M10 was extracted from the live design-guidelines page as a Constraint:
  *"No fixed-width layouts; responsive from 320px; no side margins."* It has to be re-argued
  against the requirement, and the answer changes with display mode.

  PG's rule is unconditional (`widget-react/src/main.css:32-35`):
      #root { width: 100%; max-width: 600px; margin: 0 auto; }

  - **Inline: compliant.** `max-width` is not a *fixed* width — with `width: 100%` the layout
    reflows freely from 320px up to 600px, so "no fixed-width layouts" and "responsive from
    320px" are both satisfied. Below the cap, `margin: 0 auto` computes to zero. Nothing binds.
  - **Fullscreen: NOT compliant.** Above 600px the cap binds and `margin: 0 auto` produces
    exactly the artifact M10 names — side margins, on a surface *"meant to use the full
    viewport."* This is not hypothetical: PG declares fullscreen itself
    (`App.tsx:83`, `availableDisplayModes: ['inline','fullscreen']`), and **grep confirms no
    fullscreen-scoped override of the cap exists anywhere in the widget's CSS.**

  **Corrected verdict:** the cap is a legitimate product choice *in inline* and a live M10
  violation *in fullscreen*. The remedy is to scope it, not delete it — the readable-measure
  argument for capping line length is sound where the widget sits in a chat column, and
  irrelevant when the user has explicitly asked for the full viewport.
  **Code fix NOT applied** — the fix decision is Nadja's.
- **Max actions:** 2, placed at the bottom of the card
- **Max data points:** 4–5 (stated constraint — no "recommended" qualifier in official docs)
- No drill-ins, breadcrumbs, or multiple views
- No menus or popovers — use visible controls (segmented buttons, toggles, inline options)
- Touch targets minimum 44×44pt on mobile
- WCAG AA accessibility required: maintain high contrast (AA minimum), support keyboard navigation, provide text alternatives for visual content, test with assistive technologies

**Source verified (June 2026):** Official design-guidelines page at https://claude.com/docs/connectors/building/mcp-apps/design-guidelines

Fullscreen constraints (mandatory):
- No floating panels — use collapsible sidebars, tabs, or pagination
- App provides its own fullscreen button; close button appears in native header
- Composer always visible — design UX to work with it

Mobile constraints:
- **Fullscreen IS supported on mobile** (verified June 2026): App fills the entire screen with chat input and navigation bar overlaid on top. Keep critical UI within the safe area.
- Renders in WKWebView (iOS) / WebView (Android), not sandboxed iframe
- No camera/mic/location access on mobile
- Connectors must be added via web or desktop before appearing on mobile
- Honor safeAreaInsets for notches and home indicator
- Design responsively from 320px minimum width up to fullscreen — no fixed breakpoints
- Full-width layouts — do not add side margins that waste mobile screen real estate
- Avoid fixed-width layouts; content must reflow gracefully

Styling requirements (mandatory):
- Use host CSS variable tokens for ALL structural elements: backgrounds, text, borders, icons
- NEVER hardcode colors for structural UI — use var(--color-*) tokens
- Brand accent colors are permitted for identity, but core UI must use host palette
- All views must support both light and dark themes — tokens adapt automatically
- Test both light and dark mode before submitting
- Icons: use monochromatic, outlined icons matching host icon color tokens. Icons must SUPPORT understanding — never be the sole means of conveying information (provide aria-label or text alternative)
- Typography: follow three-level size scale (heading, body, caption) and two weights (regular=400, emphasized=600). Avoid arbitrary font sizes outside the token scale.
- Loading states: prefer skeleton screens over spinners for inline content — skeletons match the layout structure of the final content for seamless transition

CSP declaration (mandatory for MCP Apps):
Declare external origins per ui:// resource via _meta.ui.csp:
{
  "_meta": {
    "ui": {
      "csp": {
        "connectDomains": ["https://api.example.com"],
        "resourceDomains": ["https://cdn.example.com"]
      }
    }
  }
}
By default, all external origins are blocked. connectDomains = API endpoints the widget calls. resourceDomains = CDN/asset origins. frameDomains (third-party iframes) is currently restricted pending security review.

Display modes:
Declare supported modes via appCapabilities.availableDisplayModes in ui/initialize. Modes: inline, fullscreen, pip. Host responds with supported modes. Request a switch with ui/request-display-mode.

Widget App Domain (_meta.ui.domain) — mandatory for MCP Apps:
Source: https://claude.com/docs/connectors/building/mcp-apps/cross-compatibility
The _meta.ui.domain field is required on every ui:// resource. Without it the widget will not render.
For Claude, compute the value by hashing your full MCP resource URL (including /mcp path):

  node -e 'const url = "https://your-server.com/mcp"; console.log(require("crypto").createHash("sha256").update(url).digest("hex").slice(0,32) + ".claudemcpcontent.com")'

Formula: sha256(MCP_RESOURCE_URL)[:32] + ".claudemcpcontent.com"
The URL is the FULL MCP endpoint including /mcp path — NOT just the origin.
Example: sha256("https://example.com/mcp")[:32] = c3d80a4ed901ee05b21755a88273b4a4
Result: c3d80a4ed901ee05b21755a88273b4a4.claudemcpcontent.com

PG status: domain computed from https://mcp.priority-guard.com/mcp → a7b31ccb44096357600a7460eb0a78e9.claudemcpcontent.com. Confirmed working ✅

Cross-platform note (source: https://claude.com/docs/connectors/building/mcp-apps/cross-compatibility):
MCP Apps can run in both Claude and ChatGPT from a single codebase. The SDK auto-detects the host
environment via App.connect() (no explicit transport parameter needed). registerAppTool() and
registerAppResource() automatically generate platform-specific metadata.

Complete host CSS token reference (source: https://claude.com/docs/connectors/building/mcp-apps/design-guidelines)
IMPORTANT: Hardcoded fallback hex values MUST match official values below. Mismatches cause incorrect rendering when host tokens fail to load.

Background tokens (Light / Dark):
--color-background-primary:    #FFFFFF        / #30302E
--color-background-secondary:  #F5F4ED        / #262624
--color-background-tertiary:   #FAF9F5        / #141413
--color-background-inverse:    #141413        / #FAF9F5
--color-background-info:       #D6E4F6        / #253E5F
--color-background-danger:     #F7ECEC        / #602A28
--color-background-success:    #E9F1DC        / #1B4614
--color-background-warning:    #F6EEDF        / #483A0F

Text tokens (Light / Dark):
--color-text-primary:          #141413        / #FAF9F5
--color-text-secondary:        #3D3D3A        / #C2C0B6
--color-text-tertiary:         #73726C        / #9C9A92
--color-text-inverse:          #FFFFFF        / #141413
--color-text-info:             #3266AD        / #80AADD
--color-text-danger:           #7F2C28        / #EE8884
--color-text-success:          #265B19        / #7AB948
--color-text-warning:          #5A4815        / #D1A041

Border tokens (Light / Dark):
--color-border-primary:        #1F1E1D (40%)  / #DEDCD1 (40%)
--color-border-secondary:      #1F1E1D (30%)  / #DEDCD1 (30%)
--color-border-tertiary:       #1F1E1D (15%)  / #DEDCD1 (15%)
--color-border-info:           #4682D5        / #4682D5
--color-border-danger:         #A73D39        / #CD5C58
--color-border-success:        #437426        / #599130
--color-border-warning:        #805C1F        / #A87829

Typography tokens:
--font-sans: "Anthropic Sans, sans-serif" | --font-mono: "ui-monospace, monospace"
Weights: normal=400, medium=500, semibold=600, bold=700
Sizes: xs=12px, sm=14px, md=16px, lg=20px
Line heights: xs/sm/md=1.4, lg=1.25

Radius tokens:
--border-radius-xs: 4px | --border-radius-sm: 6px | --border-radius-md: 8px
--border-radius-lg: 10px | --border-radius-xl: 12px | --border-radius-full: 9999px

Border width: --border-width-regular: 0.5px

Shadow tokens:
--shadow-hairline: 0 1px 2px 0 rgba(0,0,0,0.05)
--shadow-sm: 0 1px 3px 0 rgba(0,0,0,0.1), 0 1px 2px -1px rgba(0,0,0,0.1)
--shadow-md: 0 4px 6px -1px rgba(0,0,0,0.1), 0 2px 4px -2px rgba(0,0,0,0.1)
--shadow-lg: 0 10px 15px -3px rgba(0,0,0,0.1), 0 4px 6px -4px rgba(0,0,0,0.1)

⚠️ NOTE: The -solid suffix tokens (e.g. --color-background-success-solid, --color-background-info-solid)
are NOT in the official token table. These appear to be internal/undocumented tokens. Use with caution.
Consider using the official non-solid equivalents as fallbacks.

✅ PG FALLBACK VALUES — corrected (verified 2025-05-30):
- color-text-tertiary:         #73726C ✓
- color-text-secondary:        #3D3D3A ✓
- color-background-secondary:  #F5F4ED ✓
All PG fallbacks now match official values.

PG widget pre-submission checklist (MCP Apps specific):
[x] All structural colors use var(--color-*) tokens with hex fallbacks — verified 2025-05-30
[x] Widget tested in both light and dark mode — useHostStyles hook active
[x] _meta.ui.csp declared on ui:// resource (connectDomains, resourceDomains) — resources_dupl.py
[x] Inline card: auto-fit height (no nested scroll), ≤2 actions, no popovers — App.tsx inline mode
[x] All touch targets ≥44×44pt — verified across all components
[x] safeAreaInsets honored for mobile layout — App.tsx line 52
[x] html, body { background: transparent; margin: 0; } — main.css
[x] <meta name="color-scheme" content="light dark" /> in document head — pg-dashboard-claude.html
[x] prefersBorder: false set in _meta.ui — resources_dupl.py
[x] openLink() only called from user gesture handlers — ConnectionStatus.tsx onClick
[ ] Allowed link URIs declared in submission form — pending (external submission form)
[ ] Widget handles multiple instances gracefully — NOT IMPLEMENTED (non-blocking, enhancement)
[x] Loading states use appropriate indicators — inline uses shimmer, fullscreen uses spinners
[x] Icons have text alternatives (aria-label) — verified across all components
[x] No fixed-width layouts — flex layouts reflow at narrow widths

4L. External Links Behavior (MCP Apps)
Source: https://claude.com/docs/connectors/building/mcp-apps/external-links

Default behavior: ui/open-link always shows a confirmation modal before navigating. Directory connectors can allowlist destinations to skip the modal.

Allowlisting (declare in submission form Allowed link URIs field):
- HTTPS origin format: https://example.com (exact hostname match, no subdomains implied)
- Custom URI scheme format: example-app or example-app:
- Entries must be URLs/schemes your organization owns
- Generic schemes (http, file, mailto, javascript, etc.) are rejected

User-activation requirement (hard requirement):
ui/open-link MUST be triggered by a real user gesture (button click). Programmatic calls or timer-triggered calls always show the confirmation modal regardless of allowlist. Design your app so openLink is always in an event handler.

Reserved/rejected URI schemes (full list from official docs):
http, https, file, data, javascript, blob, mailto, tel, sms, intent, android-app, browser-extension schemes, Windows shell schemes (search-ms, shell). Any entry matching these is rejected during review.

PG status: compliant — ConnectionStatus.tsx triggers openLink only on button click user gesture.

4M. Widget Instance Supersession (MCP Apps)
Source: https://claude.com/docs/connectors/building/mcp-apps/instance-supersession

Each time Claude calls a tool that renders an MCP App, a new iframe is mounted. There is no host API to unmount earlier instances. If the tool is called multiple times in a conversation, multiple live widget copies exist simultaneously, each independently able to push model-context updates and messages.

For stateful single-instance widgets (dashboards, carts): implement BroadcastChannel-based supersession — older instances detect a newer sibling and disable themselves (grey out UI, disable buttons, stop sending model-context updates).

Why BroadcastChannel works:
All widget iframes from a single connector are served from the same sandbox origin on *.claudemcpcontent.com (iframe sandbox includes allow-same-origin). A BroadcastChannel opened in one instance reaches every other instance from the same connector in the current conversation.

Pattern: server stamps each tool result with an election key (createdAt + seq) in structuredContent. Widget reads key via toolresult event, broadcasts on BroadcastChannel. Older instances compare keys and mark themselves superseded.

PG status: get_priorities, render_weekly_report, create_priority can all be called multiple times. PG does not currently implement instance supersession. Multiple live dashboard instances will coexist. This is not a submission blocker but is a known UX degradation. Track as post-submission improvement.

Implementation details (from official docs):
- Election key MUST use server wall-clock time (createdAt) — NOT client-side Date.now(). Client mount time does not reflect tool-call order; stored conversations remount widgets as they scroll into view.
- seq should be monotonic counter or derived from durable state (database row ID, version number)
- Channel scope: without fixed ui.domain, BroadcastChannel is scoped per-conversation automatically. With fixed ui.domain, scope widens — include a server-minted conversation scope key to prevent cross-conversation interference.
- Election key is read from the SDK toolresult event (params.structuredContent), NOT from initial widget props.

localStorage caching across remounts:
- On Claude.ai web: hostContext.toolInfo.id is the stable tool-use ID. Persist the resolved server key to localStorage keyed by toolInfo.id to reuse on remount without waiting for toolresult event again.
- On Claude iOS: toolInfo.id is undefined when a stored conversation is rehydrated. Detect this case (toolInfo?.id == null) and skip the cache — fall back to waiting for the toolresult event. This is the only ordering source that works on every platform.
- Treat localStorage as an optimization, not a correctness guarantee.

Fallback if server key is delayed:
- Race the toolresult event against a 1-second timeout after connect()
- If timeout fires first: fall back to client-side Date.now() as orderKey
- CRITICAL: if mixing server and client timestamps, tag with keySource ('server' | 'client') and refuse to compare a client value against a server value — a server createdAt from hours ago will always be smaller than a fresh client timestamp, wrongly handing 'live' to the wrong instance

SDK App class requirement:
- Use the SDK App class (new App() / useApp() in React), not a hand-rolled postMessage bridge
- Hand-rolled bridges silently drop ping (liveness check) and ui/resource-teardown (host asking widget to clean up before unmount)
- Claude.ai web does not currently send ping or resource-teardown to widgets; Claude iOS sends resource-teardown only when user navigates away from the conversation
- The App class handles the full request surface and is required for production
- PG status: uses useApp() React hook — correct. ✅

4N. Transparency and Theming (MCP Apps)
Source: https://claude.com/docs/connectors/building/mcp-apps/transparent-theming

For widgets to blend with Claude's conversation UI (strongly recommended for directory apps):

Required CSS:
  html, body { margin: 0; background: transparent; }
  (any opaque background on <html> or <body> hides the chat surface)

Required HTML head tag:
  <meta name="color-scheme" content="light dark" />
  CRITICAL: Keep this tag even though applyDocumentTheme() also sets color-scheme at runtime.
  The tag covers the FIRST PAINT before your script runs and prevents an opaque-backdrop flash.
  Both are needed — the static tag and the runtime API serve different purposes.

Recommended resource meta:
  _meta.ui.prefersBorder: false — removes host card border; Claude web defaults to borderless
  but other hosts differ; being explicit keeps app portable

Host font loading (optional but expected):
  Add https://assets.claude.ai to CSP resourceDomains to enable Anthropic Sans loading
  _meta.ui.csp: { resourceDomains: ["https://assets.claude.ai"] }
  SECURITY NOTE: resourceDomains also adds listed origins to script-src and style-src.
  Only allowlist origins you trust to serve executable code. Prefer bundling third-party
  fonts into your widget rather than allowlisting public CDNs.

hostContext theming fields (passed by Claude on connect and on hostcontextchanged):
  theme:               "light" or "dark"
  styles.variables:    --color-background-*, --color-text-*, --color-border-*,
                       --color-ring-*, --font-*, --border-radius-*, --border-width-*
                       (complete list, verified 2026-08-04 — this line previously ended
                       "etc.", which hid four of the seven categories)
  styles.css.fonts:    @font-face rules for Anthropic Sans, served from https://assets.claude.ai
  Updates carry only the changed fields — guard with existence checks before applying.

Listener ordering (T4 — ADDED 2026-08-04, absent from this section before):
  "Register the listener before you connect so you don't miss an early update."
  PG assigns onhostcontextchanged at App.tsx:144, inside the onAppCreated callback (:85).
  Whether onAppCreated fires before connect() is SDK internals and is NOT verified. PG
  also uses useHostStyles, which re-applies on the event, so the React path likely covers
  it regardless. ⚠️ unverified, low risk.

SDK helpers (import from @modelcontextprotocol/ext-apps):
  applyDocumentTheme(theme)          — sets <html data-theme> and root color-scheme
  applyHostStyleVariables(variables) — writes all style tokens onto :root as CSS custom properties
  applyHostFonts(fontCss)            — injects @font-face rules once

React pattern (preferred):
  useHostStyles(app, app?.getHostContext()) — applies all three helpers and re-applies
  automatically on hostcontextchanged. This is the correct React hook for theming.
  PG status: ✅ correct — App.tsx:166 is `useHostStyles(app, app?.getHostContext())`,
  TWO args, with the comment "must pass hostContext for dark mode".
  ⚠️ This line previously read "uses useHostStyles(app)" — the ONE-ARG form this very
  section warns against. The verdict was right and the evidence was false; an audit line
  whose supporting evidence is wrong is worse than no line. Corrected 2026-08-04.

CSS fallback pattern (preferred — uses light-dark() for dual-mode fallbacks):
  Once applyDocumentTheme sets color-scheme, light-dark() resolves correctly:
  color: var(--color-text-primary, light-dark(#141413, #faf9f5));
  border: var(--border-width-regular, 0.5px) solid var(--color-border-primary);
  This is better than single-value fallbacks — handles both light and dark correctly
  even when host tokens are not yet loaded.

⚠️ HOST FONTS ARE PAID FOR AND NEVER USED (found 2026-08-04, code fix NOT applied)

  resourceDomains: ["https://assets.claude.ai"] is set (resources_dupl.py:94, :118) so that
  applyHostFonts can inject Anthropic Sans, and useHostStyles does inject it. The @font-face
  rules load. Nothing consumes them:

    main.css:25  font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI',
                              Roboto, sans-serif;      <- hardcoded, no var(--font-sans, …)
    main.css:40  font-family: inherit;                 <- inherits the hardcoded stack

  VERIFIED TOTAL, not partial: grep for "--font-" across the whole of widget-react/src/
  returns nothing. Those two lines are the only font-family declarations in the widget.

  So T3 ✅ is TRUE AND HOLLOW. The CSP allowance is granted and the security surface widened
  (resourceDomains also feeds script-src and style-src — the page's own caveat), and the widget
  renders in system-ui regardless. PG pays the cost and takes none of the benefit.

  The page's canonical form closes it in one edit:
    font-family: var(--font-sans, system-ui, sans-serif);
  NOT APPLIED — this is a widget code change requiring a rebuild and deploy; the fix decision
  is Nadja's. The alternative (drop assets.claude.ai from resourceDomains and narrow the CSP)
  is equally valid and cheaper to ship. Either closes it; doing neither is the only wrong answer.

PG status:
  useHostStyles(app, app?.getHostContext()) hook: ✅ correct (App.tsx:166 — two args)
  color-scheme meta tag: verified in pg-dashboard-claude.html ✅ (both the Vite input and the
    built widgets/pg-dashboard-claude.html:6 that is actually served)
  prefersBorder: false: set in resources_dupl.py ✅
  host fonts consumed: ❌ injected, never referenced — see above
  html/body background: transparent in main.css ✅
  CSS fallbacks: single-value, not light-dark() — verified at main.css:29
    `color: var(--color-text-primary, #141413)`.
    SCOPE: a fallback applies only when the custom property is ABSENT, i.e. when the
    widget renders OUTSIDE a Claude host. Inside Claude, applyHostStyleVariables sets the
    variables and the fallback is never used — so in-host light/dark correctness is
    UNAFFECTED. The gap is that out-of-host rendering shows the light value in dark mode.
    "Suboptimal" is the right severity; scoped 2026-08-04 so it is not read as an M1 risk.

4J. Token Efficiency Response size should be reasonable for the task (~150k character ceiling is a hard limit, but reviewers will reject responses far below this if they're unnecessarily verbose)
Claude Code: Max 25,000 tokens per tool result (configurable)
Do not return full database dumps when summaries were requested
When possible, give users options to exclude unnecessary text

⚠️ MCP Apps specific: If a tool result exceeds ~150,000 characters AND Claude's code execution sandbox is active,
the result is written to the sandbox filesystem instead of passed inline. Your app receives a pointer to the
stored file rather than the structured content it needs — the widget never hydrates.
Mitigation strategies:
- Paginate large results — return summary/first page, let user request more via follow-up interactions
- Fetch details on demand — use app-initiated tool calls to load additional data as user explores
- Defer heavy content — return identifiers/previews in initial result, provide separate tool for full content
PG status: get_priorities returns ~1-6KB, render_weekly_report returns ~2-4KB — well within limit. ✅

4O. MCP Apps Technical Requirements (from troubleshooting docs)
Source: https://claude.com/docs/connectors/building/mcp-apps/troubleshooting

app.connect() is mandatory:
  Your widget MUST call app.connect() (Vanilla JS) or useApp() (React) to establish communication
  with the host. Event handlers (ontoolinput, ontoolresult) are NOT invoked until connected.
  Without app.connect(), the tool call appears in Claude but the widget is invisible.
  PG status: uses useApp() React hook — correct. ✅

Non-zero height required:
  The widget iframe must have a non-zero height. Zero height causes the app to be invisible even
  when fully connected. Ensure root element has explicit dimensions or content that gives it height.
  Do NOT call sendSizeChanged({ width, height: 0 }) except to explicitly hide.
  PG status: autoResize: true is set — height is driven by content. ✅

Debugging in Claude Desktop:
  Enable Developer Mode: Help > Troubleshooting > Enable Developer Mode
  Open DevTools: Cmd+Option+I (Mac) or Ctrl+Shift+I (Windows)
  Your app loads as content of the inner iframe (iframe nested inside another iframe)
  After editing claude_desktop_config.json: Developer > Reload MCP Configuration


5. Submission Form Requirements
Have the following ready when filling out the submission form:

Server basics — server name, URL, tagline, description, use cases
Connection details — auth type, transport protocol, read/write capabilities, connection requirements
Data & compliance — data handling practices, third-party connections, health data access, category
Tools, resources & prompts — list of all tools with human-readable names, resources, and prompts; confirmation of all tool annotations
Documentation & support — links to docs, privacy policy, support channel
Test account — credentials with step-by-step setup instructions (fully populated, no MFA required)
Launch readiness — GA date, confirmation of which surfaces tested (Claude.ai, Desktop, etc.)
Branding — server logo (URL or SVG upload), favicon verification
For MCP Apps — screenshots mandatory for directory listing. Requirements: 3–5 PNG screenshots, at least 1000px wide, cropped to the app response area only — do NOT include the prompt in the image. Provide the prompt text separately for each screenshot.
Allowed link URIs — if connector uses ui/open-link, declare allowed HTTPS origins and custom URI schemes (declared destinations open without confirmation prompt; anything else still prompts user)
Policy & requirements checklists — confirming compliance with directory policy, technical requirements (OAuth, HTTPS, Origin-header validation, annotations), documentation, and testing standards
Optional: Skills & Plugins — if submitting a related Agent Skill alongside the server


6. Anthropic Software Directory Policy (Full Text)
1. Safety and Security
A. Software must not violate or facilitate violation of Anthropic's Usage Policy. Must comply with Universal Usage Standards, High-Risk Use Case requirements, and supported countries policy.

B. Software must not evade or enable users to circumvent Claude's safety guardrails, system instructions, or sandbox environments.

C. Software must prioritize protecting user privacy and the privacy interests of third parties. Responsibly handle personal and sensitive data, follow privacy best practices, ensure compliance with applicable laws.

D. Software must only collect data from the user's context that is necessary to perform their function. Must not collect extraneous conversation data, even for logging purposes.

E. Software must not infringe on the intellectual property rights of others.

F. Software must not query or extract data from Claude's memory, chat history, conversation summaries, or user-generated or uploaded files. (NEW vs old policy)
2. Compatibility
Applies to Software that provides Claude with tools or capabilities through natural language descriptions ("Instructional Software").

A. Must define each tool through narrow, unambiguous natural language specifying what it does and when to invoke it.

B. Tool descriptions must precisely match actual functionality. Must not include unexpected functionality or promise undelivered features.

C. Tool descriptions must not create confusion or conflict with other Software in the Directories.

D. Must not intentionally call or coerce Claude into calling other external software unless requested and intended by a user.

E. Must not attempt to interfere with Claude calling tools from other software, tools, databases, or resources.

F. Must not direct Claude to dynamically pull behavioral instructions from external sources.

G. Must not contain hidden, obfuscated, or encoded instructions. All behavioral guidance must be human-readable and clearly presented. (NEW vs old policy)

Prompt injection patterns that are rejected:

Tool descriptions that instruct Claude to call external software the user didn't request
Instructions that interfere with Claude calling other tools
Directions to pull behavioral instructions from external sources
Hidden, obfuscated, or encoded instructions
Instructions that tell Claude to behave in ways unrelated to the tool's function, attempt to override system instructions, or promote products/services
3. Developer Requirements
A. Must provide a clear, accessible privacy policy link explaining data collection, usage, and retention. Provide Anthropic with links to all applicable privacy policies.

B. Must provide verified contact information and support channels.

C. Must document how Software works, its intended purpose, and how users can troubleshoot issues.

D. Must provide a standard testing account with sample data for Anthropic to verify full functionality.

E. Must provide at least three working examples of prompts or use cases.

F. Must verify ownership/control of any API endpoint, domain, or user interface Software connects to. (Plugins are an exception.)

G. Must maintain Software and address issues within reasonable timeframes.

H. Must agree to Software Directory Terms and follow design guidelines Anthropic publishes.
4. Unsupported Use Cases
A. Software that transfers money, cryptocurrency, or other financial assets, or executes financial transactions.

B. Software that uses AI models to generate images, video, or audio content. (Exception: design-focused software creating visual aids — slides, diagrams, charts, UI mockups, logos — permitted if not offered as standalone image generation.)

C. Software that serves advertisements, sponsored content, paid product placements, or exists primarily as an advertising vehicle.
5. Additional Requirements for MCP Servers
A. Must gracefully handle errors and provide helpful feedback rather than generic error messages.

B. Must be frugal with tokens. Amount of tokens a tool call uses should be commensurate with complexity of the task. Give users options to exclude unnecessary text when possible.

C. Tool names must not exceed 64 characters.

D. Remote MCP servers requiring authentication must use secure OAuth 2.0 (with certificates from recognized authorities). In practice: OAuth 2.1 with PKCE S256 per MCP authorization spec.

E. Must provide all applicable annotations for tools, in particular readOnlyHint, destructiveHint, and title.

F. Should support Streamable HTTP transport. SSE may be supported for now but will be deprecated.

G. Local MCP servers must be built with reasonably current versions of all dependencies, including node_modules.


7. Common Rejection Reasons (ranked by frequency)
Missing tool annotations (~30% of rejections) — Every tool must have readOnlyHint OR destructiveHint AND title. Fix all tools before submitting.

OAuth callback URL errors — Missing https://claude.ai/api/mcp/auth_callback. Also ensure Claude Code loopback URIs support port-agnostic matching.

Catch-all API tools — A single tool with method parameter accepting GET and POST is rejected. Split read/write into separate tools.

Incomplete documentation — Missing examples, unclear setup, missing required sections. Minimum 3 detailed examples with user prompt + what happens + expected output.

Production readiness — Server marked as "beta" or shows instability. Must be GA status.

Missing or inaccessible privacy policy — Immediate rejection. Verify URL is live before submitting.

Generic error messages — "Internal Server Error" or "Bad Request" with no detail fails functional review. Reviewers call every tool with valid parameters.


8. Pre-Submission Checklist
Code requirements
All tools have readOnlyHint OR destructiveHint annotation
All tools have title annotation (human-readable name)
MCP tool names ≤ 64 characters
Read and write operations are in separate tools (no catch-all api_request with method parameter)
Custom query tools link to target API in description
OAuth 2.1 with PKCE S256 implemented
PKCE S256 advertised in authorization server metadata
Protected Resource Metadata hosted at /.well-known/oauth-protected-resource
resource field in metadata exactly matches submission URL
https://claude.ai/api/mcp/auth_callback allowlisted in OAuth provider
Claude Code loopback URIs registered (port-agnostic matching for localhost and 127.0.0.1)
Server returns 401 with WWW-Authenticate header for unauthenticated requests
Server returns invalid_grant (not custom codes) when refresh token is invalid
HTTPS/TLS with valid certificates
Origin header validation — server validates Origin header on all incoming requests
Anthropic IP range 160.79.104.0/21 allowlisted (if behind firewall)
Token-efficient responses — no verbose dumps; users given options to exclude unnecessary text
Error handling — actionable messages, not generic errors
Streamable HTTP transport supported
Operational requirements
Server is production-ready (GA status, not beta)
Three-way URL match verified: submission URL = /.well-known/oauth-protected-resource resource field
Tested from Claude.ai
Tested from Claude Desktop
OAuth flow completes successfully end-to-end
Every tool returns successful response with valid parameters (reviewers call all tools)
Performance acceptable under load
Documentation requirements
Documentation page published at stable HTTPS URL
All required sections present (description, features, setup, auth, examples, privacy, support)
Minimum 3 working usage examples with user prompt + what happens + expected output
Privacy policy published and accessible
Support channel documented
Submission form materials
Test account fully populated (no MFA/SMS required for reviewer)
Server logo (URL or SVG) ready
Favicon verified
Screenshots of widget in use (MCP Apps only — mandatory)
Allowed link URIs declared (if connector uses ui/open-link)


9. PG-Specific Compliance Blockers (Claude Submission)
This section tracks Priority Guardian-specific gaps. Items already satisfied for OpenAI are not re-listed here — see compliance_master_1.3.26.md.
🟢 Blocker 0 — title Annotation — RESOLVED (verified in code 2026-08-04)
`ToolDefinition` declares `title: str` as a REQUIRED field (mcp_server/priority_guardian/tools/base.py), and every tool in TOOL_REGISTRY supplies one. Verified live in the served `tools/list` payload on BOTH platforms — every tool carries a title in its ToolAnnotations. This entry described code work that was already done and told a reader to redeploy for it. A false 🔴 is worse than a missing one: it spends a submission cycle on nothing.

🔴 Blocker 1 — Documentation Page (Must Be Created Before Submission)
No Claude-specific documentation page exists. Must be published at a stable HTTPS URL (e.g. priority-guard.com/docs/mcp-claude) before submission, containing all required sections including minimum 3 usage examples.
🟢 Blocker 2 — MCP App Screenshots (Submission Prep) — RESOLVED
Screenshots of the widget rendering in Claude.ai are mandatory for MCP App directory listing.
**Status (June 2026):** Widget rendering for third-party connectors is now working. Issue #61 resolved. Screenshots can be collected once widget increment ships.
✅ Resolved — OAuth Callback URLs (Fixed in Increment Claude-03)
https://claude.ai/api/mcp/auth_callback and https://claude.com/api/mcp/auth_callback both added to backend/core/config.py allowlist. PKCE S256 already implemented. No further code change needed.
🟡 Item — CORS Origins (Operational Verify)
Confirm whether Claude's browser client hits the MCP server directly. If yes, https://claude.ai must be in CORS_ALLOWED_ORIGINS on the Claude Render service.
🟡 Item — /.well-known/oauth-protected-resource URL Match (Operational Verify)
Verify before submission:

# Use the URL your 401 actually advertises — Claude probes the PATH-SUFFIXED document
# FIRST and falls back to the bare one. Checking only the bare path tests a document
# Claude may not use, so the check can pass while the real one is wrong.
curl https://<CLAUDE_MCP_SERVER_URL>/.well-known/oauth-protected-resource/mcp
curl https://<CLAUDE_MCP_SERVER_URL>/.well-known/oauth-protected-resource   # fallback
# For PG-Claude both currently serve an identical document (verified 2026-08-04) — that is
# what makes the bare-path-only check misleading rather than obviously broken.

# → the "resource" field must match your MCP server URL EXACTLY AS THE USER ENTERS IT IN
#   CLAUDE, INCLUDING ANY PATH COMPONENT (authentication page, A4). For PG-Claude that is
#   https://mcp.priority-guard.com/mcp — WITH /mcp. Do NOT compare against the bare origin.
#   This line previously read 'must equal <CLAUDE_MCP_SERVER_URL>', which is ambiguous and
#   FALSE if read as the origin: resources_dupl.py deliberately distinguishes MCP_SERVER_URL
#   (passed to _extract_origin for the widget domain) from MCP_RESOURCE_URL (the /mcp
#   endpoint). A correct server would have failed this check. Corrected 2026-08-04.
🟢 Item — MCP App Widget Rendering — RESOLVED (June 2026)
**Previous status:** Widget rendering for third-party custom connectors was silently failing (anthropics/claude-ai-mcp GitHub issue #61, filed February 17, 2026).
**Current status (June 2026):** Issue #61 resolved. Widgets now render correctly for third-party custom connectors. resources/read is called as expected. No longer a blocker.


10. Items That Do NOT Need Changes for Claude
Backend API endpoints — unchanged
Google OAuth integration — unchanged
Inbound OAuth provider (DCR, PKCE S256, JWT issuance, JWKS) — unchanged; PKCE S256 already implemented and tested
Token verification logic (mcp_auth.py) — unchanged
Safety annotations (readOnlyHint, destructiveHint, openWorldHint) — 100% coverage across all 17 tools
Privacy policy — already discloses Google Calendar data handling per Google and GDPR requirements
Test account — review@priority-guard.com with seed data already exists
Transport — FastMCP Streamable HTTP already in use; SSE deprecated path not used
Error handling — implemented with structured error messages


11. What Changed From Previous Version

### 2026-08-04 Update (round 1 on 3 of 10 pages — design guidelines, authentication, transparent theming)

**Sources re-fetched:** `mcp-apps/design-guidelines`, `building/authentication`,
`mcp-apps/transparent-theming`. Seven source pages remain on the 2026-06-23 verification and are
flagged in the header. Round 2 (reverse trace) has not started on any page.

- **The 500px inline height limit does not exist and never did as a published requirement.**
  Removed from `design guidelines_mcpapps_claude.md` (3 assertions),
  `remote_server_submission_guide.md` (1) and `structural_guideline_claude_vs_openai.md` (1).
  The live page states "Height: auto-fits to content"; the *Scrolling and gestures* section
  (new, not in any previous repo copy) explains the mechanism — the host caps and clips, with
  no published pixel value. This false constraint shaped at least two increments.
- **Mobile fullscreen IS supported.** Two repo docs said otherwise.
- **§9 Blocker 0 (title annotation) → RESOLVED**, and the duplicate false claim in §4A
  corrected. Verified in code and in the served `tools/list` on both platforms.
- **New in the source, now captured:** *Scrolling and gestures*; safe areas apply on web and
  desktop, not only mobile; `prefersBorder` defaults changed (unspecified = borderless on web,
  bordered on mobile) with a stated safe-area consequence; `baseUriDomains` in the CSP example.
- **Design guidelines duplication removed** from the submission guide — it is now a pointer.
  Duplicating a living upstream page into a second file is what produced the drift.

**Authentication page (§4C) — findings:**

- **§4C:141 is KNOWN FALSE and flagged inline.** *"static_bearer (user-pasted tokens) is
  not yet supported"* — the live page has no `static_bearer`; it has `static_headers`,
  org-admin-entered, **Beta**. Renamed + actor changed + promoted, or removed. Not
  PG-affecting (PG uses `oauth_dcr`), but it is a live false claim in this file.
- **§4C's obligations did NOT drift.** PKCE, the 401 handshake, resource matching,
  callbacks and refresh semantics all still match. The drift was in the capability
  inventory, not the requirement set — a distinction worth keeping, because an earlier
  draft of the artifact concluded "nothing in §4C was stale" and that was false.
- **§9's operational PRM check was fixed twice**: it fetched the pathless document (Claude
  probes the path-suffixed one first), and its trailing assertion compared `resource`
  against the bare origin rather than the full URL including path.
- **New artifact:** `authentication_claude_connectors.md` — 17 MUST requirements, 11
  verified against PG live and from source, 4 explicitly not verified.
- **Six items queued for the §4C rewrite**, including that CIMD selection needs `"none"`
  in `token_endpoint_auth_methods_supported` alongside the CIMD flag, and the DCR-at-scale
  warning. **PG is one metadata flag from CIMD** — it already advertises `"none"`.

### June 2026 Update (final — verified against official docs)
| Item | Previous | Correct (per official docs) |
|------|----------|----------------------------|
| Inline height | "Max 500px (mandatory)" | "Auto-fits to content, no nested scrolling. Host caps and clips overflow. No published px limit." |
| 4-5 data points | Listed as mandatory | Listed as "Constraint" — no "recommended" qualifier (earlier edit fabricating "recommended" was wrong) |
| Mobile fullscreen | "not yet available" | **Supported** — "App fills the entire screen with chat input and navigation bar overlaid" |
| Issue #61 widget rendering | "silently failing" | **RESOLVED** per owner confirmation |

**Correction notes:**
- The "500px hard limit" was from a stale/cached fetch; current official docs show "auto-fits to content" with no px value
- The "recommended" qualifier for 4-5 data points was fabricated and has been removed
- Mobile fullscreen IS supported per current official docs

### May 2026 Update
Item
Previous
Updated
OAuth spec
OAuth 2.0
OAuth 2.1 with PKCE S256; three registration options documented; DCR scaling warning added
title annotation
"Additional recommended"
Mandatory — listed in policy §5E alongside readOnlyHint and destructiveHint
Tool result size
"25,000 tokens" (all surfaces)
Claude.ai/Desktop: ~150,000 characters; Claude Code: 25,000 tokens
Timeout
Not documented
Claude.ai/Desktop: 300 seconds; Claude Code: configurable
IP range
"See docs.claude.com"
160.79.104.0/21 (documented explicitly)
Read/write split
Not documented
Catch-all tools rejected; must split read/write into separate tools
Custom query tools
Not documented
Must link to target API in description
Token refresh
Not documented
Reactive on 401 + proactive 5min before expiry; must return invalid_grant
Enterprise auth
Not documented
Single shared OAuth app per connector; no tenant isolation
static_bearer
Not documented
Not supported
Callback URL
Both .ai and .com listed
Official docs list only .ai; register both during transition
MCP Apps screenshots
Not documented
Mandatory for listing
Submission form fields
Partial
Full field list including branding, Skills/Plugins, allowed link URIs
Policy document name
"Anthropic MCP Directory Policy"
"Anthropic Software Directory Policy" (broader scope)
Hidden instructions
Not in policy
Policy §2G — explicitly prohibited
Claude memory access
Not in policy
Policy §1F — explicitly prohibited
ui/open-link URIs
Not documented
Must declare in submission form
Prompt injection patterns
Listed generically
Explicit list of rejected patterns from review-criteria page
Cross-service automation
Old policy item 30 — prohibited
Removed entirely from new policy — no longer an unsupported use case


