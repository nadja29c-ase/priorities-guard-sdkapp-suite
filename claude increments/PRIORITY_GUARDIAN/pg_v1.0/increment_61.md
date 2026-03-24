Increment 61 — Localized hour unit in accessibility strings
Files: src/utils.ts, src/i18n.ts
No other files. No backend. No migration.

Context
formatHours() in utils.ts always returns e.g. "10.5h" — the h suffix is hardcoded English. This string is used in aria-labels across PieChart, TimeAllocationBar, and HourRing. VoiceOver performs language detection at the word/token level: when it encounters "10.5h" it recognises the h abbreviation as English and switches to the English voice for that element, even though document.documentElement.lang is "de".
Visual display strings ("10.5h") are fine as-is — compact format is correct for sighted users. The fix applies only to accessibility (aria-label) strings.

What to implement
1. Add formatHoursA11y(hours: number): string to utils.ts
This function formats hours for use in aria-labels only. It uses the full spelled-out unit word from i18n instead of the h abbreviation.

Call getLocale() from i18n.ts to get the current locale
Use t('hoursUnit') for the unit word — already exists in both locales: "hours" (EN) and "Stunden" (DE)
Format: "10.5 Stunden" / "10.5 hours" (space between number and unit)
For zero: "0 Stunden" / "0 hours"
Same rounding logic as formatHours (1 decimal, strip trailing .0)
Import getLocale and t from ./i18n — this is already imported in utils.ts via normalizeLocale, but getLocale and t are not yet imported there. Add them.

2. In i18n.ts — no changes needed. hoursUnit already exists in both locales ("hours" / "Stunden").
3. Update aria-label usages — three locations:
HourRing.tsx — the ariaLabel uses t('hourRingAria') with {hours} and {target} replaced by formatHours(). Replace both formatHours() calls in that string with formatHoursA11y():
ts// Before
const ariaLabel = t('hourRingAria')
  .replace('{hours}', formatHours(actual))
  .replace('{target}', formatHours(target))

// After
const ariaLabel = t('hourRingAria')
  .replace('{hours}', formatHoursA11y(actual))
  .replace('{target}', formatHoursA11y(target))
Import formatHoursA11y alongside the existing formatHours import.
PieChart.tsx — two locations:
The segment aria-label on each <circle>:
ts// Before
aria-label={`${translateSliceLabel(seg.slice.label)}: ${seg.slice.hours}h (${seg.percent.toFixed(0)}%)`}

// After
aria-label={`${translateSliceLabel(seg.slice.label)}: ${formatHoursA11y(seg.slice.hours)} (${seg.percent.toFixed(0)}%)`}
The sr-only paragraph (visually hidden total for screen readers):
ts// Before
{totalHours.toFixed(1)} {t('hoursUnit')} {t('totalHours')}

// After
{formatHoursA11y(totalHours)} {t('totalHours')}
Import formatHoursA11y alongside the existing imports from ../utils.
TimeAllocationBar.tsx — buildAriaLabel uses formatHours() for each keyword and otherHours. Replace all formatHours() calls inside buildAriaLabel with formatHoursA11y(). The visual legend below still uses formatHours() — leave those unchanged.
Import formatHoursA11y alongside the existing formatHours import.

What NOT to change

formatHours() itself — leave it unchanged, it is correct for visual display
Any visual/rendered text (legend labels, center text in SVG, hour numbers in cards)
The h suffix in SVG <text> elements — those are aria-hidden or inside role="img" with a separate aria-label
Backend, MCP, build config, other components


Pre-deploy
No DB changes. No backend changes. No migration. Standard widget build + deploy:

npm run build in widget-react/
Verify widgets/pg-dashboard.html is updated
Deploy to Render (manual trigger)


No tests required
formatHoursA11y is pure function logic — add a unit test if the existing utils test file exists, otherwise skip. No component test changes needed.