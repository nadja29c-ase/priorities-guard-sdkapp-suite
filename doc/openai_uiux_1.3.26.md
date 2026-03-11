# OpenAI SDK App UI & UX Requirements

**Version:** 1.4 — Updated March 2026
**Previous version:** 1.3.26
**Verified against:** OpenAI Apps SDK Documentation — live docs cross-referenced March 2026
**Sources:** UI Guidelines, UX Principles, App Submission Guidelines, API Reference, Security & Privacy, Submit your app guide, Design Components, State Management, Build ChatGPT UI, Monetize your app

> **⚠️ URL NOTE:** `/apps-sdk/app-submission-guidelines/` and `/apps-sdk/app-developer-guidelines` currently resolve to the same content. Monitor for divergence on next review cycle.

---

## What Changed in v1.4

| Item | Change | Why |
|------|--------|-----|
| #1 | `_meta.ui.resourceUri` clarified as MCP Apps standard; `openai/outputTemplate` is ChatGPT compat alias | Framing shift in live Define Tools doc |
| #6b | NEW — additional sandbox-blocked browser APIs | Confirmed in Security & Privacy docs |
| #9b | NEW — CSP (`connectDomains`, `resourceDomains`) required for widget app submission | Confirmed in Submit your app guide |
| #9c | NEW — OpenAI Platform project must use **global** data residency (not EU) | Submission blocker, confirmed in Submit your app guide |
| #14–17 | Tool annotations upgraded: now explicitly **Required** per API Reference, not just "common rejection cause" | API Reference table marks all three as Required |
| #20b | NEW — `idempotentHint` annotation documented | API Reference |
| #20c | NEW — `outputSchema` / `structuredContent` conformance requirement | API Reference |
| #20d | NEW — retry-safe tool behavior requirement | App Submission Guidelines |
| #29b | NEW — Regulated sensitive/special category data clause | App Submission Guidelines: Privacy |
| #30 | Updated — clarified location side channel (`_meta["openai/userLocation"]`) | App Submission Guidelines |
| #37b | NEW — No unauthorized third-party scraping or unofficial connectors | App Submission Guidelines: Third-party content |
| #37c | NEW — Press release coordination required before public announcement | Submit your app guide |
| #78–80 | Note added: `window.openai` is a compatibility layer; MCP Apps bridge is primary for new apps | Build ChatGPT UI doc |
| Source table | Added: Monetize your app, Build ChatGPT UI | New pages in live docs |

---

## Category Definitions

| Category | Meaning | Source Language |
|----------|---------|-----------------|
| **MUST** | Submission blocker — will cause rejection | "will be rejected", "must", "expected to", sandbox enforced |
| **UI Guideline** | Explicit prohibition — likely scrutinized in review | "Don't", "Do not", "must not", explicit "avoid" with prohibition tone |
| **Recommended** | Best practice — improves approval odds | "Rules of thumb", "should", "avoid" (guidance tone) |

---

## MUST — Submission Blockers

### Technical Requirements

| # | Requirement | Source |
|---|-------------|--------|
| 1 | `_meta.ui.resourceUri` on every tool returning UI — this is the MCP Apps standard field. ChatGPT also honors `_meta["openai/outputTemplate"]` as a backwards-compat alias; do not rely on alias alone for cross-host portability | API Reference + Define Tools guide |
| 2 | Widget files registered in MCP resource manifest with MIME type `text/html;profile=mcp-app` | MCP Server Guide — host only enables MCP Apps bridge for this MIME type |
| 3 | `_meta.ui.domain` — dedicated origin, unique per app | API Reference — "required for app submission; must be unique per app" |
| 4 | Error handling with clear, user-readable messages on all 4xx/5xx | "Errors...must be well-handled with clear messaging or fallback behaviors" |
| 5 | No crashes, hangs, or inconsistent behavior | "Apps that crash, hang, or show inconsistent behavior will be rejected" |
| 6 | No browser cookies | Sandbox constraint — technically blocked in iframe |
| 6b | Additional sandbox-blocked APIs: `window.alert`, `window.prompt`, `window.confirm`, `navigator.clipboard` — widgets cannot access privileged browser APIs | Security & Privacy docs |
| 7 | Production-ready — no trial or demo submissions | "Any app submitted as a trial or demo will not be accepted" |
| 8 | Test cases must pass on both ChatGPT web AND mobile apps | Submit your app guide — common rejection reason |
| 9 | Developer verification via OpenAI Platform Dashboard | "All submissions must come from verified individuals or organizations" |
| 9b | CSP defined (`connectDomains`, `resourceDomains`) — required for widget apps at submission | Submit your app guide: "You defined a content security policy (CSP) to allow the exact domains you fetch from (this is required to submit your app for security reasons)" |
| 9c | **OpenAI Platform project must use global data residency — EU data residency projects cannot submit apps** | Submit your app guide: "projects with EU data residency cannot submit apps for review. Please use a project with global data residency" |

