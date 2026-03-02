# Increment: UI Guideline Compliance — Card Color Overrides

## Context

OpenAI UI Guidelines audit found 3 violations in DeadlineCard and FlexibleCard:

1. **#42 — Text color overrides**: `style={{ color: colors.accent }}` on deadline date text and days-left text in DeadlineCard. Guideline: "Don't change text colors or other core component styles."
2. **#41 — Colored background on text area**: `style={{ background: colors.soft }}` on DeadlineCard's deadline banner div (contains text). Guideline: "Don't apply colors to backgrounds in text areas."
3. **#64 — Hardcoded hex border colors**: FlexibleCard defines local `BORDER_COLORS` with hardcoded hex. DeadlineCard uses `ACCENT_COLORS.border` with hardcoded hex. Both are inline `style={{ borderLeft: ... }}`.

**Note:** `constants.ts` already has a compliant `BORDER_COLORS` using SDK tokens via Tailwind arbitrary values, but neither card imports it.

## Scope

**Files to modify:**
- `mcp_server/priority_guardian/widget-react/src/components/DeadlineCard.tsx`
- `mcp_server/priority_guardian/widget-react/src/components/FlexibleCard.tsx`
- `mcp_server/priority_guardian/widget-react/src/constants.ts` (if needed)

**Out of scope:** TimeAllocationBar, HourRing, PieChart (these use SDK tokens correctly via Tailwind classes or CSS variables for SVG — compliant).

## Design Decision: Option B (Minimal)

