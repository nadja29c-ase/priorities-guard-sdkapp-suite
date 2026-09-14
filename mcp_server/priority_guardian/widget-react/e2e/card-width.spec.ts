import { test, expect, type Page } from '@playwright/test'

/**
 * Regression layer for inc_card_size_fix.md.
 *
 * Asserts REAL resolved CSS (getComputedStyle / bounding geometry) in an
 * actual Chromium engine, against the built bundle on disk
 * (../widgets/pg-dashboard.html — `npm run test:e2e` rebuilds it first, so
 * this reflects the working tree, not necessarily HEAD unless it's clean).
 * This is stronger than the vitest/jsdom suite (CardWidth.test.tsx), which
 * can only assert which classes are applied, not what they resolve to.
 *
 * What this layer is NOT: it loads the widget document standalone in a tab,
 * not inside ChatGPT's actual host iframe/container. It cannot reproduce how
 * ChatGPT itself sizes the inline card or the Canvas-style fullscreen
 * surface. Manual verification in a real ChatGPT session at these same three
 * width classes (narrow mobile / standard desktop / wide desktop-Canvas),
 * with screenshots or measured DOM geometry, remains required primary
 * evidence per inc_card_size_fix.md and is not satisfied by this file.
 */

const EXPECTED_MAX_WIDTH_PX = 672 // Tailwind max-w-2xl (42rem @ 16px root) — see CARD_MAX_WIDTH_CLASS in App.tsx

const VIEWPORTS = {
  narrowMobile: { width: 375, height: 812 },
  standardDesktop: { width: 1024, height: 768 },
  wideDesktopCanvas: { width: 1600, height: 900 },
} as const

async function mockOpenAiAndGoto(page: Page, displayMode: 'inline' | 'fullscreen') {
  await page.addInitScript((mode) => {
    ;(window as unknown as { openai: Record<string, unknown> }).openai = {
      displayMode: mode,
      locale: 'en-US',
      toolOutput: {
        structuredContent: {
          data: {
            google_connected: false,
            priorities: [],
            available_keywords: [],
          },
        },
      },
      callTool: async () => ({ structuredContent: { data: { priorities: [] } } }),
      notifyIntrinsicHeight: () => {},
      setWidgetState: () => {},
      widgetState: undefined,
    }
  }, displayMode)
  await page.goto('/pg-dashboard.html')
  await page.waitForSelector('main[role="main"]')
}

for (const [label, viewport] of Object.entries(VIEWPORTS)) {
  test.describe(`viewport: ${label} (${viewport.width}x${viewport.height})`, () => {
    for (const mode of ['inline', 'fullscreen'] as const) {
      test(`${mode} <main> resolves an explicit max-width, independent of #root`, async ({ page }) => {
        await page.setViewportSize(viewport)
        await mockOpenAiAndGoto(page, mode)

        const main = page.locator('main[role="main"]')
        const resolvedMaxWidth = await main.evaluate((el) => getComputedStyle(el).maxWidth)
        expect(resolvedMaxWidth).toBe(`${EXPECTED_MAX_WIDTH_PX}px`)

        // #root independence: mutate #root's own max-width live (widen it)
        // and confirm main's resolved max-width is unaffected — the
        // regression this increment exists to prevent (inline used to
        // inherit #root's cap because it had no width rule of its own).
        //
        // Only the "grow #root" direction is meaningful here. A "shrink
        // #root below 672px" case was removed: max-w-2xl is a fixed 42rem
        // value, so its *specified* max-width can never read anything but
        // "672px" regardless of #root — that assertion would pass on the
        // pre-fix code path too and proves nothing about this fix. Growing
        // #root past 672px is the case that actually distinguishes "main
        // owns its width" from "main inherited #root's (now larger) cap" —
        // and we check the *rendered* box, not just the CSS property string,
        // since a fixed-unit max-width property trivially reads back
        // unchanged either way.
        await page.evaluate(() => {
          const root = document.getElementById('root')
          if (root) root.style.maxWidth = '1400px'
        })
        const afterRootGrow = await main.evaluate((el) => getComputedStyle(el).maxWidth)
        expect(afterRootGrow).toBe(`${EXPECTED_MAX_WIDTH_PX}px`)
        const growBox = await main.boundingBox()
        expect(growBox).not.toBeNull()
        expect(growBox!.width).toBeLessThanOrEqual(EXPECTED_MAX_WIDTH_PX)
      })
    }

    for (const mode of ['inline', 'fullscreen'] as const) {
      test(`${mode} stays fluid/full-width on mobile (max-width only caps, never forces narrower)`, async ({ page }) => {
        test.skip(viewport.width >= EXPECTED_MAX_WIDTH_PX, 'only meaningful below the cap')
        await page.setViewportSize(viewport)
        await mockOpenAiAndGoto(page, mode)

        const main = page.locator('main[role="main"]')
        const box = await main.boundingBox()
        expect(box).not.toBeNull()
        // Below the 672px cap, the card should fill the available width (minus
        // body's 16px padding + main's own side padding), not be squeezed to
        // some other fixed value — this is the "fluid/full-width on mobile"
        // requirement (openai_uiux_1.3.26.md item 73) staying intact, checked
        // for both modes per inc_card_size_fix.md's integration test list.
        expect(box!.width).toBeGreaterThan(viewport.width - 64)
      })
    }
  })
}

test.describe('host-driven displayMode transition (regression on handleSetGlobals)', () => {
  test('inline -> fullscreen -> inline via openai:set_globals keeps an explicit max-width, and genuinely switches mode UI, throughout', async ({ page }) => {
    // Inline and fullscreen intentionally share the same width class, so a
    // width-only assertion would pass even if handleSetGlobals silently
    // stopped switching modes — the width never changes either way. Pairing
    // it with a mode-exclusive UI marker (ExpandButton is inline-only,
    // FullscreenHeader's minimize button is fullscreen-only) proves the mode
    // transition itself actually happened.
    await page.setViewportSize(VIEWPORTS.standardDesktop)
    await mockOpenAiAndGoto(page, 'inline')

    const main = page.locator('main[role="main"]')
    const expandButton = page.getByRole('button', { name: /open full dashboard/i })
    const minimizeButton = page.getByRole('button', { name: /minimize dashboard/i })

    await expect(main).toHaveCSS('max-width', `${EXPECTED_MAX_WIDTH_PX}px`)
    await expect(expandButton).toBeVisible()
    await expect(minimizeButton).toHaveCount(0)

    await page.evaluate(() => {
      ;(window as unknown as { openai: { displayMode: string } }).openai.displayMode = 'fullscreen'
      window.dispatchEvent(new Event('openai:set_globals'))
    })
    await expect(main).toHaveCSS('max-width', `${EXPECTED_MAX_WIDTH_PX}px`)
    await expect(minimizeButton).toBeVisible()
    await expect(expandButton).toHaveCount(0)

    await page.evaluate(() => {
      ;(window as unknown as { openai: { displayMode: string } }).openai.displayMode = 'inline'
      window.dispatchEvent(new Event('openai:set_globals'))
    })
    await expect(main).toHaveCSS('max-width', `${EXPECTED_MAX_WIDTH_PX}px`)
    await expect(expandButton).toBeVisible()
    await expect(minimizeButton).toHaveCount(0)
  })
})
