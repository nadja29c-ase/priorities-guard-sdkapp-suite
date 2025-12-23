# Compliance Master Checklist â€” Labeled by Enforcer

**Legend:**
- `[OpenAI]` â€” Will block SDK app submission/approval (verified against official docs)
- `[OpenAI UI Guideline]` â€” Explicit UI guideline with "don't" language â€” likely scrutinized in review
- `[Sandbox]` â€” Technical limitation of iframe sandbox environment â€” will cause app to fail if violated
- `[Google]` â€” Will block Google OAuth verification (only applies to apps using Google APIs)
- `[GDPR]` â€” Legal risk for EU/DE market, not platform-enforced
- `[Recommended]` â€” Speeds approval or improves quality, not strictly required

**âš ï¸ VERIFIED: Dec 2024 against OpenAI Apps SDK official documentation (developers.openai.com)**
**âš ï¸ DOUBLE-CHECKED: Against external feedback â€” corrections applied**

---

## A. Technical & SDK Architecture

| # | Requirement | Enforcer | Verification Notes |
|---|-------------|----------|-------------------|
| 1 | Bundle each widget as one compiled HTML/JS file; no external CDNs or remote scripts | `[Recommended]` | Best practice from examples, not explicit requirement |
| 2 | Every backend tool that returns UI output must include `_meta.openai/outputTemplate` | `[OpenAI]` | API Reference confirms this |
| 3 | Register all widget files in your MCP server resource manifest | `[OpenAI]` | Required for widget rendering |
| 4 | Add try/catch around `window.openai.toolOutput` with friendly fallback text | `[Recommended]` | Best practice |
| 5 | Use `window.openai.setWidgetState()` for filters and toggles | `[Recommended]` | Optional API feature |
| 6 | Accessibility: keyboard focus, aria-labels, readable text | `[OpenAI]` | Implied by "accessible via keyboard and screen readers" |
| 7 | Manifest completeness: name, description, privacy-policy URL, support-email, developer identity | `[OpenAI]` | App Submission Guidelines confirms |
| 8 | Provide demo dataset for reviewers | `[OpenAI]*` | *Only for AUTHENTICATED apps â€” "fully-featured demo account" |
| 9 | Light/dark-mode compatibility and responsive design for mobile | `[Recommended]` | UX Guidelines recommends, not blocking |
| 10 | Catch all 4xx/5xx errors with readable messages | `[OpenAI]` | "Errors...must be well-handled with clear messaging" |
| 11 | Avoid localStorage/sessionStorage for core state; prefer widgetState or backend | `[Recommended]` | Docs say "Avoid using localStorage for **core state**" â€” guidance, not prohibition |
| 11b | Browser cookies blocked in iframe sandbox | `[Sandbox]` | "we still will not permit the storage or access to browser cookies, even with dedicated subdomains" |
| 12 | **Don't use custom fonts** â€” inherit system font stack | `[OpenAI UI Guideline]` | UI guidelines: "Don't use custom fonts, even in full screen modes. Always inherit the system font stack" |
| 13 | Component CSP configuration with connect_domains and resource_domains | `[Recommended]` | API Reference shows as optional `_meta` field |

> **Note:** `<form>` tags ARE allowed â€” OpenAI's state-management guide explicitly uses `<form>` in their React example.

---

## B. Google OAuth 2.0 & API Integration

> **Note:** This entire section only applies to apps using Google APIs (Focused, Done). **Skip for Clarity.**

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
| 25 | Log anonymized technical events only; no tokens or user data; retain â‰¤30 days | `[Google]` + `[GDPR]` |
| 26 | Sensitive-scope justification PDF explaining why scope is needed | `[Google]` |
| 27 | Google branding compliance screenshots in verification package | `[Google]` |

---

## C. Privacy, Data Protection & Legal

