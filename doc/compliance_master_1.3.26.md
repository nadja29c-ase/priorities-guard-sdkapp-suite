# OpenAI Compliance Master Checklist — Labeled by Enforcer

**Legend:**
- `[OpenAI]` — Will block SDK app submission/approval (verified against official docs; source uses "must", "must not", or explicit prohibition language)
- `[OpenAI Guideline]` — In an enforcement section of the submission guidelines but uses "avoid" or scrutiny language rather than hard prohibition — review risk, not a guaranteed blocker
- `[OpenAI UI Guideline]` — Explicit UI guideline with "don't" language — likely scrutinized in review
- `[Sandbox]` — Technical limitation of iframe sandbox environment — will cause app to fail if violated
- `[Google]` — Will block Google OAuth verification (only applies to apps using Google APIs)
- `[GDPR]` — Legal risk for EU/DE market, not platform-enforced
- `[Recommended]` — Speeds approval or improves quality, not strictly required

**⚠️ VERIFIED: 04 March 2026 against OpenAI Apps SDK official documentation (developers.openai.com)**
**⚠️ SOURCE: App Submission Guidelines, UI Guidelines, UX Principles, Security & Privacy, API Reference, State Management, MCP Server Guide, Submission FAQs, Authentication Guide**
**⚠️ PREVIOUS VERSION: 01 March 2026**
**⚠️ THIS VERSION: 04 March 2026 — full re-verification against live docs + two rounds of ChatGPT feedback validation. Changes: added 11c, B2-16, E5, K6, K7; updated D5 (side-channel clarification + wording), B2-3 (DCR as implementation expectation not spec mandate); label corrections: F3→Recommended, I4→Recommended, I63→Recommended, G3→Recommended; wording corrections: 64, 28b, 11c, 65c; rejected fabricated graceful-degradation requirement; confirmed A10, 11b, commerce wording, B2-3 enforcer label all stand**

---

## A. Technical & SDK Architecture

