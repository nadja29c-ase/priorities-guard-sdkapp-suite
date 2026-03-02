# OpenAI Compliance Master Checklist — Labeled by Enforcer

**Legend:**
- `[OpenAI]` — Will block SDK app submission/approval (verified against official docs)
- `[OpenAI UI Guideline]` — Explicit UI guideline with "don't" language — likely scrutinized in review
- `[Sandbox]` — Technical limitation of iframe sandbox environment — will cause app to fail if violated
- `[Google]` — Will block Google OAuth verification (only applies to apps using Google APIs)
- `[GDPR]` — Legal risk for EU/DE market, not platform-enforced
- `[Recommended]` — Speeds approval or improves quality, not strictly required

**⚠️ VERIFIED: 01 March 2026 against OpenAI Apps SDK official documentation (developers.openai.com)**
**⚠️ SOURCE: App Submission Guidelines, UI Guidelines, UX Principles, Security & Privacy, API Reference, State Management, MCP Server Guide, Submission FAQs**
**⚠️ PREVIOUS VERSION: Dec 2024 — this update adds ~15 new requirements and reclassifies several items**

---

## A. Technical & SDK Architecture

| # | Requirement | Enforcer | Verification Notes |
|---|-------------|----------|-------------------|
| 1 | Bundle each widget as one compiled HTML/JS file; no external CDNs or remote scripts | `[Recommended]` | Best practice from examples, not explicit requirement |
| 2 | Every backend tool that returns UI output must include `_meta["openai/outputTemplate"]` (or `_meta.ui.outputTemplate`). Alternative: `_meta.ui.resourceUri` | `[OpenAI]` | API Reference confirms; both standard and OpenAI-specific namespaces accepted. `resourceUri` is also valid per docs |
| 3 | Register all widget files in your MCP server resource manifest (`registerResource`) | `[OpenAI]` | Required for widget rendering |
| 4 | Add try/catch around `window.openai.toolOutput` with friendly fallback text | `[Recommended]` | Best practice |
| 5 | Use `window.openai.setWidgetState()` for filters and toggles | `[Recommended]` | Optional API feature; use for UI-only state persistence across re-renders |
| 6 | Accessibility: keyboard focus, aria-labels, readable text | `[OpenAI]` | "All UI components accessible via keyboard and screen readers" |
| 7 | Manifest completeness: name, description, privacy-policy URL, support-email, developer identity | `[OpenAI]` | App Submission Guidelines confirms |
| 8 | Provide demo dataset for reviewers | `[OpenAI]*` | *Only for AUTHENTICATED apps — "provide a login and password for a fully-featured demo account" |
| 9 | Light/dark-mode compatibility and responsive design for mobile | `[Recommended]` | UX Guidelines recommends, not blocking |
| 10 | Catch all 4xx/5xx errors with readable messages | `[OpenAI]` | "Errors...must be well-handled with clear messaging or fallback behaviors" |
| 11 | Avoid localStorage/sessionStorage for core state; prefer widgetState or backend | `[Recommended]` | Docs say "Avoid using localStorage for **core state**" — guidance, not prohibition |
| 11b | Browser cookies blocked in iframe sandbox | `[Sandbox]` | "we still will not permit the storage or access to browser cookies, even with dedicated subdomains" |
| 12 | **Don't use custom fonts** — inherit system font stack | `[OpenAI UI Guideline]` | "Don't use custom fonts, even in full screen modes. Use system font variables wherever possible." |
| 12b | **Don't change text colors or core component styles** — use system colors | `[OpenAI UI Guideline]` | "Don't apply colors to backgrounds in text areas." Use brand accent colors only on primary buttons inside app display modes |
| 12c | **Don't include your logo in responses** — ChatGPT appends logo + app name automatically | `[OpenAI UI Guideline]` | "Do not include your logo as part of the response" |
| 13 | Component CSP: `connectDomains` and `resourceDomains` in `_meta.ui.csp` | `[Recommended]` | Optional during development, required before broad distribution |
| 13b | **`_meta.ui.domain` — dedicated origin, unique per app** | `[OpenAI]` | **NEW** — "required for app submission; must be unique per app". Defaults to `https://web-sandbox.oaiusercontent.com` |
| 13c | `frameDomains` triggers extra scrutiny — avoid unless core to experience | `[OpenAI]` | **NEW** — "Apps that declare frameDomains are subject to higher scrutiny...and are likely to be rejected" |

