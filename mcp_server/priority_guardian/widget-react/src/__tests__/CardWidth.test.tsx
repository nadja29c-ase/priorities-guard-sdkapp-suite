/**
 * Card width fix (inc_card_size_fix.md).
 *
 * Scope of these tests: verify that inline and fullscreen <main> each carry
 * their own explicit, stated width class (CARD_MAX_WIDTH_CLASS in App.tsx),
 * and that this no longer depends on isInline branching or on #root.
 *
 * IMPORTANT — what jsdom can and cannot prove:
 * vitest's jsdom environment does not load main.css or run the Tailwind
 * build, so getComputedStyle() here cannot resolve a real pixel max-width —
 * these assertions check which CSS *classes* are applied, not rendered
 * geometry. Real resolved geometry at representative viewport widths is
 * covered by the Playwright regression suite (e2e/card-width.spec.ts) and,
 * as the primary evidence layer, manual verification in a real ChatGPT
 * session (narrow mobile / standard desktop / wide desktop-Canvas) —
 * neither jsdom nor Playwright can substitute for that layer; see
 * inc_card_size_fix.md's Verification section.
 */

import { describe, it, expect } from 'vitest'
import { render, act, screen } from '@testing-library/react'
import App from '../App'
import { setMockPriorities, mockOpenai } from '../test/setup'
import type { Priority } from '../types'

const priority: Priority = {
  id: 'pri-1',
  name: 'Launch Feature X',
  type: 'deadline',
  calendarKeyword: 'P1',
  status: 'active',
  deadline: '2025-02-15',
  weeklyHourTarget: 10,
  weeklyHourActual: 8,
  checkpointDate: undefined,
  deliverables: [],
  goals: [],
}

function renderInMode(mode: 'inline' | 'fullscreen') {
  mockOpenai.displayMode = mode
  setMockPriorities([priority], true)
  return render(<App />)
}

describe('Card width — explicit, non-accidental max-width', () => {
  it('inline <main> carries an explicit max-width class', () => {
    const { container } = renderInMode('inline')
    const main = container.querySelector('main[role="main"]')
    expect(main).toBeTruthy()
    expect(main).toHaveClass('max-w-2xl')
    expect(main).toHaveClass('mx-auto')
  })

  it('fullscreen <main> carries an explicit max-width class', () => {
    const { container } = renderInMode('fullscreen')
    const main = container.querySelector('main[role="main"]')
    expect(main).toBeTruthy()
    expect(main).toHaveClass('max-w-2xl')
    expect(main).toHaveClass('mx-auto')
  })

  it('inline and fullscreen resolve to the same stated width class — a stated decision, not an accident', () => {
    const inline = renderInMode('inline')
    const inlineMain = inline.container.querySelector('main[role="main"]')
    inline.unmount()

    const fullscreen = renderInMode('fullscreen')
    const fullscreenMain = fullscreen.container.querySelector('main[role="main"]')

    expect(inlineMain?.className).toContain('max-w-2xl')
    expect(fullscreenMain?.className).toContain('max-w-2xl')
    // Same width value is a documented choice (see CARD_MAX_WIDTH_CLASS
    // comment in App.tsx), not a requirement — this test locks in *today's*
    // width decision, not a requirement that the two modes' full class
    // lists must always match. They no longer do: inc_cardsize_fix_3.md
    // (density pass) added an inline-only 'pg-inline' class for vertical
    // padding, unrelated to width — inline's classes are exactly
    // fullscreen's plus that one class.
    expect(inlineMain?.className).toBe(`${fullscreenMain?.className} pg-inline`)
  })

  it('the width class is not conditional on display mode (no accidental #root dependency)', () => {
    // Before the fix, inline had NO width class at all and silently inherited
    // #root's max-width: 900px from main.css. Asserting the class is present
    // unconditionally (same string regardless of mode) is the structural proof
    // that width is now owned by <main> itself, not derived from an ancestor.
    const inline = renderInMode('inline')
    const inlineClass = inline.container.querySelector('main[role="main"]')?.className ?? ''
    expect(inlineClass).not.toBe('bg-surface-secondary rounded-2xl p-4 pb-2')
    expect(inlineClass).toMatch(/max-w-2xl/)
  })
})

describe('Card width — host-driven displayMode transitions (regression on handleSetGlobals)', () => {
  it('keeps its explicit width class, and genuinely switches mode UI, across inline -> fullscreen -> inline via openai:set_globals', () => {
    // Inline and fullscreen intentionally share the same width class (see
    // CARD_MAX_WIDTH_CLASS), so a width-only assertion here would pass even
    // if handleSetGlobals silently stopped switching modes — the width
    // never changes either way. Pairing it with a mode-exclusive UI marker
    // (ExpandButton is inline-only, FullscreenHeader's minimize button is
    // fullscreen-only) proves the mode transition itself actually happened.
    const { container } = renderInMode('inline')
    const getMainClass = () => container.querySelector('main[role="main"]')?.className ?? ''

    expect(getMainClass()).toMatch(/max-w-2xl/)
    expect(screen.queryByRole('button', { name: /open full dashboard/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /minimize dashboard/i })).not.toBeInTheDocument()

    // Host syncs to fullscreen
    mockOpenai.displayMode = 'fullscreen'
    act(() => { window.dispatchEvent(new Event('openai:set_globals')) })
    expect(getMainClass()).toMatch(/max-w-2xl/)
    expect(screen.queryByRole('button', { name: /minimize dashboard/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /open full dashboard/i })).not.toBeInTheDocument()

    // Host syncs back to inline
    mockOpenai.displayMode = 'inline'
    act(() => { window.dispatchEvent(new Event('openai:set_globals')) })
    expect(getMainClass()).toMatch(/max-w-2xl/)
    expect(screen.queryByRole('button', { name: /open full dashboard/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /minimize dashboard/i })).not.toBeInTheDocument()
  })
})

describe('Card width — mobile (structural only; fluid/full-width is a real-viewport claim)', () => {
  it('mobile user agent does not change which width class is applied', () => {
    const originalUA = navigator.userAgent
    Object.defineProperty(navigator, 'userAgent', {
      value: 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)',
      configurable: true,
    })

    try {
      const inline = renderInMode('inline')
      const inlineClass = inline.container.querySelector('main[role="main"]')?.className ?? ''
      expect(inlineClass).toMatch(/max-w-2xl/)
      inline.unmount()

      const fullscreen = renderInMode('fullscreen')
      const fullscreenClass = fullscreen.container.querySelector('main[role="main"]')?.className ?? ''
      expect(fullscreenClass).toMatch(/max-w-2xl/)
    } finally {
      Object.defineProperty(navigator, 'userAgent', { value: originalUA, configurable: true })
    }
  })
})