### Accessibility

| # | Requirement | Source |
|---|-------------|--------|
| 10 | Keyboard navigation — all interactive elements reachable | App Developer Guidelines: "accessible via keyboard" |
| 11 | Screen reader support — proper semantics, ARIA labels | App Developer Guidelines: "accessible via...screen readers" |
| 12 | Readable contrast in light/dark modes — must meet minimum contrast ratios (WCAG AA) | UI Guidelines: "minimum contrast ratio (WCAG AA)" |
| 13 | Text scaling — UI must not break when text size increases | UI Guidelines: "Support text resizing without breaking layouts" |

### Tool Annotations (**Required** — Common Rejection Cause)

> API Reference now marks `readOnlyHint`, `destructiveHint`, and `openWorldHint` as **Required** fields, not optional. Missing or incorrect values are a leading rejection reason.

| # | Requirement | Source |
|---|-------------|--------|
| 14 | `readOnlyHint: true` for tools that ONLY fetch/list/retrieve data and do not modify anything | API Reference: Required field |
| 15 | `readOnlyHint: false` for tools that create/update/delete, trigger actions, or change state | API Reference: Required field |
| 16 | `destructiveHint: true` for tools with irreversible outcomes (delete, overwrite, send, revoke) — justification must describe what is irreversible and under what conditions | API Reference: Required field + App Submission Guidelines |
| 17 | `openWorldHint: true` for tools that write to publicly visible internet state (posting, emailing, uploading) | API Reference: Required field + App Submission Guidelines |
| 18 | Detailed justification for each annotation at submission, including irreversibility descriptions and safeguards | "provide a detailed justification for each at submission time" |
| 19 | Tool names: human-readable, verb-based, unique within app, no promotional/comparative language (e.g. no `pick_me`, `best`, `official`) | App Submission Guidelines |
| 20 | Tool descriptions: accurate, no misleading language, no manipulation of model selection, no overly-broad triggering beyond explicit user intent | App Submission Guidelines — fair play requirement |
| 20b | `idempotentHint: true` for tools safe to retry with the same arguments (no extra effect on environment) — optional but recommended for read-only tools | API Reference |
| 20c | If `outputSchema` is declared on a tool, `structuredContent` must conform to it — mismatch causes runtime validation failure | API Reference |
| 20d | Tools should be safe to retry where possible; if retries may cause repeated effects (e.g. duplicate writes), the tool must clearly indicate this | App Submission Guidelines |

### Content & Commerce Rules

| # | Requirement | Source |
|---|-------------|--------|
| 21 | **No advertisements** — apps must not serve ads or exist primarily as advertising vehicles | App Submission Guidelines: "Apps must not serve advertisements" |
| 22 | **No digital sales** — no subscriptions, digital content, tokens, credits (direct or indirect, including freemium upsells) | App Submission Guidelines: "Selling digital products or services...is not allowed" |
| 23 | **Physical goods only** — if commerce is involved, direct users to complete purchases on your own domain via external checkout | App Submission Guidelines. Note: OpenAI has signaled intent to expand commerce support beyond physical goods in future. |
| 23b | **No embedded third-party checkout** — no third-party checkout solutions embedded or hosted within the app experience | App Submission Guidelines: "No other third-party checkout solutions may be embedded or hosted within the app experience" |
| 24 | **Age-appropriate** — suitable for general audiences including users 13–17; no explicit targeting of children under 13 | App Submission Guidelines: Safety |
| 25 | **App name clear, non-generic** — avoid single-word dictionary terms not tied to your brand | App Submission Guidelines |

### Data Minimization (Enforceable)