> **Note:** `<form>` tags ARE allowed — OpenAI's state-management guide explicitly uses `<form>` in their React example.

---

## B. Google OAuth 2.0 & API Integration

> **Note:** This entire section only applies to apps using Google APIs (Priority Guardian Calendar apps). **Skip for non-Google apps.**

| # | Requirement | Enforcer |
|---|-------------|----------|
| 14 | Implement Google OAuth 2.0 with `calendar.readonly`; handle redirects, token exchange, refresh | `[Google]` |
| 15 | Complete domain verification in Google Cloud Console | `[Google]` |
| 16 | Configure OAuth consent screen (External app type) with app name, contact info, privacy-policy URL | `[Google]` |
| 17 | Complete Google OAuth verification before public release | `[Google]` |
| 18 | Use minimal scopes only; prefer read-only access | `[Google]` |
| 19 | Encrypt access and refresh tokens; store short-term only; never log or hard-code | `[Google]` + `[GDPR]` |
| 20 | Provide `/disconnect` endpoint that calls Google's revoke endpoint | `[Google]` |
| 21 | Do not permanently store Google Calendar data; keep only in temporary encrypted cache | `[Google]` |
| 22 | Offer visible "Disconnect Google Calendar" or "Delete my data" button | `[Google]` + `[GDPR]` |
| 23 | Follow Google's Limited-Use policy: no advertising, analytics, profiling, or model training | `[Google]` |
| 24 | HTTPS for all redirects, endpoints, and webhooks | `[Google]` + `[OpenAI]` |
| 25 | Log anonymized technical events only; no tokens or user data; retain ≤30 days | `[Google]` + `[GDPR]` |
| 26 | Sensitive-scope justification PDF explaining why scope is needed | `[Google]` |
| 27 | Google branding compliance screenshots in verification package | `[Google]` |

---

## B2. Inbound OAuth Provider (ChatGPT-as-Client) — NEW

> **⚠️ This section applies to ALL authenticated SDK apps where ChatGPT connects to YOUR OAuth provider. This is distinct from Section B (Google OAuth = outbound to Google). If your app uses authentication, this is submission-blocking.**
> **Source: developers.openai.com/apps-sdk/build/auth/ — verified March 2026**