| # | Requirement | Enforcer | Verification Notes |
|---|-------------|----------|-------------------|
| 1 | Bundle each widget as one compiled HTML/JS file. CDNs are permitted if the domain is explicitly allowlisted in your CSP; avoid CDNs that are not strictly necessary | `[Recommended]` | System is CSP-driven — OpenAI requires allowlisting fetch domains but does not blanket-prohibit CDNs |
| 2 | Every backend tool that returns UI output must include `_meta["openai/outputTemplate"]` (or `_meta.ui.outputTemplate`). Alternative: `_meta.ui.resourceUri` | `[OpenAI]` | API Reference confirms; both standard and OpenAI-specific namespaces accepted. `resourceUri` is also valid per docs |
| 3 | Register all widget files in your MCP server resource manifest (`registerResource`) | `[OpenAI]` | Required for widget rendering |
| 4 | Add try/catch around `window.openai.toolOutput` with friendly fallback text | `[Recommended]` | Best practice |
| 5 | Use `window.openai.setWidgetState()` for filters and toggles | `[Recommended]` | Optional API feature; use for UI-only state persistence across re-renders |
| 6 | Accessibility: keyboard focus, aria-labels, readable text, WCAG AA minimum contrast ratio for text/background, alt text for all images | `[OpenAI]` | "All UI components accessible via keyboard and screen readers"; UI Guidelines explicitly require WCAG AA contrast and alt text |
| 7 | Manifest completeness: name, description, privacy-policy URL, support-email, developer identity | `[OpenAI]` | App Submission Guidelines confirms |
| 8 | Provide demo dataset for reviewers | `[OpenAI]*` | *Only for AUTHENTICATED apps — "provide a login and password for a fully-featured demo account" |
| 9 | Light/dark-mode compatibility and responsive design for mobile | `[Recommended]` | UX Guidelines recommends, not blocking |
| 10 | Errors must be well-handled with clear messaging or fallback behavior | `[OpenAI]` | Submission Guidelines > Quality & Reliability: "Errors, including unexpected ones, must be well-handled with clear messaging or fallback behaviors." Note: specific 4xx/5xx catch-all is an implementation pattern, not a doc requirement — the enforceable requirement is the outcome (no crashes, no silent failures, no blank states) |
| 11 | Avoid localStorage/sessionStorage for core state; prefer widgetState or backend | `[Recommended]` | Docs say "Avoid using localStorage for **core state**" — guidance, not prohibition |
| 11b | Browser cookies blocked in iframe sandbox | `[Sandbox]` | "we still will not permit the storage or access to browser cookies, even with dedicated subdomains" |
| 11c | **Privileged browser APIs unavailable in iframe sandbox** — `window.alert`, `window.prompt`, `window.confirm`, `navigator.clipboard` are documented as blocked; other privileged APIs may also be unavailable. Do not rely on these in widget code | `[Sandbox]` | Security & Privacy: "Widgets cannot access privileged browser APIs **such as**..." — "such as" indicates a non-exhaustive list; exact set may vary by host |
| 12 | **Don't use custom fonts** — inherit system font stack | `[OpenAI UI Guideline]` | "Don't use custom fonts, even in full screen modes. Use system font variables wherever possible." |
| 12b | **Don't change text colors or core component styles** — use system colors | `[OpenAI UI Guideline]` | "Don't apply colors to backgrounds in text areas." Use brand accent colors only on primary buttons inside app display modes |
| 12c | **Don't include your logo in responses** — ChatGPT appends logo + app name automatically | `[OpenAI UI Guideline]` | "Do not include your logo as part of the response" |
| 13 | **CSP required for submission when widget UI is used** — define `connectDomains` and `resourceDomains` in `_meta.ui.csp` (or `_meta["openai/widgetCSP"]`) to allowlist the exact domains your widget fetches from. Tool-only apps with no widget UI are exempt | `[OpenAI]` | Submission doc lists CSP as a named prerequisite "required to submit your app for security reasons"; only applies to apps with widget UI components |
| 13b | **`_meta.ui.domain` — dedicated origin, unique per app** | `[OpenAI]` | **NEW** — "required for app submission; must be unique per app". Defaults to `https://web-sandbox.oaiusercontent.com`. **⚠️ PLACEMENT: must be set on the resource template (`registerResource` / `registerAppResource`), NOT on the tool descriptor. Wrong placement silently fails — widget renders on default sandbox origin instead of your domain.** Source: Reference > Component resource `_meta` fields |
| 13c | `frameDomains` triggers additional manual review and apps using it are often not approved for broad distribution — avoid unless embedding a third-party experience is essential (e.g. notebook, IDE) | `[OpenAI Guideline]` | Submission guidelines: "often not approved for broad distribution" — probability statement, not a guaranteed blocker. Does not meet `[OpenAI]` bar; review risk, not a certain submission block |

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
| B2-3 | **Dynamic Client Registration (DCR)** — `registration_endpoint` must be functional; ChatGPT currently expects OAuth providers to support DCR and mints a fresh `client_id` per connector | `[OpenAI]` | ChatGPT's connector implementation expects DCR today — this is an implementation expectation, not a formal OAuth spec mandate. Continue supporting until CMID lands. **⚠️ Operationally: DCR can generate thousands of short-lived clients — often one per user session. Plan your auth server client storage accordingly.** |
| B2-4 | **PKCE with S256** — `code_challenge_methods_supported` must include `"S256"`; ChatGPT will refuse to proceed if missing | `[OpenAI]` | "ChatGPT will refuse to complete the flow because it cannot confirm PKCE support" |
| B2-5 | **Resource parameter echo** — authorization server must accept `resource=` parameter on authorization and token requests and copy it into the access token (typically `aud` claim) | `[OpenAI]` | "Configure your authorization server to copy that value into the access token" |
| B2-6 | **Token verification on every request** — MCP server must verify signature (via JWKS), `iss`, `aud`/`resource`, `exp`/`nbf`, and required scopes on every tool call | `[OpenAI]` | "You must assume the token is untrusted and perform the full set of resource-server checks yourself" |
| B2-7 | **HTTP-layer 401 + WWW-Authenticate challenge** — on auth failure at the HTTP level, return `401 Unauthorized` with `WWW-Authenticate: Bearer resource_metadata="..."` header pointing to protected resource metadata. This enables ChatGPT to **discover** your auth configuration. **Not interchangeable with B2-10.** | `[OpenAI]` | Required for ChatGPT to discover metadata and re-trigger OAuth flow |
| B2-8 | **Redirect URIs allowlisted** — new production format: `https://chatgpt.com/connector/oauth/{callback_id}` (shown in app management page after submission); legacy format `https://chatgpt.com/connector_platform_oauth_redirect` continues to work for already-published apps; **review URI** `https://platform.openai.com/apps-manage/oauth` must ALSO be allowlisted for reviewer OAuth to complete | `[OpenAI]` | Three URIs total: new production + legacy + review. New apps must use new format. Review URI is a separate submission blocker — missing it blocks reviewer auth flow. Source: developers.openai.com/apps-sdk/build/auth/ |
| B2-9 | **securitySchemes per tool** — each tool must declare `securitySchemes` array (`noauth`, `oauth2` with scopes) to tell ChatGPT which tools need auth | `[OpenAI]` | "Stick to per-tool declarations even if the entire server uses the same policy" |
| B2-10 | **Tool-result `_meta["mcp/www_authenticate"]`** — tool handlers must return this meta field with `error` and `error_description` parameters when auth is missing/insufficient. This is what actually **triggers ChatGPT's OAuth linking UI** mid-tool-call. Requires B2-1 metadata + B2-9 securitySchemes to be in place. **Not interchangeable with B2-7.** | `[OpenAI]` | "This WWW-Authenticate payload is what actually triggers the tool-level OAuth UI once steps 1 and 2 are in place" |
| B2-11 | **JWKS endpoint** — host public signing keys so your MCP server can verify token signatures; plan for key rotation | `[Recommended]` | Auth doc says "usually via JWKS" — "usually" indicates JWKS is the typical mechanism, not the only one. The actual `[OpenAI]` requirement is token verification (B2-6); JWKS is the standard implementation path |
| B2-12 | **Rate limiting on auth endpoints** — protect `/register`, `/token`, `/authorize` against abuse | `[Recommended]` | Security best practice; OpenAI Security & Privacy doc says "Defense in depth" |
| B2-13 | **Token revocation endpoint** — support revoking access/refresh tokens | `[Recommended]` | Good practice for user disconnect flows; not explicitly required by OpenAI |
| B2-14 | **OIDC scopes enabled** — if your provider advertises OIDC scopes (`openid`, `email`, `profile`) in discovery, ensure they are actually enabled for DCR clients | `[OpenAI]` | "Check your provider's configuration settings and make sure every advertised scope is enabled" |
| B2-15 | **HTTPS on all OAuth endpoints** — all discovery, authorization, token, registration, and JWKS endpoints must be HTTPS | `[OpenAI]` | Implicit in OAuth 2.1 spec and throughout OpenAI docs |