| # | Requirement | Source |
|---|-------------|--------|
| 27 | Tool inputs: narrowly scoped, specific to task, no "just in case" fields — design schema to limit data collection by default | App Submission Guidelines: "Design the input schema to limit data collection by default" |
| 28 | Tool responses: return ONLY user-relevant data. No session IDs, trace IDs, timestamps, internal identifiers in any tool response | App Submission Guidelines — common rejection reason |
| 29 | No PCI data, PHI, government IDs (e.g. SSN), or access credentials (API keys, MFA/OTP codes, passwords) in any tool flow | App Submission Guidelines: restricted data categories |
| 29b | **Regulated sensitive/special category data** — do not collect data considered "sensitive" or "special category" in the jurisdiction of collection unless: (a) strictly necessary, (b) user has given legally adequate consent, (c) collection is clearly disclosed at or before point of collection | App Submission Guidelines: Privacy > Regulated Sensitive Data |
| 30 | No raw location fields (e.g. city, GPS coordinates, addresses) in tool input schema. When location is needed, obtain via client's controlled side channel such as `_meta["openai/userLocation"]` (environment metadata) | App Submission Guidelines: "Avoid requesting raw location fields" |
| 31 | No chat log reconstruction from tool inputs | App Submission Guidelines: "must not pull, reconstruct, or infer the full chat log" |
| 31b | **No full conversation history in tool inputs** — tool inputs must not request or accept raw chat transcripts or broad contextual fields. A tool may request a brief, task-specific user intent field ONLY when it meaningfully improves execution | App Submission Guidelines |

### Metadata & Submission

| # | Requirement | Source |
|---|-------------|--------|
| 32 | Published privacy policy disclosing ALL data categories returned by tools | App Submission Guidelines + Submit your app guide |
| 33 | Support contact details visible in store listing, kept accurate and up to date | "You must provide customer support contact details" |
| 34 | Demo account credentials for authenticated apps — provide a fully-featured demo account with sample data; no MFA, no SMS verification, no extra sign-up or onboarding steps | Submit your app guide: "provide a login and password for a fully-featured demo account...Apps requiring any additional steps for login...will be rejected" |
| 35 | App name and description clear, accurate, non-misleading | App Submission Guidelines |
| 36 | Screenshots must accurately represent functionality and conform to required dimensions | App Submission Guidelines |
| 37 | Original IP only — no copycat designs, impersonation, or implying OpenAI endorsement | "Do not engage in misleading or copycat designs, impersonation" |
| 37b | **No unauthorized third-party scraping or unofficial connectors** — do not scrape external websites, relay queries, or integrate with third-party APIs without proper authorization and compliance with that party's terms | App Submission Guidelines: Third-party content |
| 37c | **Press release coordination** — before issuing any press releases or public announcements about your app launch, contact press@openai.com first | Submit your app guide |

---

## UI Guidelines — Explicit "Don't" Language

These use explicit prohibition language and will likely be scrutinized in review:

| # | Requirement | Source Quote |
|---|-------------|--------------|
| 38 | **No custom fonts** — inherit system font stack | "Don't use custom fonts, even in full screen modes. Use system font variables wherever possible." |
| 39 | **No logos in widget responses** | "Do not include your logo as part of the response. ChatGPT will always append your logo and app name." |
| 40 | **No custom gradients/patterns breaking ChatGPT look** | "Avoid custom gradients or patterns that break ChatGPT's minimal look" |
| 41 | **No colors on backgrounds in text areas** | "Don't apply colors to backgrounds in text areas" |
| 42 | **No text color changes or core component style overrides** | "Don't change text colors or other core component styles" |
| 43 | **No deep navigation within cards** — no drill-ins, tabs, or deeper navigation | "No deep navigation or multiple views within a card. Cards should not contain multiple drill-ins, tabs, or deeper navigation." |
| 44 | **No duplicative inputs or replication of ChatGPT system functions** (e.g., input composer) | UI Guidelines: "No duplicative inputs. Don't replicate ChatGPT features in a card." + UX Principles: "Duplicating ChatGPT's system functions" in avoid list |
| 45 | **No nested scrolling** — cards should auto-fit content | "No nested scrolling. Cards should auto-fit their content and prevent internal scrolling." |
| 46 | **`frameDomains` triggers extra review scrutiny** — avoid unless core to experience; these apps are often not approved for broad distribution | App Submission Guidelines: "often not approved for broad distribution" |

---

## Display Modes — Rules & Constraints

### Inline Card