| # | Requirement | Enforcer | Verification Notes |
|---|-------------|----------|-------------------|
| B2-1 | **Protected Resource Metadata** — expose `GET /.well-known/oauth-protected-resource` returning JSON with `resource`, `authorization_servers`, and optionally `scopes_supported` | `[OpenAI]` | "Key fields you **must** populate"; ChatGPT uses this to discover your auth server |
| B2-2 | **OAuth/OIDC Discovery** — authorization server must expose `/.well-known/oauth-authorization-server` OR `/.well-known/openid-configuration` with correct `authorization_endpoint`, `token_endpoint`, `registration_endpoint`, `code_challenge_methods_supported` | `[OpenAI]` | "Fields that must be correct"; ChatGPT reads this to configure the entire flow |
| B2-3 | **Dynamic Client Registration (DCR)** — `registration_endpoint` must be functional; ChatGPT mints a fresh `client_id` per connector via DCR | `[OpenAI]` | "The MCP spec currently requires dynamic client registration"; continue supporting until CMID lands |
| B2-4 | **PKCE with S256** — `code_challenge_methods_supported` must include `"S256"`; ChatGPT will refuse to proceed if missing | `[OpenAI]` | "ChatGPT will refuse to complete the flow because it cannot confirm PKCE support" |
| B2-5 | **Resource parameter echo** — authorization server must accept `resource=` parameter on authorization and token requests and copy it into the access token (typically `aud` claim) | `[OpenAI]` | "Configure your authorization server to copy that value into the access token" |
| B2-6 | **Token verification on every request** — MCP server must verify signature (via JWKS), `iss`, `aud`/`resource`, `exp`/`nbf`, and required scopes on every tool call | `[OpenAI]` | "You must assume the token is untrusted and perform the full set of resource-server checks yourself" |
| B2-7 | **HTTP-layer 401 + WWW-Authenticate challenge** — on auth failure at the HTTP level, return `401 Unauthorized` with `WWW-Authenticate: Bearer resource_metadata="..."` header pointing to protected resource metadata. This enables ChatGPT to **discover** your auth configuration. **Not interchangeable with B2-10.** | `[OpenAI]` | Required for ChatGPT to discover metadata and re-trigger OAuth flow |
| B2-8 | **Redirect URIs allowlisted** — production: `https://chatgpt.com/connector_platform_oauth_redirect`; review: `https://platform.openai.com/apps-manage/oauth` | `[OpenAI]` | Both must be in your authorization server's allowlist |
| B2-9 | **securitySchemes per tool** — each tool must declare `securitySchemes` array (`noauth`, `oauth2` with scopes) to tell ChatGPT which tools need auth | `[OpenAI]` | "Stick to per-tool declarations even if the entire server uses the same policy" |
| B2-10 | **Tool-result `_meta["mcp/www_authenticate"]`** — tool handlers must return this meta field with `error` and `error_description` parameters when auth is missing/insufficient. This is what actually **triggers ChatGPT's OAuth linking UI** mid-tool-call. Requires B2-1 metadata + B2-9 securitySchemes to be in place. **Not interchangeable with B2-7.** | `[OpenAI]` | "This WWW-Authenticate payload is what actually triggers the tool-level OAuth UI once steps 1 and 2 are in place" |
| B2-11 | **JWKS endpoint** — host public signing keys so your MCP server can verify token signatures; plan for key rotation | `[OpenAI]` | Operationally required to fulfill B2-6 (token verification); docs say "Fetch the signing keys published by your authorization server (usually via JWKS)" |
| B2-12 | **Rate limiting on auth endpoints** — protect `/register`, `/token`, `/authorize` against abuse | `[Recommended]` | Security best practice; OpenAI Security & Privacy doc says "Defense in depth" |
| B2-13 | **Token revocation endpoint** — support revoking access/refresh tokens | `[Recommended]` | Good practice for user disconnect flows; not explicitly required by OpenAI |
| B2-14 | **OIDC scopes enabled** — if your provider advertises OIDC scopes (`openid`, `email`, `profile`) in discovery, ensure they are actually enabled for DCR clients | `[OpenAI]` | "Check your provider's configuration settings and make sure every advertised scope is enabled" |
| B2-15 | **HTTPS on all OAuth endpoints** — all discovery, authorization, token, registration, and JWKS endpoints must be HTTPS | `[OpenAI]` | Implicit in OAuth 2.1 spec and throughout OpenAI docs |

> **Architecture note:** In the Priority Guardian shared backend, these endpoints live at `/oauth/<app>/...` with per-app discovery documents. Clarity and Unpack currently use this OAuth provider. All PG calendar apps will also use it.

---

## C. Privacy, Data Protection & Legal

| # | Requirement | Enforcer | Verification Notes |
|---|-------------|----------|-------------------|
| 28 | Publish privacy policy describing: categories of personal data collected, purposes of use, categories of recipients, and user controls | `[OpenAI]` | "Submissions must include a clear, published privacy policy explaining — at minimum — the categories of personal data collected, the purposes of use, the categories of recipients, and any controls offered" |
| 28b | **Privacy policy must disclose ALL data types returned by tools** | `[OpenAI]` | **NEW** — Common rejection reason: "Your app returns user-related data types that are not disclosed in your privacy policy" |
| 29 | Host infrastructure in EU region (e.g., Render Frankfurt) | `[GDPR]` | Your policy decision, not OpenAI-mandated |
| 30 | Implement unified consent-revocation mechanism | `[GDPR]` | Best practice, not platform-enforced |
| 31 | Disclosure for AI-generated content: "Generated by AI — may contain errors" | `[Recommended]` | Good practice, not explicitly required |
| 32 | Data Protection Impact Assessment (DPIA) | `[GDPR]` | Legal requirement, not OpenAI-enforced |
| 33 | Data-subject rights workflow (access, correction via support email) | `[GDPR]` | Legal requirement, not OpenAI-enforced |
| 34 | Records of Processing Activities (ROPA) — internal document | `[GDPR]` | Legal requirement, not OpenAI-enforced |
| 35 | Data-use disclosure inside app | `[Recommended]` | Good UX, not required |
| 36 | Terms of Use and visible support email or Impressum (for DE market) | `[GDPR]` | German legal requirement |
| 37 | Keep audit logs of access and deletion actions | `[GDPR]` | Best practice for compliance. Also recommended by OpenAI Security & Privacy: "keep audit logs" |
| 38 | Data-deletion mechanism (MCP tool or support email) | `[OpenAI]` | "Respect deletion requests promptly" — NO `data_deletion_url` manifest field required |
| 39 | Privacy Policy available in target languages (EN + DE) | `[GDPR]` | Legal requirement for German market |
| 40 | Incident response plan (breach notification) — internal document | `[GDPR]` | Legal requirement, not OpenAI-enforced |