| B2-16 | **ChatGPT client identification via IP allowlist** — the only reliable way to confirm a request comes from ChatGPT today is network-level filtering: allowlist ChatGPT's published egress IP ranges at `openai.com/chatgpt-connectors.json`. ChatGPT does NOT support mTLS, client credentials, service accounts, or JWT bearer assertions for machine-to-machine identity | `[Recommended]` | Auth Guide: "Today the only reliable control is network-level filtering, such as allowlisting ChatGPT's published egress IP ranges". CMID (Client Metadata Documents) will address this more robustly once available |

> **Architecture note:** In the Priority Guardian shared backend, these endpoints live at `/oauth/<app>/...` with per-app discovery documents. Clarity and Unpack currently use this OAuth provider. All PG calendar apps will also use it.

---

## C. Privacy, Data Protection & Legal

| # | Requirement | Enforcer | Verification Notes |
|---|-------------|----------|-------------------|
| 28 | Publish privacy policy describing: categories of personal data collected, purposes of use, categories of recipients, and user controls | `[OpenAI]` | "Submissions must include a clear, published privacy policy explaining — at minimum — the categories of personal data collected, the purposes of use, the categories of recipients, and any controls offered" |
| 28b | **Privacy policy must disclose categories of personal data returned or processed by tools** — not every field, but every category of personal data | `[OpenAI]` | Submission guidelines require disclosure of "categories of personal data"; common rejection reason is undisclosed data types. Wording softened from "all data types" to match the actual requirement |
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
| D5 | **Avoid raw location fields** in tool input schema — when location is needed, use the client's controlled side channel: if available, `_meta["openai/userLocation"]` provides coarse city, region, country, timezone, longitude, latitude. Servers must tolerate its absence — it is a hint only, not guaranteed on every tool call. Prefer not adding city/coordinates as explicit input schema fields | `[OpenAI Guideline]` | Source uses "avoid" language — weaker than adjacent D6 "must not". API Reference explicitly notes `_meta["openai/userLocation"]` is a hint; servers must tolerate absence |
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