Keep the colored left border for visual priority differentiation. Remove the banner background and text color overrides. Calendar icon keeps accent stroke (icons can use custom monochromatic colors per #74).

## Required Changes

### DeadlineCard.tsx

**1. Remove `ACCENT_COLORS` constant entirely.**

**2. Replace with SDK-compliant constants.** Import `BORDER_COLORS` from `constants.ts` for the left border. Define icon stroke colors using SDK CSS variables (same pattern as `RING_STROKE_COLORS` in constants.ts):

```
ICON_STROKE_COLORS: Record<string, string> = {
  P1: 'var(--color-text-info, #0285ff)',
  P2: 'var(--color-text-discovery, #924ff7)',
  P3: 'var(--color-text-caution, #e0ac00)',
}
```

Consider adding `ICON_STROKE_COLORS` to `constants.ts` if FlexibleCard or other components also need icon stroke colors.

**3. Card `<article>` element:**
- BEFORE: `style={{ borderLeft: '4px solid ${colors.border}' }}`
- AFTER: Use `BORDER_COLORS[kw]` from constants.ts as a className (it already includes `border-l-4 border-l-[var(...)]`)

**4. Deadline banner div:**
- BEFORE: `style={{ background: colors.soft }}` with colored text children
- AFTER: Remove `style` entirely. Use `className="bg-surface-secondary"` (SDK neutral surface). This removes the tinted background.

**5. Deadline date text:**
- BEFORE: `style={{ color: colors.accent }}`
- AFTER: Use `className="text-secondary"` (SDK semantic token). Remove `style` prop.

**6. Days-left text:**
- BEFORE: `style={{ color: colors.accent }}`
- AFTER: Use `className="text-secondary"` (SDK semantic token). Remove `style` prop.

**7. Calendar SVG icon:**
- BEFORE: `stroke={colors.accent}`
- AFTER: `stroke={ICON_STROKE_COLORS[kw]}` — icon stroke colors using CSS variables are acceptable per #74 ("Use system icons or custom monochromatic/outlined iconography"). The icon is decorative (already has `aria-hidden="true"`), and using CSS custom properties is not a text color override.

### FlexibleCard.tsx

**1. Remove local `BORDER_COLORS` constant** (lines 12-16, the hardcoded hex version).

**2. Import `BORDER_COLORS` from `'../constants'`** (SDK-token version already exists there).

**3. Card `<article>` element:**
- BEFORE: `style={{ borderLeft: '4px solid ${borderColor}' }}`  
- AFTER: Add `BORDER_COLORS[kw]` to className string. Remove `style` prop entirely.

**4. Hourglass SVG icon** (in the "Tracking in progress" section): Already uses `stroke="currentColor"` — no change needed.

### constants.ts (optional)

If both cards need icon stroke colors, add:

```typescript
export const ICON_STROKE_COLORS: Record<string, string> = {
  P1: 'var(--color-text-info, #0285ff)',
  P2: 'var(--color-text-discovery, #924ff7)',
  P3: 'var(--color-text-caution, #e0ac00)',
}
```

These are CSS custom property references with hex fallbacks — the same pattern already used by `RING_STROKE_COLORS`. They are NOT hardcoded hex values; the CSS variable is resolved at runtime by the theme.

### Both Cards — Eliminate Remaining Inline Styles

**Badge `<span>` in both DeadlineCard and FlexibleCard:**
- BEFORE: `style={{ fontSize: '0.65rem' }}`
- AFTER: Add `text-2xs` to className. Remove `style` prop entirely.
- `text-2xs` = 0.625rem (10px) vs current 0.65rem (10.4px). Visually identical. Maps to SDK token.

**Streak pill `<span>` in FlexibleCard only:**
- BEFORE: `style={{ fontSize: '0.7rem' }}`
- AFTER: Add `text-xs` to className. Remove `style` prop entirely.
- `text-xs` = 0.75rem (12px) vs current 0.7rem (11.2px). Close enough. Maps to SDK token.

**Goal:** Zero `style=` attributes on any element in either card. Fully class-based. No inline style for a reviewer to question.

## What Must NOT Change

- HourRing SVG stroke colors (`RING_STROKE_COLORS`) — these are data visualization, not text areas. Compliant.
- PieChart segment colors — data visualization. Compliant.
- TimeAllocationBar `BAR_COLORS` — uses Tailwind SDK classes. Compliant.
- Badge colors (`BADGE_COLORS`) — uses SDK semantic tokens. Compliant.
- Edit/Delete button SVG icons — use `stroke="currentColor"`. Compliant.
- The colored left border on cards — this IS the primary P1/P2/P3 visual differentiator. Keep it, but via SDK tokens.

## Acceptance Criteria

### Functional
- [ ] No `style={{ color: ... }}` on any text element in DeadlineCard or FlexibleCard
- [ ] No `style={{ background: ... }}` on any text-containing div in DeadlineCard
- [ ] No hardcoded hex values for borders — all borders via SDK token Tailwind classes
- [ ] No `style={{ fontSize: ... }}` — all font sizes via SDK Tailwind classes
- [ ] **Zero `style=` attributes on any element in either card component**
- [ ] Calendar icon in DeadlineCard still shows priority-appropriate color via CSS variable
- [ ] Left border on both card types still shows P1 blue / P2 purple / P3 yellow
- [ ] Cards visually distinguish priorities (left border color + badge + icon stroke)
- [ ] Light mode and dark mode both render correctly (SDK tokens auto-switch)

### Unit Tests

**File:** `mcp_server/priority_guardian/widget-react/src/__tests__/CardCompliance.test.tsx`

Test each card for absence of prohibited patterns:

- DeadlineCard: no element in the entire component has a `style` attribute (query all elements, assert none have `style`)
- DeadlineCard: calendar icon SVG has `stroke` attribute using CSS variable (not hardcoded hex)
- DeadlineCard: card has colored left border via className (not inline style)
- DeadlineCard: badge uses `text-2xs` class (not inline fontSize)
- FlexibleCard: no element in the entire component has a `style` attribute
- FlexibleCard: card has colored left border via className (not inline style)
- FlexibleCard: badge uses `text-2xs` class (not inline fontSize)
- FlexibleCard: streak pill uses `text-xs` class (not inline fontSize)

Testing approach: render the component, query the DOM. Use `expect(element).not.toHaveAttribute('style')` on text elements and text-containing divs. Do NOT use regex or string matching on serialized style — JSDOM serialization is unreliable.

### Integration Tests
None required — pure UI attribute changes with no backend interaction.

## Build Verification

After changes:
```
cd mcp_server/priority_guardian/widget-react && npm run build
```
Grep the built HTML for any remaining hardcoded hex in style attributes:
```
grep -o 'style="[^"]*#[0-9a-fA-F]' dist/pg-dashboard.html
```
Should return no matches (all hex should be inside CSS variable fallbacks, not bare in style attributes).