| # | Requirement | Enforcer | Verification Notes |
|---|-------------|----------|-------------------|
| 28 | Publish privacy policy describing: data accessed, why, how long stored, how to revoke/delete | `[OpenAI]` | "Submissions must include a clear, published privacy policy" |
| 29 | Host infrastructure in EU region (e.g., AWS Frankfurt) | `[GDPR]` | Your policy decision, not OpenAI-mandated |
| 30 | Implement unified consent-revocation mechanism | `[GDPR]` | Best practice, not platform-enforced |
| 31 | Disclosure for AI-generated content: "Generated by AI â€“ may contain errors" | `[Recommended]` | Good practice, not explicitly required |
| 32 | Data Protection Impact Assessment (DPIA) | `[GDPR]` | Legal requirement, not OpenAI-enforced |
| 33 | Data-subject rights workflow (access, correction via support email) | `[GDPR]` | Legal requirement, not OpenAI-enforced |
| 34 | Records of Processing Activities (ROPA) â€” internal document | `[GDPR]` | Legal requirement, not OpenAI-enforced |
| 35 | Data-use disclosure inside app | `[Recommended]` | Good UX, not required |
| 36 | Terms of Use and visible support email or Impressum (for DE market) | `[GDPR]` | German legal requirement |
| 37 | Keep audit logs of access and deletion actions | `[GDPR]` | Best practice for compliance |
| 38 | Data-deletion mechanism (MCP tool or support email) | `[OpenAI]` | "Respect deletion requests promptly" â€” NO `data_deletion_url` field required |
| 39 | Privacy Policy available in target languages (EN + DE) | `[GDPR]` | Legal requirement for German market |
| 40 | Incident response plan (breach notification) â€” internal document | `[GDPR]` | Legal requirement, not OpenAI-enforced |

---

## D. UX & User Experience

| # | Requirement | Enforcer |
|---|-------------|----------|
| 41 | Pre-connection notice explaining what app accesses | `[Recommended]` |
| 42 | Clear placeholders for empty/loading states | `[Recommended]` |
| 43 | All UI components accessible via keyboard and screen readers | `[OpenAI]` |
| 44 | Avoid using Google or OpenAI logos; follow branding rules | `[Google]` + `[OpenAI]` |
| 45 | Manual "Refresh" button for user control | `[Recommended]` |
| 46 | Tooltips or help text explaining permissions | `[Recommended]` |
| 47 | Localized interface and consent texts (EN + DE) | `[GDPR]` |

---

## E. Security & Infrastructure

| # | Requirement | Enforcer |
|---|-------------|----------|
| 48 | HTTPS everywhere; encrypt data in transit and at rest | `[OpenAI]` + `[GDPR]` |
| 49 | Encrypt OAuth tokens (AES-256 or stronger) at rest | `[GDPR]` |
| 50 | Document data-retention and deletion schedule | `[GDPR]` |
| 51 | No API keys in client-side code; credentials server-side only | `[OpenAI]` |
| 52 | Incident response plan (breach handling) | `[GDPR]` |

---

## F. App Store Submission & Operational Readiness

| # | Requirement | Enforcer | Verification Notes |
|---|-------------|----------|-------------------|
| 53 | Prepare functional demo video showing key flows | `[Recommended]` | Helpful but not required per official docs |
| 54 | Supply test credentials for reviewers | `[OpenAI]*` | *ONLY for authenticated apps: "provide a login and password for a fully-featured demo account" |
| 55 | Reviewer Testing Guide with login steps and expected behavior | `[Recommended]` | Best practice |
| 56 | Disclose if app triggers paid GPT-4 calls | `[Recommended]` | Good practice |
| 57 | Support contact information visible in store listing | `[OpenAI]` | "You must provide customer support contact details" |
| 58 | Rate-limit handling and error UX prevent freezes/blank states | `[OpenAI]` | "Apps should not crash, hang, or show inconsistent behavior" |
| 59 | No beta/trial/demo submissions â€” must be production-ready | `[OpenAI]` | "Apps submitted as betas, trials, or demos will not be accepted" |
| 60 | Original IP only â€” no copycat designs, impersonation, unauthorized third-party IP | `[OpenAI]` | "Do not engage in misleading or copycat designs, impersonation" |

---

## G. MCP Server Implementation

| # | Requirement | Enforcer | Verification Notes |
|---|-------------|----------|-------------------|
| 61 | STDIO logging restriction â€” never write to stdout; use logging framework | `[Recommended]` | Best practice for MCP, not explicit OpenAI requirement |
| 62 | Proper User-Agent headers on all external API requests | `[Recommended]` | Best practice |
| 63 | Async error handling â€” wrap all async ops in try-catch | `[OpenAI]` | "Errors...must be well-handled with clear messaging or fallback behaviors" |

---

## H. Tool Annotations (CRITICAL OpenAI Requirement)

