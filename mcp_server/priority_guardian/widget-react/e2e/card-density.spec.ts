import { test, expect, type Page } from '@playwright/test'

/**
 * Regression layer for inc_cardsize_fix_3.md (density pass — "Increment 3").
 *
 * Written fresh, not adapted from the old (deleted) inline-density.spec.ts —
 * that file asserted InlinePriorityRow-specific structure from the reverted
 * Increment 2 (compact-row redesign), which no longer exists. This increment
 * keeps DeadlineCard/FlexibleCard structurally identical in both modes and
 * only tightens spacing/sizing values via isInline — a completely different
 * shape of change, so a completely different spec.
 *
 * What this layer is NOT: a substitute for manual verification in a real
 * ChatGPT session. Loading the widget standalone in a Chromium tab cannot
 * reproduce ChatGPT's actual host iframe/container behavior — that gate is
 * still required and separate from this file, same as every prior increment.
 */

const PRE_INCREMENT_INLINE_HEIGHT_PX = 896 // measured against the pre-increment committed bundle, same 3-priority fixture below

const VIEWPORTS = {
  narrowMobile: { width: 375, height: 1200 },
  standardDesktop: { width: 1024, height: 1200 },
  wideDesktopCanvas: { width: 1600, height: 1200 },
} as const

// Same mixed dataset used for the before/after visual review in the delivery report.
const MIXED_PRIORITIES = [
  {
    id: 'p1', name: 'Launch Feature X', type: 'deadline', calendarKeyword: 'P1', status: 'active',
    deadline: '2026-10-01', weeklyHourTarget: 10, weeklyHourActual: 8,
    deliverables: [{ id: 'd1', name: 'Design doc', done: true }, { id: 'd2', name: 'Implementation', done: false }],
    goals: [],
  },
  {
    id: 'p2', name: 'Learn Rust', type: 'flexible', calendarKeyword: 'P2', status: 'active',
    weeklyHourTarget: 5, weeklyHourActual: 3, avgTargetAchievement: 84.0, checkpointDate: '2026-11-15',
    deliverables: [], goals: [{ id: 'g1', text: 'Finish book', achieved: false }],
  },
  {
    id: 'p3', name: 'Family time', type: 'flexible', calendarKeyword: 'P3', status: 'active',
    weeklyHourTarget: 8, weeklyHourActual: 6, avgTargetAchievement: 60.0,
    deliverables: [], goals: [],
  },
]

async function mockOpenAiAndGoto(page: Page, displayMode: 'inline' | 'fullscreen') {
  await page.addInitScript(({ mode, priorities }) => {
    ;(window as unknown as { openai: Record<string, unknown> }).openai = {
      displayMode: mode,
      locale: 'en-US',
      toolOutput: {
        structuredContent: {
          data: {
            google_connected: true,
            priorities,
            available_keywords: [],
            timeAllocation: {
              weekStart: '2026-09-08T00:00:00+00:00',
              weekEnd: '2026-09-15T00:00:00+00:00',
              totalTrackedHours: 31.75,
              keywords: { P1: { hours: 10.5, eventCount: 6 }, P2: { hours: 3.0, eventCount: 2 }, P3: { hours: 0.0, eventCount: 0 } },
              otherHours: 18.25,
              barSegments: { P1: 10.5, P2: 3.0, P3: 0.0, other: 18.25 },
            },
          },
        },
      },
      callTool: async () => ({ structuredContent: { data: { priorities: [] } } }),
      notifyIntrinsicHeight: () => {},
      setWidgetState: () => {},
      widgetState: undefined,
    }
  }, { mode: displayMode, priorities: MIXED_PRIORITIES })
  await page.goto('/pg-dashboard.html')
  await page.waitForSelector('main[role="main"]')
}

for (const [label, viewport] of Object.entries(VIEWPORTS)) {
  test(`inline height at ${label} (${viewport.width}px) is materially shorter than the pre-increment ${PRE_INCREMENT_INLINE_HEIGHT_PX}px baseline`, async ({ page }) => {
    await page.setViewportSize(viewport)
    await mockOpenAiAndGoto(page, 'inline')

    const box = await page.locator('main[role="main"]').boundingBox()
    expect(box).not.toBeNull()

    // No fixed target per inc_cardsize_fix_3.md — report the number, assert
    // only that it's a real reduction (not a regression back toward the
    // pre-increment height), same qualitative-only acceptance criterion the
    // briefing specifies.
    console.log(`[card-density] ${label}: inline height = ${box!.height}px (pre-increment baseline: ${PRE_INCREMENT_INLINE_HEIGHT_PX}px)`)
    expect(box!.height).toBeLessThan(PRE_INCREMENT_INLINE_HEIGHT_PX)
  })
}