---

## D. Data Collection & Minimization (NEW SECTION)

> **⚠️ This section is new as of March 2026. These requirements are explicitly stated in the App Submission Guidelines under "Privacy > Data collection" and are enforceable MUST requirements that cause rejections.**

| # | Requirement | Enforcer | Verification Notes |
|---|-------------|----------|-------------------|
| D1 | **Collection minimization** — tool inputs must be specific, narrowly scoped, clearly linked to task. No "just in case" fields or broad profile data | `[OpenAI]` | "Design the input schema to limit data collection by default, rather than a funnel for optional context" |
| D2 | **Response minimization** — tool responses must return only data directly relevant to the user's request. No diagnostic, telemetry, or internal identifiers (session IDs, trace IDs, request IDs, timestamps, logging metadata) | `[OpenAI]` | Common rejection reason: tools returning undisclosed user data types |
| D3 | **Restricted data** — never collect PCI data, PHI, government identifiers (SSN), or access credentials (API keys, MFA/OTP codes, passwords) | `[OpenAI]` | Explicit prohibition in App Submission Guidelines |
| D4 | **Regulated sensitive data** — do not collect "sensitive" or "special category" data unless strictly necessary, user has given legally adequate consent, and collection is clearly disclosed | `[OpenAI]` | Jurisdiction-dependent; must be disclosed at or before point of collection |
| D5 | **No raw location fields** in tool input schema — use client's controlled side channel (environment metadata or referenced resource) when location is needed | `[OpenAI]` | "Avoid requesting raw location fields (e.g., city or coordinates) in your input schema" |
| D6 | **No chat log reconstruction** — app must not pull, reconstruct, or infer the full chat log. Operate only on explicit snippets and resources the client or model chooses to send | `[OpenAI]` | "This separation can help prevent covert data expansion" |
| D7 | **No surveillance, tracking, or behavioral profiling** — including metadata collection (timestamps, IPs, query patterns) unless explicitly disclosed, narrowly scoped, subject to meaningful user control | `[OpenAI]` | Under "Transparency and user control" |
| D8 | **No data exfiltration** — any action that sends data outside current boundary (posting, emailing, uploading) must be surfaced as a write action so client can require user confirmation | `[OpenAI]` | "Reduces unintentional data leakage" |

---

## E. Commerce & Monetization (NEW SECTION)

> **⚠️ CRITICAL for Priority Guardian monetization strategy. This section is new as of March 2026.**

| # | Requirement | Enforcer | Verification Notes |
|---|-------------|----------|-------------------|
| E1 | **Physical goods only** — apps may conduct commerce ONLY for physical goods | `[OpenAI]` | "Selling digital products or services—including subscriptions, digital content, tokens, or credits—is not allowed" |
| E2 | **No digital sales** — no subscriptions, digital content, tokens, credits, whether offered directly or indirectly (e.g., freemium upsells) | `[OpenAI]` | Explicit prohibition |
| E3 | **External checkout required** — direct users to complete purchases on your own domain | `[OpenAI]` | "No other third-party checkout solutions may be embedded or hosted within the app experience" |
| E4 | **No advertising** — apps must not serve advertisements and must not exist primarily as an advertising vehicle | `[OpenAI]` | "Every app is expected to deliver clear, legitimate functionality that provides standalone value" |

> **⚠️ IMPACT ON PRIORITY GUARDIAN:** Voluntary donations via Stripe must happen entirely outside the app (on your website). Any in-app payment flow — even "donate" — risks being classified as selling a digital service. Safest approach: app is 100% free, donation/support link goes to external site.

---

## F. UX & User Experience

