Anthropic/Claude: COMPLIANCE FOR CONNECTORS
Last updated: May 2026 — Sources verified against live Anthropic documentation
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


⚠️ PG codebase gap: PG's ToolDefinition dataclass has no title field. All 17 tools lack title in their ToolAnnotations. This is a required code fix before submission.
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


static_bearer (user-pasted tokens) is not yet supported.

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
4J. Token Efficiency Response size should be reasonable for the task (~150k character ceiling is a hard limit, but reviewers will reject responses far below this if they're unnecessarily verbose)
Claude Code: Max 25,000 tokens per tool result (configurable)
Do not return full database dumps when summaries were requested
When possible, give users options to exclude unnecessary text


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
🔴 Blocker 0 — title Annotation Missing (Code Change Required)
All 17 tools lack title in ToolAnnotations. ToolDefinition dataclass has no title field. The Claude MCP server (tools_list_dupl.py) already derives title from snake_case names — but the shared ToolDefinition and ChatGPT list_tools() also need this for the ChatGPT submission.

Fix: Add title to ToolDefinition, pass it to ToolAnnotations in list_tools(). Affects all tools, requires redeploy.
🔴 Blocker 1 — Documentation Page (Must Be Created Before Submission)
No Claude-specific documentation page exists. Must be published at a stable HTTPS URL (e.g. priority-guard.com/docs/mcp-claude) before submission, containing all required sections including minimum 3 usage examples.
🔴 Blocker 2 — MCP App Screenshots (Submission Prep)
Screenshots of the widget rendering in Claude.ai are mandatory for MCP App directory listing. Cannot be collected until widget rendering is confirmed working (currently blocked by claude.ai host-side issue — widget implementation is correct per spec, platform rendering for third-party custom connectors is silently failing per anthropics/claude-ai-mcp issue #61).
✅ Resolved — OAuth Callback URLs (Fixed in Increment Claude-03)
https://claude.ai/api/mcp/auth_callback and https://claude.com/api/mcp/auth_callback both added to backend/core/config.py allowlist. PKCE S256 already implemented. No further code change needed.
🟡 Item — CORS Origins (Operational Verify)
Confirm whether Claude's browser client hits the MCP server directly. If yes, https://claude.ai must be in CORS_ALLOWED_ORIGINS on the Claude Render service.
🟡 Item — /.well-known/oauth-protected-resource URL Match (Operational Verify)
Verify before submission:

curl https://<CLAUDE_MCP_SERVER_URL>/.well-known/oauth-protected-resource

# → "resource" field must equal <CLAUDE_MCP_SERVER_URL>
🟡 Item — MCP App Widget Rendering (Platform Issue)
Widget rendering for third-party custom connectors is silently failing in claude.ai. _meta.ui.resourceUri is set correctly on the wire (confirmed via logs), but claude.ai never calls resources/read. This is a known platform issue (anthropics/claude-ai-mcp GitHub issue #61, filed February 17, 2026, open, unacknowledged by Anthropic staff). Expected to resolve upon directory approval.


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


11. What Changed From Previous Version (May 2026 Update)
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