const PRE_INCREMENT_FULLSCREEN_HEIGHT_PX = 1194.5 // measured against the pre-increment committed bundle, same 3-priority fixture, standardDesktop

test('fullscreen height at standardDesktop is unchanged by the density pass', async ({ page }) => {
  await page.setViewportSize(VIEWPORTS.standardDesktop)
  await mockOpenAiAndGoto(page, 'fullscreen')

  const box = await page.locator('main[role="main"]').boundingBox()
  expect(box).not.toBeNull()
  console.log(`[card-density] fullscreen height = ${box!.height}px (pre-increment baseline: ${PRE_INCREMENT_FULLSCREEN_HEIGHT_PX}px)`)

  // Tight tolerance, not a loose sanity floor — a >1000px-style ceiling
  // would still pass even if fullscreen picked up the ~124px-shorter inline
  // spacing by mistake (1194.5 - 124 = ~1070, still > 1000). This must
  // match the pre-increment height almost exactly; ±2px only for
  // sub-pixel/font-rendering variance across environments.
  expect(box!.height).toBeGreaterThan(PRE_INCREMENT_FULLSCREEN_HEIGHT_PX - 2)
  expect(box!.height).toBeLessThan(PRE_INCREMENT_FULLSCREEN_HEIGHT_PX + 2)

  // Structural corroboration, not just a height sum that could coincidentally
  // match: confirm the actual fullscreen-only spacing classes are present.
  const cardContainer = page.locator('main[role="main"] > div.flex.flex-col')
  await expect(cardContainer).toHaveClass(/gap-5/)
  await expect(cardContainer).not.toHaveClass(/gap-2/)
  const banner = page.getByTestId('deadline-banner')
  await expect(banner).toHaveClass(/py-2\.5/)
  await expect(banner).not.toHaveClass(/py-1\.5/)
})

// Pre-existing, out-of-scope finding (flagged in the delivery report, not
// fixed here per inc_cardsize_fix_3.md's own instruction on adjacent
// issues): at 375px width + 200% text-resize, <main> already overflowed
// horizontally BEFORE this increment (scrollWidth 397 vs clientWidth 343,
// measured against the pre-increment committed bundle) — driven by content
// width at 2x font size, not by this increment's vertical spacing/sizing
// changes. This increment's changes did not introduce or worsen it — the
// after-bundle's overflow is smaller (373 vs 397) — so the regression guard
// below checks "did not get worse," not "zero overflow," at narrowMobile
// specifically. standardDesktop/wideDesktopCanvas have no such pre-existing
// condition and are held to the strict zero-overflow bar.
const PRE_EXISTING_NARROW_MOBILE_OVERFLOW_PX = 397 // scrollWidth at 375px+200%, pre-increment bundle

for (const [label, viewport] of Object.entries(VIEWPORTS)) {
  test(`200% text-resize on inline at ${label}: no overlap, no new horizontal overflow`, async ({ page }) => {
    await page.setViewportSize(viewport)
    await mockOpenAiAndGoto(page, 'inline')

    // WCAG 1.4.4-style text resize (scales text, not full-page zoom) — same
    // approach as the width increment's equivalent check.
    await page.addStyleTag({ content: 'html { font-size: 200% !important; }' })

    const main = page.locator('main[role="main"]')
    const { scrollWidth, overflowsX } = await main.evaluate((el) => ({
      scrollWidth: el.scrollWidth,
      overflowsX: el.scrollWidth > el.clientWidth + 1,
    }))

    if (label === 'narrowMobile') {
      console.log(`[card-density] narrowMobile 200% scrollWidth = ${scrollWidth}px (pre-existing pre-increment overflow was ${PRE_EXISTING_NARROW_MOBILE_OVERFLOW_PX}px — not this increment's to fix, only not to worsen)`)
      expect(scrollWidth).toBeLessThanOrEqual(PRE_EXISTING_NARROW_MOBILE_OVERFLOW_PX)
    } else {
      expect(overflowsX).toBe(false)
    }

    // Name/metric non-overlap check on the long-ish "Learn Rust" row's HourRing
    // and stat text — mirrors the width increment's long-name overlap check.
    const ring = page.locator('svg[role="img"]').first()
    const ringBox = await ring.boundingBox()
    const statText = page.getByText('~84%')
    const statBox = await statText.boundingBox()
    expect(ringBox).not.toBeNull()
    expect(statBox).not.toBeNull()
    // Non-overlap: side-by-side (stat's left >= ring's right) or stacked
    // (no vertical intersection) — either is an acceptable layout outcome;
    // visual overlap is not.
    const sideBySide = statBox!.x >= ringBox!.x + ringBox!.width - 1
    const stacked = statBox!.y + statBox!.height <= ringBox!.y || ringBox!.y + ringBox!.height <= statBox!.y
    expect(sideBySide || stacked).toBe(true)
  })
}
