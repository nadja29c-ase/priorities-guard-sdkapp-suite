# Widget Design Token Hardening — Priority Guardian

## Context

The PG widget currently uses inline `style` attributes with raw CSS custom properties and hex fallbacks (e.g., `style={{ color: 'var(--gray-900, #181818)' }}`) instead of OpenAI SDK semantic Tailwind classes. This bypasses the design system and will break if the SDK theme changes.

**Goal:** Replace all hardcoded `var(--gray-*)` / `var(--green-*)` / `var(--red-*)` / `var(--blue-*)` inline styles with SDK semantic Tailwind classes. Zero visual regression in light mode. Dark mode gets correct for free.

**Not in scope:** `constants.ts` RING_STROKE_COLORS and ACCENT_COLORS in DeadlineCard — these use `var(--color-background-*-solid)` and `var(--color-text-*)` which ARE SDK semantic tokens already (needed as CSS values for SVG stroke/fill where Tailwind classes don't apply). Leave them.

---

## Token Mapping Reference

Use this exact mapping. When multiple gray values map to the same semantic class, that's correct — the SDK normalizes the visual hierarchy through its semantic layer.

### Text Colors

| Inline style | SDK Tailwind class |
|---|---|
| `color: 'var(--gray-900, #181818)'` | `text-default` |
| `color: 'var(--gray-700, #303030)'` | `text-default` |
| `color: 'var(--gray-600, #414141)'` | `text-default` |
| `color: 'var(--gray-500, #5d5d5d)'` | `text-secondary` |
| `color: 'var(--gray-450, #767676)'` | `text-secondary` |
| `color: 'var(--gray-400, #8f8f8f)'` | `text-tertiary` |
| `color: 'var(--gray-350, #9f9f9f)'` | `text-tertiary` |
| `color: 'var(--gray-300, #afafaf)'` | `text-tertiary` (for text) |

### Background Colors

| Inline style | SDK Tailwind class |
|---|---|
| `background: 'var(--gray-0, #ffffff)'` | `bg-surface` |
| `background: 'var(--gray-50, #f9f9f9)'` | `bg-surface-secondary` |
| `background: 'var(--gray-75, #f3f3f3)'` | `bg-surface-tertiary` |

### Border Colors

| Inline style | SDK Tailwind class |
|---|---|
| `border: '1px solid var(--gray-100, #ededed)'` | `border border-default` |
| `borderTop: '1px solid var(--gray-75, #f3f3f3)'` | `border-t border-subtle` |

### Status Colors (ConnectionStatus, GoalItem)

| Inline style | SDK Tailwind class / token |
|---|---|
| `background: 'var(--green-500, #00a240)'` | `bg-success-solid` |
| `color: 'var(--red-500, #e02e2a)'` | `text-danger` |
| `background: 'var(--red-50, #fef2f2)'` | `bg-danger-soft-alpha` |
| `border: '1px solid var(--red-200, #fecaca)'` | `border border-danger-outline` |
| `color: 'var(--red-600, #dc2626)'` | `text-danger` |
| `color: 'var(--blue-500, #0169cc)'` | `text-info` |
| `background: 'var(--blue-50, #eff6ff)'` | `bg-info-soft` |

### Bar/Legend (TimeAllocationBar — `var(--gray-*)` for "other")

| Inline style | SDK Tailwind class |
|---|---|
| `background: 'var(--gray-100, #ededed)'` | `bg-surface-tertiary` (bar track) |
| `background: 'var(--gray-300, #afafaf)'` | Use existing `BAR_COLORS.other` class from constants |

---

## Files to Modify

All files are in `mcp_server/priority_guardian/widget-react/src/components/`:

### 1. ExpandButton.tsx
- Replace inline `color` + `background` with `text-inverse bg-default` (or `text-surface bg-[var(--gray-900)]` if `text-inverse` doesn't exist — verify first)
- Remove `border: 'none'` and `cursor: 'pointer'` (already handled by `<button>`)

### 2. FullscreenHeader.tsx
- Container: `bg-surface border border-default` → remove `style`
- Title: `text-default` → remove `style`
- Minimize button: `text-secondary` → remove `style`, remove `background: 'none'`, `border: 'none'`, `cursor: 'pointer'`

### 3. CalendarConnectionMinimal.tsx
- Green dot: `bg-success-solid` → remove `style`
- Label: `text-tertiary` → remove `style`

### 4. ChevronIcon.tsx
- No `var(--gray-*)` found. `stroke="currentColor"` inherits correctly. **No changes needed** — but verify no inline color style was added. Only `transform` + `transition` remain as inline (these are fine, no Tailwind equivalent for dynamic transform).

### 5. DeadlineCard.tsx
**Leave ACCENT_COLORS alone** — they use SDK semantic tokens already.
- Card article: `bg-surface border border-default` + keep `borderLeft: 4px solid ${colors.border}` as inline (dynamic per-priority)
- Name `<h3>` and `<input>`: add `text-default`, remove `style={{ color: ... }}`
- Edit/trash icon SVGs: add `text-tertiary` class, remove `style={{ color: ... }}`
- Lead measure large number: `text-default`, remove style
- Lead measure denominator: `text-tertiary`, remove style
- "Deliverables done" label: `text-secondary`, remove style
- Deliverables section border: `border-t border-subtle`, remove inline `borderTop`
- Section header "E2E Deliverables": `text-tertiary`, remove style
- Count badge: `text-tertiary`, remove style
- Empty state italic: `text-secondary`, remove style
- Collapsible button: remove `background: 'none'`, `border: 'none'`, `cursor: 'pointer'`, `padding: 0` (use Tailwind: `bg-transparent border-none cursor-pointer p-0` or just remove since `<button>` already resets)

### 6. FlexibleCard.tsx
Same patterns as DeadlineCard:
- Card article: `bg-surface border border-default` + keep dynamic `borderLeft`
- Name text: `text-default`
- Streak pill: `text-default bg-surface-tertiary`
- Icon SVGs: `text-tertiary`
- Avg percentage: `text-default`
- Avg subtitle: `text-secondary`
- Hourglass SVG stroke: keep as `stroke="var(--gray-350, #9f9f9f)"` → change to `stroke="currentColor"` and add `text-tertiary` on the SVG element
- First week italic: `text-tertiary`

### 7. GoalItem.tsx
- Unchecked border: `border-[1.5px] border-[var(--gray-300)]` or keep as inline with just `var(--color-border-strong)` (SDK token)
- Checked background: `bg-success-solid`
- Active text: `text-default`
- Achieved text: `text-tertiary`

### 8. ConnectionStatus.tsx (heaviest)
- Section container: `bg-surface border border-default`
- Status dot: `bg-success-solid` (connected) / use `bg-outline-default` (disconnected)
- "Google Calendar" label: `text-default`
- "Disconnect?" text: `text-secondary`
- Disconnect button: `text-danger bg-danger-soft-alpha`
- Cancel button: `text-secondary bg-surface-secondary`
- Connect button: `text-info bg-info-soft`
- Check status button: `text-info bg-info-soft`
- Info box background: `bg-surface-secondary`
- Info box icon stroke: use `currentColor` + `text-tertiary`
- Info box text: `text-secondary`
- Bold P1/P2/P3 in instruction: `text-default` via `<strong className="text-default">`
- Error box: `bg-danger-soft-alpha border border-danger-outline`
- Error text: `text-danger`

### 9. TimeAllocationBar.tsx
- Section header: `text-secondary`
- Total hours: `text-default`
- Refresh icon: `text-tertiary` + use `currentColor`
- Date range: `text-secondary`
- Bar track: `bg-surface-tertiary`
- Legend "other" dot: keep inline `var(--gray-300)` or use `bg-outline-default` (same as BAR_COLORS.other)
- Legend labels: `text-secondary` (priority) / `text-tertiary` (other)

### 10. PieChart.tsx
- `OTHER_GREY`: Replace with `var(--color-border-default)` or keep — it's used as SVG stroke value, not as a class
- `SEMANTIC_COLORS` array: The raw hex colors (`#14b8a6`, `#f97316`, etc.) are intentional for distinct semantic slices — **leave these**. They're not gray-scale theme tokens; they're categorical data colors.
- CTA text at bottom: `text-secondary`, remove inline style
- SVG text `fill` attributes already use `var(--color-text-default)` and `var(--color-text-tertiary)` — **correct, no change needed**

---

## Implementation Rules

1. **Class-only when possible.** If the color is static (not computed at runtime), use a Tailwind class. Remove the `style` attribute entirely when it contained only color.

2. **Keep inline styles for dynamic values.** `borderLeft: 4px solid ${colors.border}` must stay inline because the color is per-priority. SVG `stroke` that uses `var(--color-*)` tokens for dynamic fill must stay.

3. **Use `currentColor` pattern for SVG icons.** Add the semantic text class to the SVG element, then use `stroke="currentColor"` or `fill="currentColor"`. This is already the pattern in most icons.

4. **Remove dead inline properties.** When converting a `style` object to classes, also remove `border: 'none'`, `cursor: 'pointer'`, `background: 'none'`, `padding: 0` — these are default for `<button>` elements or achievable via existing Tailwind utilities already on the element.

5. **Do not change any layout, spacing, sizing, or structural code.** This is a color-token-only migration.

---

## Unit Tests

**Scope:** Verify no runtime errors and correct class application. No visual regression testing (that's manual).

For each modified component, verify:
- Component renders without errors (no missing props, no broken references)
- No inline `style` attributes contain `var(--gray-` (grep-based assertion)

**Test file:** Add to existing test files or create `__tests__/DesignTokens.test.tsx`

```
Test: "no components use hardcoded gray CSS variables"
- Import all component modules
- Render each with minimal required props
- Assert: rendered output contains zero instances of `var(--gray-` in style attributes
- This is a snapshot-free structural test
```

---

## Integration Tests

**Scope:** Widget renders correctly end-to-end with real data shapes.

1. **Dashboard view renders with token classes** — Mount App with mock `window.openai.toolOutput` containing 3 priorities (1 deadline, 2 flexible). Verify DeadlineCard, FlexibleCard, TimeAllocationBar all render. No `var(--gray-` in any rendered style attribute.

2. **Pie chart view renders with token classes** — Mount App with PieChartData mock. Verify PieChart renders. No `var(--gray-` in rendered style attributes (SVG `fill`/`stroke` using `var(--color-*)` tokens are allowed).

3. **ConnectionStatus states** — Render connected and disconnected states. Verify correct semantic classes applied (e.g., `bg-success-solid` for connected dot, `text-danger` for disconnect button).

---

## Acceptance Criteria

- [ ] Zero `var(--gray-` references in any inline `style` attribute across all widget `.tsx` files (excluding `constants.ts` RING_STROKE_COLORS which use `var(--color-*)` SDK tokens)
- [ ] Zero `var(--green-` / `var(--red-` / `var(--blue-` in inline styles (replaced with semantic classes)
- [ ] All replaced values use SDK semantic Tailwind classes from the mapping table above
- [ ] Dynamic per-priority colors (card left borders, SVG strokes for rings) remain as inline styles using SDK `var(--color-*)` tokens
- [ ] `ACCENT_COLORS` in DeadlineCard unchanged
- [ ] `RING_STROKE_COLORS` in constants.ts unchanged
- [ ] `SEMANTIC_COLORS` hex values in PieChart.tsx unchanged
- [ ] All existing tests pass
- [ ] New design token test passes
- [ ] No layout, spacing, or structural changes
- [ ] `npm run build` succeeds with zero errors