| E5 | **Instant Checkout exists but is restricted** — `window.openai.requestCheckout` / "Instant Checkout" is in beta and available only to select marketplace partners. Do not attempt to use it outside the beta program | `[OpenAI]` | Submission doc: "Instant Checkout...is currently available only to select marketplace partners and may expand...over time." Standard external checkout is required for everyone else |

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
| F2 | **No ads, upsells, or irrelevant messaging in widgets** | `[OpenAI Guideline]` | Source is UX Principles "avoid" language — does not meet `[OpenAI]` bar of explicit prohibition. Note: E4 covers the harder rule ("must not serve advertisements") in the submission guidelines; F2 covers the broader UX guidance about upsells and irrelevant messaging |
| F3 | **Don't display long-form or static content better suited for a website** | `[Recommended]` | Downgraded from `[OpenAI]` — appears only in UX Principles pre-publishing checklist "avoid" list, not in submission guidelines as a rejection criterion. Treat as strong UX guidance |
| F4 | **Age-appropriate** — suitable for general audiences including users 13–17. Must not explicitly target children under 13 | `[OpenAI]` | **NEW** — App Submission Guidelines > Safety |
| F5 | **Must not facilitate illegal, harmful, or deceptive activities** — apps must not enable illegal acts, cause harm to users, or deceive/impersonate. Covers fraud, misrepresentation, circumvention of third-party controls | `[OpenAI]` | App Submission Guidelines > Safety > Usage Policies: "Do not engage in or facilitate activities prohibited under OpenAI usage policies." Partially covered by H5 (unofficial connectors) but the broader safety obligation applies independently |

---

## G. Security & Infrastructure

