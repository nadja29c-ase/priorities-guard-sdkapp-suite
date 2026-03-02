# OpenAI SDK App UI & UX Requirements

**Verified against:** OpenAI Apps SDK Documentation — March 2026
**Sources:** UI Guidelines, UX Principles, App Submission Guidelines, API Reference, Security & Privacy, Submission FAQs

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
| 1 | `_meta["openai/outputTemplate"]` (or `_meta.ui.outputTemplate` / `_meta.ui.resourceUri`) on every tool returning UI | API Reference |
| 2 | Widget files registered in MCP resource manifest with MIME type `text/html;profile=mcp-app` | MCP Server Guide — host only enables MCP Apps bridge for this MIME type |
| 3 | `_meta.ui.domain` — dedicated origin, unique per app | API Reference — "required for app submission; must be unique per app" |
| 4 | Error handling with clear, user-readable messages on all 4xx/5xx | "Errors...must be well-handled with clear messaging or fallback behaviors" |
| 5 | No crashes, hangs, or inconsistent behavior | "Apps that crash, hang, or show inconsistent behavior will be rejected" |
| 6 | No browser cookies | Sandbox constraint — technically blocked in iframe |
| 7 | Production-ready — no trial or demo submissions | "Any app submitted as a trial or demo will not be accepted" |
| 8 | Test cases must pass on both ChatGPT web AND mobile apps | Submission FAQs — common rejection reason |
| 9 | Developer verification via OpenAI Platform Dashboard | "All submissions must come from verified individuals or organizations" |

### Accessibility

| # | Requirement | Source |
|---|-------------|--------|
| 10 | Keyboard navigation — all interactive elements reachable | Developer Guidelines: "accessible via keyboard" |
| 11 | Screen reader support — proper semantics, ARIA labels | Developer Guidelines: "accessible via...screen readers" |
| 12 | Readable contrast in light/dark modes — must meet minimum contrast ratios per accessibility guidelines (WCAG AA recommended) | UI Guidelines: "minimum contrast ratio (WCAG AA)" |
| 13 | Text scaling — UI must not break when text size increases | UI Guidelines: "Support text resizing without breaking layouts" |

### Tool Annotations (Common Rejection Cause)

| # | Requirement | Source |
|---|-------------|--------|
| 14 | `readOnlyHint: true` for tools that ONLY fetch/list/retrieve data | "Incorrect or missing action labels are a common cause of rejection" |
| 15 | `readOnlyHint: false` for tools that create/update/delete, trigger actions, or change state | Submission FAQs — detailed guidance |
| 16 | `destructiveHint: true` for tools with irreversible outcomes (delete, overwrite, send, revoke) | App Submission Guidelines + Submission FAQs |
| 17 | `openWorldHint: true` for tools that write to publicly visible internet state | App Submission Guidelines + Submission FAQs |
| 18 | Detailed justification for each annotation at submission, including irreversibility descriptions and safeguards | "provide a detailed justification for each at submission time" |
| 19 | Tool names: human-readable, verb-based, unique, no promotional/comparative language | App Submission Guidelines |
| 20 | Tool descriptions: accurate, no misleading language, no manipulation of model selection | App Submission Guidelines — fair play requirement |

### Content & Commerce Rules

| # | Requirement | Source |
|---|-------------|--------|
| 21 | **No advertisements** — apps must not serve ads or exist primarily as advertising vehicles | App Submission Guidelines: "Apps must not serve advertisements" |
| 22 | **No digital sales** — no subscriptions, digital content, tokens, credits (direct or indirect) | App Submission Guidelines: commerce restrictions |
| 23 | **Physical goods only** — if commerce is involved, external checkout on your own domain | App Submission Guidelines |
| 23b | **No embedded third-party checkout** — no third-party checkout solutions embedded or hosted within the app experience | App Submission Guidelines: "No other third-party checkout solutions may be embedded or hosted within the app experience" |
| 24 | **Age-appropriate** — suitable for general audiences including users 13–17 | App Submission Guidelines: Safety |
| 25 | **App name clear, non-generic** — avoid single-word dictionary terms not tied to your brand | App Submission Guidelines |

### Data Minimization (Enforceable)

| # | Requirement | Source |
|---|-------------|--------|
| 27 | Tool inputs: narrowly scoped, specific to task, no "just in case" fields | App Submission Guidelines: "Design the input schema to limit data collection by default" |
| 28 | Tool responses: return ONLY user-relevant data. No session IDs, trace IDs, timestamps, internal identifiers | Submission FAQs — common rejection reason |
| 29 | No PCI data, PHI, government IDs, or access credentials in any tool flow | App Submission Guidelines: restricted data categories |
| 30 | No raw location fields in tool input schema | App Submission Guidelines: "Avoid requesting raw location fields" |
| 31 | No chat log reconstruction from tool inputs | App Submission Guidelines: "must not pull, reconstruct, or infer the full chat log" |
| 31b | **No full conversation history in tool inputs** — tool inputs must not request or accept raw chat transcripts or broad contextual fields | App Submission Guidelines: tools may request "a brief, task-specific user intent field ONLY when it meaningfully improves execution" |

### Metadata & Submission

| # | Requirement | Source |
|---|-------------|--------|
| 32 | Published privacy policy disclosing ALL data categories returned by tools | App Submission Guidelines + Submission FAQs |
| 33 | Support contact details visible in store listing | "You must provide customer support contact details" |
| 34 | Demo account credentials for authenticated apps (no MFA, no SMS, no extra sign-up) | Submission FAQs: "Apps requiring any additional steps for login...will be rejected" |
| 35 | App name and description clear, accurate, non-misleading | App Submission Guidelines |
| 36 | Screenshots must accurately represent functionality | App Submission Guidelines |
| 37 | Original IP only — no copycat designs, impersonation | "Do not engage in misleading or copycat designs, impersonation" |

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
| 46 | **`frameDomains` triggers extra review scrutiny** — avoid unless core to experience | "Apps that declare frameDomains are subject to higher scrutiny...and are likely to be rejected" |

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

| # | Recommendation | Source |
|---|----------------|--------|
| 77 | Avoid localStorage for core state — prefer widgetState or backend | "Avoid using localStorage for core state" — guidance, not prohibition |
| 78 | Use `window.openai.setWidgetState()` for UI-only state persistence | Optional API feature |
| 79 | Add try/catch around `window.openai.toolOutput` with fallback | Best practice |
| 80 | Use `ui/update-model-context` when model needs to see UI state changes | State Management docs |

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
2. ❌ Crashes or silent errors
3. ❌ Missing or mismatched tool annotations
4. ❌ Advertisements
5. ❌ Digital product sales (subscriptions, tokens, credits)
6. ❌ Embedded third-party checkout inside the app
7. ❌ Trial/demo submissions
8. ❌ Undisclosed data types in tool responses
9. ❌ Missing `_meta.ui.domain`
10. ❌ Test cases failing on mobile
11. ❌ Chat log reconstruction from tool inputs

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
| API Reference | developers.openai.com/apps-sdk/reference/ |
| Security & Privacy | developers.openai.com/apps-sdk/guides/security-privacy/ |
| Submission FAQs | developers.openai.com/apps-sdk/deploy/submission/ |
| Design Components | developers.openai.com/apps-sdk/plan/components/ |
| State Management | developers.openai.com/apps-sdk/build/state-management/ |
| MCP Server Guide | developers.openai.com/apps-sdk/build/mcp-server/ |
| Authentication | developers.openai.com/apps-sdk/build/auth/ |