| # | Requirement | Enforcer | Verification Notes |
|---|-------------|----------|-------------------|
| 64 | Set `readOnlyHint: true` for tools that only read/list data | `[OpenAI]` | "Incorrect or missing action labels are a common cause of rejection" |
| 65 | Set `readOnlyHint: false` + `openWorldHint: true` for write/destructive tools | `[OpenAI]` | "Write or destructive tools...must be clearly marked" |
| 66 | Set `destructiveHint: true` for tools that delete/overwrite user data | `[OpenAI]` | Required per App Submission Guidelines |
| 67 | Provide detailed justification for each annotation at submission time | `[OpenAI]` | "provide a detailed justification for each at submission time" |
| 68 | Tool names must be human-readable, specific, descriptive, unique within app | `[OpenAI]` | "Tool names should be human-readable, specific, and descriptive" |
| 69 | Tool descriptions must accurately explain purpose; no misleading language | `[OpenAI]` | "If a tool's behavior is unclear...your app may be rejected" |
| 70 | Tool inputs must be minimal â€” no "just in case" fields | `[OpenAI]` | "Gather only the minimum data required" |

---

## I. Strongly Recommended

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
| `[OpenAI]` | ~17 | **Blocks submission** â€” fix before submitting |
| `[OpenAI UI Guideline]` | 1 | **Likely scrutinized** â€” "don't" language in guidelines |
| `[Sandbox]` | 1 | **App will fail** â€” iframe sandbox blocks cookies |
| `[Google]` | ~14 | **Blocks OAuth verification** â€” only for apps using Google APIs |
| `[GDPR]` | ~15 | **Legal risk** â€” required for EU/DE market, not platform-enforced |
| `[Recommended]` | ~16 | **Speeds approval** â€” defer if time-constrained |

---

# Key Corrections Applied

| Item | Was | Now | Evidence |
|------|-----|-----|----------|
| `<form>` tags | "Never use" | **REMOVED** | OpenAI state-management guide uses `<form>` in React example |
| localStorage | `[OpenAI]` prohibition | `[Recommended]` guidance | Docs say "Avoid for **core state**" not "never use" |
| Browser cookies | Unverified | `[Sandbox]` confirmed | "we still will not permit...browser cookies" (Set Up Server doc) |
| System fonts | `[Recommended]` | `[OpenAI UI Guideline]` | UI guidelines: "**Don't** use custom fonts" |
| `data_deletion_url` | Required | NOT required | No manifest field; MCP tool + support email sufficient |
| Demo dataset | Required for all | Required for **authenticated apps only** | "fully-featured demo account" for auth apps |

---

# Clarity-Specific Blockers

Since Clarity has **no Google OAuth**, filter out all `[Google]` items.

## MUST fix before submission (~15 items)

**OpenAI Blockers:**
- [ ] `_meta.openai/outputTemplate` on tools returning widgets
- [ ] Register widget resources in MCP server
- [ ] Accessibility (keyboard, ARIA)
- [ ] Manifest with name, description, privacy_policy_url, support_email
- [ ] Error handling with clear messages
- [ ] Published privacy policy
- [ ] Data-deletion mechanism (MCP tool or support email)
- [ ] Support contact visible
- [ ] No crashes/hangs/inconsistent behavior
- [ ] Production-ready (no beta/trial)
- [ ] Original IP only
- [ ] Async error handling

**Tool Annotations (CRITICAL):**
- [ ] `readOnlyHint: true` for read-only tools
- [ ] `destructiveHint: true` for delete tools
- [ ] Tool names human-readable and descriptive
- [ ] Tool inputs minimal
- [ ] Annotation justifications ready for submission

**UI Guideline:**
- [ ] Don't use custom fonts â€” inherit system font stack

**Sandbox Constraint:**
- [ ] Browser cookies blocked â€” use widgetState instead

## MUST fix before German market launch

- [ ] All GDPR items (C29-C40)
- [ ] Localization (EN + DE)

---

# Source Documents Verified

- `ChatGPT Apps SDK - Developer Guidelines.md`
- `ChatGPT Apps SDK - Official Developer Guidelines.md`
- `App submission guidelines` (developers.openai.com)
- `ChatGPT Apps SDK - API Reference.md`
- `ChatGPT Apps SDK - Security & Privacy.md`
- `ChatGPT Apps SDK - Set Up Your Server.md` â€” cookie restriction source
- `ChatGPT Apps SDK - Build a Custom UX.md`
- `ChatGPT Apps SDK - Examples.md`
- **Managing State guide** (developers.openai.com/apps-sdk/build/state-management) â€” disproved `<form>` prohibition
- **UI guidelines** (developers.openai.com/apps-sdk/concepts/ui-guidelines) â€” font requirements source