| # | Requirement | Enforcer | Verification Notes |
|---|-------------|----------|-------------------|
| 48 | HTTPS everywhere; encrypt data in transit and at rest | `[OpenAI]` + `[GDPR]` | |
| 49 | Encrypt OAuth tokens (AES-256 or stronger) at rest | `[GDPR]` | |
| 50 | Document data-retention and deletion schedule | `[GDPR]` | Also OpenAI Security & Privacy: "publish a retention policy" |
| 51 | No API keys in client-side code; credentials server-side only | `[OpenAI]` | |
| 52 | Incident response plan (breach handling) | `[GDPR]` | |
| G1 | **Validate all inputs server-side** even if the model provided them | `[Recommended]` | Security & Privacy lists this under "Prompt injection" mitigations, not as a submission enforcement rule. Critical security practice but not a platform-enforced requirement |
| G2 | **Assume prompt injection and malicious inputs will reach your server** | `[Recommended]` | Security & Privacy: "Defense in depth" principle — in Security Principles section, not submission enforcement rules. Critical operational practice but not a platform-enforced submission requirement |
| G3 | **Verify and enforce scopes on every tool call; reject expired/malformed tokens with 401** | `[Recommended]` | Security & Privacy phrases this as best practice. For OAuth apps, this is already covered as `[OpenAI]` in B2-6. Downgraded to avoid double-counting and because non-OAuth apps have no platform enforcement mechanism here |
| G4 | **Keep third-party dependencies patched** to mitigate supply chain risks | `[Recommended]` | Security & Privacy: Operational readiness |
| G5 | **Rate limit and abuse-protect all backend tool endpoints** — not just OAuth endpoints | `[Recommended]` | Security & Privacy: "Monitor for anomalous traffic patterns" and "Defense in depth". B2-12 covers OAuth endpoints specifically; this covers general tool API endpoints |

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
| H2b | **App description must accurately represent functionality** — no misleading claims about what the app does at the store listing level | `[OpenAI]` | App Submission Guidelines: "App names and descriptions must be clear, accurate, and easy to understand." Distinct from tool description accuracy (J items) — applies to the public store listing |
| H3 | **Screenshots must accurately represent functionality** and comply with required dimensions | `[OpenAI]` | **NEW** — App Submission Guidelines |
| H4 | **Apps must function correctly on both ChatGPT web and mobile clients** — reviewers test on both platforms | `[OpenAI]` | Common rejection reason from FAQs; reviewers will test on both platforms, not just web |
| H5 | **No unauthorized third-party connectors** — apps that primarily function as unofficial connectors to third-party services will not be approved | `[OpenAI]` | **NEW** — "We cannot approve apps that primarily function as unofficial connectors" |
| H6 | **EU data residency blocks submission** — projects with EU data residency on the OpenAI Platform cannot submit apps for review. Use a project with global data residency. **This is an OpenAI Platform project setting, independent of your hosting region (e.g., Render Frankfurt is fine).** Verify your OpenAI Platform org project is set to global before submitting | `[OpenAI]` | **NEW** — Submission Guide: "projects with EU data residency cannot submit apps for review". Directly relevant to Priority Guardian. |
| H7 | **Press release coordination** — before any public announcements or press releases regarding app launch, contact press@openai.com to coordinate with OpenAI communications team | `[Recommended]` | **NEW** — Submission Guide |

---

## I. MCP Server Implementation

| # | Requirement | Enforcer | Verification Notes |
|---|-------------|----------|-------------------|
| 61 | STDIO logging restriction — never write to stdout; use logging framework | `[Recommended]` | Best practice for MCP, not explicit OpenAI requirement |
| 62 | Proper User-Agent headers on all external API requests | `[Recommended]` | Best practice |
| 63 | Async error handling — wrap all async ops in try-catch | `[Recommended]` | No explicit try/catch requirement in SDK docs; general error-handling quality is `[OpenAI]` (A10), but the specific implementation pattern is not mandated |
| I1 | **Widget MIME type must be `text/html;profile=mcp-app`** | `[OpenAI]` | Required for widget rendering; host only enables MCP Apps bridge for this MIME type |
| I2 | **Structured payloads must be trimmed to what the model needs** — oversized payloads degrade performance | `[Recommended]` | MCP Server Guide: Troubleshooting |
| I3 | **`additionalProperties: false` in all tool INPUT_SCHEMA objects** — set at top level and all nested `type: object` definitions. Shown in all official examples | `[Recommended]` | OpenAI Reference shows it in examples but does not explicitly mandate it as a hard requirement. Treat as strong best practice — some client implementations may reject schemas without it (observed behavior, not a documented rule) |
| I4 | **Memory is off by default in apps** — ChatGPT memory is user-controlled and model-mediated; apps do not receive a memory feed. Tool inputs must be explicit and self-contained. Do not rely on memory for correctness-critical fields. For write or destructive actions, re-confirm intent and key parameters in the current turn | `[Recommended]` | Downgraded from `[OpenAI]` — MCP Server Guide presents this as "best practices" guidance, not as a submission rejection criterion. Treat as strong operational guidance for correctness |
| I5 | **`outputSchema` declared → must match** — if a tool declares `outputSchema`, the `structuredContent` returned must conform to it. Mismatch causes runtime validation failure. `outputSchema` is optional to declare but mandatory to match if declared | `[OpenAI]` | **NEW** — API Reference: "Must match the declared outputSchema, when provided" |

---

## J. Tool Annotations (CRITICAL OpenAI Requirement)

