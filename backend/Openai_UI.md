# OpenAI SDK App UI Requirements

**Verified against:** OpenAI Apps SDK Documentation (December 2024)

---

## Category Definitions

| Category | Meaning | Source Language |
|----------|---------|-----------------|
| **MUST** | Submission blocker — will cause rejection | "will be rejected", "must", sandbox enforced |
| **UI Guideline** | Explicit prohibition — likely scrutinized | "Don't", "Do not", "must not" |
| **Recommended** | Best practice — improves approval odds | "Rules of thumb", "should", "avoid" |

---

## MUST — Submission Blockers

### Technical Requirements

| Requirement | Source |
|-------------|--------|
| `_meta.openai/outputTemplate` on every tool returning UI | API Reference |
| Widget files registered in MCP resource manifest | Developer Guidelines |
| Error handling with clear, user-readable messages | "Errors...must be well-handled with clear messaging or fallback behaviors" |
| No crashes, hangs, or inconsistent behavior | "Apps that crash, hang, or show inconsistent behavior will be rejected" |
| No browser cookies | Sandbox constraint — technically blocked |
| Production-ready (no betas, trials, demos) | "Apps submitted as betas, trials, or demos will not be accepted" |

### Accessibility

| Requirement | Source |
|-------------|--------|
| Keyboard navigation — all interactive elements reachable | Developer Guidelines: "accessible via keyboard" |
| Screen reader support — proper semantics, ARIA labels | Developer Guidelines: "accessible via...screen readers" |
| Readable contrast in light/dark modes | Design Guidelines: "minimum contrast ratio (WCAG AA)" |
| Text scaling — UI must not break when text size increases | Design Guidelines |

### Tool Annotations (Common Rejection Cause)

| Requirement | Source |
|-------------|--------|
| `readOnlyHint: true` for read-only tools | "Incorrect or missing action labels are a common cause of rejection" |
| `destructiveHint: true` for delete/overwrite tools | App Submission Guidelines |
| `openWorldHint: true` for external system interactions | App Submission Guidelines |
| Detailed justification for each annotation at submission | "provide a detailed justification for each at submission time" |

### Content Rules

| Requirement | Source |
|-------------|--------|
| No ads, upsells, or monetization messaging | Design Guidelines: "Avoid" in Poor Use Cases |
| No sensitive/private info visible in cards | Design Guidelines: "Avoid" in Poor Use Cases |
| No duplicating ChatGPT system functions (composer, etc.) | Design Guidelines: explicit prohibition |

### Metadata & Submission

| Requirement | Source |
|-------------|--------|
| Published privacy policy URL | Developer Guidelines |
| Support contact details | Developer Guidelines |
| Demo account credentials (for authenticated apps) | "Apps requiring any additional steps for login...will be rejected" |
| App name and description clear and accurate | Developer Guidelines |

---

## UI Guidelines — Explicit "Don't" Language

These use explicit prohibition language and will likely be scrutinized in review:

| Requirement | Source Quote |
|-------------|--------------|
| **No custom fonts** — inherit system font stack | "Don't use custom fonts, even in fullscreen modes" |
| **No logos in widget responses** | "Do not include your logo as part of the response" |
| **No custom gradients/patterns breaking ChatGPT look** | "Avoid custom gradients or patterns that break ChatGPT's minimal look" |
| **No colors on backgrounds in text areas** | "Don't apply colors to backgrounds in text areas" |
| **No deep navigation within cards** | "No deep navigation or multiple views within a card" |
| **No duplicative inputs** | "No duplicative inputs - don't replicate ChatGPT features" |

---

## Recommended — Rules of Thumb

These improve approval odds but won't block alone:

### Layout & Components

| Recommendation | Source |
|----------------|--------|
| Limit primary actions to 2 per card | "Rules of thumb" |
| Place primary actions at bottom of card | "Rules of thumb" |
| Cards should auto-fit content (avoid nested scrolling) | "Rules of thumb" |
| Responsive design — collapse gracefully on mobile | "Rules of thumb" |
| Consistent padding, avoid cramming | "Rules of thumb" |
| Maintain visual hierarchy: headline → supporting text → CTA | "Rules of thumb" |

### Color & Theming

| Recommendation | Source |
|----------------|--------|
| Use system colors for text, icons, dividers | "Rules of thumb" |
| Brand accents only on primary buttons | "Rules of thumb" |
| Light/dark mode compatibility | UX Guidelines |

### Typography

| Recommendation | Source |
|----------------|--------|
| Limit variation in font size | "Rules of thumb" |
| Use partner styling (bold, italic) only within content areas | "Rules of thumb" |

### Icons & Imagery

| Recommendation | Source |
|----------------|--------|
| Use system icons or monochromatic/outlined custom icons | "Rules of thumb" |
| Follow enforced aspect ratios for imagery | "Rules of thumb" |
| Provide alt text for images | Design Guidelines |

### State Management

| Recommendation | Source |
|----------------|--------|
| Avoid localStorage for core state — prefer widgetState or backend | "Avoid using localStorage for **core state**" — guidance |
| Use `window.openai.setWidgetState()` for UI state | Best practice from examples |
| Add try/catch around `window.openai.toolOutput` | Best practice |

### Content & Tone

| Recommendation | Source |
|----------------|--------|
| Keep content concise and scannable | Design Guidelines |
| Context-driven responses | Design Guidelines |
| Avoid jargon or promotional language | Design Guidelines |
| Proactive nudges only when tied to user intent | Design Guidelines |

---

## Quick Reference: The "Don'ts"

### Hard Don'ts (Will Block)

1. ❌ Browser cookies (sandbox blocked)
2. ❌ Crashes or silent errors
3. ❌ Missing tool annotations
4. ❌ Ads / upsells / monetization
5. ❌ Duplicate ChatGPT UI features
6. ❌ Beta/trial/demo submissions

### UI Guideline Don'ts (Likely Scrutinized)

1. ❌ Custom fonts
2. ❌ Logos inside widget responses
3. ❌ Custom gradients breaking ChatGPT look
4. ❌ Background colors in text areas
5. ❌ Deep navigation within cards

### Soft Don'ts (Guidance)

1. ⚠️ localStorage for core state (discouraged, not banned)
2. ⚠️ Nested scrolling (strongly discouraged)
3. ⚠️ More than 2 primary actions per card
4. ⚠️ Hardcoded colors breaking themes
5. ⚠️ Overloaded cards with too much content

---

## Clarity Widget Compliance Status

| Category | Status | Notes |
|----------|--------|-------|
| Accessibility (keyboard, ARIA) | ✅ | Implemented |
| System fonts | ✅ | Inherits system stack |
| No custom logos | ✅ | Not included |
| Light/dark mode | ✅ | Uses `data-theme` |
| Tool annotations | ✅ | Verify before submission |
| Error handling | ✅ | Implemented |
| No cookies | ✅ | Uses backend storage |
| Privacy policy | ✅ | Published |
| Primary actions at bottom | 🔄 | Pending (sticky bottom fix) |

---

## Source Documents

- `ChatGPT Apps SDK - Developer Guidelines.md` — rejection language source
- `ChatGPT Apps SDK - Official Design Guidelines.md` — UI rules of thumb
- `ChatGPT Apps SDK - Official Developer Guidelines.md` — submission requirements
- `App Submission Guidelines` — tool annotation requirements
- `ChatGPT Apps SDK - API Reference.md` — technical requirements