| # | Rule | Category |
|---|------|----------|
| 47 | Limit primary actions to 2 per card (1 primary CTA + 1 optional secondary) | `Recommended` |
| 48 | Place primary actions at bottom of card | `Recommended` |
| 49 | Actions should perform either a conversation turn or a tool call | `Recommended` |
| 50 | Card layout can expand height up to mobile viewport height | `Recommended` |
| 51 | No deep navigation or multiple views within a card | `UI Guideline` |
| 52 | No nested scrolling — auto-fit content | `UI Guideline` |

### Inline Carousel

| # | Rule | Category |
|---|------|----------|
| 53 | 3–8 items per carousel for scannability | `Recommended` |
| 54 | Each card: single optional CTA (e.g., "Book" or "Play") | `Recommended` |
| 55 | Items should always include an image or visual | `Recommended` |
| 56 | Reduce metadata to most relevant details, 3 lines max | `Recommended` |
| 57 | Consistent visual hierarchy across cards | `Recommended` |

### Fullscreen

| # | Rule | Category |
|---|------|----------|
| 58 | Design UX to work WITH the system composer (always present) | `Recommended` |
| 59 | Use fullscreen to deepen engagement, not replicate native app wholesale | `Recommended` |
| 60 | Navigation elements must stay visible during launcher/fullscreen transitions | `Recommended` |

### Picture-in-Picture (PiP)

| # | Rule | Category |
|---|------|----------|
| 61 | PiP state must update/respond when users interact via system composer | `Recommended` |
| 62 | Close PiP automatically when session ends | `Recommended` |
| 63 | Do not overload PiP with controls or static content better suited for inline/fullscreen | `Recommended` |

---

## Recommended — Rules of Thumb

### Color & Theming

| # | Recommendation | Source |
|---|----------------|--------|
| 64 | Use system colors for text, icons, and spatial elements like dividers | "Rules of thumb" |
| 65 | Brand accents only on primary buttons inside app display modes | "Rules of thumb" |
| 66 | Light/dark mode compatibility (match `color-scheme`) | UI Guidelines + Components guide |

### Typography

| # | Recommendation | Source |
|---|----------------|--------|
| 67 | Limit variation in font size — prefer body and body-small sizes | "Rules of thumb" |
| 68 | Use partner styling (bold, italic, highlights) only within content areas, not structural UI | "Rules of thumb" |

### Spacing & Layout

| # | Recommendation | Source |
|---|----------------|--------|
| 69 | Use system grid spacing for cards, collections, panels | "Rules of thumb" |
| 70 | Keep padding consistent, avoid cramming or edge-to-edge text | "Rules of thumb" |
| 71 | Respect system corner rounds for shape consistency | "Rules of thumb" |
| 72 | Maintain visual hierarchy: headline → supporting text → CTA | "Rules of thumb" |
| 73 | Responsive design — collapse gracefully on mobile (adaptive breakpoints) | Components guide |

### Icons & Imagery

| # | Recommendation | Source |
|---|----------------|--------|
| 74 | Use system icons or custom monochromatic/outlined iconography | "Rules of thumb" |
| 75 | All imagery must follow enforced aspect ratios | "Rules of thumb" |
| 76 | Provide alt text for all images | UI Guidelines: Accessibility |

### State Management

> **⚠️ Architecture note (v1.4):** `window.openai` is now documented as a ChatGPT-specific **compatibility layer**, not the primary API surface. New apps should be built against the MCP Apps bridge (JSON-RPC 2.0 over postMessage: `ui/notifications/tool-result`, `tools/call`, `ui/message`, `ui/update-model-context`). `window.openai` APIs remain valid in ChatGPT but should not be relied on for cross-host MCP Apps portability.

| # | Recommendation | Source |
|---|----------------|--------|
| 77 | Avoid localStorage for core state — prefer widgetState or backend | "Avoid using localStorage for core state" — guidance, not prohibition |
| 78 | Use `window.openai.setWidgetState()` for UI-only state persistence (ChatGPT-specific; use MCP Apps bridge for cross-host portability) | Optional ChatGPT extension |
| 79 | Add try/catch around `window.openai.toolOutput` with fallback | Best practice |
| 80 | Use `ui/update-model-context` when model needs to see UI state changes | State Management docs — this is the MCP Apps standard method |

### Content & Tone

| # | Recommendation | Source |
|---|----------------|--------|
| 81 | Keep content concise and scannable | UX Principles |
| 82 | Context-driven responses — avoid irrelevant or extraneous information | UX Principles |
| 83 | Avoid jargon or promotional language | UX Principles |
| 84 | Proactive nudges only when tied to user intent | UX Principles |
| 85 | Avoid long-form or static content better suited for a website | UX Principles: "avoid" checklist |
| 86 | Avoid complex multi-step workflows exceeding display modes | UX Principles: "avoid" checklist |