| # | Requirement | Enforcer | Verification Notes |
|---|-------------|----------|-------------------|
| 41 | Pre-connection notice explaining what app accesses | `[Recommended]` | Good UX |
| 42 | Clear placeholders for empty/loading states | `[Recommended]` | Good UX |
| 43 | All UI components accessible via keyboard and screen readers | `[OpenAI]` | Submission requirement |
| 44 | Avoid using Google or OpenAI logos; follow branding rules | `[Google]` + `[OpenAI]` | "Apps should not imply that they are made or endorsed by OpenAI" |
| 45 | Manual "Refresh" button for user control | `[Recommended]` | Good UX |
| 46 | Tooltips or help text explaining permissions | `[Recommended]` | Good UX |
| 47 | Localized interface and consent texts (EN + DE) | `[GDPR]` | German market requirement |
| F1 | **Respect user intent** — provide experiences that directly address the user's request. No unrelated content, no redirecting interaction, no data collection beyond what is reasonably necessary | `[OpenAI]` | **NEW** — App Submission Guidelines > Safety |
| F2 | **No ads, upsells, or irrelevant messaging in widgets** | `[OpenAI]` | **NEW** — UX Principles checklist explicitly lists as "avoid" |
| F3 | **Don't display long-form or static content better suited for a website** | `[OpenAI]` | **NEW** — UX Principles "avoid" list |
| F4 | **Age-appropriate** — suitable for general audiences including users 13–17. Must not explicitly target children under 13 | `[OpenAI]` | **NEW** — App Submission Guidelines > Safety |

---

## G. Security & Infrastructure

| # | Requirement | Enforcer | Verification Notes |
|---|-------------|----------|-------------------|
| 48 | HTTPS everywhere; encrypt data in transit and at rest | `[OpenAI]` + `[GDPR]` | |
| 49 | Encrypt OAuth tokens (AES-256 or stronger) at rest | `[GDPR]` | |
| 50 | Document data-retention and deletion schedule | `[GDPR]` | Also OpenAI Security & Privacy: "publish a retention policy" |
| 51 | No API keys in client-side code; credentials server-side only | `[OpenAI]` | |
| 52 | Incident response plan (breach handling) | `[GDPR]` | |
| G1 | **Validate all inputs server-side** even if the model provided them | `[OpenAI]` | **NEW** — Security & Privacy: "Validate everything and keep audit logs" |
| G2 | **Assume prompt injection and malicious inputs will reach your server** | `[OpenAI]` | **NEW** — Security & Privacy: "Defense in depth" principle |
| G3 | **Verify and enforce scopes on every tool call; reject expired/malformed tokens with 401** | `[OpenAI]` | **NEW** — Security & Privacy: Authentication & authorization |
| G4 | **Keep third-party dependencies patched** to mitigate supply chain risks | `[Recommended]` | Security & Privacy: Operational readiness |

---

## H. App Store Submission & Operational Readiness

| # | Requirement | Enforcer | Verification Notes |
|---|-------------|----------|-------------------|
| 53 | Prepare functional demo video showing key flows | `[Recommended]` | Helpful but not required per official docs |
| 54 | Supply test credentials for reviewers | `[OpenAI]*` | *ONLY for authenticated apps: "provide a login and password for a fully-featured demo account" |
| 54b | **Test credentials must NOT require MFA, SMS verification, or additional sign-up** | `[OpenAI]` | **NEW** — Common rejection: "Apps requiring any additional steps for login...will be rejected" |
| 55 | Reviewer Testing Guide with login steps and expected behavior | `[Recommended]` | Best practice |
| 56 | Disclose if app triggers paid GPT-4 calls | `[Recommended]` | Good practice |
| 57 | Support contact information visible in store listing | `[OpenAI]` | "You must provide customer support contact details" |
| 58 | Rate-limit handling and error UX prevent freezes/blank states | `[OpenAI]` | "Apps should not crash, hang, or show inconsistent behavior" |
| 59 | No trial/demo submissions — must be production-ready | `[OpenAI]` | "Any app submitted as a trial or demo will not be accepted" |
| 60 | Original IP only — no copycat designs, impersonation, unauthorized third-party IP | `[OpenAI]` | "Do not engage in misleading or copycat designs, impersonation" |
| H1 | **Developer verification required** — verified individual or organization via OpenAI Platform Dashboard | `[OpenAI]` | **NEW** — "All submissions must come from verified individuals or organizations" |
| H2 | **App name must be clear, non-generic** — avoid single-word dictionary terms not tied to your brand | `[OpenAI]` | **NEW** — "Avoid overly generic names—especially single-word dictionary terms" |
| H3 | **Screenshots must accurately represent functionality** and comply with required dimensions | `[OpenAI]` | **NEW** — App Submission Guidelines |
| H4 | **Test cases must pass on both ChatGPT web AND mobile apps** | `[OpenAI]` | **NEW** — Common rejection reason from FAQs |
| H5 | **No unauthorized third-party connectors** — apps that primarily function as unofficial connectors to third-party services will not be approved | `[OpenAI]` | **NEW** — "We cannot approve apps that primarily function as unofficial connectors" |

