# Increment: SVG Accessibility Audit — PG Widget

## Context
OpenAI Apps SDK compliance audit (items #74-76) requires all SVG elements in the widget to have correct ARIA attributes. Decorative SVGs must be hidden from assistive tech. Data-visualization SVGs must be announced. SVGs inside interactive elements must not duplicate the parent's accessible name.

## Scope
**Files:** `mcp_server/priority_guardian/widget-react/src/components/` — only `.tsx` files containing `<svg>` elements.

**Out of scope:** Clarity widget (uses SDK `<Badge>` components, no custom SVGs). Backend. Tests are in scope (see below).

## Current State (from code review)

### Already correct ✅
- **HourRing.tsx** — `<svg role="img" aria-label="5.0 of 10.0 this week">` — data visualization, properly announced.
- **PieChart.tsx** — `<svg aria-label="Pie chart showing 24.5 total hours across 4 categories" role="img">` — data visualization, properly announced. Individual `<circle>` segments have `aria-label`. Legend color dots have `aria-hidden="true"`.
- **DeleteConfirmation.tsx** — No SVGs. Uses SDK `<Button>` components.
- **FullscreenHeader.tsx** — No SVGs. "Minimize" is a text button with `aria-label`.

### Needs fix 🔧
1. **ChevronIcon.tsx** — `<svg>` has NO `aria-hidden` and NO `aria-label`. This SVG is always decorative (used inside `<button>` elements that have their own text labels like "Section header text"). Must add `aria-hidden="true"`.

2. **ExpandButton.tsx** — `<svg>` (right-chevron arrow) inside a `<button>` that already has `aria-label="Open full dashboard"` and visible text "Open full dashboard". The SVG is decorative — it visually reinforces the button text. Must add `aria-hidden="true"` to the `<svg>`.

### Likely correct but verify
3. **TimeAllocationBar.tsx** — Check if this component contains SVGs. If it does, apply the same rules.
4. **DeadlineCard.tsx**, **FlexibleCard.tsx** — Check if any inline SVGs exist beyond ChevronIcon usage.
5. **CalendarConnectionMinimal.tsx** — Check for SVGs.

## Rules (from OpenAI UI/UX spec)

- **Decorative SVGs** (visual-only, meaning already conveyed by adjacent text or parent element): `aria-hidden="true"`
- **Data-visualization SVGs** (charts, rings, progress indicators): `role="img"` + `aria-label` describing the data
- **Interactive SVGs** (standalone clickable): wrap in `<button>` with `aria-label`, add `aria-hidden="true"` to the SVG itself
- **SVGs inside labeled buttons**: always `aria-hidden="true"` on the SVG (the button's `aria-label` or text content provides the name)

## Required Changes

### Fix 1: ChevronIcon.tsx
Add `aria-hidden="true"` to the `<svg>` element. This is a decorative icon always used inside labeled interactive elements.

### Fix 2: ExpandButton.tsx
Add `aria-hidden="true"` to the `<svg>` element inside the button. The button already has `aria-label="Open full dashboard"` and visible text.

### Fix 3: Any other SVGs found during audit
Apply the rules above. Grep all `.tsx` files for `<svg` and classify each as decorative or informational.

## Acceptance Criteria

### Functional
- [ ] Every `<svg>` in PG widget has either `aria-hidden="true"` (decorative) or `role="img"` + `aria-label` (informational)
- [ ] No SVG inside a `<button>` is announced separately by screen readers (all have `aria-hidden="true"`)
- [ ] HourRing and PieChart SVGs retain their existing `role="img"` + `aria-label` (do NOT add `aria-hidden` to these)

### Unit Tests
**File:** `mcp_server/priority_guardian/widget-react/src/__tests__/SvgAccessibility.test.tsx`

Test each SVG component in isolation:
- `ChevronIcon` renders with `aria-hidden="true"`
- `ExpandButton` SVG has `aria-hidden="true"`, button has `aria-label`
- `HourRing` SVG has `role="img"` and `aria-label` containing hour values
- `PieChart` SVG has `role="img"` and `aria-label` containing total hours
- `PieChart` legend dots have `aria-hidden="true"`

### Integration Tests
None required — this is a pure UI attribute change with no backend interaction.

## Build Verification
After changes, rebuild the widget and verify the built `pg-dashboard.html` contains the updated attributes:
```
cd mcp_server/priority_guardian/widget-react && npm run build
```
Grep the built HTML for `aria-hidden` to confirm the attributes made it through the build pipeline.

