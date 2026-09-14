import { test, expect, type Page } from '@playwright/test'

/**
 * Regression layer for inc_card_size_fix2.md — real-browser measurements
 * against the built bundle on disk (npm run test:e2e rebuilds first; see
 * playwright.config.ts's note on what "committed" does and doesn't mean).
 *
 * What this layer is NOT: a substitute for manual verification in a real
 * ChatGPT session. Loading the widget standalone in a Chromium tab cannot
 * reproduce ChatGPT's actual host iframe/container behavior — that gate is
 * still required and separate from this file, same as the width increment.
 */

const PRODUCTION_BASELINE_PX = 899 // measured production height before this increment, per inc_card_size_fix2.md

const VIEWPORTS = {
  narrowMobile: { width: 375, height: 900 },
  standardDesktop: { width: 1024, height: 900 },
  wideDesktopCanvas: { width: 1600, height: 900 },
} as const

// Same shape as the production measurement this increment is reducing:
// 3 mixed deadline/flexible priorities, Google Calendar connected, one
// deliberately long name to exercise truncation/overlap checks.
const MIXED_PRIORITIES = [
  {
    id: 'p1', name: 'Launch Feature X', type: 'deadline', calendarKeyword: 'P1', status: 'active',
    deadline: '2026-10-01', weeklyHourTarget: 10, weeklyHourActual: 8,
    deliverables: [{ id: 'd1', name: 'Design doc', done: true }, { id: 'd2', name: 'Implementation', done: false }],
    goals: [],
  },
  {
    id: 'p2', name: 'This Is A Deliberately Very Long Priority Name That Should Truncate Visually Without Overlapping Its Neighbors',
    type: 'flexible', calendarKeyword: 'P2', status: 'active',
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
  test(`inline height at ${label} (${viewport.width}x${viewport.height}) is materially shorter than the ${PRODUCTION_BASELINE_PX}px baseline`, async ({ page }) => {
    await page.setViewportSize(viewport)
    await mockOpenAiAndGoto(page, 'inline')

    const main = page.locator('main[role="main"]')
    const box = await main.boundingBox()
    expect(box).not.toBeNull()

    // No fixed target — report the number. A loose ceiling (well above any
    // plausible compact result) catches a true regression back toward the
    // old rich-card height without pretending to optimize to a px target.
    console.log(`[inline-density] ${label}: inline height = ${box!.height}px (baseline was ${PRODUCTION_BASELINE_PX}px)`)
    expect(box!.height).toBeLessThan(PRODUCTION_BASELINE_PX * 0.75)
  })
}

test('no nested scrolling anywhere in the inline subtree (canon item 52)', async ({ page }) => {
  await page.setViewportSize(VIEWPORTS.standardDesktop)
  await mockOpenAiAndGoto(page, 'inline')

  const main = page.locator('main[role="main"]')
  const hasNestedScroll = await main.evaluate((el) => {
    const all = [el, ...Array.from(el.querySelectorAll('*'))]
    return all.some((node) => {
      const style = getComputedStyle(node as Element)
      const overflowY = style.overflowY
      const scrollable = (overflowY === 'auto' || overflowY === 'scroll')
        && (node as HTMLElement).scrollHeight > (node as HTMLElement).clientHeight
      return scrollable
    })
  })
  expect(hasNestedScroll).toBe(false)
})

test('200% text-resize: long priority name truncates without overlapping the metric or wrapping onto it', async ({ page }) => {
  await page.setViewportSize(VIEWPORTS.standardDesktop)
  await mockOpenAiAndGoto(page, 'inline')

  // WCAG 1.4.4-style text resize, not a full-page zoom — scales text, not layout chrome.
  await page.addStyleTag({ content: 'html { font-size: 200% !important; }' })

  const rows = page.locator('main[role="main"] > div > div')
  const longNameRow = rows.filter({ hasText: 'This Is A Deliberately Very Long Priority Name' })
  await expect(longNameRow).toBeVisible()

  const nameBox = await longNameRow.locator('span.truncate').boundingBox()
  // BADGE_CIRCLE_CLASS also carries flex-shrink-0, so the badge matches
  // span.flex-shrink-0 too — it's the first one in DOM order, the metric is
  // the last, so .last() (not .first()) is the metric.
  const metricBox = await longNameRow.locator('span.flex-shrink-0').last().boundingBox()
  expect(nameBox).not.toBeNull()
  expect(metricBox).not.toBeNull()

  // Non-overlap: either side-by-side (name's right edge <= metric's left
  // edge, with a small epsilon for subpixel rounding) or stacked (no
  // vertical intersection) — both are acceptable layouts; visual overlap is not.
  const sideBySide = nameBox!.x + nameBox!.width <= metricBox!.x + 1
  const stacked = nameBox!.y + nameBox!.height <= metricBox!.y || metricBox!.y + metricBox!.height <= nameBox!.y
  expect(sideBySide || stacked).toBe(true)

  // No horizontal overflow on <main> itself at 200% text size.
  const overflowsX = await page.locator('main[role="main"]').evaluate((el) => el.scrollWidth > el.clientWidth + 1)
  expect(overflowsX).toBe(false)
})

test('mode-switch timing: openai:set_globals inline -> fullscreen reflects in the DOM promptly', async ({ page }) => {
  await page.setViewportSize(VIEWPORTS.standardDesktop)
  await mockOpenAiAndGoto(page, 'inline')

  await expect(page.locator('main[role="main"] article')).toHaveCount(0)

  const start = Date.now()
  await page.evaluate(() => {
    ;(window as unknown as { openai: { displayMode: string } }).openai.displayMode = 'fullscreen'
    window.dispatchEvent(new Event('openai:set_globals'))
  })
  await expect(page.locator('main[role="main"] article')).toHaveCount(3)
  const elapsedMs = Date.now() - start

  console.log(`[inline-density] set_globals inline->fullscreen reflected in DOM after ${elapsedMs}ms`)
  // No mandated threshold — sanity ceiling only, to catch a true perf regression.
  expect(elapsedMs).toBeLessThan(1000)
})

test('initial render timing: navigation to first main[role="main"] paint', async ({ page }) => {
  await page.setViewportSize(VIEWPORTS.standardDesktop)
  const start = Date.now()
  await mockOpenAiAndGoto(page, 'inline')
  const elapsedMs = Date.now() - start
  console.log(`[inline-density] initial render (goto -> main[role="main"] present) = ${elapsedMs}ms`)
  expect(elapsedMs).toBeLessThan(3000)
})