| # | Requirement | Enforcer | Verification Notes |
|---|-------------|----------|-------------------|
| 64 | Set `readOnlyHint: true` for tools that ONLY fetch/list/retrieve data and do not modify anything. **Omitting any annotation or leaving it `null` is a common cause of review rejection** — treat missing annotations as a bug | `[OpenAI]` | MCP Server Guide developer guidance: "treat it as a validation error" (not a platform enforcement statement). App Submission Guidelines: "Incorrect or missing action labels are a common cause of rejection" |
| 65 | Set `readOnlyHint: false` for tools that create/update/delete, trigger actions, or change state | `[OpenAI]` | Includes: send emails, run jobs, enqueue tasks, write logs, start workflows |
| 65b | Set `openWorldHint: true` for tools that write to or change publicly visible internet state | `[OpenAI]` | **CLARIFIED** — Posting to social media, sending emails/SMS, creating public tickets, publishing pages, pushing code to public endpoints |
| 65c | Set `openWorldHint: false` ONLY if tool operates entirely within closed/private systems. **Default behavior when unspecified is treated as `true` (open world)** — always set explicitly | `[OpenAI]` | MCP Server Guide: "Leave `true` for tools that can write to arbitrary URLs/files/resources" — implicit default is open world |
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
| J3 | **`idempotentHint`** — optional boolean annotation. Declare `true` when calling the tool with identical arguments has no additional effect on its environment (safe to retry). Use for read-only tools where retry safety is relevant | `[Recommended]` | **NEW** — API Reference lists as 4th optional annotation alongside readOnlyHint, destructiveHint, openWorldHint |

---

## K. Strongly Recommended

| # | Requirement | Enforcer | Notes |
|---|-------------|----------|-------|
| 71 | Semantic versioning and changelog | `[Recommended]` | |
| 72 | Document API rate limits for users | `[Recommended]` | |
| 73 | Technical diagram illustrating data flow | `[Recommended]` | |
| 74 | Support contact easily discoverable | `[Recommended]` | |
| 75 | Robust rate-limit error handling | `[Recommended]` | |
| 76 | API-key rotation policy (e.g., every 90 days) | `[Recommended]` | |
| 77 | Dependency vulnerability reviews and patching | `[Recommended]` | |
| 78 | Security testing/vulnerability scans in CI | `[Recommended]` | |
| K1 | **Standard `_meta.ui.*` keys preferred over OpenAI-specific aliases** — `_meta.ui.outputTemplate` preferred over `_meta["openai/outputTemplate"]`; `_meta.ui.csp` (camelCase) preferred over `_meta["openai/widgetCSP"]` (snake_case); `_meta.ui.domain` preferred over `_meta["openai/widgetDomain"]`. OpenAI-specific keys remain valid as compatibility aliases | `[Recommended]` | **NEW** — API Reference documents standard keys as preferred; OpenAI-specific keys work today but migrate forward |
| K2 | **`_meta.ui.visibility`** — optional string array (default `["model", "app"]`). Set to `["app"]` to make a tool callable from your widget UI but hidden from model selection. Useful for widget-initiated actions that should not be LLM-triggered | `[Recommended]` | **NEW** — API Reference |
| K3 | **`_meta["openai/widgetDescription"]`** — optional human-readable summary surfaced to the model when the component loads. Reduces redundant assistant narration after tool runs | `[Recommended]` | **NEW** — API Reference |
| K4 | **Tool invocation status text** — `_meta["openai/toolInvocation/invoking"]` (≤64 chars): shown while tool runs. `_meta["openai/toolInvocation/invoked"]` (≤64 chars): shown after completion. User-visible UX feedback during tool execution | `[Recommended]` | **NEW** — API Reference |
| K5 | **Widget URI cache-busting** — treat the widget URI as a cache key. When updating widget markup or bundle, version the URI (e.g., `?v=2` or path change). Stale widgets will persist in ChatGPT until URI changes or user clears cache via Settings | `[Recommended]` | **NEW** — MCP Server Guide operational note. Operationally critical post-submission |
| K6 | **`_meta.ui.prefersBorder`** — optional boolean hint on the resource template. Set to `true` to render the widget inside a bordered card when the host supports it. Alias: `_meta["openai/widgetPrefersBorder"]` | `[Recommended]` | API Reference > Component resource `_meta` fields |
| K7 | **Company Knowledge compatibility** — implement `search` and `fetch` tools with the exact MCP input schema signatures to make your app eligible as a Company Knowledge source in ChatGPT Business/Enterprise/Edu. Mark all other read-only tools with `readOnlyHint: true`. This is a significant distribution opportunity for apps with proprietary data | `[Recommended]` | MCP Server Guide: "Company knowledge in ChatGPT can call any read-only tool in your app" — only apps implementing exact `search`/`fetch` schemas are included as sources |

