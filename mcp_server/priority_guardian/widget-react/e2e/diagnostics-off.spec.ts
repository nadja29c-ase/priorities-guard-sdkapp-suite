import { test, expect, type Page } from '@playwright/test'

/**
 * Regression layer for the Inc 89 cleanup (PG_DIAG_FULLSCREEN = false).
 *
 * Loads the BUILT bundle (../widgets/pg-dashboard.html) in Chromium with a mocked
 * window.openai whose callTool records every call, then drives the events that used
 * to emit diagnostics: mount, host openai:set_globals, expand and minimize. Asserts
 * that no record_widget_diagnostic call is made and that desktop fullscreen still
 * survives a stale host inline sync (Inc 89.10 intent guard, c1fddf1).
 *
 * Checks the shipped bytes rather than the source: a stale or wrongly built bundle
 * would still emit diagnostics here even with the vitest suite green.
 *
 * What this layer is NOT: a ChatGPT host. It cannot show how often the real host
 * fires set_globals, or anything about the host's own fullscreen handling.
 */

async function mockOpenAiAndGoto(page: Page) {
  await page.addInitScript(() => {
    const calls: string[] = []
    ;(window as unknown as { __toolCalls: string[] }).__toolCalls = calls
    ;(window as unknown as { openai: Record<string, unknown> }).openai = {
      displayMode: 'inline',
      locale: 'en-US',
      toolOutput: {
        structuredContent: {
          data: { google_connected: true, priorities: [], available_keywords: [] },
        },
      },
      callTool: async (name: string) => {
        calls.push(name)
        return { structuredContent: { data: { priorities: [] } } }
      },
      notifyIntrinsicHeight: () => {},
      setWidgetState: () => {},
      widgetState: undefined,
    }
  })
  await page.goto('/pg-dashboard.html')
  await page.waitForSelector('main[role="main"]')
}

async function hostSetGlobals(page: Page, displayMode: 'inline' | 'fullscreen') {
  await page.evaluate((mode) => {
    ;(window as unknown as { openai: { displayMode: string } }).openai.displayMode = mode
    window.dispatchEvent(new Event('openai:set_globals'))
  }, displayMode)
}

async function diagnosticCalls(page: Page) {
  const calls = await page.evaluate(() => (window as unknown as { __toolCalls: string[] }).__toolCalls)
  return calls.filter((name) => name === 'record_widget_diagnostic')
}

test.use({ viewport: { width: 1024, height: 768 } })

test('built bundle sends no record_widget_diagnostic calls on mount, set_globals, expand, minimize', async ({ page }) => {
  await mockOpenAiAndGoto(page)
  for (let i = 0; i < 10; i++) {
    await hostSetGlobals(page, i % 2 === 0 ? 'inline' : 'fullscreen')
  }
  await hostSetGlobals(page, 'inline')
  await page.getByRole('button', { name: 'Open full dashboard' }).click()
  await page.getByRole('button', { name: 'Minimize dashboard' }).click()
  // Fire-and-forget calls are async; give any stray call time to land
  await page.waitForTimeout(300)
  expect(await diagnosticCalls(page)).toEqual([])
})

test('built bundle keeps desktop fullscreen across a stale host inline sync', async ({ page }) => {
  await mockOpenAiAndGoto(page)
  await page.getByRole('button', { name: 'Open full dashboard' }).click()
  await hostSetGlobals(page, 'inline')
  await hostSetGlobals(page, 'inline')
  await expect(page.getByRole('button', { name: 'Minimize dashboard' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Open full dashboard' })).toHaveCount(0)
})