---

## Quick Reference: The "Don'ts"

### Hard Don'ts (Will Block Submission)

1. ❌ Browser cookies (sandbox blocked)
2. ❌ Privileged browser APIs: `window.alert`, `window.prompt`, `window.confirm`, `navigator.clipboard` (sandbox blocked)
3. ❌ Missing CSP (`connectDomains`, `resourceDomains`) — required for widget apps
4. ❌ EU data residency project — must use global data residency to submit
5. ❌ Crashes or silent errors
6. ❌ Missing or mismatched tool annotations (`readOnlyHint`, `destructiveHint`, `openWorldHint` are Required)
7. ❌ Advertisements
8. ❌ Digital product sales (subscriptions, tokens, credits)
9. ❌ Embedded third-party checkout inside the app
10. ❌ Trial/demo submissions
11. ❌ Undisclosed data types in tool responses
12. ❌ Missing `_meta.ui.domain`
13. ❌ Test cases failing on mobile
14. ❌ Chat log reconstruction from tool inputs
15. ❌ Unauthorized third-party scraping or unofficial connectors

### UI Guideline Don'ts (Likely Scrutinized)

1. ❌ Custom fonts
2. ❌ Logos inside widget responses
3. ❌ Custom gradients breaking ChatGPT look
4. ❌ Background colors in text areas
5. ❌ Text color overrides on core components
6. ❌ Deep navigation within cards
7. ❌ Nested scrolling in cards
8. ❌ Duplicative inputs or replication of ChatGPT system functions
9. ❌ `frameDomains` (unless absolutely core to experience)

### Soft Don'ts (Guidance)

1. ⚠️ localStorage for core state (discouraged, not banned)
2. ⚠️ More than 2 primary actions per card
3. ⚠️ Hardcoded colors breaking system themes
4. ⚠️ Overloaded cards with too much content
5. ⚠️ Replicating native app wholesale in fullscreen
6. ⚠️ Sensitive/private info visible in inline cards
7. ⚠️ Upsell messaging or irrelevant nudges in widgets

---

## Known Gotchas & Implementation Notes

| # | Note |
|---|------|
| G1 | **SVG inline styles — CSS variable names ≠ Tailwind class names.** When using CSS variables in SVG `<text>` or other SVG elements via `style={{ fill: 'var(--...)' }}`, always verify the exact token name against the reference doc. Tailwind class `text-default` maps to CSS variable `--color-text` (not `--color-text-default`). An invalid variable name silently resolves to nothing and the browser falls back to inherited color (black), which breaks dark mode. |

---

## Design System Reference

OpenAI provides the [Apps SDK UI](https://openai.github.io/apps-sdk-ui/) design system with:
- Tailwind CSS styling foundations
- CSS variable design tokens
- Accessible component library
- [Figma component library](https://www.figma.com/community/file/1560064615791108827/apps-in-chatgpt-components-templates)

Using Apps SDK UI is **not required** but recommended for native ChatGPT look and feel.

---

## Source Documents (March 2026)

| Document | URL |
|----------|-----|
| UI Guidelines | developers.openai.com/apps-sdk/concepts/ui-guidelines/ |
| UX Principles | developers.openai.com/apps-sdk/concepts/ux-principles/ |
| App Submission Guidelines | developers.openai.com/apps-sdk/app-submission-guidelines/ |
| App Developer Guidelines | developers.openai.com/apps-sdk/app-developer-guidelines/ |
| API Reference | developers.openai.com/apps-sdk/reference/ |
| Security & Privacy | developers.openai.com/apps-sdk/guides/security-privacy/ |
| Submit your app | developers.openai.com/apps-sdk/deploy/submission/ |
| Design Components | developers.openai.com/apps-sdk/plan/components/ |
| State Management | developers.openai.com/apps-sdk/build/state-management/ |
| Build ChatGPT UI | developers.openai.com/apps-sdk/build/chatgpt-ui/ |
| MCP Server Guide | developers.openai.com/apps-sdk/build/mcp-server/ |
| Monetize your app | developers.openai.com/apps-sdk/build/monetization/ |
| Authentication | developers.openai.com/apps-sdk/build/auth/ |
| Define Tools | developers.openai.com/apps-sdk/plan/tools/ |