---

## I. MCP Server Implementation

| # | Requirement | Enforcer | Verification Notes |
|---|-------------|----------|-------------------|
| 61 | STDIO logging restriction — never write to stdout; use logging framework | `[Recommended]` | Best practice for MCP, not explicit OpenAI requirement |
| 62 | Proper User-Agent headers on all external API requests | `[Recommended]` | Best practice |
| 63 | Async error handling — wrap all async ops in try-catch | `[OpenAI]` | "Errors...must be well-handled with clear messaging or fallback behaviors" |
| I1 | **Widget MIME type must be `text/html;profile=mcp-app`** | `[OpenAI]` | Required for widget rendering; host only enables MCP Apps bridge for this MIME type |
| I2 | **Structured payloads must be trimmed to what the model needs** — oversized payloads degrade performance | `[Recommended]` | MCP Server Guide: Troubleshooting |

---

## J. Tool Annotations (CRITICAL OpenAI Requirement)

| # | Requirement | Enforcer | Verification Notes |
|---|-------------|----------|-------------------|
| 64 | Set `readOnlyHint: true` for tools that ONLY fetch/list/retrieve data and do not modify anything | `[OpenAI]` | "Incorrect or missing action labels are a common cause of rejection" |
| 65 | Set `readOnlyHint: false` for tools that create/update/delete, trigger actions, or change state | `[OpenAI]` | Includes: send emails, run jobs, enqueue tasks, write logs, start workflows |
| 65b | Set `openWorldHint: true` for tools that write to or change publicly visible internet state | `[OpenAI]` | **CLARIFIED** — Posting to social media, sending emails/SMS, creating public tickets, publishing pages, pushing code to public endpoints |
| 65c | Set `openWorldHint: false` ONLY if tool operates entirely within closed/private systems | `[OpenAI]` | **CLARIFIED** — Including internal writes; cannot change state of publicly visible internet |
| 66 | Set `destructiveHint: true` for tools that can cause irreversible outcomes | `[OpenAI]` | **EXPANDED** — Includes: deleting, overwriting, sending messages/transactions you can't undo, revoking access — even in select modes or via indirect side effects |
| 66b | **Destructive justification must describe what is irreversible and under what conditions** including safeguards (confirmation steps, dry-run options, scoping constraints) | `[OpenAI]` | **NEW** — From submission FAQs |
| 67 | Provide detailed justification for each annotation at submission time | `[OpenAI]` | "provide a detailed justification for each at submission time" |
| 68 | Tool names must be human-readable, specific, descriptive, unique within app | `[OpenAI]` | Use plain language reflecting the action, ideally as a verb (e.g., `get_order_status`) |
| 68b | **No misleading, promotional, or comparative tool names** | `[OpenAI]` | **NEW** — "Avoid misleading, overly promotional, or comparative language (e.g., pick_me, best, official)" |
| 69 | Tool descriptions must accurately explain purpose; no misleading language | `[OpenAI]` | "If a tool's behavior is unclear...your app may be rejected" |
| 69b | **Tool descriptions must not attempt to influence model selection** — no favoring or disparaging other apps | `[OpenAI]` | **NEW** — Fair play requirement |
| 69c | **Tool descriptions must not recommend overly-broad triggering** beyond explicit user intent | `[OpenAI]` | **NEW** — App Submission Guidelines |
| 70 | Tool inputs must be minimal — no "just in case" fields | `[OpenAI]` | "Gather only the minimum data required" |
| 70b | **A tool may request a brief, task-specific user intent field ONLY when it meaningfully improves execution** and does not expand data collection | `[OpenAI]` | **NEW** — No full conversation history, raw chat transcripts, or broad contextual fields |
| J1 | **Predictable, auditable behavior** — side effects must never be hidden or implicit | `[OpenAI]` | **NEW** — "Tools should be safe to retry where possible, or clearly indicate when retries may cause repeated effects" |
| J2 | **Data-sending tools must be surfaced as write actions** — any tool that sends data outside current boundary must be labeled for user confirmation | `[OpenAI]` | **NEW** — Prevents unintentional data leakage |