---

# Summary by Enforcer

| Enforcer | Count | Impact |
|----------|-------|--------|
| `[OpenAI]` | **~51** | **Blocks submission** — source uses "must"/"must not"/explicit prohibition |
| `[OpenAI Guideline]` | 3 | **Review risk** — enforcement section or "avoid" language, not guaranteed blockers (D5, F2, 13c) |
| `[OpenAI UI Guideline]` | 3 | **Likely scrutinized** — "don't" language in UI guidelines |
| `[Sandbox]` | 2 | **App will fail** — iframe sandbox blocks cookies and privileged browser APIs |
| `[Google]` | ~14 | **Blocks OAuth verification** — only for apps using Google APIs |
| `[GDPR]` | ~15 | **Legal risk** — required for EU/DE market, not platform-enforced |
| `[Recommended]` | ~26 | **Speeds approval** — defer if time-constrained (added B2-11, G1, G5) |

> **Note:** OpenAI blockers increased from ~17 (Dec 2024) to ~51 due to: data minimization section, commerce restrictions, tool annotations, inbound OAuth (B2), EU data residency, redirect URIs, outputSchema validation. `[OpenAI Guideline]` tier added March 2026 (3 items: D5, F2, 13c). `[Recommended]` count reflects all downgrades from `[OpenAI]`: I4, F3, I63, G3, B2-11, G1, G2.

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
| **OAuth redirect URIs** | New production format `chatgpt.com/connector/oauth/{callback_id}` + review URI `platform.openai.com/apps-manage/oauth` must both be allowlisted | **CRITICAL** — missing review URI blocks reviewer auth |
| **EU data residency** | OpenAI Platform project must be global (not EU) to submit | **CRITICAL** — blocks submission entirely |
| **Memory off by default** | Tools must be self-contained; no reliance on memory for correctness | **MEDIUM** — affects tool input design |
| **outputSchema validation** | If declared, structuredContent must conform | **MEDIUM** — runtime validation failure if mismatched |
| **Standard `_meta.ui.*` keys** | Preferred over OpenAI-specific aliases going forward | **LOW** — backward compatible today |

---

# Priority Guardian Suite — Specific Blockers

## ALL PG apps: MUST fix before submission

**Before submitting:** Re-verify the 10 source URLs in the Source Documents section against the live pages. Takes ~30 minutes. OpenAI updates these silently. Flag any mismatch before committing to the submission.

**OpenAI Blockers (submission-blocking):**
- [ ] `_meta["openai/outputTemplate"]` on all tools returning widgets
- [ ] `_meta.ui.domain` — unique dedicated origin per app
- [ ] Register widget resources in MCP server with `text/html;profile=mcp-app`
- [ ] CSP defined (`connectDomains` + `resourceDomains`) — **submission prerequisite** (A13)
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
- [ ] Redirect URIs allowlisted: new production `https://chatgpt.com/connector/oauth/{callback_id}` + review `https://platform.openai.com/apps-manage/oauth`
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
- [ ] `additionalProperties: false` in all INPUT_SCHEMA objects (top-level AND nested) — strong best practice, enforced by some clients

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
- [ ] No `window.alert`, `window.prompt`, `window.confirm`, `navigator.clipboard` calls in widget code
- [ ] All fetch requests comply with CSP

## PG Calendar apps (Google OAuth): ALSO fix

- [ ] All Section B items (14–27)
- [ ] Google OAuth verification completed
- [ ] Test credentials with NO MFA requirement
- [ ] OpenAI Platform project set to **global data residency** (not EU) before submitting (H6)

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
- **Authentication Guide** — developers.openai.com/apps-sdk/build/auth/ *(added 04 March 2026)*