---

## K. Strongly Recommended

| # | Requirement | Enforcer |
|---|-------------|----------|
| 71 | Semantic versioning and changelog | `[Recommended]` |
| 72 | Document API rate limits for users | `[Recommended]` |
| 73 | Technical diagram illustrating data flow | `[Recommended]` |
| 74 | Support contact easily discoverable | `[Recommended]` |
| 75 | Robust rate-limit error handling | `[Recommended]` |
| 76 | API-key rotation policy (e.g., every 90 days) | `[Recommended]` |
| 77 | Dependency vulnerability reviews and patching | `[Recommended]` |
| 78 | Security testing/vulnerability scans in CI | `[Recommended]` |

---

# Summary by Enforcer

| Enforcer | Count | Impact |
|----------|-------|--------|
| `[OpenAI]` | **~49** | **Blocks submission** — fix before submitting |
| `[OpenAI UI Guideline]` | 3 | **Likely scrutinized** — "don't" language in guidelines |
| `[Sandbox]` | 1 | **App will fail** — iframe sandbox blocks cookies |
| `[Google]` | ~14 | **Blocks OAuth verification** — only for apps using Google APIs |
| `[GDPR]` | ~15 | **Legal risk** — required for EU/DE market, not platform-enforced |
| `[Recommended]` | ~18 | **Speeds approval** — defer if time-constrained |

> **Note:** OpenAI blocker count increased from ~17 (Dec 2024) to ~49 (March 2026) due to newly explicit requirements around data minimization, commerce restrictions, tool annotations, submission requirements, and inbound OAuth provider compliance.

---

# Key Changes from Dec 2024 → March 2026

| Area | Change | Impact |
|------|--------|--------|
| **Inbound OAuth** | NEW section B2 — 15 items covering OAuth provider requirements for authenticated apps | **CRITICAL** — submission-blocking for all authenticated apps |
| **Commerce** | NEW section — physical goods only, no digital sales, no ads | **CRITICAL** — affects monetization strategy |
| **Data minimization** | NEW section with 8 explicit enforceable requirements | **HIGH** — every tool response must be audited |
| **`_meta.ui.domain`** | Now REQUIRED for submission (was part of optional CSP) | **HIGH** — needs unique origin per app |
| **Tool annotations** | Much more detailed guidance on `openWorldHint`, `destructiveHint` | **MEDIUM** — update all annotation justifications |
| **Test credentials** | Explicitly cannot require MFA/SMS/additional sign-up | **MEDIUM** — reviewer account must be frictionless |
| **Developer verification** | Now explicit requirement via Platform Dashboard | **MEDIUM** — verify before first submission |
| **Age appropriateness** | Must be suitable for 13–17 year olds | **LOW** — unlikely issue for productivity tools |
| **App naming** | No single-word generic dictionary terms | **LOW** — "Priority Guardian" is fine |
| **UI guidelines** | Added: no custom text colors, no logo in responses | **LOW** — reinforces existing design token approach |
| **Fair play** | Tool descriptions must not manipulate model selection | **LOW** — but important for multi-app suite |
| **Chat log prohibition** | Cannot reconstruct full chat log from tool inputs | **MEDIUM** — affects how tools receive context |
| **frameDomains** | Using iframes triggers extra review scrutiny | **LOW** — avoid unless essential |
| **Mobile testing** | Test cases must pass on both web AND mobile | **HIGH** — add to QA checklist |

---

# Priority Guardian Suite — Specific Blockers

## ALL PG apps: MUST fix before submission

**OpenAI Blockers (submission-blocking):**
- [ ] `_meta["openai/outputTemplate"]` on all tools returning widgets
- [ ] `_meta.ui.domain` — unique dedicated origin per app
- [ ] Register widget resources in MCP server with `text/html;profile=mcp-app`
- [ ] Accessibility (keyboard, ARIA)
- [ ] Manifest complete (name, description, privacy_policy_url, support_email)
- [ ] Error handling with clear user-facing messages on all 4xx/5xx
- [ ] Published privacy policy disclosing ALL data categories returned by tools
- [ ] Data-deletion mechanism (MCP tool or support email)
- [ ] Support contact visible and accurate
- [ ] No crashes/hangs/inconsistent behavior
- [ ] Production-ready (no beta/trial/demo)
- [ ] Original IP only
- [ ] Developer verification via OpenAI Platform Dashboard
- [ ] Test cases pass on ChatGPT web AND mobile

**Inbound OAuth Provider (submission-blocking for authenticated apps):**
- [ ] Protected Resource Metadata at `/.well-known/oauth-protected-resource`
- [ ] OAuth/OIDC discovery document correct and complete
- [ ] Dynamic Client Registration functional
- [ ] PKCE S256 advertised and enforced
- [ ] Resource parameter echoed into access token `aud` claim
- [ ] Token verification on every tool call (signature, iss, aud, exp, scopes)
- [ ] 401 + WWW-Authenticate challenge on auth failure
- [ ] Redirect URIs allowlisted (production + review)
- [ ] `securitySchemes` declared per tool
- [ ] `_meta["mcp/www_authenticate"]` in error responses triggers OAuth UI
- [ ] OIDC scopes enabled if advertised in discovery

**Tool Annotations (CRITICAL — common rejection reason):**
- [ ] `readOnlyHint: true` for all read-only tools
- [ ] `readOnlyHint: false` + `destructiveHint: true` for delete/overwrite tools
- [ ] `openWorldHint: true` for any tool interacting with external systems
- [ ] Tool names: human-readable, verb-based, unique, no promotional language
- [ ] Tool inputs: minimal, no "just in case" fields, no full conversation context
- [ ] Tool responses: no session IDs, trace IDs, timestamps, internal identifiers
- [ ] Annotation justifications prepared with irreversibility descriptions and safeguards
- [ ] No tool descriptions that manipulate model selection

**Data Minimization (enforceable):**
- [ ] All tool inputs narrowly scoped to task
- [ ] All tool responses return ONLY user-relevant data
- [ ] No raw location fields in schemas
- [ ] No chat log reconstruction
- [ ] No PCI, PHI, government IDs, credentials in any tool flow

**Commerce (CRITICAL for monetization):**
- [ ] No in-app payments, subscriptions, or digital product sales
- [ ] No ads or upsells in widgets
- [ ] Donation/support model must be entirely external (website link only)

**UI Guidelines:**
- [ ] System font stack only — no custom fonts
- [ ] System colors for text/icons — brand accent only on primary buttons
- [ ] No app logo in responses
- [ ] Suitable for ages 13+

**Sandbox Constraints:**
- [ ] No browser cookies — use widgetState or backend
- [ ] All fetch requests comply with CSP

## PG Calendar apps (Google OAuth): ALSO fix

- [ ] All Section B items (14–27)
- [ ] Google OAuth verification completed
- [ ] Test credentials with NO MFA requirement

## German market launch: ALSO fix

- [ ] All GDPR items (Section C: 28–40)
- [ ] Localization (EN + DE) for all user-facing text
- [ ] Impressum compliant with German law

---

# Source Documents Verified (March 2026)

- **App Submission Guidelines** — developers.openai.com/apps-sdk/app-submission-guidelines/
- **UI Guidelines** — developers.openai.com/apps-sdk/concepts/ui-guidelines/
- **UX Principles** — developers.openai.com/apps-sdk/concepts/ux-principles/
- **Security & Privacy** — developers.openai.com/apps-sdk/guides/security-privacy/
- **API Reference** — developers.openai.com/apps-sdk/reference/
- **State Management** — developers.openai.com/apps-sdk/build/state-management/
- **Build MCP Server** — developers.openai.com/apps-sdk/build/mcp-server/
- **Submission FAQs** — developers.openai.com/apps-sdk/deploy/submission/
- **Design Components** — developers.openai.com/apps-sdk/plan/components/
